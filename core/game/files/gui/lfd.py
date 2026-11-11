"""MT Framework (3DS) layout fonts: "lfd" files, ARC type 0x3516C3D2 (the game's text font is `<lang>/data/
core_common.arc`'s `loc\\lyt\\font\\font_loc`).

Header (0x28 bytes):
    0x00  magic "lfd\\0"
    0x04  u32 version (3)
    0x08  u32 glyph count
    0x0C  u32 page count
    0x10  u32 unknown (2)
    0x14  u32 the font's size in texels (14)
    0x18  f32 1 / size
    0x1C  u32 offset of the glyph table
    0x20  u32 offset of the page table
    0x24  u32 offset of a table after the pages' names (unknown)

A glyph, 0x14 bytes; the table is sorted by code (the game looks a character up by a binary search):
    0x00  u32 character code (UTF-16)
    0x04  u32 page (bits 0-7), x (bits 8-19) and y (bits 20-31) of its cell in the page, in texels
    0x08  u32 width (bits 0-11) and height (bits 12-23) of the cell; the bits above are flags
    0x0C  u32 advance (bits 0-11); the bits above are flags
    0x10  u32 unknown (0)

A page, 0x24 bytes: 0x00 its texture (0 in the file), 0x04 the offset of its texture's name (the path of the ARC entry,
"loc\\lyt\\font\\font_loc_00_AM_NOMIP"), then floats the game fills when it loads the font (the UV scale).
"""

import struct
from dataclasses import dataclass

LFD_TYPE_HASH = 0x3516C3D2
MAGIC = b"lfd\x00"
GLYPH_SIZE = 0x14
PAGE_SIZE = 0x24
COUNTS_AT, TABLES_AT = 0x08, 0x1C
FIELD = 0xFFF


class LfdFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Glyph:
    index: int          # its place in the table
    code: int
    page: int
    x: int
    y: int
    width: int
    height: int
    advance: int


def _check(data: bytes) -> tuple[int, int, int, int]:
    """(glyph count, page count, glyph table offset, page table offset)."""
    if data[:4] != MAGIC:
        raise LfdFormatError("not a layout font")
    count, pages = struct.unpack_from("<2I", data, COUNTS_AT)
    glyph_table, page_table = struct.unpack_from("<2I", data, TABLES_AT)
    if glyph_table + count * GLYPH_SIZE > len(data) or page_table + pages * PAGE_SIZE > len(data):
        raise LfdFormatError("a table runs past the end of the font")
    return count, pages, glyph_table, page_table


def glyphs(data: bytes) -> list[Glyph]:
    """The font's glyphs, in table order."""
    count, _, table, _ = _check(data)
    out = []
    for index in range(count):
        code, cell, size, advance = struct.unpack_from("<4I", data, table + index * GLYPH_SIZE)
        out.append(Glyph(index, code, cell & 0xFF, cell >> 8 & FIELD, cell >> 20 & FIELD, size & FIELD,
                         size >> 12 & FIELD, advance & FIELD))
    return out


def page_names(data: bytes) -> list[str]:
    """The path of each page's texture, in page order."""
    _, pages, _, table = _check(data)
    names = []
    for page in range(pages):
        at = struct.unpack_from("<I", data, table + page * PAGE_SIZE + 4)[0]
        end = data.find(b"\x00", at) if at < len(data) else -1
        if end < 0:
            raise LfdFormatError(f"page {page} has no name")
        names.append(data[at:end].decode("ascii"))
    return names


def with_cells(data: bytes, cells: dict[int, tuple[int, int]]) -> bytes:
    """The font with the glyphs at the `cells` indices drawn from the cell at (x, y) of the same page. Their size,
    advance, flags and place in the table stay."""
    count, _, table, _ = _check(data)
    out = bytearray(data)
    for index, (x, y) in cells.items():
        if not 0 <= index < count or not (0 <= x <= FIELD and 0 <= y <= FIELD):
            raise LfdFormatError(f"glyph {index} cannot be drawn from ({x}, {y})")
        at = table + index * GLYPH_SIZE + 4
        page = struct.unpack_from("<I", out, at)[0] & 0xFF
        struct.pack_into("<I", out, at, page | x << 8 | y << 20)
    return bytes(out)
