"""Build the program for Windows: a folder with its .exe (the app) and its -cli.exe (the command line), zipped.
The names are the edition's (game/data/curated/edition.json: an edition made with tools/release/export_edition.py builds
its own).

    python tools/release/build_exe.py [--work DIR] [--no-zip] [--no-check]

The folder also holds <updater>.exe (install/self_update.py), a single-file console program that brings the program and
the installed mod to the latest published release; it bundles only the edition file and the standard library.

Needs PyInstaller (requirements-build.txt) and the packages of requirements.txt. PyInstaller reads
tools/release/heavenfall.spec, which takes every list from this module. Output, under DIR (default <main
checkout>/work/exe):

    dist/<app>/                <app>.exe, <cli>.exe, <updater>.exe and _internal/ (Python, Qt, core and its data)
    dist/<app>-windows.zip     the same folder zipped: what the GitHub release carries (docs/develop/development.md)

Inside the bundle the package sits where it does in the checkout (`_internal/core/...`), so every module
that finds its files from `__file__` works unchanged; the one file outside the package, `extra_ost_volumes.json`,
goes to `_internal/` where `music/audio/volumes.py` looks for it (the checkout's top). `RESOURCES` lists what the
program reads at run time; tests/tools/release/test_packaging.py checks it against the package. An edition
 carries only some of them: what its checkout lacks is left out, and without a logo the
programs keep Windows' icon.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.app.edition import edition  # noqa: E402

PACKAGE = ROOT / "core"
SPEC = ROOT / "tools" / "release" / "heavenfall.spec"
LAUNCHERS = ROOT / "tools" / "release" / "exe"
LOGO = PACKAGE / "gui" / "qt" / "assets" / "logo.png"

APP_NAME = edition().app_name
CLI_NAME = edition().cli_name       # "heavenfall-cli"
UPDATER_NAME = edition().updater_name   # "Heavenfall-update": beside the app in the zip, single file
ZIP_NAME = edition().zip_name
ICON_ENV = "HEAVENFALL_ICON"       # the .ico `main` makes for the spec

# The folders of data files the program reads, bundled whole (relative to core/).
ASSET_FOLDERS = (
    "game/data",                    # the knowledge base: curated rules, generated data
    "interface/monster_icons/icons",
    "interface/monster_icons/mhw",  # MH World's icons
    "music/mhw/music",              # MH World's music
    "install/installer_3ds",        # the 3DS app
    "interface/single_screen/layout/images",
    "interface/damage_numbers/art",  # Damage Numbers' picture and its cells
)
# What the program reads at run time, relative to core/ (a folder: every file in it that is not code).
RESOURCES = ASSET_FOLDERS + (
    "gui/qt/assets",                # the logo (gui/qt/resources.py)
    # the installed title's HOME Menu icons (install/title/smdh.py)
    "install/title/icon_48.png",
    "install/title/icon_24.png",
    "install/title/certs.bin",      # the CIA's certificate chain (install/title/cia.py)
    # code_space.json: the code added to the executable, and the game versions' maps
    "game/executable/generated",
    # the ported monsters' recordings of what the game's code does with its files
    "monsters/alatreon/recordings.json",
    "monsters/glavenus/recordings_em080.json",
    "monsters/mizutsune/recordings_em082.json",
    "monsters/great_maccao/recordings_em085.json",
    "monsters/maccao/recordings_ems046.json",
    "monsters/valstrax/recordings_em086.json",
    "monsters/astalos/recordings_em081.json",
    # read for the sizes of the shells' point tables (monsters/porting/proof_blocks.py)
    "monsters/alatreon/em050/statics.c",
    "monsters/glavenus/em080/statics.c",
    "monsters/mizutsune/em082/statics.c",
    "monsters/great_maccao/em085/statics.c",
    "monsters/maccao/ems046/static.c",       # Maccao has no shells: his spec's statics, read the same way
    "monsters/valstrax/em086/static.c",
    "monsters/astalos/em081/static.c",
    "native/lib",                   # the native kernels' library
)
# Files outside the package, to the bundle's top (where the modules that use them look: the checkout's top).
ROOT_RESOURCES = ("extra_ost_volumes.json",)
# Notices that go next to the exe in the zip.
NOTICES = (("LICENSE", "LICENSE.txt"), ("tools/release/exe/THIRD_PARTY.txt", "THIRD_PARTY.txt"))

# Not needed in the bundle: the music encoder's numpy (only tools use it), the test and research packages.
EXCLUDES = ("numpy", "pytest", "_pytest", "xdist", "execnet", "unicorn", "capstone", "tkinter", "PySide6.QtNetwork")
# Modules of the package only the tools use, left out of the bundle: the game GUI's pictures, checker, gallery and
# the commands of tools/ui/ui.py, which need numpy. Nothing the program runs may import them
# (tests/tools/release/test_packaging.py).
TOOLS_ONLY = ("core.interface.game_gui.check", "core.interface.game_gui.edit", "core.interface.game_gui.fidelity",
              "core.interface.game_gui.gallery", "core.interface.game_gui.render",
              "core.install.title.patchset")           # the release patch sets' writer (numpy): tools/release only
# The command line has no Qt.
CLI_EXCLUDES = ("PySide6", "shiboken6")
# The updater (tools/release/exe/heavenfall_update.py) is one file with the standard library and these modules of the
# package: tests/tools/release/test_packaging.py checks that it imports nothing else of `core`.
UPDATER_SCRIPT = "heavenfall_update.py"
UPDATER_MODULES = ("core.install.self_update", "core.app.edition", "core.app.i18n", "core.game.data.paths",
                   "core.gui.i18n", "core.gui.preferences")
UPDATER_DATA = "game/data/curated/edition.json"             # the one data file it reads
UPDATER_EXCLUDES = (*EXCLUDES, *CLI_EXCLUDES, "sqlite3", "unittest")
# Files of the Qt that PyInstaller collects and the app never loads (it is a Widgets app on the raster painter that
# shows PNGs and its own texts): matched against the file's place in the bundle, `PySide6/...`. Without them the
# folder is about 50 MB smaller.
QT_DROPPED = (
    r"PySide6/Qt6(Quick|Qml|Pdf|Svg|VirtualKeyboard|Network|OpenGL)",    # Qt modules the plugins depend on
    r"PySide6/opengl32sw\.dll",                                          # the software OpenGL (20 MB)
    r"PySide6/translations/",                                            # Qt's own texts: the app has its own
    r"PySide6/plugins/(generic|iconengines|platforminputcontexts|networkinformation|tls)/",
    r"PySide6/plugins/platforms/(?!qwindows\.dll)",                      # the other platforms (direct2d, offscreen)
    r"PySide6/plugins/imageformats/(?!(qgif|qico|qjpeg)\.dll)",          # the logo is a PNG, which Qt reads itself
)

SKIPPED_FILES = {".py", ".pyc", ".pyo"}


def resource_files() -> list[tuple[Path, str]]:
    """Every file of RESOURCES as (source, folder in the bundle): the same place under `core/`."""
    files = []
    for name in RESOURCES:
        path = PACKAGE / name
        if not path.exists():      # not in this edition
            continue
        if path.is_dir():
            sources = sorted(p for p in path.rglob("*")
                             if p.is_file() and p.suffix not in SKIPPED_FILES and "__pycache__" not in p.parts)
        else:
            sources = [path]
        for source in sources:
            files.append((source, source.parent.relative_to(ROOT).as_posix()))
    return files


def data_files() -> list[tuple[str, str]]:
    """PyInstaller's `datas`: (source file, folder in the bundle)."""
    files = [(str(source), folder) for source, folder in resource_files()]
    files += [(str(ROOT / name), ".") for name in ROOT_RESOURCES if (ROOT / name).is_file()]
    return files


