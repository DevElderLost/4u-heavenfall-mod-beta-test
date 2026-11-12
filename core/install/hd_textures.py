"""Keeping an HD texture pack working with the mod.

An emulator's texture pack (`load/textures/<title>`) names each picture after a hash of the game's texture, so a texture
the mod changes (a glyph or icons drawn into one of the game's atlases) no longer finds its picture. After an install,
`adapt_pack` gives each such texture a copy of the pack's picture with the same change painted on it, named as the
emulator now looks for it, in a folder of ours inside the pack's. The pack's own files are never written.

Runs in the installer, which carries no numpy: plain Python, over the formats the mod can write.
"""

import json
import logging
import math
import os
import re
import struct
import zlib
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Protocol

from core.game.files.arc import parse_arc
from core.game.files.gui.png import read_png, write_png
from core.game.files.gui.tex import (BITS_PER_PIXEL, ETC1A4, HEADER_SIZE, LA4, MORTON_INDEX, RGBA4444, RGBA5551,
                                     TEX_TYPE_HASH, TILE, Tex, parse_tex)
from core.install.cityhash import city_hash64

GENERATED_FOLDER = "heavenfall_hd"   # inside the pack's folder: only what `adapt_pack` wrote
PACK_CONFIG = "pack.json"
# Our formats (tex.py) -> the emulator's pixel format, the last number of a texture's file name.
EMULATOR_FORMAT = {RGBA4444: 4, RGBA5551: 2, ETC1A4: 13, LA4: 9}
DECODED_BEFORE_HASH = (ETC1A4, LA4)  # the emulator's old naming hashes these as RGBA, the others as they are stored
PICTURE_NAME = re.compile(r"tex1_\d+x\d+_([0-9A-Fa-f]+)_\d+")   # the start of the name, as the emulator reads it
OUR_FILE = re.compile(r"tex1_.*\.(png|tmp)")
BLOCK = 4                            # the mod's changes are compared in blocks of this many pixels a side
READ_ERRORS = (OSError, ValueError, KeyError, IndexError, struct.error, zlib.error)  # a file we cannot use

log = logging.getLogger(__name__)


class GameFiles(Protocol):
    """The base game: core.game.executable.romfs.RomFS or anything with the same two methods."""
    def read(self, path: str) -> bytes: ...
    def walk(self) -> Iterator[str]: ...


def textures_folder(mods_dir: Path) -> Path | None:
    """The pack's folder for the emulator mod folder `mods_dir` (`.../load/mods/<title>`); None where no emulator reads
    packs, such as a 3DS card's `luma/titles/<title>`."""
    path = Path(mods_dir)
    if [part.lower() for part in path.parts[-3:-1]] != ["load", "mods"]:
        return None
    return path.parent.parent / "textures" / path.name


# ---- the names the emulator looks for -------------------------------------------------------------------------------

def _stored_words(tex: Tex) -> bytes:
    """A 16-bit texture's pixels in rows from the top, out of the 8x8 tiles it is stored in."""
    width, height = tex.width, tex.height
    in_tile = {index: place for place, index in MORTON_INDEX.items()}
    out = bytearray(width * height * 2)
    at = HEADER_SIZE
    for tile_y in range(0, height, TILE):
        for tile_x in range(0, width, TILE):
            for index in range(TILE * TILE):
                x, y = in_tile[index]
                to = ((tile_y + y) * width + tile_x + x) * 2
                out[to:to + 2] = tex.raw[at:at + 2]
                at += 2
    return bytes(out)


def _rows_from_the_bottom(pixels: bytes, stride: int) -> bytes:
    return b"".join(pixels[at:at + stride] for at in range(len(pixels) - stride, -1, -stride))


def texture_hash(tex: Tex, new_naming: bool) -> int:
    """The hash an emulator names the picture of mip 0 of `tex` with. A pack with a `pack.json` that asks for
    `use_new_hash` hashes the bytes as stored; any other (the old naming) the picture in rows from the bottom."""
    if new_naming:
        size = tex.width * tex.height * BITS_PER_PIXEL[tex.format] // 8
        return city_hash64(bytes(tex.raw[HEADER_SIZE:HEADER_SIZE + size]))
    if tex.format in DECODED_BEFORE_HASH:
        return city_hash64(_rows_from_the_bottom(tex.get_rgba(), tex.width * 4))
    return city_hash64(_rows_from_the_bottom(_stored_words(tex), tex.width * 2))


