"""Finding the player's game files where an emulator knows them, so the Install page opens with both pickers filled.

Where, in this order (the first is the best):
  1. each emulator user folder `targets.emulator_targets` finds: the game folders listed in its `config/qt-config.ini`
     (Qt's `Paths\\gamedirs\\<n>\\path` and `deep_scan` keys; `INSTALLED` and `SYSTEM` are not folders) and the titles
     installed in `sdmc/Nintendo 3DS/<id>/<id>/title/00040000/<low>/content/00000000.app`;
  2. the player's Downloads, Desktop and Documents, a few folders deep.
Only files with an accepted extension (`containers.EXTENSIONS`) are opened, and only for their NCCH header
(`extract.ncch_identity`); encrypted files, the games' updates, other games and anything unreadable are left out. The
search is bounded (curated/find_games.json: files read, entries listed, seconds) and never raises: a folder it cannot
list is skipped. It reads, never writes.
"""

import json
import os
import re
import sys
import threading
import time
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from ..exefs import titles
from ..exefs.containers import EXTENSIONS
from ..exefs.extract import ncch_identity

LIMITS_PATH = Path(__file__).resolve().parents[1] / "data" / "curated" / "find_games.json"

# Where a candidate was found (Candidate.source); `place` is the emulator's or the folder's name.
EMULATOR_FOLDER, EMULATOR_INSTALLED, USER_FOLDER = "emulator_folder", "emulator_installed", "user_folder"
_TIER = {EMULATOR_FOLDER: 0, EMULATOR_INSTALLED: 0, USER_FOLDER: 1}

QT_CONFIG = Path("config") / "qt-config.ini"
_GAMEDIR = re.compile(r"^Paths\\gamedirs\\(\d+)\\(path|deep_scan)=(.*)$")
_INSTALLED_PATH, _SYSTEM_PATH = "INSTALLED", "SYSTEM"
PROGRAM_CONTENT = "00000000.app"       # the program of an installed title (its manual and DLC are other contents)
_EXTENSIONS = frozenset(EXTENSIONS)


class Limits(NamedTuple):
    """curated/find_games.json: where and how far to look."""
    user_folders: tuple[str, ...]
    user_depth: int
    game_folder_depth: int
    min_bytes: int
    max_files: int
    max_entries: int
    max_seconds: float

    @classmethod
    def load(cls, path: Path = LIMITS_PATH) -> "Limits":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        values = {name: raw[name]["value"] for name in cls._fields}
        values["user_folders"] = tuple(values["user_folders"])
        return cls(**values)


class Candidate(NamedTuple):
    path: Path
    game: str        # titles.MH4U or titles.MHGEN
    region: str      # titles.EUR or titles.USA
    source: str      # EMULATOR_FOLDER, EMULATOR_INSTALLED or USER_FOLDER
    place: str       # the emulator's folder name ("Azahar"), or the home folder's ("Downloads")


@dataclass
class Found:
    """What a search found, each list best first. `checked`: files whose header was read (a search's cost)."""
    mh4u: list[Candidate] = field(default_factory=list)
    mhgen: list[Candidate] = field(default_factory=list)
    checked: int = 0


# ---- the places ----------------------------------------------------------------------------------------------------

def _qt_string(value: str) -> str:
    """A value of qt-config.ini as the program wrote it: maybe quoted, backslashes doubled."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value.replace("\\\\", "\\")


def config_folders(base: Path) -> list[tuple[Path, bool]]:
    """(folder, deep scan) of the game folders `base`'s qt-config.ini lists, in its order. The `INSTALLED` and
    `SYSTEM` entries are not folders. Nothing for a missing or unreadable file."""
    try:
        text = (Path(base) / QT_CONFIG).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    entries: dict[int, dict[str, str]] = {}
    for line in text.splitlines():
        match = _GAMEDIR.match(line.strip())
        if match:
            entries.setdefault(int(match[1]), {})[match[2]] = _qt_string(match[3])
    folders = []
    for number in sorted(entries):
        path, deep = entries[number].get("path", ""), entries[number].get("deep_scan", "false")
        if path and path not in (_INSTALLED_PATH, _SYSTEM_PATH):
            folders.append((Path(path), deep.lower() == "true"))
    return folders


def installed_programs(base: Path) -> list[Path]:
    """The `00000000.app` of each MH4U and MH Generations title installed in the emulator's virtual SD card."""
    lows = sorted({title[8:] for table in (titles.MH4U_REGIONS, titles.MHGEN_REGIONS) for title in table})
    found = []
    for first in _listing(Path(base) / "sdmc" / "Nintendo 3DS"):
        for second in _listing(first):
            for low in lows:
                program = second / "title" / titles.MH4U_EUR[:8] / low / "content" / PROGRAM_CONTENT
                if program.is_file():
                    found.append(program)
    return found


def _listing(folder: Path) -> list[Path]:
    try:
        with os.scandir(folder) as entries:
            return sorted((Path(entry.path) for entry in entries if entry.is_dir()), key=lambda p: p.name.lower())
    except OSError:
        return []