def updater_data_files() -> list[tuple[str, str]]:
    """The updater's `datas`: the edition file, where `core/app/edition.py` looks for it."""
    source = PACKAGE / UPDATER_DATA
    return [(str(source), source.parent.relative_to(ROOT).as_posix())]


def package_modules(gui: bool = True) -> list[str]:
    """Every module of core, from the file names (nothing is imported). Some are imported by name at run
    time (the GUI's pages, the ported monsters' files), which PyInstaller's scan cannot see: all go in but
    `TOOLS_ONLY`."""
    names = []
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(ROOT).with_suffix("").parts
        if "__pycache__" in parts:
            continue
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        if (not gui and name.startswith("core.gui.qt")) or name in TOOLS_ONLY:
            continue
        names.append(name)
    return names


def excludes(gui: bool) -> list[str]:
    return list(EXCLUDES) if gui else [*EXCLUDES, *CLI_EXCLUDES]


def dropped(name: str) -> bool:
    """Whether the bundle's file `name` (its place inside the bundle) is one of QT_DROPPED."""
    name = name.replace("\\", "/")
    return any(re.match(pattern, name) for pattern in QT_DROPPED)


def make_icon(path: Path, sizes: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)) -> Path:
    """<APP_NAME>.ico from the logo (wide: centred on a transparent square, as the window's icon is), a PNG a size."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage, QPainter

    logo = QImage(str(LOGO))
    if logo.isNull():
        raise SystemExit(f"cannot read {LOGO}")
    side = max(logo.width(), logo.height())
    square = QImage(side, side, QImage.Format.Format_ARGB32)
    square.fill(Qt.GlobalColor.transparent)
    painter = QPainter(square)
    painter.drawImage((side - logo.width()) // 2, (side - logo.height()) // 2, logo)
    painter.end()
    pngs = []
    for size in sizes:
        scaled = square.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buffer, "PNG")
        pngs.append(bytes(data))
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = len(head) + 16 * len(sizes)
    entries = []
    for size, png in zip(sizes, pngs):
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
        offset += len(png)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(head + b"".join(entries) + b"".join(pngs))
    return path


def default_work() -> Path:
    sys.path.insert(0, str(ROOT))
    from core.app import local_config
    return local_config.load().work_dir / "exe"


def build(work: Path) -> Path:
    """Run PyInstaller on tools/release/heavenfall.spec; returns dist/<app>."""
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        raise SystemExit("PyInstaller is not installed: python -m pip install -r requirements-build.txt") from None
    work.mkdir(parents=True, exist_ok=True)
    if LOGO.is_file():
        os.environ[ICON_ENV] = str(make_icon(work / "build" / f"{APP_NAME}.ico"))
    pyinstaller.run([str(SPEC), "--distpath", str(work / "dist"), "--workpath", str(work / "build" / "pyinstaller"),
                     "--noconfirm", "--clean"])
    folder = work / "dist" / APP_NAME
    if not (folder / f"{APP_NAME}.exe").is_file():
        raise SystemExit(f"PyInstaller did not make {folder / (APP_NAME + '.exe')}")
    updater = work / "dist" / f"{UPDATER_NAME}.exe"
    if not updater.is_file():
        raise SystemExit(f"PyInstaller did not make {updater}")
    shutil.move(str(updater), folder / updater.name)
    for source, target in NOTICES:
        shutil.copyfile(ROOT / source, folder / target)
    return folder


def check(folder: Path) -> None:
    """Every resource is in the bundle, and the command line and the updater start."""
    inner = folder / "_internal"
    missing = [str(Path(dest) / Path(src).name) for src, dest in data_files()
               if not (inner / dest / Path(src).name).is_file()]
    if missing:
        raise SystemExit(f"missing from the bundle ({len(missing)}): {missing[:5]}")
    done = subprocess.run([str(folder / f"{CLI_NAME}.exe"), "--help"], capture_output=True, text=True, timeout=120)
    if done.returncode != 0 or "--rom" not in done.stdout:
        raise SystemExit(f"{CLI_NAME}.exe --help failed ({done.returncode}):\n{done.stdout}\n{done.stderr}")


def make_zip(folder: Path) -> Path:
    """dist/<zip>: one top folder, so unzipping gives <app>/<app>.exe."""
    target = folder.parent / ZIP_NAME
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, (Path(folder.name) / path.relative_to(folder)).as_posix())
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--work", type=Path, help="build folder (default <main checkout>/work/exe)")
    parser.add_argument("--no-zip", action="store_true", help="only the folder")
    parser.add_argument("--no-check", action="store_true", help="skip the checks of the finished folder")
    args = parser.parse_args(argv)
    folder = build((args.work or default_work()).resolve())
    if not args.no_check:
        check(folder)
    print(f"folder: {folder}")
    if not args.no_zip:
        target = make_zip(folder)
        print(f"zip:    {target} ({target.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
