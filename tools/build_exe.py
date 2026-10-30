"""Build the program for Windows: a folder with its .exe (the app) and its -cli.exe (the command line), zipped.
The names are the edition's (data/curated/edition.json: an edition made with tools/export_edition.py builds its own).

    python tools/build_exe.py [--work DIR] [--no-zip] [--no-check]

Needs PyInstaller (requirements-build.txt) and the packages of requirements.txt. PyInstaller reads
tools/duality.spec, which takes every list from this module. Output, under DIR (default <main checkout>/work/exe):

    dist/<app>/                <app>.exe, <cli>.exe and _internal/ (Python, Qt, mh4u_rando and its data)
    dist/<app>-windows.zip     the same folder zipped: what the GitHub release carries (docs/development.md)

Inside the bundle the package sits where it does in the checkout (`_internal/mh4u_rando/...`), so every module
that finds its files from `__file__` works unchanged; the one file outside the package, `extra_ost_volumes.json`,
goes to `_internal/` where `audio/volumes.py` looks for it (the checkout's top). `RESOURCES` lists what the
program reads at run time; tests/test_packaging.py checks it against the package. An edition
carries only some of them: what its checkout lacks is left out, and without a logo the programs keep Windows' icon.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mh4u_rando.edition import edition  # noqa: E402

PACKAGE = ROOT / "mh4u_rando"
SPEC = ROOT / "tools" / "duality.spec"
LAUNCHERS = ROOT / "tools" / "exe"
LOGO = PACKAGE / "gui" / "qt" / "assets" / "logo.png"

APP_NAME = edition().app_name
CLI_NAME = edition().cli_name       # "duality-cli"
ZIP_NAME = edition().zip_name
ICON_ENV = "DUALITY_ICON"           # the .ico `main` makes for the spec

# What the program reads at run time, relative to mh4u_rando/ (a folder: every file in it that is not code).
RESOURCES = (
    "data",                         # knowledge base, curated rules, icons, MH World's icons and music, the 3DS app
    "gui/qt/assets",                # the logo (gui/qt/resources.py)
    "exefs/generated",              # code_space.json: the code added to the executable, and the game versions' maps
    "alatreon/generated",           # the ported monsters' recordings of what the game's code does with its files
    "alatreon/em050/statics.c",     # read for the sizes of the shells' point tables (alatreon/proof_blocks.py)
    "alatreon/em080/statics.c",
    "alatreon/em082/statics.c",
)
# Files outside the package, to the bundle's top (where the modules that use them look: the checkout's top).
ROOT_RESOURCES = ("extra_ost_volumes.json",)
# Notices that go next to the exe in the zip.
NOTICES = (("LICENSE", "LICENSE.txt"), ("tools/exe/THIRD_PARTY.txt", "THIRD_PARTY.txt"))

# Not needed in the bundle: the music encoder's numpy (only tools use it), the test and research packages.
EXCLUDES = ("numpy", "pytest", "_pytest", "xdist", "execnet", "unicorn", "capstone", "tkinter", "PySide6.QtNetwork")
# Modules of the package only the tools use, left out of the bundle: the game GUI's pictures, checker, gallery and
# the commands of tools/ui.py and the arrangement editor (tools/ui_editor.py), which need numpy. Nothing the program
# runs may import them (tests/test_packaging.py).
TOOLS_ONLY = ("mh4u_rando.gamegui.check", "mh4u_rando.gamegui.edit", "mh4u_rando.gamegui.editor",
              "mh4u_rando.gamegui.editor.state", "mh4u_rando.gamegui.editor.window", "mh4u_rando.gamegui.fidelity",
              "mh4u_rando.gamegui.gallery", "mh4u_rando.gamegui.render")
# The command line has no Qt.
CLI_EXCLUDES = ("PySide6", "shiboken6")
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
    """Every file of RESOURCES as (source, folder in the bundle): the same place under `mh4u_rando/`."""
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


def package_modules(gui: bool = True) -> list[str]:
    """Every module of mh4u_rando, from the file names (nothing is imported). Some are imported by name at run
    time (the GUI's pages, the ported monsters' files), which PyInstaller's scan cannot see: all go in but
    `TOOLS_ONLY`."""
    names = []
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(ROOT).with_suffix("").parts
        if "__pycache__" in parts:
            continue
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        if (not gui and name.startswith("mh4u_rando.gui.qt")) or name in TOOLS_ONLY:
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
    from mh4u_rando import local_config
    return local_config.load().work_dir / "exe"


def build(work: Path) -> Path:
    """Run PyInstaller on tools/duality.spec; returns dist/<app>."""
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
    for source, target in NOTICES:
        shutil.copyfile(ROOT / source, folder / target)
    return folder


def check(folder: Path) -> None:
    """Every resource is in the bundle, and the command line starts."""
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
