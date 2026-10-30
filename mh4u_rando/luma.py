"""The mod folder in the form Luma3DS loads on a real 3DS.

A run writes the emulator's form: `romfs/`, `exefs/code.bin` and `exheader.bin` at the mod's
root, which Citra / Azahar take from `load/mods/<title>/`. Luma3DS, with game patching on, takes the same files
from `luma/titles/<title>/` on the SD card, the executable's file next to `romfs/` (no `exefs/` folder). The title is
the player's game's: European 0004000000126100 or American 0004000000126300 (exefs/titles.py, `mod_title`).

`to_luma` moves a written mod into that form inside the mod folder, so the folder's `luma/` is copied as it is to
the SD card's root; the logs and the settings file stay at the mod folder's top. `from_luma` moves it back, so a
run (another seed, a fix) always writes into the emulator's form and finds the files of the run before.
"""

import os
import shutil
from pathlib import Path

from .exefs import titles
from .exefs.output import CODE_PATH, EXHEADER_PATH, IPS_PATH

TITLES_DIR = Path("luma") / "titles"


def mod_titles() -> list[str]:
    """Every title a mod folder may be named after (upper case, as Luma writes them)."""
    return [titles.mod_title(region) for region in (titles.EUR, titles.USA)]


def luma_dir(title_id: str) -> Path:
    """The title's folder on the SD card, relative to its root: luma/titles/<TITLE>."""
    return TITLES_DIR / titles.normal(title_id).upper()


def luma_titles(mod_dir: Path) -> list[str]:
    """The titles `mod_dir` holds in Luma's form (a folder of luma/titles named after a mod title)."""
    return [title for title in mod_titles() if (Path(mod_dir) / luma_dir(title)).is_dir()]


def _moves(title_id: str) -> tuple[tuple[Path, Path], ...]:
    """The emulator's path -> Luma's, both relative to the mod folder."""
    folder = luma_dir(title_id)
    return (
        (Path("romfs"), folder / "romfs"),
        (IPS_PATH, folder / "code.ips"),
        (CODE_PATH, folder / "code.bin"),
        (EXHEADER_PATH, folder / "exheader.bin"),
    )


def luma_path(mod_dir: Path, path: Path, title_id: str) -> Path:
    """Where `path`, a file of the emulator's form in `mod_dir`, is in Luma's form (itself if it does not move)."""
    path, mod_dir = Path(path), Path(mod_dir)
    for source, target in _moves(title_id):
        if path == mod_dir / source or (mod_dir / source) in path.parents:
            return mod_dir / target / path.relative_to(mod_dir / source)
    return path


def to_luma(mod_dir: Path, title_id: str) -> Path:
    """Move the mod in `mod_dir` from the emulator's form to Luma's, in the folder of `title_id`, and return that
    folder. Whatever an earlier run left in Luma's form (of any region) is removed first."""
    mod_dir = Path(mod_dir)
    for old in luma_titles(mod_dir):
        shutil.rmtree(mod_dir / luma_dir(old))
    title = mod_dir / luma_dir(title_id)
    for source, target in _moves(title_id):
        if (mod_dir / source).exists():
            (mod_dir / target).parent.mkdir(parents=True, exist_ok=True)
            os.replace(mod_dir / source, mod_dir / target)
    _remove_empty(mod_dir / IPS_PATH.parent, mod_dir)
    title.mkdir(parents=True, exist_ok=True)
    return title


def from_luma(mod_dir: Path) -> None:
    """Move a mod in Luma's form in `mod_dir` back to the emulator's form (nothing to do in an emulator folder)."""
    mod_dir = Path(mod_dir)
    for title_id in luma_titles(mod_dir):
        for source, target in _moves(title_id):
            if (mod_dir / target).exists():
                if (mod_dir / source).is_dir():
                    shutil.rmtree(mod_dir / source)
                (mod_dir / source).parent.mkdir(parents=True, exist_ok=True)
                os.replace(mod_dir / target, mod_dir / source)
        _remove_empty(mod_dir / luma_dir(title_id), mod_dir)


def _remove_empty(folder: Path, top: Path) -> None:
    """Remove `folder` and its parents up to `top` (excluded) while they are empty."""
    while folder != top and folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
        folder = folder.parent
