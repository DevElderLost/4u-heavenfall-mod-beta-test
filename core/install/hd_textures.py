"""Keeping an HD texture pack working with the mod.

An emulator's texture pack (`load/textures/<title>`) names each picture after a hash of the game's texture, so a texture
the mod changes (a glyph or icons drawn into one of the game's atlases) no longer finds its picture, and one the mod
makes (the weapon tree's marks, the item wheel) never had one. After an install, `adapt_pack` gives each changed
texture a copy of the pack's picture with the same change painted on it, and each texture of ours that has a ready-made
picture (curated/hd_textures.json) that picture, named as the emulator looks for them, in a folder of ours inside the
pack's. The pack's own files are never written.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from core.game.data.paths import CURATED_DIR
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
PICTURE_SIZE = re.compile(r"tex1_(\d+)x(\d+)_")                   # the game texture's size, in the name
OUR_FILE = re.compile(r"tex1_.*\.(png|tmp)")
BLOCK = 4                            # the mod's changes are compared in blocks of this many pixels a side
READ_ERRORS = (OSError, ValueError, KeyError, IndexError, struct.error, zlib.error)  # a file we cannot use
READY_PICTURES = CURATED_DIR / "hd_textures.json"
CORE_DIR = Path(__file__).resolve().parents[1]   # ready-made pictures are named from here
PNG_SIZE_AT = 16                     # a PNG's width and height, big-endian, after its signature and IHDR's header

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


def _pack_scale(pictures: dict[int, Path], default: int, sample: int = 64) -> int:
    """How many times bigger than the game's textures the pack draws them: the middle ratio of its first `sample`
    pictures (the texture's width is in the name, the picture's in its PNG header); `default` when none reads."""
    ratios = []
    for path in list(pictures.values())[:sample]:
        size = PICTURE_SIZE.match(path.name)
        try:
            with path.open("rb") as file:
                width = struct.unpack(">I", file.read(PNG_SIZE_AT + 4)[PNG_SIZE_AT:])[0]
        except READ_ERRORS:
            continue
        if size and int(size.group(1)):
            ratios.append(width / int(size.group(1)))
    if not ratios:
        return default
    return max(1, round(sorted(ratios)[len(ratios) // 2]))


# ---- ready-made pictures --------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ReadyPicture:
    """An HD picture made for a texture the mod writes."""
    texture: str                       # the texture's name in its archives, without its folders
    path: Path
    # The texels (x, y, width, height) it covers in a game texture the mod draws into; None: the whole of a texture
    # of the mod's own
    region: tuple[int, int, int, int] | None = None
    # A texture of the mod's own drawn beside a game texture (the item marks over the icon sheet's icons): written
    # only for an archive whose copy of that texture the pack has a picture of, at that picture's scale
    beside: str | None = None


@dataclass(frozen=True)
class ReadyList:
    """curated/hd_textures.json."""
    pictures: list[ReadyPicture]
    default_scale: int                 # a pack none of whose pictures can be measured
    no_hd_source: dict[str, str] = field(default_factory=dict)  # name pattern -> why the texture has no picture


def ready_list(path: Path = READY_PICTURES) -> ReadyList:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pictures = [ReadyPicture(entry["texture"], CORE_DIR / entry["picture"],
                             tuple(entry["region"]) if "region" in entry else None, entry.get("beside"))
                for entry in data["pictures"]]
    return ReadyList(pictures, data["default_scale"], data["no_hd_source"])


def resize(rgba: bytes, width: int, height: int, new_width: int, new_height: int) -> bytes:
    """An RGBA picture at another size: shrunk by averaging areas, enlarged smoothly, colours weighted by alpha."""
    if (width, height) == (new_width, new_height):
        return rgba
    if new_width > width or new_height > height:
        out = bytearray(new_width * new_height * 4)
        for y in range(new_height):
            y0, y1, fy = _axis((y + 0.5) * height / new_height - 0.5, height)
            for x in range(new_width):
                x0, x1, fx = _axis((x + 0.5) * width / new_width - 0.5, width)
                at = (y * new_width + x) * 4
                out[at:at + 4] = _sample(rgba, width, ((x0, y0, (1 - fx) * (1 - fy)), (x1, y0, fx * (1 - fy)),
                                                      (x0, y1, (1 - fx) * fy), (x1, y1, fx * fy)))
        return bytes(out)
    columns, lines = _area_weights(width, new_width), _area_weights(height, new_height)
    rows = []
    for y in range(height):
        row = rgba[y * width * 4:(y + 1) * width * 4]
        shrunk = []
        for cells in columns:
            red = green = blue = alpha = 0.0
            for x, weight in cells:
                part = row[x * 4 + 3] * weight
                red += row[x * 4] * part
                green += row[x * 4 + 1] * part
                blue += row[x * 4 + 2] * part
                alpha += part
            shrunk.append((red, green, blue, alpha))
        rows.append(shrunk)
    out = bytearray(new_width * new_height * 4)
    for new_y, cells in enumerate(lines):
        for new_x in range(new_width):
            red = green = blue = alpha = 0.0
            for y, weight in cells:
                r, g, b, a = rows[y][new_x]
                red += r * weight
                green += g * weight
                blue += b * weight
                alpha += a * weight
            if alpha > 0:
                at = (new_y * new_width + new_x) * 4
                out[at:at + 4] = bytes((min(255, round(red / alpha)), min(255, round(green / alpha)),
                                        min(255, round(blue / alpha)), min(255, round(alpha))))
    return bytes(out)


def _area_weights(size: int, new_size: int) -> list[list[tuple[int, float]]]:
    """For each of `new_size` cells along an axis, the cells of `size` it covers and their share of it."""
    step = size / new_size
    weights = []
    for cell in range(new_size):
        start, end = cell * step, (cell + 1) * step
        weights.append([(old, (min(end, old + 1) - max(start, old)) / step)
                        for old in range(int(start), min(size, math.ceil(end)))
                        if min(end, old + 1) > max(start, old)])
    return weights


def _read_ready(picture: ReadyPicture, width: int, height: int) -> bytes:
    """`picture` resized to `width` x `height`; ValueError when it is not a whole multiple of the texels it covers
    (it would be drawn stretched)."""
    picture_width, picture_height, rgba = read_png(picture.path.read_bytes())
    texels = picture.region[2:] if picture.region else None
    if texels and (picture_width % texels[0] or picture_height % texels[1]
                   or picture_width // texels[0] != picture_height // texels[1]):
        raise ValueError(f"{picture.path.name} is {picture_width}x{picture_height}, not a multiple of {texels}")
    return resize(rgba, picture_width, picture_height, width, height)


def _flip(rgba: bytes, width: int) -> bytes:
    return _rows_from_the_bottom(rgba, width * 4)


# ---- what the mod changed -------------------------------------------------------------------------------------------

@dataclass
class ModTextures:
    """The textures of a build's archives the game's do not hold as they are."""
    changed: list[tuple[str, bytes, bytes]]   # (name, the game's TEX file, the mod's), each different pair once
    new: list[tuple[str, bytes]]              # (name, the mod's TEX file) of textures the game's archive has not
    # For each new texture (its TEX file), the game's TEX files of the same archive asked for by short name
    # (mod_textures' `beside`): the textures a ready picture is drawn beside
    neighbours: dict[bytes, dict[str, bytes]] = field(default_factory=dict)


def short_name(name: str) -> str:
    """A texture's name without its folders: what curated/hd_textures.json names it by."""
    return name.rsplit("\\", 1)[-1]


