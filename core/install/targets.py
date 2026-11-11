"""Where the mod can be installed: emulator user folders and 3DS SD cards."""

import os
import sys
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from core.memo import remember
from core.game.executable import titles
from core.install.luma import mod_titles

# The names of the emulators' user folders: Windows and macOS, then Linux.
EMULATORS = ("Citra", "Azahar", "Lime3DS", "citra-emu", "azahar-emu", "lime3ds-emu")
SETTINGS = "qt-config.ini"
# A portable emulator keeps its user folder, named so, beside its program (Azahar's `SetUserPath`).
PORTABLE_USER = "user"
# The emulators' programs: Windows' executables, Linux' binaries; an AppImage is any `<name>*.AppImage` of these names.
PROGRAMS = ("citra-qt", "citra", "azahar", "azahar-qt", "lime3ds", "lime3ds-gui")


def _homes() -> list[tuple[Path, Path | None]]:
    """(folder, settings folder) of each place the emulators' user folders may be in: Windows' APPDATA, Linux's
    XDG_DATA_HOME and ~/.local/share (settings apart, in XDG_CONFIG_HOME or ~/.config), each Flatpak app's own data
    folder (settings in its config folder), macOS' Application Support. None: the settings are in the emulator's own
    `config` folder."""
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    homes: list[tuple[Path, Path | None]] = []
    if os.environ.get("APPDATA"):
        homes.append((Path(os.environ["APPDATA"]), None))
    if os.environ.get("XDG_DATA_HOME"):
        homes.append((Path(os.environ["XDG_DATA_HOME"]), config))
    homes.append((home / ".local" / "share", config))
    try:
        apps = sorted(entry for entry in (home / ".var" / "app").iterdir() if entry.is_dir())
    except OSError:
        apps = []
    homes += [(app / "data", app / "config") for app in apps]
    homes.append((home / "Library" / "Application Support", None))
    return homes


def emulator_folders() -> list[Path]:
    """User folders where Citra and its forks may keep their data (Windows, Linux and its Flatpak apps, macOS)."""
    return [folder / name for folder, _ in _homes() for name in EMULATORS]


def settings_file(base: str | Path) -> Path:
    """The qt-config.ini of the emulator whose user folder is `base`: in its `config` (Windows, macOS, a portable
    `user` folder), else, for a user folder in Linux's data folders, in the settings folder Linux keeps apart."""
    base = Path(base)
    inside = base / "config" / SETTINGS
    if not inside.is_file():
        for folder, settings in _homes():
            if settings is not None and base.parent == folder:
                return settings / base.name / SETTINGS
    return inside


class Target(NamedTuple):
    name: str       # the emulator's folder name, e.g. "Azahar"
    base: Path      # its user folder

    def mods_dir(self, title_id: str) -> Path:
        """base/load/mods/<title>: the mod folder of the player's region; created on install."""
        return mods_folder_for(self.base, title_id)


def mods_folder_for(chosen: str | Path, title_id: str) -> Path:
    """The emulator's mod folder of `title_id` for a folder the player chose: an emulator's user folder, its
    load/mods, or a mod folder of either region (an earlier choice, or the other region's)."""
    path = Path(chosen)
    title_id = titles.normal(title_id).upper()
    if path.name.upper() in mod_titles():
        return path.with_name(title_id)
    if path.name.lower() == "mods" and path.parent.name.lower() == "load":
        return path / title_id
    return path / "load" / "mods" / title_id


def _newest(base: Path) -> float:
    """When the emulator was last used: the newest of its folder and its first-level entries."""
    times = [base.stat().st_mtime]
    try:
        times += [entry.stat().st_mtime for entry in base.iterdir()]
    except OSError:
        pass
    return max(times)


