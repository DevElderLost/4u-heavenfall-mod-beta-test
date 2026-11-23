"""Item marks' art in the game's icon sheet: four gold stars (5, 7, 9 and 11
texels) and the rare halo, grey on transparent so that the sprites' vertex colour tints them, drawn into a strip of the
sheet `<lang>\\lyt\\common\\texture\\cmn_icon_GSM_NOMIP` (256 x 512, LA4) that no copy of the sheet draws in and no
layout shows. Every item icon is a sprite of that sheet, so a mark is a sprite of the same texture with another cell.

The stars are pixel art (STAR_ROWS: the outline, then the fill shaded from a bright core to deeper tips, and the
corners between the arms half transparent); the halo is a round glow. An HD texture pack gets the stylized stars of
`art/marks_4x.png` over this region (curated/hd_textures.json; tools/build/build_item_marks_art.py).

Only `core_common.arc` of each language is changed: the sheet is loaded by its path, and core_common's copy is the
one in memory (English's other archives carry no copy at all, and their layouts draw the sheet all the same).
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from pathlib import Path

from core.game.files.arc import parse_arc, write_arc
from core.game.files.gui.tex import TEX_TYPE_HASH, parse_tex

SHEET = "cmn_icon_GSM_NOMIP"
SHEET_SIZE = (256, 512)
SHEET_ARC = "core_common.arc"
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
REGION = (0, 492, 64, 20)           # the texels the marks take (x, y, width, height): free in every copy of the sheet
STAR_SIZES = (5, 7, 9, 11)
HALO_SIDE = 18
# Each cell's top-left texel and side, one texel apart (the sprites are filtered: a neighbour must not bleed in)
CELLS = {11: (1, 493, 11), 9: (14, 493, 9), 7: (25, 493, 7), 5: (34, 493, 5), "halo": (41, 493, HALO_SIDE)}
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
    """The star `size` texels across: RGBA rows, grey, at the sheet's 16 levels."""
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


def region_picture() -> bytes:
    """REGION's RGBA rows at the sheet's size, the cells in place and the rest transparent."""
    x0, y0, width, height = REGION
    out = bytearray(width * height * 4)
    for key, (x, y, side) in CELLS.items():
        pixels = halo_pixels(side) if key == "halo" else star_pixels(side)
        for row in range(side):
            at = ((y - y0 + row) * width + (x - x0)) * 4
            out[at:at + side * 4] = pixels[row * side * 4:(row + 1) * side * 4]
    return bytes(out)


def cell_uv(key) -> tuple[float, float, float, float]:
    """A cell's place in the sheet as a sprite's UV: u, v, width, height (0-1, v from the top)."""
    x, y, side = CELLS[key]
    return x / SHEET_SIZE[0], y / SHEET_SIZE[1], side / SHEET_SIZE[0], side / SHEET_SIZE[1]


def paint_sheet(tex_bytes: bytes) -> bytes:
    """The sheet with REGION drawn. Refuses a sheet of another size or one with something already there."""
    tex = parse_tex(tex_bytes)
    if (tex.width, tex.height) != SHEET_SIZE:
        raise ItemMarksArtError(f"{SHEET} is {tex.width} x {tex.height}, not {SHEET_SIZE[0]} x {SHEET_SIZE[1]}")
    x0, y0, width, height = REGION
    if any(tex.get_region(x0, y0, width, height)[3::4]):
        raise ItemMarksArtError(f"{SHEET} already has texels in {REGION}")
    tex.set_region(x0, y0, width, height, region_picture())
    return tex.to_bytes()


def patch_sheet_arc(raw: bytes) -> bytes | None:
    """The archive with its copy of the sheet drawn on, or None when it has none."""
    arc = parse_arc(raw)
    sheets = [e for e in arc.entries if e.type_hash == TEX_TYPE_HASH and e.name.endswith("\\" + SHEET)]
    if not sheets:
        return None
    for entry in sheets:
        entry.data = paint_sheet(entry.data)
    return write_arc(arc)


def sheet_files(read, files: Mapping[str, bytes] | None = None) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new archive) of each language's core_common.arc with the marks drawn into its sheet. An archive
    already in `files` (an earlier step's) is drawn on top of that version; the others are read with `read(path)`."""
    files = files or {}
    for lang in LANGUAGES:
        path = f"{lang}/data/{SHEET_ARC}"
        patched = patch_sheet_arc(files.get(path) or read(path))
        if patched is None:
            raise ItemMarksArtError(f"no {SHEET} in {path}")
        yield path, patched


__all__ = ["CELLS", "CORNER_ALPHA", "HALO_FALLOFF", "HALO_SIDE", "HD_PICTURE", "HD_SCALE", "ItemMarksArtError",
           "LANGUAGES", "REGION", "SHADES", "SHEET", "SHEET_ARC", "SHEET_SIZE", "STAR_ROWS", "STAR_SIZES", "cell_uv",
           "halo_pixels", "paint_sheet", "patch_sheet_arc", "region_picture", "sheet_files", "star_pixels"]
