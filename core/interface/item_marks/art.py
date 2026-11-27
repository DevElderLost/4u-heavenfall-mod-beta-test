"""Item marks' art: four gold stars (5, 7, 9 and 11 texels) and the rare
halo, grey on transparent so that the sprites' vertex colour tints them, in a texture of the mod's own, TEXTURE (64 x
32, LA4, as the game's icon sheet), added to each language's core_common.arc. The stars' sprites are made at run time
from their icon's and bound to it (item_marks.c `bind_texture`); the game's icon sheet keeps its bytes, so an HD
texture pack's picture of it applies with any installer.

The stars are pixel art (STAR_ROWS: the outline, then the fill shaded from a bright core to deeper tips, and the
corners between the arms half transparent); the halo is a round glow. An HD texture pack gets the stylized stars of
`art/marks_4x.png` instead (curated/hd_textures.json; tools/build/build_item_marks_art.py).

Each language's copy differs in one texel no sprite reaches (MARKER), so a pack can tell them apart: the installer
writes the HD picture only for the languages whose icon sheet the pack has.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from pathlib import Path

from core.game.files.arc import ArcEntry, parse_arc, write_arc
from core.game.files.gui.tex import LA4, TEX_TYPE_HASH, new_tex

SHEET = "cmn_icon_GSM_NOMIP"        # the game's item sheet the icons draw from (its flags are the texture's)
SHEET_ARC = "core_common.arc"
TEXTURE = "lyt\\common\\texture\\hf_marks_GSM_NOMIP"
TEXTURE_SIZE = (64, 32)
ART_SIZE = (64, 20)                 # the part the art takes, from the top-left corner
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
MARKER = (63, 31)                   # transparent, its grey the language's number: no cell's filter reaches it
STAR_SIZES = (5, 7, 9, 11)
HALO_SIDE = 18
# Each cell's top-left texel and side, one texel apart and from the edges (the sprites are filtered: a neighbour must
# not bleed in)
CELLS = {11: (1, 1, 11), 9: (14, 1, 9), 7: (25, 1, 7), 5: (34, 1, 5), "halo": (41, 1, HALO_SIDE)}
HD_PICTURE = Path(__file__).resolve().parent / "art" / "marks_4x.png"
HD_SCALE = 4

# The stars' silhouettes: O outline, F fill (shaded in star_pixels)
STAR_ROWS = {
    5: ["..O..", ".OFO.", "OFFFO", ".OFO.", "..O.."],
    7: ["...O...", "..OFO..", ".OOFOO.", "OFFFFFO", ".OOFOO.", "..OFO..", "...O..."],
    9: ["....O....", "...OFO...", "...OFO...", ".OOFFFOO.", "OFFFFFFFO", ".OOFFFOO.", "...OFO...", "...OFO...",
        "....O...."],
    11: [".....O.....", "....OFO....", "....OFO....", "...OFFFO...", ".OOFFFFFOO.", "OFFFFFFFFFO", ".OOFFFFFOO.",
         "...OFFFO...", "....OFO....", "....OFO....", ".....O....."],
}
# Luminance of each kind of texel: the outline (and the half-transparent corners, o), the deep tips (D), the fill
# (F) and the bright core (H); the alpha of a corner texel
SHADES = {"O": 0.14, "o": 0.14, "D": 0.72, "F": 0.87, "H": 1.0}
CORNER_ALPHA = 0.53
HALO_FALLOFF = 1.6                  # the glow's alpha is (1 - distance from the middle / radius) ** this


class ItemMarksArtError(ValueError):
    pass


def _shaded(size: int) -> list[list[str]]:
    rows = [list(row) for row in STAR_ROWS[size]]
    c = size // 2
    for r in range(size):
        for col in range(size):
            if rows[r][col] == "F":
                d = abs(r - c) + abs(col - c)
                rows[r][col] = "H" if d == 0 or (d == 1 and size >= 9) else ("F" if d <= size // 4 + 1 else "D")
    for r in range(size):
        for col in range(size):
            if rows[r][col] != ".":
                continue
            across = any(0 <= col + d < size and rows[r][col + d] == "O" for d in (-1, 1))
            down = any(0 <= r + d < size and rows[r + d][col] == "O" for d in (-1, 1))
            if across and down:
                rows[r][col] = "o"
    return rows


def star_pixels(size: int) -> bytes:
    """The star `size` texels across: RGBA rows, grey, at LA4's 16 levels."""
    if size not in STAR_ROWS:
        raise ItemMarksArtError(f"no star of {size} texels")
    out = bytearray()
    for row in _shaded(size):
        for kind in row:
            if kind == ".":
                out += bytes(4)
                continue
            grey = round(SHADES[kind] * 15) * 17
            alpha = round((CORNER_ALPHA if kind == "o" else 1.0) * 15) * 17
            out += bytes((grey, grey, grey, alpha))
    return bytes(out)


