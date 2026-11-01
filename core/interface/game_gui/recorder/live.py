"""The live recorder: one `WindowRecorder` per emulator window, each
copying the game's GUI between its frame counters, checking the copy and feeding the screens; `RecorderService` finds
the emulator windows (two at once in multiplayer, «Ventana 1» / «Ventana 2», "Window 1" in English), reconnects after
restarts, loaded states and the emulator closing and opening, pairs the Ctrl+P pictures with the snapshots and keeps the
log. The statuses are in the tools' language (interface/game_gui/strings.py); the log is in English."""

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from core.interface.game_gui import emulator as emulator_module
from core.interface.game_gui import memory as memory_module
from core.interface.game_gui import strings as S
from core.interface.game_gui.process import LinkDenied, LinkError, LinkRefused
from core.interface.game_gui.snapshot import Proof, Snapshot, Source
from core.interface.game_gui.recorder import checks, identity
from core.interface.game_gui.recorder import reader as default_reader
from core.interface.game_gui.recorder.coverage import load_coverage, missing
from core.interface.game_gui.recorder.exact import (
    NO_PROBE, FrameCounters, NoFrameCounters, NotExact, copy_arguments, exact_copy,
)
from core.interface.game_gui.recorder.image import MemoryImage, OutsideImage
from core.interface.game_gui.recorder.marks import MARKS_DIR, PictureWatch, file_mark, pair, screenshot_folder
from core.interface.game_gui.recorder.screens import ScreenTracker
from core.interface.game_gui.recorder.store import Session, recorded_signatures, session_name

LOG = logging.getLogger("core.interface.game_gui.recorder")


def setup_log(root: Path) -> Path:
    """The recorder's log in `root` (work/ui/recorder.log), appended to."""
    path = Path(root) / "recorder.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not any(getattr(h, "baseFilename", None) == str(path.resolve()) for h in LOG.handlers):
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    return path


class TickWatch:
    """Whether the frame counters tick: both moved since the link was made and once read equal (the recording probe runs
    the game's frames). NoFrameCounters when they stay still for `window` seconds, or without counters. Each check reads
    the counters in a row for up to `spin` seconds of `timer` (the fine clock, real time in a run): the quiet window can
    be shorter than the gap between two turns, and one read per turn took its absence for a probe that never lets the
    counters agree."""

    def __init__(self, counters: FrameCounters | None, window: float, clock=time.monotonic, spin: float = 0.0,
                 timer=time.perf_counter):
        self.counters, self.window, self.clock, self.spin, self.timer = counters, window, clock, spin, timer
        self.first: tuple[int, int] | None = None
        self.since = 0.0
        self.moved = [False, False]
        self.equal = False
        self.refused = False                # the last window ended still: the probe counts as missing

    def check(self, memory) -> bool:
        if self.counters is None:
            raise NoFrameCounters(S.tr(S.NO_COUNTERS_DECLARED))
        now = self.clock()
        stop = self.timer() + self.spin
        while True:
            value = self.counters.read(memory)
            if self.first is None:
                self.first, self.since = value, now
            self.moved = [self.moved[i] or value[i] != self.first[i] for i in range(2)]
            self.equal = self.equal or value[0] == value[1]
            if (all(self.moved) and self.equal) or self.timer() >= stop:
                break
        if all(self.moved) and self.equal:
            self.refused = False
            return True
        if now - self.since >= self.window:
            why = S.tr(S.COUNTERS_NEVER_AGREE if all(self.moved) else S.COUNTERS_STILL)
            self.first, self.since, self.moved, self.equal = value, now, [False, False], False
            self.refused = True
            raise NoFrameCounters(why)
        return False


@dataclass
class KeptCopy:
    """An exact copy that passed the checks, kept compressed (a few MB of the game's memory each) so the last seconds
    fit in memory; its snapshot is read again from it when a mark needs it."""
    time: float
    proof: Proof
    regions: list[tuple[int, bytes]]
    version: object

    @classmethod
    def of(cls, image: MemoryImage, proof: Proof, when: float, version) -> "KeptCopy":
        import zstandard
        compressor = zstandard.ZstdCompressor(level=1)
        return cls(when, proof, [(start, compressor.compress(data)) for start, data in image.regions], version)

    def image(self) -> MemoryImage:
        import zstandard
        decompressor = zstandard.ZstdDecompressor()
        return MemoryImage({start: decompressor.decompress(data) for start, data in self.regions},
                           memory_module.GameMemory(None, self.version).shift)


