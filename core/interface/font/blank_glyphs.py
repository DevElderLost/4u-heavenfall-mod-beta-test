"""The game's font with its blank characters drawn from an empty part of its page, far from every glyph.

The game draws a space like a letter: a quad cut from the font's page (`loc\\lyt\\font\\font_loc_00_AM_NOMIP` of
`<lang>/data/core_common.arc`, A4, 1024 x 1024), from a blank cell between two glyphs. The space's cell (x 850, y 16)
comes right after the katakana long vowel mark's, a horizontal bar whose ink ends two texels before it, and the update's
font has that bar six texels further right, over the space's cell. An emulator's HD picture of the page drawn from
another version of the font, or one whose upscaling spreads the bar, therefore shows every space as a dash. Moved
below the last row of glyphs, a blank character draws nothing whatever picture covers the page; its width and advance
stay, so every text is laid out as before.
"""

from collections.abc import Callable

from core.game.files.arc import parse_arc, write_arc
from core.game.files.gui import lfd
from core.game.files.gui.tex import A4, HEADER_SIZE, MORTON_INDEX, TEX_TYPE_HASH, TILE, Tex, parse_tex
from core.game.files.text.common_texts import COMMON_ARC, LANGUAGES

# Blank texels kept around a moved cell: more than a filter reaches or an upscaled picture spreads a glyph.
MARGIN = 16


def _blank(page: Tex, x: int, y: int, width: int, height: int) -> bool:
    """True if the rectangle is inside the A4 `page` and every texel of it is transparent."""
    if x < 0 or y < 0 or x + width > page.width or y + height > page.height:
        return False
    tiles = page.width // TILE
    for row in range(y, y + height):
        for column in range(x, x + width):
            index = ((row // TILE) * tiles + column // TILE) * TILE * TILE + MORTON_INDEX[column % TILE, row % TILE]
            byte = page.raw[HEADER_SIZE + index // 2]
            if (byte >> 4 if index & 1 else byte & 15) != 0:      # the low nibble is the first texel
                return False
    return True


def moved_blank_glyphs(font: bytes, pages: dict[int, Tex]) -> bytes:
    """`font` (an lfd file) with each glyph whose cell is blank in its page drawn from a new cell, one after another
    below the page's last glyph, MARGIN texels from anything. Only A4 pages are read (`pages`: page number -> texture);
    a glyph that finds no room keeps its cell."""
    table = lfd.glyphs(font)
    cells: dict[int, tuple[int, int]] = {}
    for number, page in pages.items():
        if page.format != A4:
            continue
        own = [glyph for glyph in table if glyph.page == number and glyph.width and glyph.height]
        blank = [glyph for glyph in own if _blank(page, glyph.x, glyph.y, glyph.width, glyph.height)]
        inked = [glyph for glyph in own if glyph not in blank]
        if not blank or not inked:
            continue
        x, y = MARGIN, max(glyph.y + glyph.height for glyph in inked) + MARGIN     # the same places on a second pass
        for glyph in blank:
            if not _blank(page, x - MARGIN, y - MARGIN, glyph.width + 2 * MARGIN, glyph.height + 2 * MARGIN):
                break
            cells[glyph.index] = (x, y)
            x += glyph.width + MARGIN
    return lfd.with_cells(font, cells) if cells else font


def font_arc(arc: bytes) -> bytes:
    """`arc` with `moved_blank_glyphs` on every layout font whose pages it holds; `arc` itself when none changes."""
    parsed = parse_arc(arc)
    textures = {entry.name: entry for entry in parsed.entries if entry.type_hash == TEX_TYPE_HASH}
    changed = False
    for entry in parsed.entries:
        if entry.type_hash != lfd.LFD_TYPE_HASH:
            continue
        names = lfd.page_names(entry.data)
        pages = {number: parse_tex(textures[name].data) for number, name in enumerate(names) if name in textures}
        moved = moved_blank_glyphs(entry.data, pages)
        if moved != entry.data:
            entry.data = moved
            changed = True
    return write_arc(parsed) if changed else arc


def font_files(read: Callable[[str], bytes]) -> dict[str, bytes]:
    """{RomFS path: core_common.arc} of the languages whose font gets its blank characters moved. `read` gives each
    file as the mod has it so far (the base game's copy, or another feature's), so what the others wrote stays."""
    out = {}
    for lang in LANGUAGES:
        path = COMMON_ARC.format(lang=lang)
        arc = read(path)
        moved = font_arc(arc)
        if moved is not arc:
            out[path] = moved
    return out
