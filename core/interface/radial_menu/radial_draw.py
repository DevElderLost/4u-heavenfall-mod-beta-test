"""The item wheel's picture: its own layout in the quest's files and the data the drawing code reads
(interface/radial_menu/radial_draw.c).

The layout `lyt\\quest\\hf_wheel` (each language's core_quest.arc, with its picture `lyt\\quest\\texture\\
hf_wheel_GSM_NOMIP`) is loaded by the quest's shared hooks (interface/quest_layouts/) at INDEX of the GUI manager. One
root group, `hf_wheel`, holds one null, `hf_wheel_root` (the C moves and scales it: the centre or the right of the
screen), and under it, back to front (root_children, the order radial_draw.c walks): the 4 quarters of the ring that
joins the slots; each slot's diamond (its fill, then its edge); the chosen slot's gold glow and gold diamond; the 8 item
pictures (the game's item sheet, filled by the game's own call); each slot's quantity (two digits); each slot's craft
mark (a cell of the same sheet, at the top right of its picture); the middle circle
with the C-stick's symbol; 8 needles, each drawn toward its slot; the 8 names, each a text in a null of its own; and
the chosen slot's larger gold name, a null with three texts (left-aligned, right-aligned, centred) the code picks from.

The ring, the diamonds, the glow, the circle, the needles and the digits are cells of one LA4 picture (art/,
tools/build/build_radial_art.py): white and grey, tinted by the curated vertex colours. A ring quarter and the needles
of the other directions are the same cells with their texture coordinates mirrored. The records are copies of the item
selector's (ui205 of the same language: its group, a null, the item picture and the name's text, with the HUD's font
and its outline). Every number is in the curated radial_menu.json; the wheel has one size whatever the HUD's.

The START menu's Edit Slots draws the same tree: built by
the same constructor as the last child of ui020's big list frame group (each language's core_common.arc, which the
game keeps loaded in a quest and in town), its root hidden at load, its art added to core_common.arc as MENU_TEXTURE
and its pictures on ui020's own entry of the item sheet. radial_draw.c's radial_menu_wheel moves it to the curated
places of Edit Slots' two layouts (menu_places).

Layout coordinates have the screen's middle as the origin and both axes reversed (x grows to the left, y upwards); the
curated numbers are screen pixels from the top-left corner, or offsets in screen pixels (right and down), and are
turned into layout ones here.
"""

import json
import math
import struct
from collections.abc import Mapping
from functools import cache
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.executable.blocks import RADIAL_DRAW_DATA_SIZE
from core.game.files.arc import ArcEntry, parse_arc, write_arc
from core.game.files.gui.lyt import HEADER, LYT_TYPE_HASH, MAGIC, RECORD_SIZES, VERSION, Layout, PaneKind, name_hash, \
    parse_lyt
from core.game.files.gui.png import read_png
from core.game.files.gui.tex import LA4, TEX_TYPE_HASH, new_tex
from core.interface.hud.build import LANGUAGES, QUEST_ARC, GameFiles
from core.interface.hud.scale import SCREEN_HALF_HEIGHT, SCREEN_HALF_WIDTH
from core.interface.mod_settings.ten_rows import ARC as COMMON_ARC
from core.interface.mod_settings.ten_rows import BIG_FRAME, BIG_GROUP, BIG_STRIPS
from core.interface.mod_settings.ten_rows import LAYOUT as MENU_LAYOUT

SETTINGS_FILE = CURATED_DIR / "radial_menu.json"
ART = Path(__file__).resolve().parent / "art"
PICTURE, CELLS = ART / "radial_menu.png", ART / "radial_menu_atlas.json"
LAYOUT_PATH = "lyt\\quest\\hf_wheel"            # the quest layouts' entry; the arc entry is "<lang>\\" + it
TEXTURE = "lyt\\quest\\texture\\hf_wheel_GSM_NOMIP"
INDEX = 0x5D2           # the group's slot in the GUI manager (quest_layouts.FREE_INDICES), after the horn's songs
SELECTOR = "lyt\\quest\\ui205"                  # the item selector: the records copied
TEMPLATE_GROUP, TEMPLATE_NULL, TEMPLATE_ICON, TEMPLATE_TEXT = "ui205_name_base", "ui205_icon00", "ui205_icon_b00", \
    "ui205_m_00"
GROUP, ROOT = "hf_wheel", "hf_wheel_root"
HALO, GOLD_FILL, GOLD_EDGE, HUB, BIG = "hf_wheel_halo", "hf_wheel_gfill", "hf_wheel_gedge", "hf_wheel_hub", \
    "hf_wheel_big"
BIG_TEXTS = ("hf_wheel_bigl", "hf_wheel_bigr", "hf_wheel_bigc")     # by alignment: left, right, centred
SLOTS = 8
QUARTERS = 4
CENTRED = 4             # a sprite's or a text box's origin: x, y is its middle
ALIGN_LEFT, ALIGN_RIGHT, ALIGN_CENTRED = 0, 1, 2        # how a text's lines sit in its box (lyt.py text_align)
MAX_SIZES = 8           # radial_choices.h: the sizes the save's half byte and the data's places per position hold
POSITIONS = 3           # the centre, the right, the bottom left (radial_choices.h: the choices' position)
SHEET_SIZE = (256, 512)     # the game's item sheet, cmn_icon_GSM_NOMIP (the picture texture of ui205)
# The craft mark: the plain "+" of the item sheet (x, y, width, height in its pixels; the glyph is 7 by 8 pixels at
# (245, 196) in a 16 by 16 cell that none of the game's layouts shows, grey)
CRAFT_CELL = (244, 195, 9, 10)
SIZE_RANGE = (0.5, 2.0)
SIDES = ("above", "below", "right", "left")
COLOURS = ("ring", "fill", "edge", "gold_fill", "gold_edge", "halo", "hub", "needle", "count", "count_none", "craft",
           "name", "big_name")
