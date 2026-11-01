"""The marks: Ctrl+P in Citra saves the emulator's own picture into its
screenshot folder (`Paths\\screenshotPath` of `<emulator_dir>/config/qt-config.ini`, else
`<emulator_dir>/screenshots/`); each new picture is paired with each window's latest exact snapshot taken at most
`pair_max_age_s` before it and filed as a mark in `work/ui/marks/<id>/`: `mark.json` (the time, the note typed in the
window, each window's recorded screen), the snapshots (`window_<n>.json.zst`) and a copy of the picture. The window's
"Mark this screen" button files one without a picture.

A mark stays as it was filed. Setting it done (`mark_done`) only writes `done.json` beside it (the time, a one-line
note, a commit); `pending` lists the marks not done yet."""

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.interface.game_gui import strings as S
from core.interface.game_gui.recorder.store import signature_id, write_json

PICTURES = (".png", ".jpg", ".jpeg", ".bmp")
MARKS_DIR = "marks"
MARK_FILE = "mark.json"
DONE_FILE = "done.json"


def screenshot_folder(emulator_dir: Path) -> Path:
    """Where the emulator saves its pictures (its Qt configuration; the default when not set)."""
    config = Path(emulator_dir) / "config" / "qt-config.ini"
    if config.is_file():
        for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "Paths\\screenshotPath" and value.strip():
                return Path(value.strip().replace("\\\\", "\\"))
    return Path(emulator_dir) / "screenshots"


class PictureWatch:
    """The pictures that appear in `folder` after it starts watching, each once, when its file has settled."""

    def __init__(self, folder: Path, settle: float, clock=time.time):
        self.folder, self.settle, self.clock = Path(folder), settle, clock
        self.seen = set(self._pictures())

    def _pictures(self) -> list[Path]:
        if not self.folder.is_dir():
            return []
        return [path for path in self.folder.iterdir() if path.suffix.lower() in PICTURES]

    def poll(self) -> list[Path]:
        out = []
        for path in sorted(self._pictures()):
            if path in self.seen:
                continue
            try:
                if self.clock() - path.stat().st_mtime < self.settle:
                    continue
            except OSError:
                continue
            self.seen.add(path)
            out.append(path)
        return out


def pair(history, when: float, max_age: float):
    """The latest snapshot of `history` (oldest first) taken at most `max_age` seconds before `when`, else None."""
    for snapshot in reversed(history):
        if snapshot.time <= when + 0.05:
            return snapshot if when - snapshot.time <= max_age else None
    return None


def _snapshot_name(window: str, position: int) -> str:
    """`window_<n>.json.zst`, n the number of the window's label («Ventana 2», "Window 2"), in any language."""
    number = re.search(r"(\d+)$", window)
    return f"window_{number.group(1) if number else position}.json.zst"


def file_mark(root: Path, snapshots: dict, note: str = "", picture: Path | None = None,
              when: float | None = None, blinking=()) -> Path:
    """A mark's folder under `root` (work/ui/marks) for the snapshots {window: Snapshot or None}."""
    when = time.time() if when is None else when
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(when))
    folder = Path(root) / stamp
    number = 1
    while folder.exists():
        number += 1
        folder = Path(root) / f"{stamp}_{number}"
    folder.mkdir(parents=True)
    windows = {}
    for position, (window, snapshot) in enumerate(snapshots.items(), 1):
        if snapshot is None:
            windows[window] = {"snapshot": None, "reason": S.tr(S.NO_RECENT_COPY)}
            continue
        name = _snapshot_name(window, position)
        snapshot.save(folder / name)
        groups = set(snapshot.shown()) - set(blinking)
        windows[window] = {"snapshot": name, "time": snapshot.time, "signature": signature_id(groups),
                           "groups": sorted(groups)}
    data = {"id": folder.name, "time": when, "note": note, "picture": None, "windows": windows}
    if picture is not None:
        copy = folder / Path(picture).name
        shutil.copy2(picture, copy)
        data["picture"] = copy.name
        data["picture_time"] = os.path.getmtime(picture)
    write_json(folder / MARK_FILE, data)
    return folder


@dataclass
class Mark:
    id: str
    folder: Path
    time: float
    note: str
    picture: Path | None
    windows: dict[str, dict] = field(default_factory=dict)  # window -> its record (snapshot, signature, groups...)
    done: dict | None = None


def read_marks(root: Path) -> list[Mark]:
    """Every mark under `root` (work/ui), newest first; a folder whose mark.json cannot be read is left out."""
    out = []
    for path in (Path(root) / MARKS_DIR).glob(f"*/{MARK_FILE}"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        folder = path.parent
        done = None
        if (folder / DONE_FILE).is_file():
            try:
                done = json.loads((folder / DONE_FILE).read_text(encoding="utf-8"))
            except ValueError:
                done = {}
        picture = folder / data["picture"] if data.get("picture") else None
        out.append(Mark(data.get("id", folder.name), folder, float(data.get("time", 0.0)), data.get("note", ""),
                        picture, data.get("windows", {}), done))
    return sorted(out, key=lambda m: (m.time, m.id), reverse=True)


def pending(root: Path) -> list[Mark]:
    """The marks not done yet, newest first."""
    return [mark for mark in read_marks(root) if mark.done is None]


def mark_done(root: Path, mark_id: str, note: str = "", commit: str = "", when: float | None = None) -> Path:
    """Sets the mark `mark_id` done (ValueError: no such mark, or done already); returns its done.json."""
    folder = Path(root) / MARKS_DIR / mark_id
    if not (folder / MARK_FILE).is_file():
        raise ValueError(f"no mark {mark_id} in {folder.parent}")
    if (folder / DONE_FILE).exists():
        raise ValueError(f"mark {mark_id} is done already ({folder / DONE_FILE})")
    path = folder / DONE_FILE
    write_json(path, {"time": time.time() if when is None else when, "note": note, "commit": commit})
    return path