def halo_pixels(side: int = HALO_SIDE) -> bytes:
    """The rare halo `side` texels across: white, its alpha a round glow falling to 0 at the cell's edge."""
    out = bytearray()
    radius = side / 2
    for y in range(side):
        for x in range(side):
            d = math.hypot(x + 0.5 - radius, y + 0.5 - radius) / radius
            alpha = round(max(0.0, 1.0 - d) ** HALO_FALLOFF * 15) * 17
            out += bytes((255, 255, 255, alpha))
    return bytes(out)


def art_picture() -> bytes:
    """ART_SIZE's RGBA rows, the cells in place and the rest transparent."""
    width, height = ART_SIZE
    out = bytearray(width * height * 4)
    for key, (x, y, side) in CELLS.items():
        pixels = halo_pixels(side) if key == "halo" else star_pixels(side)
        for row in range(side):
            at = ((y + row) * width + x) * 4
            out[at:at + side * 4] = pixels[row * side * 4:(row + 1) * side * 4]
    return bytes(out)


def cell_uv(key) -> tuple[float, float, float, float]:
    """A cell's place in TEXTURE as a sprite's UV: u, v, width, height (0-1, v from the top)."""
    x, y, side = CELLS[key]
    return x / TEXTURE_SIZE[0], y / TEXTURE_SIZE[1], side / TEXTURE_SIZE[0], side / TEXTURE_SIZE[1]


def texture(lang: str) -> bytes:
    """TEXTURE for `lang` (LANGUAGES): the art at the top, the language's marker, the rest transparent."""
    if lang not in LANGUAGES:
        raise ItemMarksArtError(f"no language {lang!r}")
    tex = new_tex(*TEXTURE_SIZE, fmt=LA4)
    tex.set_region(0, 0, *ART_SIZE, art_picture())
    grey = (LANGUAGES.index(lang) + 1) * 17
    tex.set_region(*MARKER, 1, 1, bytes((grey, grey, grey, 0)))
    return tex.to_bytes()


def add_texture(raw: bytes, lang: str) -> bytes:
    """core_common.arc of `lang` with TEXTURE at its end (no layout names it: the C binds it by its path), the flags
    of the archive's icon sheet. One already there is replaced; the archive is returned as it is when it holds it."""
    arc = parse_arc(raw)
    data = texture(lang)
    ours = [e for e in arc.entries if e.type_hash == TEX_TYPE_HASH and e.name == TEXTURE]
    if len(ours) == 1 and ours[0].data == data:
        return raw
    sheet = next((e for e in arc.entries if e.type_hash == TEX_TYPE_HASH and e.name.endswith("\\" + SHEET)), None)
    if sheet is None:
        raise ItemMarksArtError(f"{SHEET_ARC} of {lang} has no {SHEET}")
    arc.entries = [e for e in arc.entries if e not in ours]
    arc.entries.append(ArcEntry(TEXTURE, TEX_TYPE_HASH, data, sheet.flags))
    return write_arc(arc)


def texture_files(read, files: Mapping[str, bytes] | None = None) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new archive) of each language's core_common.arc with TEXTURE. An archive already in `files` (an
    earlier step's) gets it on top of that version; the others are read with `read(path)`."""
    files = files or {}
    for lang in LANGUAGES:
        path = f"{lang}/data/{SHEET_ARC}"
        yield path, add_texture(files.get(path) or read(path), lang)


__all__ = ["ART_SIZE", "CELLS", "CORNER_ALPHA", "HALO_FALLOFF", "HALO_SIDE", "HD_PICTURE", "HD_SCALE",
           "ItemMarksArtError", "LANGUAGES", "MARKER", "SHADES", "SHEET", "SHEET_ARC", "STAR_SIZES", "STAR_ROWS",
           "TEXTURE", "TEXTURE_SIZE", "add_texture", "art_picture", "cell_uv", "halo_pixels", "star_pixels",
           "texture", "texture_files"]