class Context:
    """What every window's recorder shares."""

    def __init__(self, settings, root: Path, session: Session, emulator_dir: Path | None, romfs: Path | None,
                 candidates, counters: FrameCounters | None, reader=default_reader, attach=memory_module.attach,
                 clock=time.monotonic, wall=time.time, layouts: checks.LayoutIndex | None = None,
                 timer=time.perf_counter):
        self.settings, self.root, self.session = settings, Path(root), session
        self.emulator_dir, self.romfs, self.candidates, self.counters = emulator_dir, romfs, candidates, counters
        self.reader, self.attach, self.clock, self.wall = reader, attach, clock, wall
        self.timer = timer                  # the fine clock: a copy and the counters' check last milliseconds
        self._indexes: dict[str | None, checks.LayoutIndex] = {}
        self._layouts = layouts
        self.sessions: dict[str, Session] = {session.gui_mode: session}

    def session_for(self, gui_mode: str) -> Session:
        """The session of `gui_mode` (identity.gui_mode): the one given, or its twin `<name>_<mode>` made when a
        window first shows that mode, so one session never mixes the game's own GUI with the arranged one."""
        if gui_mode not in self.sessions:
            self.sessions[gui_mode] = Session(self.root, f"{self.session.name}_{gui_mode}", gui_mode)
        return self.sessions[gui_mode]

    def layouts(self, title: str | None) -> checks.LayoutIndex:
        """The layouts the running game can have loaded: the installed mod's for its title, then the dump's, the
        other languages' and the software keyboard's when a group needs them (or the index given)."""
        if self._layouts is not None:
            return self._layouts
        if title not in self._indexes:
            where = (self.emulator_dir, self.romfs, self.settings.layout_language, title)
            self._indexes[title] = checks.LayoutIndex.from_folders(checks.layout_folders(*where),
                                                                   checks.fallback_folders(*where))
        return self._indexes[title]


