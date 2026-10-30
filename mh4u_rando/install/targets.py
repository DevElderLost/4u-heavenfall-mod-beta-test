"""Where the mod can be installed: emulator user folders and 3DS SD cards."""

import sys
from pathlib import Path
from typing import NamedTuple

from ..exefs import titles
from ..luma import mod_titles


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


def emulator_targets(folders: list[Path] | None = None) -> list[Target]:
    """Every Citra / Azahar / Lime3DS user folder found (`folders`, or hud.build.emulator_folders()), newest first."""
    if folders is None:
        from ..hud.build import emulator_folders
        folders = emulator_folders()
    found, seen = [], set()
    for base in map(Path, folders):
        if not base.is_dir() or base.resolve() in seen:
            continue
        seen.add(base.resolve())
        found.append(Target(base.name, base))
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
