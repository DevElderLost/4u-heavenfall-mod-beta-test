"""Which product this checkout builds: the full mod, or an edition made from it (editions/<name>/,
tools/export_edition.py), whose overlay replaces data/curated/edition.json. The GUI, the installer, the developer
tools and the Windows build take their names and choices from here."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .data.paths import CURATED_DIR

EDITION_FILE = CURATED_DIR / "edition.json"
PAGES = ("install", "options", "randomizer")    # the GUI's pages an edition may have (gui/qt/app.py)
PLATFORMS = ("emulator", "console")             # "console": a real 3DS (luma.py)
TOOLS_LANGUAGES = ("es", "en")


@dataclass(frozen=True)
class Edition:
    name: str                   # the product in the GUI's sentences ("<name> installed.")
    window_title: str
    app_name: str               # the Windows program, <app_name>.exe (tools/build_exe.py)
    cli_name: str               # its command line, <cli_name>.exe
    zip_name: str               # what a GitHub release carries
    app_user_model_id: str      # Windows groups the taskbar button by it
    pages: tuple[str, ...]      # of PAGES, in the sidebar's order
    platforms: tuple[str, ...]  # of PLATFORMS; with one the sidebar shows no switch
    needs_mhgen: bool           # the Install page asks for MH Generations' game too
    tools_language: str         # the developer tools' texts (the recorder, tools/ui.py), of TOOLS_LANGUAGES
    user_folder: str            # under the home folder: the GUI's preferences, its log and the builds
    marker: str                 # the file that marks our mod in a mod folder (install/deploy.py)

    @property
    def home(self) -> Path:
        return Path.home() / self.user_folder


def load_edition(path: Path = EDITION_FILE) -> Edition:
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    values.pop("description", None)
    edition = Edition(**{**values, "pages": tuple(values["pages"]), "platforms": tuple(values["platforms"])})
    unknown = [key for key in edition.pages if key not in PAGES] + \
        [key for key in edition.platforms if key not in PLATFORMS]
    if unknown or not edition.pages or not edition.platforms or edition.tools_language not in TOOLS_LANGUAGES:
        raise ValueError(f"{path}: bad pages, platforms or tools_language ({', '.join(unknown) or 'empty'})")
    return edition


@cache
def edition() -> Edition:
    """This checkout's edition (data/curated/edition.json)."""
    return load_edition()