def file_name(tex: Tex, hash_value: int) -> str:
    """The picture's file name: the emulator's "tex1_<width>x<height>_<hash>_<format>.png"."""
    return f"tex1_{tex.width}x{tex.height}_{hash_value:016X}_{EMULATOR_FORMAT[tex.format]}.png"


# ---- the pack -------------------------------------------------------------------------------------------------------

def _read_options(folder: Path) -> tuple[bool, bool]:
    """(new naming, pictures stored upside down) of the pack. No `pack.json`, or a broken one: the emulator's old
    defaults."""
    try:
        options = json.loads((folder / PACK_CONFIG).read_text(encoding="utf-8"))["options"]
        return bool(options["use_new_hash"]), not options["flip_png_files"]
    except (OSError, ValueError, KeyError, TypeError):
        return False, False


def _pack_pictures(folder: Path) -> dict[int, Path]:
    """{hash: picture} of every PNG the emulator would load as a colour map, the first of each hash when there are
    several. Our own copies are left out: a new copy always starts from the pack's picture."""
    found: dict[int, Path] = {}
    for dirpath, dirs, files in os.walk(folder):
        dirs[:] = sorted(name for name in dirs if name != GENERATED_FOLDER)
        for name in sorted(files):
            parts = name.split(".")
            match = PICTURE_NAME.match(parts[0]) if len(parts) == 2 and parts[1] == "png" else None
            if match:
                found.setdefault(int(match.group(1), 16), Path(dirpath) / name)
    return found


# ---- what the mod changed -------------------------------------------------------------------------------------------

def changed_textures(romfs_dir: Path, game: GameFiles,
                     progress: Callable[[int, int], None] | None = None) -> list[tuple[bytes, bytes]]:
    """(the game's TEX file, the mod's TEX file) of each different texture the mod's archives replace, once however
    many archives hold a copy. A texture that is new in the mod has no picture in any pack and is not listed."""
    romfs_dir = Path(romfs_dir)
    known = set(game.walk())
    arcs = sorted(path for path in romfs_dir.rglob("*.arc") if path.relative_to(romfs_dir).as_posix() in known)
    pairs: dict[tuple[bytes, bytes], None] = {}
    for done, path in enumerate(arcs):
        if progress:
            progress(done, len(arcs))
        ours = {e.name: e for e in parse_arc(path.read_bytes()).entries if e.type_hash == TEX_TYPE_HASH}
        if not ours:
            continue
        for entry in parse_arc(game.read(path.relative_to(romfs_dir).as_posix())).entries:
            mine = ours.get(entry.name) if entry.type_hash == TEX_TYPE_HASH else None
            if mine is not None and mine.data != entry.data:
                pairs[entry.data, mine.data] = None
    return list(pairs)


def _changed_blocks(before: bytes, after: bytes, width: int, height: int) -> list[tuple[int, int]]:
    """(x, y) of each block of pixels that differs between two RGBA pictures."""
    stride = width * 4
    changed = []
    for y in range(0, height, BLOCK):
        for x in range(0, width, BLOCK):
            for row in range(y, y + BLOCK):
                at = row * stride + x * 4
                if before[at:at + BLOCK * 4] != after[at:at + BLOCK * 4]:
                    changed.append((x, y))
                    break
    return changed


# ---- painting -------------------------------------------------------------------------------------------------------

def _sample(low: bytes, width: int, corners: Iterable[tuple[int, int, float]]) -> bytes:
    """The RGBA pixel of the weighted `corners` (x, y, weight). Colours are weighted by their alpha: the black under a
    transparent pixel does not darken its neighbours."""
    alpha = red = green = blue = 0.0
    for x, y, weight in corners:
        at = (y * width + x) * 4
        part = low[at + 3] * weight
        alpha += part
        red += low[at] * part
        green += low[at + 1] * part
        blue += low[at + 2] * part
    if alpha <= 0:
        return bytes(4)
    return bytes((round(red / alpha), round(green / alpha), round(blue / alpha), min(255, round(alpha))))


def _axis(position: float, size: int) -> tuple[int, int, float]:
    """The two neighbouring pixels of `position` along an axis of `size` pixels and the weight of the second."""
    first = max(0, min(size - 1, math.floor(position)))
    return first, min(size - 1, first + 1), max(0.0, min(1.0, position - first))