def mod_textures(romfs_dir: Path, game: GameFiles, progress: Callable[[int, int], None] | None = None,
                 new_archives: bool = False, beside: Iterable[str] = ()) -> ModTextures:
    """What the mod's archives change or add, once however many archives hold a copy. Archives the game does not have
    are read only with `new_archives` (the install needs none of them: our textures live in the game's archives).
    `beside`: short names of game textures to note, for each new texture, as its archive holds them."""
    romfs_dir = Path(romfs_dir)
    known, beside = set(game.walk()), set(beside)
    arcs = sorted(path for path in romfs_dir.rglob("*.arc")
                  if new_archives or path.relative_to(romfs_dir).as_posix() in known)
    changed: dict[tuple[bytes, bytes], str] = {}
    new: dict[bytes, str] = {}
    neighbours: dict[bytes, dict[str, bytes]] = {}
    for done, path in enumerate(arcs):
        if progress:
            progress(done, len(arcs))
        ours = {e.name: e for e in parse_arc(path.read_bytes()).entries if e.type_hash == TEX_TYPE_HASH}
        if not ours:
            continue
        relative = path.relative_to(romfs_dir).as_posix()
        theirs = parse_arc(game.read(relative)).entries if relative in known else []
        games = {short_name(e.name): e.data for e in theirs if e.type_hash == TEX_TYPE_HASH and short_name(e.name)
                 in beside}
        for entry in theirs:
            mine = ours.pop(entry.name, None) if entry.type_hash == TEX_TYPE_HASH else None
            if mine is not None and mine.data != entry.data:
                changed.setdefault((entry.data, mine.data), entry.name)
        for name, entry in ours.items():   # what is left: names the game's archive has not
            new.setdefault(entry.data, name)
            neighbours.setdefault(entry.data, games)
    return ModTextures([(name, base, mod) for (base, mod), name in changed.items()],
                       [(name, data) for data, name in new.items()], neighbours)


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


