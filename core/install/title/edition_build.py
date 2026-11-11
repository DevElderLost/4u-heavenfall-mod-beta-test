"""An edition's installed title on a real 3DS, built on the PC:
the edition's own run for a console (`title_build`: the settings a console can use, the START menu's rows a console
allows), then `build_title.build_cia` under the edition's title id and names.

In a checkout that makes editions (`editions/<name>/overlay/`) the edition is the overlay's: its edition file, its
run and its presets, loaded beside this checkout's own, which stay untouched. Anywhere else (an exported edition) the
edition is the code's own.
"""

import importlib.util
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from core.app.edition import Edition, load_edition
from core.install.title.build_title import build_cia

ROOT = Path(__file__).resolve().parents[3]
CURATED = Path("core") / "game" / "data" / "curated"


def overlay_folder(name: str) -> Path | None:
    """`editions/<name>/overlay` of this checkout, None when there is no such edition here."""
    folder = ROOT / "editions" / name / "overlay"
    return folder if folder.is_dir() else None


def edition_for(name: str) -> Edition:
    """The edition `name`'s file: its overlay's, or this code's own edition where there is no overlay (an exported
    edition has only itself)."""
    overlay = overlay_folder(name)
    if overlay is not None:
        return load_edition(overlay / CURATED / "edition.json")
    from core.app.edition import edition
    return edition()


def _run_for(name: str):
    """(run, install_settings, undo): the edition's run and the settings its presets give. For an overlay, its
    presets are read while the settings are made and put back after."""
    from core.app import presets
    overlay = overlay_folder(name)
    if overlay is None:
        from core.app.pipeline import run
        return run, presets.install_settings(presets.personal_defaults()), lambda: None
    saved = presets.PRESETS_PATH, presets.DEFAULTS_PATH
    curated = overlay / CURATED
    presets.PRESETS_PATH, presets.DEFAULTS_PATH = curated / "gui_presets.json", curated / "gui_defaults.json"
    presets.load_presets.cache_clear()
    try:
        settings = presets.install_settings(presets.personal_defaults())
    finally:
        presets.PRESETS_PATH, presets.DEFAULTS_PATH = saved
        presets.load_presets.cache_clear()
    module_name = f"core._edition_run_{name}"
    spec = importlib.util.spec_from_file_location(module_name, overlay / "core" / "app" / "pipeline.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.run, settings, lambda: sys.modules.pop(module_name, None)


def make_edition_mod(rom: Path, mod: Path, name: str, xx_rom: Path | None = None) -> Edition:
    """Run edition `name`'s own run for a console over the decrypted base game `rom` into the folder `mod`; return the
    edition (its title's names and ids). `xx_rom`: MH XX's decrypted .3ds, for the mod with its Layered Gear (the run
    then writes the provenance file, `mhxx_sources.txt`)."""
    current = edition_for(name)
    run, settings, undo = _run_for(name)
    try:
        run(Path(rom), Path(mod), settings, title_build=True, xx_rom=xx_rom)
    finally:
        undo()
    return current


def build_edition_cia(rom: Path, out: Path, name: str, progress: Callable[[int, int], None] | None = None,
                      stage: Callable[[str], None] | None = None, work: Path | None = None) -> str:
    """Write edition `name`'s title for the decrypted base game `rom` to `out`; return the title id. The edition's
    mod is made in a folder beside `out` (`work`) that is removed after; no MH XX, no single-screen mode."""
    current = edition_for(name)
    run, settings, undo = _run_for(name)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    mod = Path(work) if work else Path(tempfile.mkdtemp(prefix=f".{name}_mod_", dir=out.parent))
    try:
        if stage:
            stage("mod")
        run(Path(rom), mod, settings, title_build=True)
        return build_cia(rom, mod, out, progress, stage, current)
    finally:
        undo()
        shutil.rmtree(mod, ignore_errors=True)
