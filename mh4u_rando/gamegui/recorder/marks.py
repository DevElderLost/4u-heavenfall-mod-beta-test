"""The Ctrl+P marks: Ctrl+P in Citra saves the emulator's own picture into
its screenshot folder (`Paths\\screenshotPath` of `<emulator_dir>/config/qt-config.ini`, else
`<emulator_dir>/screenshots/`); each new picture is paired with each window's latest exact snapshot taken at most
`pair_max_age_s` before it and filed as a request in `work/ui/peticiones/<id>/`: `request.json`, the
snapshots (`<window>.json.zst`) and a copy of the picture. «Marcar esta pantalla» files one without a picture."""

import os
import shutil
import time
from pathlib import Path

from .. import strings as S
from .store import signature_id, write_json

PICTURES = (".png", ".jpg", ".jpeg", ".bmp")


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


def file_request(root: Path, snapshots: dict, note: str = "", picture: Path | None = None,
                 when: float | None = None, blinking=()) -> Path:
    """A request folder under `root` (work/ui/peticiones) for the snapshots {window: Snapshot or None}."""
    when = time.time() if when is None else when
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(when))
    folder = Path(root) / stamp
    number = 1
    while folder.exists():
        number += 1
        folder = Path(root) / f"{stamp}_{number}"
    folder.mkdir(parents=True)
    windows = {}
    for window, snapshot in snapshots.items():
        if snapshot is None:
            windows[window] = {"snapshot": None, "reason": S.tr(S.NO_RECENT_COPY)}
            continue
        name = window.lower().replace(" ", "_") + ".json.zst"
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
    write_json(folder / "request.json", data)
    return folder