CELL_NAMES = ("ring", "fill", "edge", "halo", "hub", "needle_up", "needle_right", "needle_diag")
MAX_FONT = 64.0         # the largest letters a name may have, in pixels
MAX_COUNT = 99          # radial_draw.c: a quantity has two digits
# The quarters of the ring, clockwise from the top right, as the screen's directions (right, down) of their corner
QUARTER_SIGNS = ((1, -1), (1, 1), (-1, 1), (-1, -1))
# Edit Slots: ui020's big list frame group, which the START menu's list binder shows and hides (its group 0xD), its
# frame null, the frame's sides and middle (the centred wheel hides them; the title strip under the title stays) and
# the rows' strips' null; the art's name in core_common.arc; the two layouts (centred, small at the left)
MENU_GROUP, MENU_FRAME, MENU_STRIPS = BIG_GROUP, BIG_FRAME, BIG_STRIPS
MENU_BODY = ("ui020_waku10_00", "ui020_waku10_01", "ui020_naka10")
MENU_TEXTURE = "lyt\\common\\texture\\hf_wheel_GSM_NOMIP"
MENU_LAYOUTS = 2
# ui020's places on the top screen, in pixels: its big list's frame starts at x 228 (the rows take 254 to 396), its
# title bar ends at y 38, and in single-screen mode the START menu's description starts at y 196 (Edit Slots' wheels
# stay inside that room at every size: menu_places)
MENU_FRAME_LEFT, MENU_TITLE_BOTTOM, MENU_DESCRIPTION_TOP = 228.0, 38.0, 196.0


class RadialDrawError(ValueError):
    """The curated radial_menu.json, the art or a layout is not what the wheel's picture can use."""


# ---- the panes' names, in the order the code walks them

def ring_name(quarter: int) -> str:
    return f"{GROUP}_ring{quarter}"


def fill_name(slot: int) -> str:
    return f"{GROUP}_fill{slot}"


def edge_name(slot: int) -> str:
    return f"{GROUP}_edge{slot}"


def icon_name(slot: int) -> str:
    return f"{GROUP}_icon{slot}"


def mark_name(slot: int) -> str:
    return f"{GROUP}_craft{slot}"


def tens_name(slot: int) -> str:
    return f"{GROUP}_tens{slot}"


def units_name(slot: int) -> str:
    return f"{GROUP}_unit{slot}"


def needle_name(slot: int) -> str:
    return f"{GROUP}_ndl{slot}"


def name_null(slot: int) -> str:
    return f"{GROUP}_n{slot}"


def name_text(slot: int) -> str:
    return f"{GROUP}_name{slot}"


def root_children() -> list[str]:
    """The root null's children in file order (radial_draw.c's enum: the rings, each slot's fill and edge, the glow,
    the gold fill and edge, the pictures, each slot's tens and units, each slot's craft mark, the middle circle, the
    needles, the name nulls, the big name's null)."""
    return ([ring_name(q) for q in range(QUARTERS)]
            + [name for k in range(SLOTS) for name in (fill_name(k), edge_name(k))]
            + [HALO, GOLD_FILL, GOLD_EDGE]
            + [icon_name(k) for k in range(SLOTS)]
            + [name for k in range(SLOTS) for name in (tens_name(k), units_name(k))]
            + [mark_name(k) for k in range(SLOTS)]
            + [HUB]
            + [needle_name(k) for k in range(SLOTS)]
            + [name_null(k) for k in range(SLOTS)]
            + [BIG])


# ---- the curated numbers

def _value(raw: dict, key: str):
    entry = raw.get(key)
    if not isinstance(entry, dict) or "value" not in entry or not isinstance(entry.get("description"), str):
        raise RadialDrawError(f"radial_menu.json: {key} must be {{\"value\": ..., \"description\": ...}}")
    return entry["value"]


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _number(raw: dict, key: str, low: float, high: float) -> float:
    value = _value(raw, key)
    if not _is_number(value) or not low <= value <= high:
        raise RadialDrawError(f"radial_menu.json: {key} must be a number from {low} to {high}")
    return float(value)


def _whole(raw: dict, key: str, low: int, high: int) -> int:
    value = _value(raw, key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RadialDrawError(f"radial_menu.json: {key} must be a whole number from {low} to {high}")
    return value


def _numbers(raw: dict, key: str, low: tuple[float, ...], high: tuple[float, ...]) -> tuple[float, ...]:
    value = _value(raw, key)
    if not isinstance(value, list) or len(value) != len(low) or not all(_is_number(v) for v in value) or \
            not all(low[i] <= value[i] <= high[i] for i in range(len(low))):
        ranges = ", ".join(f"{low[i]} to {high[i]}" for i in range(len(low)))
        raise RadialDrawError(f"radial_menu.json: {key} must be {len(low)} numbers ({ranges})")
    return tuple(float(v) for v in value)


def _sizes(raw: dict) -> tuple[float, ...]:
    value = _value(raw, "draw_sizes")
    low, high = SIZE_RANGE
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_SIZES or not all(_is_number(v) for v in value) or \
            not all(low <= v <= high for v in value) or any(b <= a for a, b in zip(value, value[1:])):
        raise RadialDrawError(f"radial_menu.json: draw_sizes must be 1 to {MAX_SIZES} numbers from {low} to {high}, "
                              "smallest first")
    return tuple(float(v) for v in value)


def _colours(raw: dict) -> dict[str, tuple[int, int, int, int]]:
    value = _value(raw, "draw_colours")
    if not isinstance(value, dict) or set(value) != set(COLOURS) or not all(
            isinstance(c, list) and len(c) == 4 and all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 255
                                                        for x in c) for c in value.values()):
        raise RadialDrawError(f"radial_menu.json: draw_colours must give {', '.join(COLOURS)} as four bytes (RGBA)")
    return {name: tuple(value[name]) for name in COLOURS}


