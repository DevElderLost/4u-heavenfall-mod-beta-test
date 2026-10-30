"""The Luma3DS mod folder as one file, for the 3DS installer app (tools/installer_3ds/).

Sending the mod's ~2,300 small files to a 3DS over FTP is slow: each file costs a round trip. One big file is
not.
`write_pack` packs `luma/` (luma.py's form) into `mh4u_luma.pack`; the installer app, run on the console, writes the
files back to the SD card's root.

Format (little endian; tools/installer_3ds/source/install.c reads it):
    header   "MH4UPACK" | version u32 | file count u32 | total bytes u64 | clean_len u16 | clean path
    record   path_len u16 | path (UTF-8, "/" separators, from the SD root) | size u64 | data | crc32 u32 of the data
`clean path` is the title's folder: every path is under it, and the installer replaces that folder whole (no file of
an older mod stays).
"""

import zlib
from pathlib import Path

from .luma import luma_dir, luma_titles

PACK_NAME = "mh4u_luma.pack"
MAGIC = b"MH4UPACK"
VERSION = 1
CHUNK = 1 << 20


def pack_files(mod_dir: Path) -> list[Path]:
    """Every file under `mod_dir`/luma, in a fixed order."""
    return sorted(path for path in (Path(mod_dir) / "luma").rglob("*") if path.is_file())


def write_pack(mod_dir: Path, pack_path: Path | None = None) -> Path:
    """Write `mod_dir`'s luma/ folder as one pack file (by default `mod_dir`/PACK_NAME) and return its path. The
    folder holds one title's mod (the player's region); the pack replaces that folder on the card."""
    mod_dir = Path(mod_dir)
    pack_path = Path(pack_path) if pack_path else mod_dir / PACK_NAME
    files = pack_files(mod_dir)
    if not files:
        raise ValueError(f"nothing to pack: {mod_dir / 'luma'} has no files")
    held = luma_titles(mod_dir)
    if len(held) != 1:  # the installer swaps one title's folder whole
        raise ValueError(f"{mod_dir / 'luma'} must hold the mod of exactly one title, it holds {held or 'none'}")
    folder = luma_dir(held[0])
    outside = [path for path in files if mod_dir / folder not in path.parents]
    if outside:  # the installer refuses anything else
        raise ValueError(f"{outside[0]} is outside {folder}")
    clean = folder.as_posix().encode()
    total = sum(path.stat().st_size for path in files)
    with open(pack_path, "wb") as out:
        out.write(MAGIC + VERSION.to_bytes(4, "little") + len(files).to_bytes(4, "little") + total.to_bytes(8, "little")
                  + len(clean).to_bytes(2, "little") + clean)
        for path in files:
            name = path.relative_to(mod_dir).as_posix().encode()
            size = path.stat().st_size
            out.write(len(name).to_bytes(2, "little") + name + size.to_bytes(8, "little"))
            crc = 0
            written = 0
            with open(path, "rb") as source:
                while block := source.read(CHUNK):
                    crc = zlib.crc32(block, crc)
                    written += len(block)
                    out.write(block)
            if written != size:
                raise OSError(f"{path} changed while it was packed")
            out.write(crc.to_bytes(4, "little"))
    return pack_path
