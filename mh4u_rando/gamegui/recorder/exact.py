"""The exact copy of the running game's GUI. The recording probe writes two u32
frame marks: "frame started" after the frame's wait for the GPU, "frame done" just before it. A copy is kept only when
the marks agree before and after it and did not move: the game ran no logic while it was taken. Without marks that tick
(no recording probe installed), nothing is recorded: never unverified data."""

import struct
import time
from dataclasses import dataclass

from .. import strings as S
from ..process import LinkError
from ..snapshot import Proof
from .image import MemoryImage

NO_PROBE = S.NO_PROBE


class NoFrameMarks(RuntimeError):
    """The game's frame marks are missing or do not tick: the recording probe is not installed (or the emulation is
    paused since the link was made)."""

    def __init__(self, detail: str):
        super().__init__(f"{S.tr(NO_PROBE)} ({detail})")
        self.detail = detail


class CopyStats:
    """What one `exact_copy` call saw, for the log when it finds no copy: the marks
    reads, how many read a frame running, how many started a copy, how many of those the game cut short (torn, thrown
    away), the slowest copy and, once copies keep being cut short, the length of the quiet windows (every other window
    is measured instead of used: read in a row until the marks part)."""

    def __init__(self):
        self.tries = self.running = self.copies = self.torn = self.frames = 0
        self.copy_s = self.elapsed_s = 0.0          # the slowest copy, the call's time
        self.windows: list[float] = []              # the quiet windows measured, in seconds
        self.measure_next = False
        self._started: int | None = None

    @property
    def window_s(self) -> float:
        """The longest quiet window measured (0 when none was)."""
        return max(self.windows, default=0.0)

    @property
    def no_pause(self) -> bool:
        """Whether the game leaves no pause long enough for a copy: copies were cut short, windows were timed and the
        longest is shorter than the slowest copy (seen: 0.02 ms against 0.5 ms). Reading the marks harder or
        sooner cannot change that; a lighter scene can."""
        return self.torn >= 2 and len(self.windows) >= 2 and self.window_s < self.copy_s

    def seen(self, started: int, done: int) -> None:
        """One marks read."""
        self.tries += 1
        if self._started is not None and started != self._started:
            self.frames += (started - self._started) & 0xFFFFFFFF
        self._started = started
        self.running += started != done

    def describe(self) -> str:
        windows = sorted(self.windows)
        quiet = (f"{len(windows)} quiet windows measured, median {windows[len(windows) // 2] * 1000:.2f} ms, longest "
                 f"{windows[-1] * 1000:.2f} ms" if windows else "no quiet window measured")
        return (f"{self.tries} reads of the marks in {self.elapsed_s * 1000:.0f} ms, {self.frames} frames seen, "
                f"{self.running} reads with the frame running, {self.copies} copies started, {self.torn} cut short by "
                f"the game, slowest copy {self.copy_s * 1000:.2f} ms, {quiet}")


class NotExact(RuntimeError):
    """No copy was taken between two frames' logic in the time allowed (the marks moved every time)."""

    def __init__(self, detail: str, stats: "CopyStats | None" = None):
        super().__init__(detail)
        self.stats = stats


@dataclass(frozen=True)
class FrameMarks:
    """The canonical addresses of the two u32 marks the recording probe writes."""
    started: int
    done: int

    @classmethod
    def from_code_space(cls, variable: str) -> "FrameMarks | None":
        """The marks at the code space's variable `variable` (two u32: started, done), None while it is not declared
        (exefs/blocks.py)."""
        from ...exefs.code_space import CodeSpaceError, load_layout
        try:
            address = load_layout().address(variable)
        except (CodeSpaceError, KeyError, OSError):
            return None
        return cls(address, address + 4)

    def read(self, memory) -> tuple[int, int]:
        """(started, done) now; "done" is read first, so a frame that starts between the two reads shows them apart."""
        done = memory.u32(self.done)
        return memory.u32(self.started), done


