"""Installing for a real 3DS: onto the SD card, or as the pack for the homebrew installer."""

import shutil
from pathlib import Path

from ..luma import luma_dir, luma_titles
from ..luma_pack import PACK_NAME, write_pack
from . import deploy

APP_NAME = "mh4u_installer.3dsx"
APP_PATH = Path(__file__).resolve().parent.parent / "data" / "installer_3ds" / APP_NAME


def installer_app() -> Path | None:
    """The shipped homebrew installer (tools/installer_3ds, built by hand), if present."""
    return APP_PATH if APP_PATH.is_file() else None


def build_title(build_dir: Path) -> str:
    """The title a console build is for (the one folder of its luma/titles/)."""
    held = luma_titles(build_dir)
    if len(held) != 1:
        raise FileNotFoundError(f"{build_dir} holds no 3DS mod (build with console=True)" if not held else
                                f"{build_dir} holds the mod of more than one title: {', '.join(held)}")
    return held[0]


def _title(build_dir: Path) -> tuple[str, Path]:
    title_id = build_title(build_dir)
    return title_id, Path(build_dir) / luma_dir(title_id)


def install_sd(build_dir: Path, sd_root: Path, kind: str, seed: str = "", checksum: str = "",
               settings: dict | None = None, replace_unknown: bool = False, progress=None, stage=None) -> None:
    """Copy a console run's luma/titles/<id> folder to the SD card at `sd_root`, with the same ownership rules as
    an emulator install (via a temp folder on the card; foreign files stay unless `replace_unknown`). The card's
    folder is the build's own title's: a USA build never lands in the European folder."""
    title_id, title = _title(build_dir)
    plan = [(p, p.relative_to(title).as_posix()) for p in sorted(title.rglob("*"))
            if p.is_file() and p.name != deploy.MARKER]
    plan += deploy.top_files(build_dir, kind)
    deploy.deploy_files(plan, Path(sd_root) / luma_dir(title_id), kind, seed, checksum, settings, replace_unknown,
                        progress, stage, title_id)


def export_ftp(build_dir: Path, dest: Path, kind: str, seed: str = "", checksum: str = "",
               settings: dict | None = None) -> tuple[Path, Path | None]:
    """The pack for FTP (every file of luma/, the marker included) and the homebrew installer, in `dest`:
    `dest`/mh4u_luma.pack for the SD card's root, `dest`/3ds/mh4u_installer.3dsx for /3ds/ (None when the app
    is not shipped)."""
    _, title = _title(build_dir)
    files = [p.relative_to(title).as_posix() for p in title.rglob("*") if p.is_file() and p.name != deploy.MARKER]
    deploy.write_marker(title, kind, files, seed, checksum, settings)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    pack = write_pack(Path(build_dir), dest / PACK_NAME)
    app = installer_app()
    if app is None:
        return pack, None
    (dest / "3ds").mkdir(exist_ok=True)
    shutil.copyfile(app, dest / "3ds" / APP_NAME)
    return pack, dest / "3ds" / APP_NAME
