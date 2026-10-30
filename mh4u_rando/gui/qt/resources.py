"""Where the Qt app's bundled files are: the source tree or a PyInstaller bundle (`sys._MEIPASS`)."""

import sys
from pathlib import Path


def resource_path(name: str) -> Path:
    """Path of a file in `gui/qt/assets/` (e.g. `resource_path("logo.png")`)."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        packaged = Path(bundle) / "mh4u_rando" / "gui" / "qt" / "assets" / name
        if packaged.exists():
            return packaged
    return Path(__file__).resolve().parent / "assets" / name