def _is_current(target: Path, sources: Iterable[Path]) -> bool:
    """The copy is still right: its name holds what the mod wrote, so only a newer picture it came from changes it."""
    return target.is_file() and all(target.stat().st_mtime >= source.stat().st_mtime for source in sources)


def _write(target: Path, width: int, height: int, rgba: bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".tmp")
    partial.write_bytes(write_png(width, height, rgba))
    os.replace(partial, target)
    return target


def _paste_region(picture: bytearray, picture_width: int, picture_height: int, mod: Tex, ready: ReadyPicture,
                  upside_down: bool) -> None:
    """Draw `ready` over the texels it covers, at the picture's scale."""
    scale_x, scale_y = picture_width / mod.width, picture_height / mod.height
    x, y, width, height = ready.region
    left, top = round(x * scale_x), round(y * scale_y)
    big_width, big_height = round((x + width) * scale_x) - left, round((y + height) * scale_y) - top
    rgba = _read_ready(ready, big_width, big_height)
    for row in range(big_height):
        big_y = top + row
        at = ((picture_height - 1 - big_y if upside_down else big_y) * picture_width + left) * 4
        picture[at:at + big_width * 4] = rgba[row * big_width * 4:(row + 1) * big_width * 4]


def _touches(region: tuple[int, int, int, int], blocks: Iterable[tuple[int, int]]) -> bool:
    x, y, width, height = region
    return any(x < bx + BLOCK and bx < x + width and y < by + BLOCK and by < y + height for bx, by in blocks)


def _adapt_texture(base_bytes: bytes, mod_bytes: bytes, pictures: dict[int, Path], new_naming: bool, upside_down: bool,
                   generated: Path, regions: Iterable[ReadyPicture] = ()) -> Path | None:
    """The copy of one texture's picture, written; None when the pack has no picture for it or already has the copy.
    `regions`: ready-made pictures of what the mod draws into this texture, pasted where the mod changed it."""
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
    regions = list(regions)
    if _is_current(target, [source] + [ready.path for ready in regions]):
        return target
    picture_width, picture_height, rgba = read_png(source.read_bytes())
    picture = bytearray(rgba)
    low = mod.get_rgba()
    blocks = _changed_blocks(base.get_rgba(), low, mod.width, mod.height)
    paint_blocks(picture, picture_width, picture_height, low, mod.width, mod.height, blocks, upside_down)
    for ready in regions:
        if _touches(ready.region, blocks):
            _paste_region(picture, picture_width, picture_height, mod, ready, upside_down)
    return _write(target, picture_width, picture_height, bytes(picture))


def _picture_of(game_bytes: bytes | None, pictures: dict[int, Path], new_naming: bool,
                hashes: dict[bytes, int | None]) -> tuple[Path, int] | None:
    """The pack's picture of the game texture `game_bytes` (a TEX file) and how many times bigger it is drawn; None
    when there is no such texture or the pack has no picture of it. `hashes` keeps the names already worked out."""
    if game_bytes is None:
        return None
    tex = parse_tex(game_bytes)
    if game_bytes not in hashes:
        hashes[game_bytes] = texture_hash(tex, new_naming) if tex.format in EMULATOR_FORMAT else None
    path = pictures.get(hashes[game_bytes]) if hashes[game_bytes] is not None else None
    if path is None:
        return None
    with path.open("rb") as file:
        width = struct.unpack(">I", file.read(PNG_SIZE_AT + 4)[PNG_SIZE_AT:])[0]
    return path, max(1, round(width / tex.width))