def _windows_known_folders() -> list[Path]:
    """The real Desktop, Downloads and Documents of this Windows user (they may live in OneDrive)."""
    if sys.platform != "win32":
        return []
    import ctypes
    import uuid
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = [("data", ctypes.c_ubyte * 16)]

    folders = []
    for text in ("B4BFCC3A-DB2C-424C-B029-7FE99A87C641",     # Desktop
                 "374DE290-123F-4565-9164-39C4925E467B",     # Downloads
                 "FDD39AD0-238F-46AF-ADB4-6C85480369C7"):    # Documents
        try:
            guid = Guid.from_buffer_copy(uuid.UUID(text).bytes_le)
            pointer = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, wintypes.HANDLE(0),
                                                          ctypes.byref(pointer)) == 0:
                folders.append(Path(pointer.value))
            ctypes.windll.ole32.CoTaskMemFree(pointer)
        except (OSError, AttributeError, ValueError, TypeError):
            continue
    return folders


def user_folders(limits: Limits | None = None, home: Path | None = None,
                 known: Sequence[Path] | None = None) -> list[Path]:
    """The player's folders to search: the system's own (`known`, else asked of Windows) and the names of the limits
    under the home folder, those that exist, once each."""
    limits = limits or Limits.load()
    home = Path.home() if home is None else Path(home)
    candidates = list(_windows_known_folders() if known is None else known)
    candidates += [home / name for name in limits.user_folders]
    found, seen = [], set()
    for folder in candidates:
        key = os.path.normcase(os.path.abspath(folder))
        if key not in seen and Path(folder).is_dir():
            seen.add(key)
            found.append(Path(folder))
    return found


# ---- the search ----------------------------------------------------------------------------------------------------

class _Search:
    """One search: the budget (files, entries, time) is shared by every place."""

    def __init__(self, limits: Limits, stop: threading.Event | None = None):
        self.limits = limits
        self.stop = stop
        self.deadline = time.monotonic() + limits.max_seconds
        self.entries = 0
        self.checked = 0
        self.order = 0
        self.seen: set[str] = set()
        self.candidates: list[tuple[tuple, Candidate]] = []

    @property
    def spent(self) -> bool:
        return (self.checked >= self.limits.max_files or self.entries >= self.limits.max_entries
                or time.monotonic() >= self.deadline or (self.stop is not None and self.stop.is_set()))

    def folder(self, root: Path, depth: int, source: str, place: str) -> None:
        """The game files in `root` and its folders down to `depth`, shallowest first."""
        queue = deque([(Path(root), 0)])
        while queue and not self.spent:
            folder, level = queue.popleft()
            try:
                with os.scandir(folder) as scanned:
                    entries = sorted(scanned, key=lambda entry: entry.name.lower())
            except OSError:
                continue
            entries = entries[:max(self.limits.max_entries - self.entries, 0)]
            self.entries += len(entries)
            for entry in entries:
                if self.spent:
                    return
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if level < depth and not entry.name.startswith("."):
                            queue.append((Path(entry.path), level + 1))
                    elif os.path.splitext(entry.name)[1].lower() in _EXTENSIONS and entry.is_file():
                        if entry.stat().st_size < self.limits.min_bytes:
                            continue
                        self.file(Path(entry.path), source, place)
                except OSError:
                    continue

    def file(self, path: Path, source: str, place: str) -> None:
        """Read `path`'s header and keep it when it is a decrypted base MH4U or MH Generations."""
        key = os.path.normcase(os.path.abspath(path))
        if key in self.seen:
            return
        self.seen.add(key)
        self.checked += 1
        try:
            title, decrypted = ncch_identity(path)
        except Exception:   # a damaged, cut or foreign file is just not a game: the search goes on
            return
        kind = titles.identify(title)
        if not decrypted or kind is None or kind[0] not in (titles.MH4U, titles.MHGEN):
            return
        self.order += 1
        rank = (_TIER[source], 0 if kind[1] == titles.EUR else 1, self.order)
        self.candidates.append((rank, Candidate(path, kind[0], kind[1], source, place)))


def find(emulators: Iterable | None = None, folders: Iterable[Path] | None = None,
         limits: Limits | None = None, stop: threading.Event | None = None) -> Found:
    """The games found in the emulators (`Target`s: default `targets.emulator_targets()`) and in the player's folders
    (default `user_folders()`), each list best first: where the emulator knows it before a plain folder, then the
    European game before the American one, then the order found. `stop`: an event that ends the search early (the
    window closing). A disk problem never raises: what cannot be read is skipped."""
    limits = limits or Limits.load()
    if emulators is None:
        from .targets import emulator_targets
        emulators = emulator_targets()
    search = _Search(limits, stop)
    for target in emulators:
        base, name = Path(target.base), target.name
        for folder, deep in config_folders(base):
            search.folder(folder, limits.game_folder_depth if deep else 0, EMULATOR_FOLDER, name)
        for program in installed_programs(base):
            if not search.spent:
                search.file(program, EMULATOR_INSTALLED, name)
    for folder in user_folders(limits) if folders is None else folders:
        search.folder(Path(folder), limits.user_depth, USER_FOLDER, Path(folder).name)
    ranked = sorted(search.candidates, key=lambda item: item[0])
    return Found([c for _, c in ranked if c.game == titles.MH4U], [c for _, c in ranked if c.game == titles.MHGEN],
                 search.checked)