def load_draw_settings(path: Path = SETTINGS_FILE) -> dict:
    """The curated drawing values, checked."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    screen = (2.0 * SCREEN_HALF_WIDTH, 2.0 * SCREEN_HALF_HEIGHT)
    size = ((1.0, 1.0), screen)
    sides = _value(raw, "draw_name_sides")
    if not isinstance(sides, list) or len(sides) != SLOTS or not all(side in SIDES for side in sides):
        raise RadialDrawError(f"radial_menu.json: draw_name_sides must give each of the {SLOTS} slots one of "
                              f"{', '.join(SIDES)}")
    settings = {
        "centre": _numbers(raw, "draw_centre", (0.0, 0.0), screen),
        "right": _numbers(raw, "draw_right", (0.0, 0.0), screen),          # the margin to the edge, the middle's y
        "bottom_left": _numbers(raw, "draw_bottom_left", (0.0, 0.0), screen),   # the margins to the edge, the bottom
        "scale": _numbers(raw, "draw_scale", (0.1,) * POSITIONS, (1.0,) * POSITIONS),   # centre, right, bottom left
        "craft_mark": _numbers(raw, "draw_craft_mark", (1.0, 1.0, -64.0, -64.0), (64.0, 64.0, 64.0, 64.0)),
        "sizes": _sizes(raw),
        "radius": _number(raw, "draw_radius", 1.0, 110.0),
        "icon": _numbers(raw, "draw_icon_size", *size),
        "rhombus": _numbers(raw, "draw_rhombus_size", *size),
        "halo": _numbers(raw, "draw_halo_size", *size),
        "hub": _numbers(raw, "draw_hub_size", *size),
        "needle": _numbers(raw, "draw_needle", (0.0, 1.0, 1.0), (110.0, 110.0, 32.0)),
        "marked_scale": _number(raw, "draw_marked_scale", 1.0, 3.0),
        "mark_magnitude": _whole(raw, "draw_mark_magnitude", 1, 127),
        "dark": _number(raw, "draw_dark_icon", 0.01, 0.99),
        "count_size": _numbers(raw, "draw_count_size", (1.0, 1.0), (32.0, 32.0)),
        "count_place": _numbers(raw, "draw_count_place", (-64.0, -64.0), (64.0, 64.0)),
        "count_advance": _number(raw, "draw_count_advance", 1.0, 32.0),
        "sides": tuple(sides),
        "name_gap": _number(raw, "draw_name_gap", 0.0, 32.0),
        "name_box": _numbers(raw, "draw_name_box", *size),
        "name_font": _numbers(raw, "draw_name_font", (1.0, 1.0), (MAX_FONT, MAX_FONT)),
        "big_box": _numbers(raw, "draw_big_box", *size),
        "big_font": _numbers(raw, "draw_big_font", (1.0, 1.0), (MAX_FONT, MAX_FONT)),
        "name_outline": _whole(raw, "draw_name_outline", 0, 15),
        "name_room": _whole(raw, "draw_name_room", 1, 200),
        "reserve": _whole(raw, "draw_pool_reserve", 16, 4096),
        "layer": _whole(raw, "draw_layer", 0, 31),
        "priority": _whole(raw, "draw_priority", 20, 62),
        "colours": _colours(raw),
        "menu_centre": _numbers(raw, "menu_centre", (0.0, 0.0), screen),
        "menu_left": _numbers(raw, "menu_left", (0.0, 0.0), screen),
        "menu_scale": _numbers(raw, "menu_scale", (0.1, 0.1), (1.0, 1.0)),      # centred, small
    }
    start, end, _width = settings["needle"]
    if start < max(settings["hub"]) / 2 or end <= start:
        raise RadialDrawError("radial_menu.json: draw_needle must start outside the middle circle (draw_hub_size) "
                              "and end farther out than it starts")
    if end > settings["radius"] - settings["rhombus"][1] / 2 * settings["marked_scale"]:
        raise RadialDrawError("radial_menu.json: draw_needle must end before the chosen slot's gold diamond "
                              "(draw_radius, draw_rhombus_size, draw_marked_scale)")
    return settings


# ---- the geometry, in screen pixels (right and down) from the wheel's middle at its full size

def slot_point(slot: int, radius: float) -> tuple[float, float]:
    """The middle of slot `slot`'s picture: slot 0 straight up, then clockwise in eighths of a turn."""
    angle = math.radians(360 * slot / SLOTS)
    return radius * math.sin(angle), -radius * math.cos(angle)


def to_layout(x: float, y: float) -> tuple[float, float]:
    """An offset in screen pixels (right, down) in layout units (x grows to the left, y upwards)."""
    return -x + 0.0, -y + 0.0


def layout_point(x: float, y: float) -> tuple[float, float]:
    """A point of the top screen in pixels from its top-left corner, in layout units."""
    return SCREEN_HALF_WIDTH - x, SCREEN_HALF_HEIGHT - y


