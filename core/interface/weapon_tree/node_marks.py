"""A node's small marks, made at build time from the player's own sheets:
the forge mark (the 16 px mallet `node.marks.forge.cell` of the icon sheet `cmn_icon_GSM_NOMIP`, with the Felyne paw
on its head repainted with the head's fill), the box mark (the icon sheet's box with its lid open) and the nine
element and status icons the forge's stats panel draws (16 x 16 cuts of the quest HUD's sheet `qst_icon_BM_MQ_NOMIP`,
`texels`). Each is shrunk by area averaging into one texture of our own (RGBA4444: the grey marks take the layout's
vertex colours, the element icons keep their own), side by side from tile edges; the panes draw them at 1:1. No game
pixel is committed: the recipes (cell or texels, pixels, size) are curated, the pictures come from the player's files.

A picture here is its RGBA bytes, rows from the top left corner.
"""

from collections.abc import Mapping

from core.game.files.gui.tex import RGBA4444, Tex, new_tex

TEXTURE = "lyt\\lobby\\texture\\hf_wt_marks_BM_NOMIP"    # the entry's and the layout's name
ICONS, STATUS = "icons", "status"     # the sheets a recipe takes from: a `cell` of ICONS, `texels` of STATUS
SHEET_COLUMNS, CELL = 10, 16     # the icon sheet's 16 px cells: number n at u = n % 10 * 16, v = n // 10 * 16
TILE = 8                         # the texture's tiles: each picture starts on a tile's edge
# The forge's stats panel's element and status icons, in the order of their index (FUN_002729b8's cuts; the game's
# table 0xDF013C maps a record's type to it): the data block holds their places in this order
ELEMENTS = ("fire", "water", "ice", "thunder", "dragon", "poison", "paralysis", "sleep", "blast")


