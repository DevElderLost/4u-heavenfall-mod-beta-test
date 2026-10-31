"""Which product this checkout builds: the full mod, or an edition made from it
(editions/<name>/, tools/release/export_edition.py), whose overlay replaces game/data/curated/edition.json. The GUI, the
installer, the developer tools and the Windows build take their names and choices from here, and so do the old names
that players' disks may still hold."""

import json
import os
import shutil
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from core.game.data.paths import CURATED_DIR

EDITION_FILE = CURATED_DIR / "edition.json"
PAGES = ("install", "options", "randomizer")    # the GUI's pages an edition may have (gui/qt/app.py)
PLATFORMS = ("emulator", "console")             # "console": a real 3DS (luma.py)
TOOLS_LANGUAGES = ("es", "en")


@dataclass(frozen=True)
class Edition:
    name: str                   # the product in the GUI's sentences ("<name> installed.")
    window_title: str
    app_name: str               # the Windows program, <app_name>.exe (tools/release/build_exe.py)
    cli_name: str               # its command line, <cli_name>.exe
    zip_name: str               # what a GitHub release carries
    app_user_model_id: str      # Windows groups the taskbar button by it
    pages: tuple[str, ...]      # of PAGES, in the sidebar's order
    platforms: tuple[str, ...]  # of PLATFORMS; with one the sidebar shows no switch
    needs_mhgen: bool           # the Install page asks for MH Generations' game too
    tools_language: str         # the developer tools' texts (the recorder, tools/ui/ui.py), of TOOLS_LANGUAGES
    user_folder: str            # under the home folder: the GUI's preferences, its log and the builds
    marker: str                 # the file that marks our mod in a mod folder (install/deploy.py)
    # The names this product used before, which players' disks may still hold (empty for an edition that never had any)
    legacy_user_folders: tuple[str, ...] = ()       # copied into user_folder once (migrate_legacy_user_folder)
    legacy_markers: tuple[str, ...] = ()            # a mod folder marked with one is still ours (install/deploy.py)
    legacy_build_markers: tuple[str, ...] = ()      # so do build folders (install/build.py)

    @property
    def home(self) -> Path:
        return Path.home() / self.user_folder

    @property
    def marker_names(self) -> tuple[str, ...]:
        """The marker, then the old ones: the first that exists in a mod folder describes it."""
        return (self.marker, *self.legacy_markers)


def load_edition(path: Path = EDITION_FILE) -> Edition:
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    values.pop("description", None)
    lists = {key: tuple(values[key]) for key in ("pages", "platforms", "legacy_user_folders", "legacy_markers",
                                                  "legacy_build_markers") if key in values}
    edition = Edition(**{**values, **lists})
    unknown = [key for key in edition.pages if key not in PAGES] + \
        [key for key in edition.platforms if key not in PLATFORMS]
    if unknown or not edition.pages or not edition.platforms or edition.tools_language not in TOOLS_LANGUAGES:
        raise ValueError(f"{path}: bad pages, platforms or tools_language ({', '.join(unknown) or 'empty'})")
    return edition


@cache
def edition() -> Edition:
    """This checkout's edition (game/data/curated/edition.json)."""
    return load_edition()


def migrate_legacy_user_folder(home: Path | None = None, current: Edition | None = None) -> Path | None:
    """Copy the first old preferences folder (`legacy_user_folders`) that exists into the edition's own
    `user_folder`, once: only while the new folder does not exist, and the old one stays. Returns the folder copied,
    None when nothing was done. The copy is made beside the new folder and renamed into place, so a copy that stops
    (a full disk) leaves no new folder to hide the next try; it never raises."""
    current = current or edition()
    home = Path.home() if home is None else Path(home)
    new = home / current.user_folder
    if new.exists():
        return None
    for name in current.legacy_user_folders:
        old = home / name
        if not old.is_dir():
            continue
        partial = home / (current.user_folder + ".copying")
        try:
            shutil.rmtree(partial, ignore_errors=True)
            shutil.copytree(old, partial)
            os.replace(partial, new)
        except OSError:
            shutil.rmtree(partial, ignore_errors=True)
            return None
        return old
    return None