def _is_program(name: str) -> bool:
    """`name` is an emulator's program file: one of PROGRAMS bare or with `.exe`, or an AppImage named after one."""
    lower = name.lower()
    if lower.endswith(".appimage"):
        return lower.startswith(PROGRAMS)
    return lower.removesuffix(".exe") in PROGRAMS


def portable_folders(roots: Iterable[Path] | None = None, depth: int | None = None) -> list[Path]:
    """Portable emulators' own data folders: a `user` folder beside an emulator's program, in a folder of `roots`
    (default: the player's folders the game search looks in, find_games.user_folders) or in their folders down to
    `depth` levels (default: that search's user_depth). The search shares that search's limit on folder entries."""
    from core.install.find_games import Limits, user_folders
    limits = Limits.load()
    roots = user_folders(limits) if roots is None else roots
    depth = limits.user_depth if depth is None else depth
    budget = limits.max_entries
    found = []
    for root in roots:
        queue = deque([(Path(root), 0)])
        while queue and budget > 0:
            folder, level = queue.popleft()
            try:
                with os.scandir(folder) as scanned:
                    entries = sorted(scanned, key=lambda entry: entry.name.lower())
            except OSError:
                continue
            budget -= len(entries)
            folders, program = [], False
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(entry)
                    elif _is_program(entry.name) and entry.is_file():
                        program = True
                except OSError:
                    continue
            user = next((entry for entry in folders if entry.name.lower() == PORTABLE_USER), None)
            if program and user is not None:
                found.append(Path(user.path))
            if level < depth:
                queue.extend((Path(entry.path), level + 1) for entry in folders
                             if entry is not user and not entry.name.startswith("."))
    return found


_PORTABLE: dict[tuple[str, ...], list[Path]] = {}


def found_portable() -> list[Path]:
    """portable_folders() of the player's folders, scanned once for the same folders (emulator_targets runs on every
    redraw of the install page); forget_portable() makes the next call scan again."""
    from core.install.find_games import Limits, user_folders
    roots = tuple(str(folder) for folder in user_folders(Limits.load()))
    return list(remember(_PORTABLE, roots, lambda: portable_folders([Path(root) for root in roots])))


def forget_portable() -> None:
    """Scan the player's folders for portable emulators again on the next found_portable() (a new search)."""
    _PORTABLE.clear()


def emulator_targets(folders: list[Path] | None = None) -> list[Target]:
    """Every Citra / Azahar / Lime3DS user folder found (`folders`, or emulator_folders() and the portable emulators'
    found_portable()), newest first. A portable emulator is named after the folder that holds its program."""
    if folders is None:
        folders = emulator_folders() + found_portable()
    found, seen = [], set()
    for base in map(Path, folders):
        if not base.is_dir() or base.resolve() in seen:
            continue
        seen.add(base.resolve())
        name = base.parent.name if base.name.lower() == PORTABLE_USER else base.name
        found.append(Target(name, base))
    return sorted(found, key=lambda target: _newest(target.base), reverse=True)


def _default_roots() -> list[Path]:
    if sys.platform == "win32":
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        roots = []
        for index in range(26):
            letter = chr(ord("A") + index) + ":\\"
            if mask >> index & 1 and ctypes.windll.kernel32.GetDriveTypeW(letter) in (2, 3):  # removable, fixed
                roots.append(Path(letter))
        return roots
    if sys.platform == "darwin":
        return sorted(Path("/Volumes").glob("*"))
    return sorted(Path("/media").glob("*")) + sorted(Path("/media").glob("*/*")) + \
        sorted(Path("/run/media").glob("*/*"))


def sd_cards(roots: list[Path] | None = None) -> list[Path]:
    """The drives (`roots`, or the machine's) that hold a 3DS' `luma/` or `Nintendo 3DS/` folder."""
    found = []
    for root in map(Path, _default_roots() if roots is None else roots):
        try:
            if (root / "luma").is_dir() or (root / "Nintendo 3DS").is_dir():
                found.append(root)
        except OSError:
            continue
    return found