def paint_blocks(picture: bytearray, picture_width: int, picture_height: int, low: bytes, width: int, height: int,
                 blocks: Iterable[tuple[int, int]], upside_down: bool = False) -> None:
    """Draw the `blocks` of the small RGBA picture `low` into the big `picture`, enlarged smoothly. Only those blocks
    are written; the pixels around them are read from `low`, so their edges join what is beside them."""
    scale_x, scale_y = picture_width / width, picture_height / height
    for block_x, block_y in blocks:
        for big_y in range(round(block_y * scale_y), round((block_y + BLOCK) * scale_y)):
            y0, y1, fy = _axis((big_y + 0.5) / scale_y - 0.5, height)
            row = (picture_height - 1 - big_y if upside_down else big_y) * picture_width
            for big_x in range(round(block_x * scale_x), round((block_x + BLOCK) * scale_x)):
                x0, x1, fx = _axis((big_x + 0.5) / scale_x - 0.5, width)
                at = (row + big_x) * 4
                picture[at:at + 4] = _sample(low, width, ((x0, y0, (1 - fx) * (1 - fy)), (x1, y0, fx * (1 - fy)),
                                                          (x0, y1, (1 - fx) * fy), (x1, y1, fx * fy)))


def _adapt_texture(base_bytes: bytes, mod_bytes: bytes, pictures: dict[int, Path], new_naming: bool, upside_down: bool,
                   generated: Path) -> Path | None:
    """The copy of one texture's picture, written; None when the pack has no picture for it or already has the copy."""
    base, mod = parse_tex(base_bytes), parse_tex(mod_bytes)
    same_shape = (base.width, base.height, base.format) == (mod.width, mod.height, mod.format)
    if not same_shape or base.format not in EMULATOR_FORMAT:
        return None
    source = pictures.get(texture_hash(base, new_naming))
    if source is None:
        return None
    mod_hash = texture_hash(mod, new_naming)
    if mod_hash in pictures:
        return None
    target = generated / file_name(mod, mod_hash)
    if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
        return target       # the name holds the mod's change: this copy is still right unless the picture is newer
    picture_width, picture_height, rgba = read_png(source.read_bytes())
    picture = bytearray(rgba)
    low = mod.get_rgba()
    blocks = _changed_blocks(base.get_rgba(), low, mod.width, mod.height)
    paint_blocks(picture, picture_width, picture_height, low, mod.width, mod.height, blocks, upside_down)
    generated.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".tmp")
    partial.write_bytes(write_png(picture_width, picture_height, bytes(picture)))
    os.replace(partial, target)
    return target


def _remove_our_files(generated: Path, keep: Iterable[Path] = ()) -> None:
    """Delete what `adapt_pack` wrote in `generated` but `keep`, and the folder once empty. Foreign files stay."""
    if not generated.is_dir():
        return
    keep = set(keep)
    for path in generated.iterdir():
        if path.is_file() and path not in keep and OUR_FILE.fullmatch(path.name):
            path.unlink()
    if not any(generated.iterdir()):
        generated.rmdir()


def adapt_pack(mods_dir: Path, romfs_dir: Path, open_game: Callable[[], GameFiles],
               progress: Callable[[int, int], None] | None = None) -> list[Path]:
    """Give the pack of the emulator holding `mods_dir` a copy of each picture the mod in `romfs_dir` changed, and
    remove the copies of an earlier install it no longer needs. Returns the copies. The game is only opened when there
    is a pack. A pack is an extra: nothing here fails the install, and what cannot be read is logged and left out."""
    folder = textures_folder(mods_dir)
    if folder is None or not folder.is_dir():
        return []
    generated = folder / GENERATED_FOLDER
    written: list[Path] = []
    try:
        pictures = _pack_pictures(folder)
        if pictures:
            new_naming, upside_down = _read_options(folder)
            pairs = changed_textures(romfs_dir, open_game(), progress)
            for done, (base, mod) in enumerate(pairs):
                if progress:
                    progress(done, len(pairs))
                try:
                    copy = _adapt_texture(base, mod, pictures, new_naming, upside_down, generated)
                except READ_ERRORS as error:
                    log.warning("HD texture pack: a texture was left out: %s", error)
                    continue
                if copy is not None:
                    written.append(copy)
        _remove_our_files(generated, written)
    except READ_ERRORS as error:
        log.warning("HD texture pack: not adapted: %s", error)
    return written


def clear_generated(mods_dir: Path) -> None:
    """Remove the copies `adapt_pack` made for the emulator holding `mods_dir`. The pack stays as it was."""
    folder = textures_folder(mods_dir)
    if folder is not None:
        _remove_our_files(folder / GENERATED_FOLDER)