def name_box(slot: int, settings: Mapping, big: bool = False) -> tuple[tuple[float, float, float, float], int]:
    """Slot `slot`'s name box (its larger gold one with `big`): (left, top, right, bottom) from the wheel's middle, and
    how its text sits in it. A name to the right starts `name_gap` beside the diamond (the chosen one's when big) and
    runs right; to the left, the other way; above or below, the box is `name_gap` from the diamond's tip, centred on a
    slot of the middle line, else starting under the picture's inner edge and running outwards."""
    x, y = slot_point(slot, settings["radius"])
    scale = settings["marked_scale"] if big else 1.0
    half_w, half_h = settings["rhombus"][0] / 2 * scale, settings["rhombus"][1] / 2 * scale
    icon_half = settings["icon"][0] / 2 * scale
    width, height = settings["big_box"] if big else settings["name_box"]
    gap, side = settings["name_gap"], settings["sides"][slot]
    if side in ("right", "left"):
        top = y - height / 2
        if side == "right":
            left, align = x + half_w + gap, ALIGN_LEFT
        else:
            left, align = x - half_w - gap - width, ALIGN_RIGHT
    else:
        top = y + half_h + gap if side == "below" else y - half_h - gap - height
        if abs(x) < 0.5:
            left, align = x - width / 2, ALIGN_CENTRED
        elif x > 0:
            left, align = x - icon_half, ALIGN_LEFT
        else:
            left, align = x + icon_half - width, ALIGN_RIGHT
    return (left, top, left + width, top + height), align