def source(sheets: Mapping[str, Tex], mark: Mapping) -> tuple[bytes, int, int]:
    """(RGBA bytes, width, height) of the mark's source: the icon sheet's 16 px `cell`, or the status sheet's
    `texels` (x, y, width, height)."""
    if "cell" in mark:
        number = mark["cell"]
        return (sheets[ICONS].get_region(number % SHEET_COLUMNS * CELL, number // SHEET_COLUMNS * CELL, CELL, CELL),
                CELL, CELL)
    x, y, width, height = mark["texels"]
    return sheets[STATUS].get_region(x, y, width, height), width, height


def repaint(cell: bytes, erase, fill_from, width: int = CELL) -> bytes:
    """A copy of `cell` (`width` pixels a row) with every pixel (x, y) of `erase` set to the value of the pixel
    `fill_from`."""
    out = bytearray(cell)
    at = (fill_from[1] * width + fill_from[0]) * 4
    fill = bytes(out[at:at + 4])
    for x, y in erase:
        out[(y * width + x) * 4:(y * width + x) * 4 + 4] = fill
    return bytes(out)


def _weights(source_size: int, target: int) -> list[list[tuple[int, float]]]:
    """For each of `target` output pixels, (source pixel, its share) of every source pixel it covers (the shares sum
    to 1)."""
    rows = []
    for index in range(target):
        low, high = index * source_size / target, (index + 1) * source_size / target
        covered = [(at, min(high, at + 1) - max(low, at)) for at in range(source_size)]
        covered = [(at, share) for at, share in covered if share > 0]
        total = sum(share for _at, share in covered)
        rows.append([(at, share / total) for at, share in covered])
    return rows


def shrink(cell: bytes, size, fit: bool = False, width: int = CELL, height: int = CELL) -> bytes:
    """The opaque part of `cell` (`width` x `height` pixels; its bounding box: the picture has no empty margin)
    averaged by area into `size` (width, height) pixels, premultiplied by alpha so that the edge does not take the
    colour of the empty pixels. `fit`: its proportions kept, as large as `size` holds, centred; else stretched to
    `size`. An empty cell gives an empty picture."""
    out_width, out_height = size
    opaque = [(at % width, at // width) for at in range(width * height) if cell[at * 4 + 3]]
    if not opaque:
        return bytes(out_width * out_height * 4)
    left, right = min(x for x, _y in opaque), max(x for x, _y in opaque)
    top, bottom = min(y for _x, y in opaque), max(y for _x, y in opaque)
    if fit:
        scale = min(out_width / (right - left + 1), out_height / (bottom - top + 1))
        inner = (max(1, round((right - left + 1) * scale)), max(1, round((bottom - top + 1) * scale)))
        small = shrink(cell, inner, False, width, height)
        dx, dy = (out_width - inner[0]) // 2, (out_height - inner[1]) // 2
        out = bytearray(out_width * out_height * 4)
        for y in range(inner[1]):
            at = ((dy + y) * out_width + dx) * 4
            out[at:at + inner[0] * 4] = small[y * inner[0] * 4:(y + 1) * inner[0] * 4]
        return bytes(out)
    box = []     # rows of (red, green, blue premultiplied, alpha)
    for y in range(top, bottom + 1):
        row = []
        for x in range(left, right + 1):
            red, green, blue, alpha = cell[(y * width + x) * 4:(y * width + x) * 4 + 4]
            row.append((red * alpha / 255, green * alpha / 255, blue * alpha / 255, float(alpha)))
        box.append(row)
    columns = _weights(right - left + 1, out_width)
    out = bytearray()
    for shares in _weights(bottom - top + 1, out_height):
        line = [[sum(share * box[at][x][channel] for at, share in shares) for channel in range(4)]
                for x in range(right - left + 1)]
        for across in columns:
            red, green, blue, alpha = (sum(share * line[at][channel] for at, share in across) for channel in range(4))
            covered = max(alpha / 255, 1e-9)
            out += bytes(min(255, max(0, round(value))) for value in (red / covered, green / covered, blue / covered,
                                                                       alpha))
    return bytes(out)


def picture(sheets: Mapping[str, Tex], mark: Mapping) -> bytes:
    """A mark's RGBA picture (`mark["size"]`), from the sheets and its curated recipe: `erase` and `fill_from` when it
    has pixels to repaint, `fit` true to keep its proportions."""
    pixels, width, height = source(sheets, mark)
    if mark.get("erase"):
        pixels = repaint(pixels, mark["erase"], mark["fill_from"], width)
    return shrink(pixels, mark["size"], mark.get("fit", False), width, height)


def _up(value: int, step: int) -> int:
    return -(-value // step) * step


def places(marks: Mapping[str, Mapping]) -> dict[str, tuple[int, int, int, int]]:
    """Each mark's rectangle (x, y, width, height) in the texture: side by side in the recipes' order, each from a
    tile's edge, on the top row."""
    out, x = {}, 0
    for name, mark in marks.items():
        width, height = mark["size"]
        out[name] = (x, 0, width, height)
        x += _up(width, TILE)
    return out


def texture_size(marks: Mapping[str, Mapping]) -> tuple[int, int]:
    """The texture's width and height: what the pictures take, up to the next power of two (at least a tile)."""
    rects = places(marks).values()
    wide = max(x + _up(w, TILE) for x, _y, w, _h in rects)
    tall = max(h for _x, _y, _w, h in rects)
    return tuple(max(TILE, 1 << (side - 1).bit_length()) for side in (wide, tall))


def texture(sheets: Mapping[str, Tex], marks: Mapping[str, Mapping]) -> bytes:
    """The marks' RGBA4444 texture: each picture at its place, the rest empty."""
    tex = new_tex(*texture_size(marks), RGBA4444)
    for name, (x, y, width, height) in places(marks).items():
        tex.set_region(x, y, width, height, picture(sheets, marks[name]))
    return tex.to_bytes()


def region(marks: Mapping[str, Mapping], name: str) -> tuple[float, float, float, float]:
    """Mark `name`'s rectangle in the texture as fractions (u, v, width, height)."""
    (x, y, width, height), (wide, tall) = places(marks)[name], texture_size(marks)
    return x / wide, y / tall, width / wide, height / tall


__all__ = ["CELL", "ELEMENTS", "ICONS", "STATUS", "TEXTURE", "picture", "places", "region", "repaint", "shrink",
           "source", "texture", "texture_size"]