class WindowRecorder:
    def __init__(self, pid: int, label: str, context: Context):
        self.pid, self.label, self.ctx = pid, label, context
        self.memory = None
        self.status = S.tr(S.CONNECTING)
        self.next_try = 0.0
        self.ticks: TickWatch | None = None
        self.rest_until = 0.0               # a game found to leave no pause for a copy is not tried before this time
        self.regions: list[tuple[int, int]] | None = None
        self.history: deque[KeptCopy] = deque()     # the last `history_s` of checked copies, for the Ctrl+P marks
        self.tracker = ScreenTracker(context.settings, context.session, label)
        self.last: Snapshot | None = None
        self.copies = self.rejected = 0
        self._last_problem = ""
        self.mod: dict | None = None
        self.language: str | None = None

    def _problem(self, status: str, detail: str = "", numbers: str = "") -> None:
        """Show `status`; log `detail` once per episode (`numbers`, measured values that change every time, ride
        along with it without making each turn a new line)."""
        self.status = status
        message = f"{self.label} (pid {self.pid}): {detail or status}"
        if message != self._last_problem:
            LOG.warning(message + (f" [{numbers}]" if numbers else ""))
            self._last_problem = message

    def drop(self, status: str, detail: str = "") -> None:
        if self.memory is not None:
            try:
                self.memory.close()
            except Exception:  # noqa: BLE001 - a link already lost
                pass
        self.memory, self.ticks, self.regions, self.rest_until = None, None, None, 0.0
        self.next_try = self.ctx.clock() + self.ctx.settings.reconnect_interval_s
        self._problem(status, detail)

    def close(self) -> None:
        self.drop(S.tr(S.CLOSED))

    def _connect(self) -> bool:
        if self.ctx.clock() < self.next_try:
            return False
        try:
            self.memory = self.ctx.attach(self.pid, self.ctx.candidates)
        except LinkDenied as error:
            self.drop(S.tr(S.AS_ADMIN), str(error))
            return False
        except memory_module.UnknownGame as error:
            self.drop(S.tr(S.OTHER_GAME), str(error))
            return False
        except LinkError as error:
            self.drop(S.tr(S.GAME_STARTING), str(error))
            return False
        version = getattr(self.memory, "version", None)
        title = getattr(version, "title_id", None)
        self.mod = identity.installed_mod(self.ctx.emulator_dir, title)
        self.language = identity.system_language(self.ctx.emulator_dir)
        session = self.ctx.session_for(identity.gui_mode(self.mod))
        if self.tracker.session is not session:
            self.tracker = ScreenTracker(self.ctx.settings, session, self.label)
        self.ticks = TickWatch(self.ctx.counters, self.ctx.settings.tick_window_s, self.ctx.clock,
                               self.ctx.settings.tick_spin_s, self.ctx.timer)
        self.status = S.tr(S.CHECKING_PROBE)
        LOG.info("%s (pid %s): connected, version %s, mod %s, session %s", self.label, self.pid,
                 getattr(version, "key", None), self.mod, session.name)
        return True

    def _copy(self):
        """(managers, the kept copy) of one exact copy, or None."""
        settings, reader = self.ctx.settings, self.ctx.reader
        for _ in range(settings.rediscover_attempts):
            if self.regions is None:
                self.regions = reader.regions(self.memory, settings.merge_gap, settings.max_slots,
                                              settings.max_panes_per_group)
            image, proof = exact_copy(self.memory, self.ctx.counters, self.regions, clock=self.ctx.timer,
                                      **copy_arguments(settings))
            when = self.ctx.wall()
            try:
                managers = reader.read_gui(image, settings.max_slots, settings.max_panes_per_group)
            except OutsideImage:
                self.regions = None             # the GUI's objects moved: find them again
                continue
            return managers, KeptCopy.of(image, proof, when, getattr(self.memory, "version", None))
        self._problem(S.tr(S.GUI_MOVING), "the GUI moved in every copy of this turn")
        return None

    def _snapshot(self, managers, kept: "KeptCopy", result: dict) -> Snapshot:
        return Snapshot(Source("live", window=self.label, pid=self.pid), kept.time, kept.proof, self.ctx.reader.NAME,
                        managers, getattr(kept.version, "key", None), self.mod, self.language, result)

    def snapshot_of(self, kept: "KeptCopy") -> Snapshot | None:
        """The snapshot of a copy of `history`, read again from its bytes (the same reader and checks)."""
        settings = self.ctx.settings
        managers = self.ctx.reader.read_gui(kept.image(), settings.max_slots, settings.max_panes_per_group)
        result = checks.check(managers, self.ctx.layouts(getattr(kept.version, "title_id", None)))
        return self._snapshot(managers, kept, result) if result["ok"] else None

    def step(self) -> Snapshot | None:
        """One turn: connect, check the probe, take one exact copy, check it and record it."""
        if self.memory is None and not self._connect():
            return None
        if self.ctx.clock() < self.rest_until:
            return None
        try:
            try:
                if not self.ticks.check(self.memory):
                    if not self.ticks.refused:
                        self.status = S.tr(S.CHECKING_PROBE)
                    return None
            except LinkRefused as error:            # the counters' page is not mapped: no probe
                raise NoFrameCounters(S.tr(S.NO_COUNTERS)) from error
            copied = self._copy()
        except NoFrameCounters as error:
            self._problem(S.tr(NO_PROBE), str(error))
            return None
        except NotExact as error:
            stats = error.stats
            if stats is not None and stats.no_pause:
                self.rest_until = self.ctx.clock() + self.ctx.settings.no_pause_rest_s
                self._problem(S.tr(S.NO_PAUSE), "the game leaves no pause long enough for a copy (the quiet "
                              "windows measured are shorter than the copy)", stats.describe())
                return None
            self._problem(S.tr(S.NO_EXACT_COPY),
                          "no copy between two frames in the time allowed", stats.describe() if stats else "")
            return None
        except (OutsideImage, LinkRefused) as error:
            self.regions = None
            self._problem(S.tr(S.GUI_NOT_LOADED), str(error))
            return None
        except LinkError as error:
            self.drop(S.tr(S.RECONNECTING), str(error))
            return None
        except ValueError as error:              # the reader's ReadError: not the GUI it knows
            self.regions = None
            self.rejected += 1
            self._problem(S.tr(S.REJECTED_READ), f"read: {error}")
            return None
        if copied is None:
            return None
        managers, kept = copied
        if not managers:
            self.status = S.tr(S.NO_GUI_YET)
            return None
        result = checks.check(managers, self.ctx.layouts(getattr(kept.version, "title_id", None)))
        self.copies += 1
        if not result["ok"]:
            self.rejected += 1
            self._problem(S.tr(S.REJECTED_CHECKS, count=len(result["failures"])),
                          "copy not kept: " + "; ".join(result["failures"][:5]))
            return None
        snapshot = self._snapshot(managers, kept, result)
        self.last = snapshot
        self.history.append(kept)
        while self.history and self.history[0].time < kept.time - self.ctx.settings.history_s:
            self.history.popleft()
        self.tracker.observe(snapshot)
        self.status = S.tr(S.RECORDING if self.tracker.session.gui_mode == "normal" else S.RECORDING_SINGLE)
        self._last_problem = ""
        return snapshot