def box_middle(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def wheel_bounds(settings: Mapping) -> tuple[float, float, float, float]:
    """The box (left, top, right, bottom) around everything the wheel may show at its full size, from its middle in
    screen pixels: every name box, small and big, each slot's chosen diamond and glow, and each quantity's digits."""
    boxes = [name_box(k, settings, big)[0] for k in range(SLOTS) for big in (False, True)]
    marked = settings["marked_scale"]
    (place_x, place_y), (digit_w, digit_h) = settings["count_place"], settings["count_size"]
    mark_w, mark_h, mark_x, mark_y = settings["craft_mark"]
    for k in range(SLOTS):
        x, y = slot_point(k, settings["radius"])
        for w, h in ((settings["rhombus"][0] * marked, settings["rhombus"][1] * marked), settings["halo"]):
            boxes.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
        boxes.append((x + mark_x - mark_w / 2, y + mark_y - mark_h / 2, x + mark_x + mark_w / 2,
                      y + mark_y + mark_h / 2))
        for dx in (0.0, -settings["count_advance"]):
            digit_x, digit_y = x + place_x + dx, y + place_y
            boxes.append((digit_x - digit_w / 2, digit_y - digit_h / 2, digit_x + digit_w / 2, digit_y + digit_h / 2))
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def wheel_places(settings: Mapping) -> tuple[tuple[tuple[float, float, float], ...], ...]:
    """Where the wheel's middle goes and how large it is drawn, (x, y, scale) in screen pixels from the top-left corner,
    for each curated size: at the centre (its curated place), then at the right, where x keeps the wheel's rightmost
    part (wheel_bounds) the curated margin from the screen's right edge, then at the bottom left, where x keeps its
    leftmost part and y its lowest part the curated margins from the left edge and the bottom."""
    left_edge, _top, right_edge, bottom_edge = wheel_bounds(settings)
    (centre_x, centre_y), (margin, right_y) = settings["centre"], settings["right"]
    (left_margin, bottom_margin), (centre_scale, right_scale, corner_scale) = settings["bottom_left"], settings["scale"]
    screen_w, screen_h = 2.0 * SCREEN_HALF_WIDTH, 2.0 * SCREEN_HALF_HEIGHT
    centre = tuple((centre_x, centre_y, centre_scale * size) for size in settings["sizes"])
    right = tuple((screen_w - margin - right_edge * right_scale * size, right_y, right_scale * size)
                  for size in settings["sizes"])
    corner = tuple((left_margin - left_edge * corner_scale * size,
                    screen_h - bottom_margin - bottom_edge * corner_scale * size, corner_scale * size)
                   for size in settings["sizes"])
    return centre, right, corner


def _largest_fit(middle: tuple[float, float], bounds: tuple[float, float, float, float],
                 room: tuple[float, float, float, float]) -> float:
    """The largest scale at which the wheel's box (`bounds`, from its middle at scale 1) drawn around `middle` stays
    inside `room` (left, top, right, bottom)."""
    (x, y), (left, top, right, bottom) = middle, bounds
    return min((x - room[0]) / -left, (y - room[1]) / -top, (room[2] - x) / right, (room[3] - y) / bottom)


def menu_places(settings: Mapping) -> tuple[tuple[tuple[float, float, float], ...], ...]:
    """Where the wheel's middle goes in Edit Slots and how large it is drawn, (x, y, scale) in screen pixels from the
    top-left corner, for each curated size (the player's Size row): centred (menu_centre) and small at the left of the
    pouch list (menu_left), at menu_scale's two scales times the size. A size that would leave the wheel's room (under
    ui020's title bar and above the description, and for the small one left of the list's frame) is drawn at the
    largest scale that fits; the middles never move, and the player's position is not used there."""
    bounds = wheel_bounds(settings)
    screen_w = 2.0 * SCREEN_HALF_WIDTH
    rooms = ((0.0, MENU_TITLE_BOTTOM, screen_w, MENU_DESCRIPTION_TOP),
             (0.0, 0.0, MENU_FRAME_LEFT, MENU_DESCRIPTION_TOP))
    places = []
    for middle, base, room in zip((settings["menu_centre"], settings["menu_left"]), settings["menu_scale"], rooms):
        fit = _largest_fit(tuple(middle), bounds, room)
        places.append(tuple((middle[0], middle[1], min(base * size, fit)) for size in settings["sizes"]))
    return tuple(places)


def needle_sizes(settings: Mapping) -> dict[str, tuple[float, float]]:
    """The needles' sprites (width, height): pointing up or down, right or left, and along a diagonal (a square whose
    corner-to-corner line is the needle)."""
    start, end, width = settings["needle"]
    length = end - start
    side = length / math.sqrt(2) + width / math.sqrt(2)
    return {"needle_up": (width, length), "needle_right": (length, width), "needle_diag": (side, side)}


def needle_of(slot: int) -> tuple[str, bool, bool]:
    """Slot `slot`'s needle: its cell and whether its texture coordinates are mirrored across and down (the cells
    point up, right and up-right)."""
    x, y = slot_point(slot, 1.0)
    across, down = round(x), round(y)
    if across == 0:
        return "needle_up", False, down > 0
    if down == 0:
        return "needle_right", across < 0, False
    return "needle_diag", across < 0, down > 0


# ---- the art

@cache
def atlas() -> dict:
    """The art's cells (art/radial_menu_atlas.json): {"size": [w, h], "cells": {name: [x, y, w, h]}, "digits": [[x, y,
    w, h] x 10], "ring_radius": the ring's radius in its cell}, in pixels from the top left."""
    cells = json.loads(CELLS.read_text(encoding="utf-8"))
    if set(cells.get("cells", {})) != set(CELL_NAMES) or len(cells.get("digits", [])) != 10 or \
            not cells.get("ring_radius"):
        raise RadialDrawError(f"{CELLS.name}: it must have the cells {', '.join(CELL_NAMES)}, ten digits and the "
                              "ring's radius (tools/build/build_radial_art.py)")
    return cells


def region(cell, mirror_x: bool = False, mirror_y: bool = False, cells: Mapping | None = None) \
        -> tuple[float, float, float, float]:
    """A cell's texture coordinates (u, v, width, height, 0-1, v from the top), mirrored across or down."""
    width, height = (cells or atlas())["size"]
    x, y, w, h = cell
    u, v, du, dv = x / width, y / height, w / width, h / height
    if mirror_x:
        u, du = u + du, -du
    if mirror_y:
        v, dv = v + dv, -dv
    return u, v, du, dv


def sheet_region(cell: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    """A cell of the item sheet (x, y, width, height in its pixels) as texture coordinates (u, v, width, height)."""
    x, y, w, h = cell
    return x / SHEET_SIZE[0], y / SHEET_SIZE[1], w / SHEET_SIZE[0], h / SHEET_SIZE[1]


def texture() -> bytes:
    """The art as an LA4 texture (grey and alpha: the vertex colours tint it)."""
    width, height, rgba = read_png(PICTURE.read_bytes())
    tex = new_tex(width, height, LA4)
    tex.set_region(0, 0, width, height, rgba)
    return tex.to_bytes()


# ---- the layout

def _padded(text: str) -> bytes:
    encoded = text.encode("ascii") + b"\x00"
    return encoded + b"\x00" * (-len(encoded) % 4)


def _skeleton(source: Layout, textures: list[str]) -> Layout:
    """A layout of one empty root group GROUP (a copy of the selector's group record) and `textures`."""
    group = source.find(TEMPLATE_GROUP)
    texture_word = struct.unpack_from("<I", source.data, source.texture_table)[0]
    last = source.panes[-1]
    last_end = last.offset + RECORD_SIZES[last.kind]
    record = bytearray(source.data[group.offset:group.offset + RECORD_SIZES[PaneKind.GROUP]])
    names = b"".join(_padded(name) for name in textures)
    texture_table = HEADER.size
    pane_table = texture_table + 8 * len(textures) + len(names)
    name_at = pane_table + 8 + len(record)
    tail = name_at + len(_padded(GROUP))
    struct.pack_into("<III3f", record, 0, name_hash(GROUP), name_at, RECORD_SIZES[PaneKind.GROUP], 0.0, 0.0, 0.0)
    record[-8:] = source.data[last_end - 8:last_end]          # the end of the pane table
    out = bytearray(HEADER.pack(MAGIC, VERSION, 1, len(textures), 0, 0, 0, 0, 0, texture_table, pane_table, tail))
    at = texture_table + 8 * len(textures)
    for name in textures:
        out += struct.pack("<II", texture_word, at)
        at += len(_padded(name))
    out += names + struct.pack("<II", PaneKind.GROUP, 0) + record + _padded(GROUP) + bytes(4)
    return parse_lyt(bytes(out))


def _templates(source: Layout):
    found = []
    for name, kind in ((TEMPLATE_GROUP, PaneKind.GROUP), (TEMPLATE_NULL, PaneKind.NULL),
                       (TEMPLATE_ICON, PaneKind.SPRITE), (TEMPLATE_TEXT, PaneKind.TEXT)):
        try:
            pane = source.find(name)
        except KeyError:
            raise RadialDrawError(f"ui205 has no pane {name}") from None
        if pane.kind != kind:
            raise RadialDrawError(f"{name} is not a {kind.name.lower()}")
        found.append(pane)
    return found


def _node_count(layout: Layout) -> None:
    """The header's null count as the loader takes it: a node for each null and one for each text's holder."""
    struct.pack_into("<I", layout.data, 0x10, sum(1 for p in layout.panes if p.kind in (PaneKind.NULL, PaneKind.TEXT)))


def build_layout(selector: bytes, settings: Mapping | None = None, cells: Mapping | None = None) -> bytes:
    """Our layout, its records copied from the item selector's layout `selector` (ui205) of one language."""
    settings = settings or load_draw_settings()
    source = parse_lyt(selector)
    templates = _templates(source)
    layout = _skeleton(source, [source.textures[templates[2].texture], TEXTURE])
    _add_wheel(layout, GROUP, templates, settings, cells or atlas(), icon_texture=0, art_texture=1)
    _node_count(layout)
    return layout.to_bytes()


def build_menu_layout(menu: bytes, selector: bytes, settings: Mapping | None = None,
                      cells: Mapping | None = None) -> bytes:
    """ui020 (`menu`, the START menu's lists of one language) with the wheel's tree, the same as our quest layout's,
    as the last child of the big list's frame group MENU_GROUP (in front of the frame), its root hidden at load (other
    screens show that group): the records copied from that language's item selector `selector` (ui205), the pictures
    on ui020's own entry of the item sheet (the selector's texture is the same file), the art as MENU_TEXTURE. A ui020
    that has the wheel is returned as it is."""
    layout = parse_lyt(menu)
    if any(pane.name == ROOT for pane in layout.panes):
        return menu
    if not any(group.name == MENU_GROUP for group in layout.roots):
        raise RadialDrawError(f"the layout has no group {MENU_GROUP}")
    source = parse_lyt(selector)
    templates = _templates(source)
    icon_texture = layout.add_texture(source.textures[templates[2].texture])
    art_texture = layout.add_texture(MENU_TEXTURE)
    _add_wheel(layout, MENU_GROUP, templates, settings or load_draw_settings(), cells or atlas(), icon_texture,
               art_texture, visible=False)
    _node_count(layout)
    return layout.to_bytes()


def _add_wheel(layout: Layout, parent: str, templates, settings: Mapping, cells: Mapping, icon_texture: int,
               art_texture: int, visible: bool = True) -> None:
    """The wheel's tree, the root null ROOT and its children (root_children), added as the last child of the pane
    `parent`: copies of the selector's records (`templates`: its group, null, item picture and text), the pictures and
    craft marks on texture `icon_texture` (the item sheet), the rest on `art_texture`; the root shown at load with
    `visible`."""
    _group_t, null_t, icon_t, text_t = templates
    colours, art = settings["colours"], cells["cells"]
    white = (255, 255, 255, 255)

    def null(parent: str, name: str, at: tuple[float, float], visible: bool = True) -> None:
        pane = layout.insert_null(layout.find(parent), null_t, name, to_layout(*at), visible=visible)
        pane.scale = (1.0, 1.0)
        layout.data[pane.offset + 0x20:pane.offset + 0x24] = bytes(white)       # its tint: none

    def sprite(name: str, at: tuple[float, float], size: tuple[float, float], area, colour, visible: bool = True,
               template=None, texture_index: int = art_texture) -> None:
        pane = layout.insert_sprite(layout.find(ROOT), template or icon_t, name, to_layout(*at), region=area,
                                    texture=texture_index)
        pane.size, pane.origin, pane.scale, pane.visible = size, CENTRED, (1.0, 1.0), visible
        pane.colors = [colour] * 4

    def text(parent: str, name: str, size: tuple[float, float], font: tuple[float, float], align: int, colour) -> None:
        pane = layout.insert_text(layout.find(parent), text_t, name, (0.0, 0.0), size, " " * settings["name_room"])
        pane.font_size, pane.text_align, pane.text_origin = font, align, CENTRED
        pane.text_outline = settings["name_outline"]
        pane.colors = [colour] * 3 + [pane.colors[3]]

    null(parent, ROOT, (0.0, 0.0), visible=visible)
    # the ring: a quarter cell drawn for the top right, mirrored for the others
    side = art["ring"][2] * settings["radius"] / cells["ring_radius"]
    for quarter, (across, down) in enumerate(QUARTER_SIGNS):
        sprite(ring_name(quarter), (across * side / 2, down * side / 2), (side, side),
               region(art["ring"], across < 0, down > 0, cells), colours["ring"])
    points = [slot_point(k, settings["radius"]) for k in range(SLOTS)]
    for k in range(SLOTS):
        sprite(fill_name(k), points[k], settings["rhombus"], region(art["fill"], cells=cells), colours["fill"])
        sprite(edge_name(k), points[k], settings["rhombus"], region(art["edge"], cells=cells), colours["edge"])
    marked = tuple(v * settings["marked_scale"] for v in settings["rhombus"])
    sprite(HALO, points[0], settings["halo"], region(art["halo"], cells=cells), colours["halo"], visible=False)
    sprite(GOLD_FILL, points[0], marked, region(art["fill"], cells=cells), colours["gold_fill"], visible=False)
    sprite(GOLD_EDGE, points[0], marked, region(art["edge"], cells=cells), colours["gold_edge"], visible=False)
    for k in range(SLOTS):
        sprite(icon_name(k), points[k], settings["icon"], icon_t.region, white, template=icon_t,
               texture_index=icon_texture)
    place_x, place_y = settings["count_place"]
    for k in range(SLOTS):
        units = (points[k][0] + place_x, points[k][1] + place_y)
        for name, at in ((tens_name(k), (units[0] - settings["count_advance"], units[1])), (units_name(k), units)):
            sprite(name, at, settings["count_size"], region(cells["digits"][0], cells=cells), colours["count"],
                   visible=False)
    mark_size, (mark_x, mark_y) = settings["craft_mark"][:2], settings["craft_mark"][2:]
    for k in range(SLOTS):
        sprite(mark_name(k), (points[k][0] + mark_x, points[k][1] + mark_y), mark_size, sheet_region(CRAFT_CELL),
               colours["craft"], visible=False, template=icon_t, texture_index=icon_texture)
    sprite(HUB, (0.0, 0.0), settings["hub"], region(art["hub"], cells=cells), colours["hub"])
    sizes, middle = needle_sizes(settings), (settings["needle"][0] + settings["needle"][1]) / 2
    for k in range(SLOTS):
        cell, across, down = needle_of(k)
        direction = slot_point(k, middle)
        sprite(needle_name(k), direction, sizes[cell], region(art[cell], across, down, cells), colours["needle"],
               visible=False)
    for k in range(SLOTS):
        box, align = name_box(k, settings)
        null(ROOT, name_null(k), box_middle(box))
        text(name_null(k), name_text(k), settings["name_box"], settings["name_font"], align, colours["name"])
    null(ROOT, BIG, box_middle(name_box(0, settings, big=True)[0]), visible=False)
    for align, name in enumerate(BIG_TEXTS):
        text(BIG, name, settings["big_box"], settings["big_font"], align, colours["big_name"])


def patch_arc(raw: bytes, lang: str, settings: Mapping | None = None, templates: bytes | None = None) -> bytes:
    """core_quest.arc of `lang` with our picture and layout added (after its own entries; the picture first), the
    records copied from the ui205 of `templates` (the game's own core_quest.arc of `lang`; default `raw`). An ARC that
    already has them is returned as it is."""
    arc = parse_arc(raw)
    names = {entry.name for entry in arc.entries}
    entry_name = f"{lang}\\{LAYOUT_PATH}"
    if entry_name in names:
        return raw
    source = arc if templates is None else parse_arc(templates)
    selector = next((e for e in source.entries if e.type_hash == LYT_TYPE_HASH and e.name == f"{lang}\\{SELECTOR}"),
                    None)
    if selector is None:
        raise RadialDrawError(f"{QUEST_ARC} of {lang} has no {SELECTOR}")
    tex_flags = next((e.flags for e in arc.entries if e.type_hash == TEX_TYPE_HASH), selector.flags)
    if TEXTURE not in names:
        arc.entries.append(ArcEntry(TEXTURE, TEX_TYPE_HASH, texture(), tex_flags))
    arc.entries.append(ArcEntry(entry_name, LYT_TYPE_HASH, build_layout(selector.data, settings), selector.flags))
    return write_arc(arc)


def wheel_files(rom: GameFiles, files: Mapping[str, bytes] | None = None,
                settings: Mapping | None = None) -> dict[str, bytes]:
    """(RomFS path -> ARC) of each language's core_quest.arc with the wheel's picture and layout, added to the copy in
    `files` (an earlier step's) or to the game's. The records are copied from the game's own ui205, never an earlier
    step's scaled copy: the wheel has one size whatever the HUD's."""
    files, settings = files or {}, settings or load_draw_settings()
    out = {}
    for lang in LANGUAGES:
        path = f"{lang}/data/{QUEST_ARC}"
        game = rom.read(path)
        out[path] = patch_arc(files.get(path) or game, lang, settings, templates=game)
    return out


def _selector(quest: bytes, lang: str) -> bytes:
    name = f"{lang}\\{SELECTOR}"
    entry = next((e for e in parse_arc(quest).entries if e.type_hash == LYT_TYPE_HASH and e.name == name), None)
    if entry is None:
        raise RadialDrawError(f"{QUEST_ARC} of {lang} has no {SELECTOR}")
    return entry.data


def patch_common_arc(raw: bytes, lang: str, quest: bytes, settings: Mapping | None = None) -> bytes:
    """core_common.arc of `lang` with the wheel built into its ui020 (build_menu_layout) and the art as MENU_TEXTURE
    right before ui020, the records copied from the ui205 of `quest` (the game's own core_quest.arc of `lang`). The
    game loads an archive's entries in order and a layout binds its textures by path as it loads, so the art must come
    first; one placed after ui020 is moved. An ARC
    that already has them is returned as it is."""
    arc = parse_arc(raw)
    name = f"{lang}\\{MENU_LAYOUT}"
    entry = next((e for e in arc.entries if e.type_hash == LYT_TYPE_HASH and e.name == name), None)
    if entry is None:
        raise RadialDrawError(f"{COMMON_ARC} of {lang} has no {MENU_LAYOUT}")
    built = build_menu_layout(entry.data, _selector(quest, lang), settings)
    at = next(i for i, e in enumerate(arc.entries) if e is entry)
    if built == entry.data and at and arc.entries[at - 1].name == MENU_TEXTURE:
        return raw
    entry.data = built
    arc.entries = [e for e in arc.entries if not (e.name == MENU_TEXTURE and e.type_hash == TEX_TYPE_HASH)]
    flags = next((e.flags for e in arc.entries if e.type_hash == TEX_TYPE_HASH), entry.flags)
    arc.entries.insert(next(i for i, e in enumerate(arc.entries) if e is entry),
                       ArcEntry(MENU_TEXTURE, TEX_TYPE_HASH, texture(), flags))
    return write_arc(arc)


def menu_wheel_files(rom: GameFiles, files: Mapping[str, bytes] | None = None,
                     settings: Mapping | None = None) -> dict[str, bytes]:
    """(RomFS path -> ARC) of each language's core_common.arc with the wheel in the START menu's ui020 (Edit Slots),
    added to the copy in `files` (an earlier step's: the menu's ten rows) or to the game's. The records are copied
    from the game's own ui205 of that language: the menu's wheel has its own curated sizes."""
    files, settings = files or {}, settings or load_draw_settings()
    out = {}
    for lang in LANGUAGES:
        path = f"{lang}/data/{COMMON_ARC}"
        out[path] = patch_common_arc(files.get(path) or rom.read(path), lang, rom.read(f"{lang}/data/{QUEST_ARC}"),
                                     settings)
    return out


# ---- the data block

DATA = struct.Struct(f"<5I{len(root_children())}I{SLOTS}I{len(BIG_TEXTS)}I{POSITIONS * MAX_SIZES * 3}f{2 * SLOTS}f"
                     f"{2 * SLOTS}f40f f2I 2II {SLOTS}B{SLOTS}B {3 + len(MENU_BODY)}I{3 * MENU_LAYOUTS * MAX_SIZES}f")


def _rgba(colour) -> int:
    return struct.unpack("<I", bytes(colour))[0]


def draw_data(sector_to_slot: list[int], settings: Mapping | None = None, cells: Mapping | None = None) -> bytes:
    """The block `radial_draw_data` (struct draw_data in radial_draw.c): the group's name hash, its slot in the GUI
    manager, its layer and priority, the root null's hash and its children's, the names' and the big name's texts'
    hashes; the root's x, y and scale at the centre, at the right and at the bottom left for each size (wheel_places;
    the last size repeated to MAX_SIZES), each slot's middle and its big name's place in the root (floats); the
    digits' cells (u, v, w, h); the chosen slot's scale; the pool's reserve, the stick's magnitude that chooses a slot;
    the quantity's colour words (carried, not carried) and the share of its colour a picture keeps when not carried
    (of 256); the sector to slot table and each slot's big name text; then the START menu's: the hashes of ui020's
    frame group, its frame null, the frame's body sprites and the strips' null, and the root's x, y and scale (layout
    units) in Edit Slots' two layouts for each size (menu_places; the last size repeated to MAX_SIZES)."""
    settings = settings or load_draw_settings()
    cells = cells or atlas()
    if sorted(sector_to_slot) != list(range(SLOTS)):
        raise RadialDrawError(f"the sector to slot table must list each slot 0 to {SLOTS - 1} once")
    hashes = [name_hash(GROUP), INDEX, settings["layer"], settings["priority"], name_hash(ROOT),
              *(name_hash(name) for name in root_children()),
              *(name_hash(name_text(k)) for k in range(SLOTS)),
              *(name_hash(name) for name in BIG_TEXTS)]
    places = [v for sized in wheel_places(settings) for x, y, scale in [*sized, *[sized[-1]] * (MAX_SIZES - len(sized))]
              for v in (*layout_point(x, y), scale)]
    slots = [v for k in range(SLOTS) for v in to_layout(*slot_point(k, settings["radius"]))]
    bigs = [name_box(k, settings, big=True) for k in range(SLOTS)]
    big_at = [v for box, _align in bigs for v in to_layout(*box_middle(box))]
    digits = [v for cell in cells["digits"] for v in region(cell, cells=cells)]
    colours = settings["colours"]
    menu = [name_hash(name) for name in (MENU_GROUP, MENU_FRAME, *MENU_BODY, MENU_STRIPS)]
    menu_at = [v for sized in menu_places(settings)
               for x, y, scale in [*sized, *[sized[-1]] * (MAX_SIZES - len(sized))]
               for v in (*layout_point(x, y), scale)]
    data = DATA.pack(*hashes, *places, *slots, *big_at, *digits, settings["marked_scale"], settings["reserve"],
                     settings["mark_magnitude"], _rgba(colours["count"]), _rgba(colours["count_none"]),
                     round(settings["dark"] * 256), *sector_to_slot, *(align for _box, align in bigs), *menu, *menu_at)
    if len(data) != RADIAL_DRAW_DATA_SIZE:
        raise RadialDrawError(f"radial_draw_data holds {RADIAL_DRAW_DATA_SIZE} bytes, the settings make {len(data)}")
    return data


__all__ = ["ALIGN_CENTRED", "ALIGN_LEFT", "ALIGN_RIGHT", "BIG", "BIG_TEXTS", "CELLS", "CRAFT_CELL", "DATA", "GOLD_EDGE",
           "GOLD_FILL", "GROUP", "HALO", "HUB", "INDEX", "LAYOUT_PATH", "MAX_COUNT", "MAX_SIZES", "MENU_BODY",
           "MENU_FRAME", "MENU_GROUP", "MENU_LAYOUTS", "MENU_STRIPS", "MENU_TEXTURE", "PICTURE", "POSITIONS",
           "QUARTER_SIGNS", "ROOT", "RadialDrawError", "SELECTOR", "SLOTS", "TEXTURE", "atlas", "box_middle",
           "build_layout", "build_menu_layout", "draw_data", "edge_name", "fill_name", "icon_name", "layout_point",
           "load_draw_settings", "mark_name", "menu_places", "menu_wheel_files", "name_box", "name_null", "name_text",
           "needle_name", "needle_of", "needle_sizes", "patch_arc", "patch_common_arc", "region", "ring_name",
           "root_children", "sheet_region", "slot_point", "tens_name", "texture", "to_layout", "units_name",
           "wheel_bounds", "wheel_files", "wheel_places"]