def _write_ready(mod_bytes: bytes, ready: ReadyPicture, pictures: dict[int, Path], scale: int, new_naming: bool,
                 upside_down: bool, generated: Path, sources: Iterable[Path] = ()) -> Path | None:
    """The ready-made picture of a texture of the mod's own, written at the pack's `scale`; None when the pack has its
    own picture of it or the format has no name. `sources`: pictures of the pack it depends on (its scale's)."""
    mod = parse_tex(mod_bytes)
    if mod.format not in EMULATOR_FORMAT:
        return None
    mod_hash = texture_hash(mod, new_naming)
    if mod_hash in pictures:
        return None
    target = generated / file_name(mod, mod_hash)
    if _is_current(target, [ready.path, *sources]):
        return target
    picture_width, picture_height = read_png(ready.path.read_bytes())[:2]
    if (picture_width % mod.width or picture_height % mod.height
            or picture_width // mod.width != picture_height // mod.height):
        raise ValueError(f"{ready.path.name} is {picture_width}x{picture_height}, not a multiple of the texture's "
                         f"{mod.width}x{mod.height}")
    width, height = mod.width * scale, mod.height * scale
    rgba = _read_ready(ready, width, height)
    return _write(target, width, height, _flip(rgba, width) if upside_down else rgba)


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
               progress: Callable[[int, int], None] | None = None,
               ready: Iterable[ReadyPicture] | None = None) -> list[Path]:
    """Give the pack of the emulator holding `mods_dir` a copy of each picture the mod in `romfs_dir` changed and the
    ready-made picture of each texture of its own (`ready`; default curated/hd_textures.json), and remove the copies
    of an earlier install it no longer needs. Returns the copies. The game is only opened when there is a pack. A pack
    is an extra: nothing here fails the install, and what cannot be read is logged and left out."""
    folder = textures_folder(mods_dir)
    if folder is None or not folder.is_dir():
        return []
    generated = folder / GENERATED_FOLDER
    written: list[Path] = []
    try:
        pictures = _pack_pictures(folder)
        if pictures:
            listed = ready_list()
            chosen = listed.pictures if ready is None else list(ready)
            ready_of: dict[str, list[ReadyPicture]] = {}
            for picture in chosen:
                ready_of.setdefault(picture.texture, []).append(picture)
            new_naming, upside_down = _read_options(folder)
            textures = mod_textures(romfs_dir, open_game(), progress, beside={p.beside for p in chosen if p.beside})
            scale, hashes = None, {}
            work = [(name, base, mod) for name, base, mod in textures.changed]
            work += [(name, None, mod) for name, mod in textures.new
                     if any(p.region is None for p in ready_of.get(short_name(name), ()))]
            for done, (name, base, mod) in enumerate(work):
                if progress:
                    progress(done, len(work))
                listed_here = ready_of.get(short_name(name), ())
                try:
                    if base is not None:
                        regions = [p for p in listed_here if p.region is not None]
                        copy = _adapt_texture(base, mod, pictures, new_naming, upside_down, generated, regions)
                    else:
                        whole = next(p for p in listed_here if p.region is None)
                        if whole.beside:            # only with the pack's picture of that texture, at its scale
                            found = _picture_of(textures.neighbours.get(mod, {}).get(whole.beside), pictures,
                                                new_naming, hashes)
                            copy = None if found is None else _write_ready(
                                mod, whole, pictures, found[1], new_naming, upside_down, generated, [found[0]])
                        else:
                            if scale is None:
                                scale = _pack_scale(pictures, listed.default_scale)
                            copy = _write_ready(mod, whole, pictures, scale, new_naming, upside_down, generated)
                except READ_ERRORS as error:
                    log.warning("HD texture pack: %s was left out: %s", short_name(name), error)
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