class RecorderService:
    """Every emulator window's recorder, the pictures and the marks; `tick` runs one turn of all of them."""

    def __init__(self, settings, root: Path, emulator_dir: Path | None = None, romfs: Path | None = None,
                 candidates=None, counters: FrameCounters | None = None, reader=default_reader,
                 attach=memory_module.attach, pids=emulator_module.emulator_pids, coverage=None,
                 session: str | None = None, clock=time.monotonic, wall=time.time, pictures: Path | None = None,
                 layouts: checks.LayoutIndex | None = None, timer=time.perf_counter):
        self.settings, self.root = settings, Path(root)
        self.session = Session(self.root, session or session_name("live"))
        self.context = Context(settings, self.root, self.session, emulator_dir, romfs,
                               [] if candidates is None else candidates, counters, reader, attach, clock, wall,
                               layouts, timer)
        self.pids, self.clock, self.wall = pids, clock, wall
        self.windows: dict[int, WindowRecorder] = {}
        self.coverage = load_coverage() if coverage is None else coverage
        folder = pictures if pictures is not None else (screenshot_folder(emulator_dir) if emulator_dir else None)
        self.pictures = PictureWatch(folder, settings.picture_settle_s, wall) if folder else None
        self.paused = False
        self.note = ""
        self.marks: list[Path] = []
        self.actions: queue.Queue = queue.Queue()
        self._next_scan = self._next_pictures = 0.0
        self.message = ""
        self._signatures = recorded_signatures(self.root)

    def _scan(self) -> None:
        now = self.clock()
        if now < self._next_scan:
            return
        self._next_scan = now + self.settings.reconnect_interval_s
        found = self.pids()
        for pid in [pid for pid in self.windows if pid not in found]:
            LOG.info("%s (pid %s): the emulator closed", self.windows[pid].label, pid)
            self.windows.pop(pid).close()
        for pid in found:
            if pid not in self.windows:
                used = {window.label for window in self.windows.values()}
                labels = (S.tr(S.WINDOW_LABEL, n=n) for n in range(1, len(found) + 2))
                label = next(label for label in labels if label not in used)
                self.windows[pid] = WindowRecorder(pid, label, self.context)
                LOG.info("%s: emulator process %s", label, pid)

    def _file(self, note: str, picture: Path | None) -> Path:
        when = picture.stat().st_mtime if picture is not None else self.wall()
        snapshots = {}
        for window in sorted(self.windows.values(), key=lambda w: w.label):
            if picture is None:
                snapshots[window.label] = window.last
            else:
                kept = pair(list(window.history), when, self.settings.pair_max_age_s)
                snapshots[window.label] = window.snapshot_of(kept) if kept is not None else None
        if not snapshots:
            snapshots = {S.tr(S.WINDOW_LABEL, n=1): None}
        blinking = set().union(*(w.tracker.blinking for w in self.windows.values())) if self.windows else set()
        folder = file_mark(self.root / MARKS_DIR, snapshots, note, picture, when, blinking)
        self.marks.append(folder)
        self.message = S.tr(S.MARK_SAVED, name=folder.name)
        LOG.info("mark %s (picture %s, note %r)", folder.name, picture, note)
        return folder

    def mark(self, note: str = "") -> None:
        """The "Mark this screen" button: a mark with each window's latest snapshot (filed by the next `tick`)."""
        self.actions.put(("mark", note))

    def tick(self) -> None:
        while not self.actions.empty():
            action, note = self.actions.get()
            if action == "mark":
                self._file(note, None)
        self._scan()
        if not self.paused:
            for window in list(self.windows.values()):
                window.step()
        now = self.clock()
        if self.pictures is not None and now >= self._next_pictures:
            self._next_pictures = now + self.settings.picture_poll_s
            for picture in self.pictures.poll():
                note, self.note = self.note, ""
                self._file(note, picture)

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            started = self.clock()
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - the recorder keeps running; the log says why
                LOG.exception("recorder turn failed")
            stop.wait(max(0.0, self.settings.copy_interval_s - (self.clock() - started)))

    def screen_name(self, groups: set[str]) -> str | None:
        for screen in self.coverage:
            if screen.told_by(groups):
                return f"{screen.id} {S.named(screen)}"
        return None

    def status(self) -> dict:
        """What the window shows (plain values; read from the Qt thread)."""
        windows = []
        for window in sorted(list(self.windows.values()), key=lambda w: w.label):
            tracker = window.tracker
            entry = tracker.session.index["signatures"].get(tracker.current) if tracker.current else None
            groups = set(entry["groups"]) if entry else set()
            windows.append({"label": window.label, "pid": window.pid, "status": window.status,
                            "screen": tracker.current, "screen_name": self.screen_name(groups) if entry else None,
                            "groups": len(groups), "copies": window.copies, "rejected": window.rejected})
        entries = [e for session in list(self.context.sessions.values()) for e in session.index["signatures"].values()]
        signatures = self._signatures + [set(e["groups"]) for e in entries]
        return {"session": ", ".join(s.name for s in list(self.context.sessions.values())), "paused": self.paused,
                "windows": windows, "screens": len(entries), "variants": sum(len(e["variants"]) for e in entries),
                "missing": [f"{s.id} {S.named(s)}" for s in missing(self.coverage, signatures)],
                "coverage": len(self.coverage), "marks": len(self.marks), "message": self.message}