class _Plain:
    """The copy through the view's own reads (a view without a read plan: save states, tests' fakes)."""

    def __init__(self, memory, marks: FrameMarks, regions):
        self.memory, self.marks, self.regions = memory, marks, regions
        self.copied: dict[int, bytes] = {}

    def read_marks(self) -> tuple[int, int]:
        return self.marks.read(self.memory)

    def copy(self) -> None:
        self.copied = {address: self.memory.read_raw(address, size) for address, size in self.regions}

    def take(self) -> dict[int, bytes]:
        return self.copied


class _Planned:
    """The copy through reads resolved ahead (process.py, `ReadPlan`): inside the quiet window the marks cost one read
    of 8 bytes and the copy only its reads. The marks are read as one pair: `started` only ever grows, so two reads that
    both say started == done with the same value prove no frame began between them, whichever word was read first."""

    def __init__(self, memory, marks: FrameMarks, regions):
        if marks.done != marks.started + 4:
            raise ValueError("the planned marks read needs the two marks side by side")
        self.pair = memory.client.plan([(memory.shift(marks.started), 8)])
        self.plan = memory.client.plan(regions)
        self.regions = regions

    def read_marks(self) -> tuple[int, int]:
        self.pair.read()
        return struct.unpack("<II", self.pair.buffers[0].raw)

    def copy(self) -> None:
        self.plan.read()

    def take(self) -> dict[int, bytes]:
        if not (self.plan.current() and self.pair.current()):
            raise LinkError("the game's page table changed during the copy: a new boot or a loaded state")
        return self.plan.result()


def exact_copy(memory, marks: FrameMarks, regions: list[tuple[int, int]], attempts: int | None = None,
               retry_sleep: float = 0.0, sleep=time.sleep, timeout: float | None = None, measure_limit: float = 0.0,
               clock=time.perf_counter) -> tuple[MemoryImage, Proof]:
    """One copy of `regions` (running addresses) taken while no frame logic ran: the marks read before (started ==
    done) and after the copy are the same four values. The copy starts at the first read that shows the quiet window
    open and the marks are read in a tight loop (`retry_sleep` 0), so the whole window serves the copy. NotExact after
    `attempts` reads of the marks or `timeout` seconds, whichever the caller gave first; its `stats` say what was seen.
    On a live link the reads are resolved ahead (ReadPlan), so a copy costs its reads and nothing else."""
    if attempts is None and timeout is None:
        raise ValueError("exact_copy needs attempts or a timeout")
    client = getattr(memory, "client", None)
    taker = _Planned(memory, marks, regions) if hasattr(client, "plan") else _Plain(memory, marks, regions)
    stats, begun = CopyStats(), clock()
    while True:
        now = clock()
        if (attempts is not None and stats.tries >= attempts) or (timeout is not None and now - begun >= timeout):
            break
        before = taker.read_marks()
        stats.seen(*before)
        if before[0] == before[1]:
            if stats.measure_next:                  # copies keep being cut short: how long does the window last?
                stats.measure_next, last = False, now
                while clock() - now < measure_limit and taker.read_marks() == before:
                    last = clock()
                stats.windows.append(last - now)
                continue
            stats.copies += 1
            taker.copy()
            after = taker.read_marks()
            stats.copy_s = max(stats.copy_s, clock() - now)
            if after == before:
                return MemoryImage(taker.take(), memory.shift), Proof("frame_marks", before[0], before[1], stats.tries)
            stats.torn += 1
            stats.measure_next = stats.torn >= 2 and measure_limit > 0
        if retry_sleep:
            sleep(retry_sleep)
    stats.elapsed_s = clock() - begun
    raise NotExact(f"no copy between two frames: {stats.describe()}", stats)


def copy_arguments(settings) -> dict:
    """The keyword arguments of `exact_copy` that the recorder's settings (recorder.json) give."""
    return {"retry_sleep": settings.retry_sleep_s, "timeout": settings.copy_timeout_s,
            "measure_limit": settings.window_measure_s}
