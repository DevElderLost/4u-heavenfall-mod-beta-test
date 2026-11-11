"""The forge-style screens' panes in the facility menu's layout (lyt\\lobby\\ui401, in core_lobby.arc).

Six root groups go into ui401, copies of the sprites and text panes of the forge's own layouts: ui402's materials frame
and ui034's model panel on the left, ui407's list on the right, with a row of filters over the list, its rows and
buttons, its cursor, and a key bar under it; the last group is START's camera cue, with ui006's key. The game creates
the groups hidden with the layout and no binder names them; the screens' code (layered_forge.c) finds them by the hash
of their names, shows and hides them, and moves their panes. Sprites sit directly in their group: a null per row or
button would cost the GUI's null pool, and a text pane costs one already. Every rectangle, font, colour and icon is
curated (layered_looks.json, `forge_screen`); `forge_screen_data` turns them into what the code reads (struct
forge_screen in layered.h), in the block layered_data.
"""

import struct
from collections.abc import Mapping

from core.equipment.layered.looks import STATE_WEAPONS, load_curated
from core.game.files.arc import ArcEntry, parse_arc, write_arc
from core.game.files.gui.lyt import LYT_TYPE_HASH, Layout, Pane, name_hash, parse_lyt
from core.game.files.gui.tex import TEX_TYPE_HASH

# Screen pixels from the top left corner -> layout units: x grows to the left, y upwards, from the screen's centre.
HALF_WIDTH, HALF_HEIGHT = 200, 120

GROUP_LEFT, GROUP_RIGHT, GROUP_ROWS, GROUP_KEYS, GROUP_CURSOR, GROUP_CUE = (
    "ui401_fg_left", "ui401_fg_right", "ui401_fg_rows", "ui401_fg_keys", "ui401_fg_cursor", "ui401_fg_cue")
GROUPS = (GROUP_LEFT, GROUP_RIGHT, GROUP_ROWS, GROUP_KEYS, GROUP_CURSOR, GROUP_CUE)
GROUP_DYE = "ui401_fg_dye"           # the colour window of the Armor screen (SELECT), over the list
GROUP_TEMPLATE = "ui401_koumoku00"   # any of ui401's root groups: the record the new ones copy

# The layouts the panes copy, in the language's ARCs.
FORGE_LAYOUT = "ui407"               # the list, in core_lobby
MATERIALS_LAYOUT = "ui402"           # the materials' frame, in core_lobby
FRAME_LAYOUT = "lyt\\common\\ui034"  # the model's panel, the key bar and the L and R keys, in core_common
KEY_LAYOUT = "lyt\\common\\ui006"    # the game's key hints: the START key, in core_common
PIGMENT_LAYOUT = "lyt\\lobby\\ui415"  # the item box's Armor Pigment (and the hunter's colours), in core_title

MAX_ROWS = 9
ROW_BUTTONS = (6, 6, 6, 6, 6, 1, 1, 1, 1)   # the buttons each row has panes for: the armor's on the first five rows
BUTTON_PANES = sum(ROW_BUTTONS)
assert len(ROW_BUTTONS) == MAX_ROWS
NAME_ROOM = 32                       # characters of a row's name a text pane holds
FILTER_ROOM = 16
FILTER_VALUES = (4, 3)               # the words of the rank row (low, high, G, All) and of the game row (layered.h)
HINT_ROOM = 44
COUNT_ROOM = 8                       # "999/999" and a NUL: layered_ui.counter_text
CUE_ROOM = 14                        # characters of the cue's word: the game's "Camera" and "Show Menu"

# Sprites by group: pane -> (layout, template). The rectangle of each is the curated table's.
LEFT_SPRITES = {"fg_side0": (MATERIALS_LAYOUT, "ui402_waku10_00"), "fg_side1": (MATERIALS_LAYOUT, "ui402_waku10_01"),
                "fg_naka": (MATERIALS_LAYOUT, "ui402_naka10"), "fg_model": (FRAME_LAYOUT, "ui034_ita20")}
RIGHT_SPRITES = {"fg_waku0": (FORGE_LAYOUT, "ui407_waku00_00"), "fg_waku1": (FORGE_LAYOUT, "ui407_waku00_01"),
                 "fg_waku2": (FORGE_LAYOUT, "ui407_waku00_02"), "fg_waku3": (FORGE_LAYOUT, "ui407_waku00_03"),
                 "fg_naka0": (FORGE_LAYOUT, "ui407_naka00"),
                 "fg_bar0_0": (FORGE_LAYOUT, "ui407_waku00_21"), "fg_bar0_1": (FORGE_LAYOUT, "ui407_waku00_20"),
                 "fg_bar1_0": (FORGE_LAYOUT, "ui407_waku00_21"), "fg_bar1_1": (FORGE_LAYOUT, "ui407_waku00_20")}
# The keys on the filter rows: L and R on the rank row, X (the cell of ui006's own key, below L's) on the game row.
KEY_SPRITES = {"fg_L": (FRAME_LAYOUT, "ui034_L"), "fg_R": (FRAME_LAYOUT, "ui034_R"),
               "fg_X": (KEY_LAYOUT, "ui006_key10")}
ROW_PIECES = ("ui407_list00_00", "ui407_list00_20", "ui407_list00_01")
CURSOR_ROW = ("ui407_cursor02_00", "ui407_cursor02_02", "ui407_cursor02_01")
CURSOR_BUTTON = ("ui407_cursor02_10", "ui407_cursor02_11")
SELECTED = "ui407_waku20_01"
PLATE = "ui407_shita00_00"
ICON_HOLDER = "ui407_icon_s00"       # a null of ui407 whose unnamed sprites are the list's item icons
NAME_TEXT = "ui407_m_00_00"
# The game's materials box: ui402's panes the code moves on a screen and puts back on leaving (layered_forge.c).
BOX_GROUPS = ("ui402_hituyo00", "ui402_item10", "ui402_item11", "ui402_item12", "ui402_item13")
BOX_FRAME = ("ui402_waku10_00", "ui402_waku10_01", "ui402_naka10", "ui402_ita10")
BOX_LINES = ("ui402_line10_00", "ui402_line10_01", "ui402_line10_02", "ui402_line10_03", "ui402_line10_04")
BOX_TITLE = ("ui402_m_title10", "ui402_m_title11")
BOX_ROWS = (("ui402_item_s10", "ui402_box02", "ui402_m_10_00", "ui402_m_suji10_00"),
            ("ui402_item_s11", "ui402_box03", "ui402_m_11_00", "ui402_m_suji11_00"),
            ("ui402_item_s12", "ui402_box04", "ui402_m_12_00", "ui402_m_suji12_00"))   # the price's row
KEY_BAR = "ui034_waku22_00"
KEY_TEXT = "ui034_m_90"
CUE_KEY = "ui006_key13"              # the START key of the game's "START Camera" hint
CUE_PANES = ("fg_start_bar", "fg_start", "fg_m_start")   # the plate, the key, the word
SHEET = "cmn_icon_GSM_NOMIP"         # the common icon sheet the icons are cells of
# The try-on mark is the red eye of the status sheet (the monsters' "has discovered you"): a sprite of its own per
# button, a copy of a pane that draws a cell of that texture, with the region of the sheet curated (`icons.try_on`).
EYE_TEMPLATE = "ui034_sprite_001"    # a pane of ui034 on `lyt\quest\texture\qst_icon_BM_MQ_NOMIP`
EYE_SHEET = (128, 256)               # that texture's size, to turn texels into the region's fractions
TRY_ON_WHAT = "p"

COLOUR_KEYS = ("model", "filter_chosen", "filter", "grey", "bought", "not_bought", "key_bar", "mark", "plate",
               "disabled_plate", "disabled_icon", "not_owned_icon")

# The colour window (layered_forge.c, "the colour window"): the game's own pieces of the item box's Armor Pigment.
SWATCH = "ui415_color_001"           # a colour button's square, which the game tints with the colour
SCALE_FRAME, SCALE, SCALE_POINT = "ui415_waku", "ui415_colorscale", "ui415_colorscale_cursor"
TARGETS = 6                          # the whole set, then the armor row's five pieces (layered.h DYE_TARGETS)
CHIPS = 12                           # the palette's colours (FUN_00c0e3c8)
KEY_SHEET = (256, 256)               # cmn_win00_ID, the START key's texture: its texels as the region's fractions
SELECT_PANES = ("fg_select_bar", "fg_select_l", "fg_select_m", "fg_select_r", "fg_m_select_key", "fg_m_select")


def dye_pane_names() -> list[str]:
    """The colour window's panes the code moves, in the order of layered.h's DH_* indices (all in GROUP_DYE but
    SELECT's cue, in GROUP_CUE): each target's plate, icon and swatch, the title, the chips, Default's plate and word,
    the scale's frame, scale and point, the cursor's two halves, L and R, then SELECT's cue."""
    names = [f"fg_dye_t{target}_{what}" for target in range(TARGETS) for what in ("ita", "ico", "sw")]
    names += ["fg_m_dye_title", *(f"fg_dye_c{chip}" for chip in range(CHIPS)), "fg_dye_def", "fg_m_dye_def"]
    names += ["fg_dye_waku", "fg_dye_scale", "fg_dye_point", "fg_dye_cur0", "fg_dye_cur1", "fg_dye_L", "fg_dye_R"]
    return names + list(SELECT_PANES)


def row_pane(row: int, piece: int) -> str:
    return f"fg_r{row}_{piece}"


def name_pane(row: int) -> str:
    return f"fg_m{row}"


def button_pane(row: int, button: int, what: str) -> str:
    return f"fg_b{row}_{button}_{what}"


def filter_pane(row: int, value: int) -> str:
    return f"fg_m_f{row}_{value}"


def cursor_panes() -> tuple[str, ...]:
    return ("fg_cur_00", "fg_cur_02", "fg_cur_01", "fg_cur_10", "fg_cur_11")


def to_layout(x: float, y: float) -> tuple[float, float]:
    """Layout units of the screen pixel (x, y)."""
    return float(HALF_WIDTH - x), float(HALF_HEIGHT - y)


def forge_settings(curated: Mapping | None = None) -> Mapping:
    """The curated `forge_screen`."""
    return (curated or load_curated())["forge_screen"]


def _drawn_colours(template: Pane) -> list[tuple[int, ...]]:
    """A sprite's corners as the game draws them: its own times the colours of the nulls above it, which a copy placed
    directly in a group no longer has above it."""
    colours = list(template.colors)
    parent = template.parent
    while parent is not None:
        if parent.tint is not None:
            colours = [tuple(c * t // 255 for c, t in zip(corner, parent.tint)) for corner in colours]
        parent = parent.parent
    return colours


class PaneBuilder:
    """Adds panes to one layout. A template comes from another layout of the language, so each copy takes the index of
    the same texture in ui401's table."""

    def __init__(self, layout: Layout, sources: Mapping[str, Layout]):
        self.layout = layout
        self.sources = sources

    def template(self, source: str, name: str) -> Pane:
        return self.sources[source].find(name)

    def _texture(self, template: Pane) -> int | None:
        index = template.texture
        textures = template.layout.textures
        return self.layout.add_texture(textures[index]) if index is not None and index < len(textures) else None

    def sprite(self, group: str, template: Pane, name: str, rect, colour=None, region=None) -> None:
        texture = self._texture(template)          # first: adding a texture makes earlier panes stale
        colours = _drawn_colours(template)
        pane = self.layout.insert_sprite(self.layout.find(group), template, name, to_layout(rect[0], rect[1]),
                                         region=region, texture=texture)
        pane.size = (float(rect[2]), float(rect[3]))
        pane.origin = template.origin & 0x100      # placed by its top left corner, keeping a mirrored piece mirrored
        pane.scale = (1.0, 1.0)
        pane.visible = True
        pane.colors = colours if colour is None else [(*colour, *(255,) * (4 - len(colour)))] * 4

    def text(self, group: str, template: Pane, name: str, rect, room: int, font: float,
             align: int | None = None, colour=(230, 230, 230)) -> None:
        pane = self.layout.insert_text(self.layout.find(group), template, name, to_layout(rect[0], rect[1]),
                                       (float(rect[2]), float(rect[3])), " " * room)
        pane.font_size = (float(font), float(font))
        pane.colors = [(*colour, 255)] * 3 + [pane.colors[3]]
        if align is not None:
            pane.text_align = align
        pane.text_origin = 0


def eye_region(screen: Mapping) -> tuple[float, float, float, float]:
    """The red eye's region of the status sheet, as the layout holds one: u, v, width, height, in fractions."""
    x, y, width, height = screen["icons"]["try_on"]["texels"]
    return x / EYE_SHEET[0], y / EYE_SHEET[1], width / EYE_SHEET[0], height / EYE_SHEET[1]


def _row_rect(screen: Mapping, row: int, kind: str = "armor") -> tuple[int, int]:
    rows = screen["rows"][kind]
    return rows["first_y"] + row * rows["pitch"], rows["pitch"]


def add_forge_panes(data: bytes, sources: Mapping[str, Layout], curated: Mapping | None = None) -> bytes:
    """A ui401 layout with the forge-style screens' groups (unchanged if it has them). `sources`: the language's layouts
    the panes copy (FORGE_LAYOUT, MATERIALS_LAYOUT, FRAME_LAYOUT, KEY_LAYOUT)."""
    layout = parse_lyt(data)
    if any(pane.name == GROUP_LEFT for pane in layout.panes):
        return bytes(data)
    screen = forge_settings(curated)
    panes, colours = screen["panes"], screen["colours"]
    build = PaneBuilder(layout, sources)
    template = layout.find(GROUP_TEMPLATE)
    for name in GROUPS:
        layout.insert_group(template, name)
        template = layout.find(GROUP_TEMPLATE)

    for name, (source, piece) in LEFT_SPRITES.items():
        colour = colours["model"] if name == "fg_model" else None
        build.sprite(GROUP_LEFT, build.template(source, piece), name, panes[name], colour)
    for name, (source, piece) in RIGHT_SPRITES.items():
        build.sprite(GROUP_RIGHT, build.template(source, piece), name, panes[name])

    # Behind the cursor's bar: the rows' backgrounds, with the frame.
    for row in range(MAX_ROWS):
        y, height = _row_rect(screen, row % screen["rows"]["armor"]["count"])
        for piece, name in enumerate(ROW_PIECES):
            rect = panes[f"fg_r_{piece}"]
            build.sprite(GROUP_RIGHT, build.template(FORGE_LAYOUT, name), row_pane(row, piece),
                         (rect[0], y, rect[2], height))

    # In front of it, back to front: the keys of the rank row, the chosen values, the buttons, the words.
    for name, (source, piece) in KEY_SPRITES.items():
        build.sprite(GROUP_ROWS, build.template(source, piece), name, panes[name])
    chosen = build.template(FORGE_LAYOUT, SELECTED)
    for row in range(2):
        rect = panes[filter_pane(row, 0)]
        build.sprite(GROUP_ROWS, chosen, f"fg_sel{row}", (rect[0], rect[1], rect[2], panes["fg_sel"][3]))
    plate = build.template(FORGE_LAYOUT, PLATE)
    icon = build.template(FORGE_LAYOUT, ICON_HOLDER).children[0]
    button = screen["button"]
    eye, region = build.template(FRAME_LAYOUT, EYE_TEMPLATE), eye_region(screen)
    for row, count in enumerate(ROW_BUTTONS):
        y, _ = _row_rect(screen, row % screen["rows"]["armor"]["count"])
        for k in range(count):
            x = screen["rows"]["armor"]["buttons"]["x"] + k * screen["rows"]["armor"]["buttons"]["pitch"]
            build.sprite(GROUP_ROWS, plate, button_pane(row, k, "ita"), (x, y, *button["plate"]))
            for what, spot in (("ico", button["icon"]), ("e", button["mark"])):
                build.sprite(GROUP_ROWS, icon, button_pane(row, k, what), (x + spot[0], y + spot[1], spot[2], spot[3]))
            spot = button["try_on"]       # in front of the icon and the E, in the cell's own colours
            build.sprite(GROUP_ROWS, eye, button_pane(row, k, TRY_ON_WHAT),
                         (x + spot[0], y + spot[1], spot[2], spot[3]), (255, 255, 255), region)
    words = build.template(FORGE_LAYOUT, NAME_TEXT)
    font = screen["fonts"]
    for row in range(2):
        for value in range(FILTER_VALUES[row]):
            name = filter_pane(row, value)
            build.text(GROUP_ROWS, words, name, panes[name], FILTER_ROOM, font["filter"], align=0)  # centred in its box
    name_rect = screen["rows"]["armor"]["name"]
    for row in range(MAX_ROWS):
        y, _ = _row_rect(screen, row % screen["rows"]["armor"]["count"])
        build.text(GROUP_ROWS, words, name_pane(row), (name_rect[0], y + name_rect[1], name_rect[2], name_rect[3]),
                   NAME_ROOM, font["name"])

    # The key bar, its words over it.
    build.sprite(GROUP_KEYS, build.template(FRAME_LAYOUT, KEY_BAR), "fg_keybar", panes["fg_keybar"],
                 colours["key_bar"])
    keys = build.template(FRAME_LAYOUT, KEY_TEXT)
    build.text(GROUP_KEYS, keys, "fg_m_hint", panes["fg_m_hint"], HINT_ROOM, font["hint"])
    build.text(GROUP_KEYS, keys, "fg_m_count", panes["fg_m_count"], COUNT_ROOM, font["hint"])

    # The cursor: the row's bar, and over the buttons (the top group) the button's bracket.
    y, height = _row_rect(screen, 0)
    for name, piece, rect in zip(cursor_panes()[:3], CURSOR_ROW, [panes[f"fg_r_{i}"] for i in range(3)]):
        build.sprite(GROUP_CURSOR, build.template(FORGE_LAYOUT, piece), name, (rect[0], y, rect[2], height),
                     colours["cursor_bar"])
    first, second, width, tall = button["bracket"]
    x = screen["rows"]["armor"]["buttons"]["x"]
    for name, piece, spot in zip(cursor_panes()[3:], CURSOR_BUTTON, (first, second)):
        build.sprite(GROUP_KEYS, build.template(FORGE_LAYOUT, piece), name,
                     (x + spot[0], y + spot[1], width, tall))

    # START's cue: a plate like the key bar's, the game's key on it and its word; the code moves them with the mode.
    cue = screen["cue"]["list"]
    build.sprite(GROUP_CUE, build.template(FRAME_LAYOUT, KEY_BAR), CUE_PANES[0], cue[CUE_PANES[0]], colours["key_bar"])
    build.sprite(GROUP_CUE, build.template(KEY_LAYOUT, CUE_KEY), CUE_PANES[1], cue[CUE_PANES[1]])
    build.text(GROUP_CUE, keys, CUE_PANES[2], cue[CUE_PANES[2]], CUE_ROOM, font["hint"])
    _add_select_cue(build, screen, keys)
    _add_dye_window(build, screen, words, layout)
    return layout.to_bytes()


def select_key_pieces(screen: Mapping) -> list[tuple[int, ...]]:
    """SELECT's key, which the game has no picture of: the START key's left end, a white column of it stretched, and its
    right end, so it has the START key's frame (the word is a text over it). Each piece's rectangle on the screen."""
    x, y, width, height = screen["select_cue"]["fg_select"]
    ends = screen["select_cue"]["key_ends"]
    return [(x, y, ends, height), (x + ends, y, width - 2 * ends, height), (x + width - ends, y, ends, height)]


def _select_key_regions(screen: Mapping, key: Pane) -> list[tuple[float, float, float, float]]:
    """The START key's region cut as select_key_pieces: its ends, and the column inside the left one."""
    u, v, width, height = key.region
    ends = screen["select_cue"]["key_ends"] / KEY_SHEET[0]
    column = 1 / KEY_SHEET[0]
    return [(u, v, ends, height), (u + ends - column, v, column, height), (u + width - ends, v, ends, height)]


def _add_select_cue(build: PaneBuilder, screen: Mapping, keys: Pane) -> None:
    """SELECT's cue beside START's, on the Armor list: a plate, the key and its word "Color" (the game's ItemBox)."""
    cue, colours, font = screen["select_cue"], screen["colours"], screen["fonts"]
    build.sprite(GROUP_CUE, build.template(FRAME_LAYOUT, KEY_BAR), SELECT_PANES[0], cue[SELECT_PANES[0]],
                 colours["key_bar"])
    key = build.template(KEY_LAYOUT, CUE_KEY)
    for name, rect, region in zip(SELECT_PANES[1:4], select_key_pieces(screen), _select_key_regions(screen, key)):
        build.sprite(GROUP_CUE, key, name, rect, region=region)
    build.text(GROUP_CUE, keys, SELECT_PANES[4], cue[SELECT_PANES[4]], CUE_ROOM, cue["key_font"], align=0,
               colour=tuple(cue["key_word"]))
    build.text(GROUP_CUE, keys, SELECT_PANES[5], cue[SELECT_PANES[5]], CUE_ROOM, font["hint"])


def _add_dye_window(build: PaneBuilder, screen: Mapping, words: Pane, layout: Layout) -> None:
    """The colour window's group, in front of the list's background: the targets as the armor row's buttons with a
    swatch under each, the target's name between L and R, the palette's chips, Default and the colour scale (the item
    box's own pieces, ui415), and a cursor."""
    dye, button = screen["dye"], screen["button"]
    layout.insert_group(layout.find(GROUP_TEMPLATE), GROUP_DYE)
    plate = build.template(FORGE_LAYOUT, PLATE)
    icon = build.template(FORGE_LAYOUT, ICON_HOLDER).children[0]
    swatch = build.template(PIGMENT_LAYOUT, SWATCH)
    targets = dye["targets"]
    for target in range(TARGETS):
        x, y = targets["x"] + target * targets["pitch"], targets["y"]
        spot = button["icon"]
        build.sprite(GROUP_DYE, plate, f"fg_dye_t{target}_ita", (x, y, *button["plate"]))
        build.sprite(GROUP_DYE, icon, f"fg_dye_t{target}_ico", (x + spot[0], y + spot[1], spot[2], spot[3]))
        dx, dy, width, height = dye["swatch"]
        build.sprite(GROUP_DYE, swatch, f"fg_dye_t{target}_sw", (x + dx, y + dy, width, height))
    build.text(GROUP_DYE, words, "fg_m_dye_title", dye["title"], FILTER_ROOM, screen["fonts"]["filter"], align=0)
    for chip, rect in enumerate(chip_rects(screen)):
        build.sprite(GROUP_DYE, swatch, f"fg_dye_c{chip}", rect)
    build.sprite(GROUP_DYE, plate, "fg_dye_def", dye["default"])
    build.text(GROUP_DYE, words, "fg_m_dye_def", dye["default_text"], FILTER_ROOM, screen["fonts"]["filter"], align=0)
    scale = dye["scale"]
    build.sprite(GROUP_DYE, build.template(PIGMENT_LAYOUT, SCALE_FRAME), "fg_dye_waku", scale["rect"])
    build.sprite(GROUP_DYE, build.template(PIGMENT_LAYOUT, SCALE), "fg_dye_scale", scale["rect"])
    build.sprite(GROUP_DYE, build.template(PIGMENT_LAYOUT, SCALE_POINT), "fg_dye_point",
                 point_rect(screen, scale["start"]))
    for name, piece in zip(("fg_dye_cur0", "fg_dye_cur1"), CURSOR_BUTTON):
        build.sprite(GROUP_DYE, build.template(FORGE_LAYOUT, piece), name, (targets["x"], targets["y"], 16, 20))
    for name, rect in dye["keys"].items():
        build.sprite(GROUP_DYE, build.template(*KEY_SPRITES[name.replace("_dye", "")]), name, rect)


def chip_rects(screen: Mapping) -> list[tuple[int, int, int, int]]:
    """Each chip's rectangle on the screen, in the palette's order, rows of `columns`."""
    chips = screen["dye"]["chips"]
    return [(chips["x"] + chip % chips["columns"] * chips["pitch"][0],
             chips["y"] + chip // chips["columns"] * chips["pitch"][1], *chips["size"]) for chip in range(CHIPS)]


def point_rect(screen: Mapping, point) -> tuple[int, int, int, int]:
    """The scale's cursor around the point (x, y) of the scale, as the item box centres the point's range on it."""
    scale = screen["dye"]["scale"]
    x, y, width, height = scale["rect"]
    (range_x, range_y), (cursor_w, cursor_h) = scale["range"], scale["cursor"]
    return (x + (width - range_x) // 2 + point[0] - cursor_w // 2,
            y + (height - range_y) // 2 + point[1] - cursor_h // 2,
            cursor_w, cursor_h)


def _layouts(arc_data: bytes, lang: str, names: tuple[str, ...]) -> dict[str, Layout]:
    entries = {e.name: e for e in parse_arc(arc_data).entries if e.type_hash == LYT_TYPE_HASH}
    return {name: parse_lyt(entries[f"{lang}\\{name}"].data) for name in names}


def forge_sources(arc: bytes, lang: str, common_arc: bytes, title_arc: bytes) -> dict[str, Layout]:
    """The layouts the screens' panes copy: ui407 and ui402 of the lobby's `arc`, ui034 and ui006 of the core_common.arc
    `common_arc`, ui415 of the core_title.arc `title_arc` (all of the language `lang`)."""
    sources = _layouts(common_arc, lang, (FRAME_LAYOUT, KEY_LAYOUT)) | _layouts(title_arc, lang, (PIGMENT_LAYOUT,))
    for layout in (FORGE_LAYOUT, MATERIALS_LAYOUT):
        sources[layout] = _layouts(arc, lang, (f"lyt\\lobby\\{layout}",))[f"lyt\\lobby\\{layout}"]
    return sources


def with_ui401(arc: bytes, lang: str, common_arc: bytes, title_arc: bytes, add) -> bytes:
    """`arc` with `add(ui401 bytes, sources)` in place of its ui401 of `lang` (unchanged if it has no such layout): the
    one way a feature adds groups to the facility menu's layout. Each feature's adder leaves a layout that already has
    its groups as it is, so two features (layered gear, the Rare Materials Exchange) call this in turn and the groups
    they share (add_forge_panes') exist once."""
    parsed = parse_arc(arc)
    name = f"{lang}\\lyt\\lobby\\ui401"
    entry = next((e for e in parsed.entries if e.name == name and e.type_hash == LYT_TYPE_HASH), None)
    if entry is None:
        return arc
    entry.data = add(entry.data, forge_sources(arc, lang, common_arc, title_arc))
    return write_arc(parsed)


def with_title_textures(arc: bytes, lang: str, title_arc: bytes) -> bytes:
    """`arc` with the textures its ui401 of `lang` draws from core_title.arc (ui415's, the colour window's swatches,
    scale and point), copied just before ui401. The Smithy has not loaded core_title, and a texture the layout cannot
    find draws blank; the layout finds one placed before it in its own archive. Each goes in once."""
    parsed = parse_arc(arc)
    names = [e.name for e in parsed.entries]
    ui401 = f"{lang}\\lyt\\lobby\\ui401"
    if ui401 not in names:
        return arc
    textures = set(parse_lyt(parsed.entries[names.index(ui401)].data).textures)
    wanted = [e for e in parse_arc(title_arc).entries
              if e.type_hash == TEX_TYPE_HASH and e.name in textures and e.name not in names]
    if not wanted:
        return arc
    at = names.index(ui401)
    parsed.entries[at:at] = [ArcEntry(e.name, e.type_hash, e.data, e.flags) for e in wanted]
    return write_arc(parsed)


def add_forge_screen(arc: bytes, lang: str, common_arc: bytes, title_arc: bytes,
                     curated: Mapping | None = None) -> bytes:
    """`arc` with the screens' panes in its ui401 of `lang`, if it has that layout; their pieces come from its ui407 and
    ui402, from ui034 and ui006 in the core_common.arc `common_arc` and from ui415 in the core_title.arc `title_arc` of
    that language (whose textures go into `arc`: with_title_textures)."""
    arc = with_ui401(arc, lang, common_arc, title_arc, lambda data, sources: add_forge_panes(data, sources, curated))
    return with_title_textures(arc, lang, title_arc)


# ----- what the code reads (struct forge_screen in layered.h) ---------------------------------------------------------

MODES = ("armor", "weapons", "felyne")       # layered.h: M_ARMOR, M_WEAPON, M_FELYNE
# Rows: count, pitch, first y, name's dy; name's x, width, height; buttons: count, pitch, dy, 0; x
ROWS_RECORD = struct.Struct("<4BH2B4BH2x")
RECT = struct.Struct("<4H")
HOLD_STEPS = 4             # layered.h: the steps of the cursor held up or down (frames held, rows a step)
PREVIEW_MAX = 0xFF         # struct ui's u8 count of the frames on a weapon's row
FORGE_SCREEN = struct.Struct(f"<6I6B2x4i48s64s6H4H8B4b2B2x12I6B4B14BB3x2I4B2H4i24H{2 * HOLD_STEPS}HH2x")
assert FORGE_SCREEN.size == 372


def pane_names() -> list[str]:
    """Every pane the code moves, in the order of layered.h's H_* indices: the rows' pieces, the rows' names, the
    buttons (plate, icon, mark), the chosen values, the filters' words, the cursor's pieces, the hint, the counter,
    START's cue and the buttons' try-on marks."""
    names = [row_pane(row, piece) for row in range(MAX_ROWS) for piece in range(3)]
    names += [name_pane(row) for row in range(MAX_ROWS)]
    names += [button_pane(row, k, what) for row, count in enumerate(ROW_BUTTONS) for k in range(count)
              for what in ("ita", "ico", "e")]
    names += ["fg_sel0", "fg_sel1"]
    names += [filter_pane(row, value) for row in range(2) for value in range(FILTER_VALUES[row])]
    names += list(cursor_panes())
    names += ["fg_m_hint", "fg_m_count"]
    names += CUE_PANES
    names += [button_pane(row, k, TRY_ON_WHAT) for row, count in enumerate(ROW_BUTTONS) for k in range(count)]
    return names


def pane_hashes() -> list[int]:
    """What the code searches by: the panes of `pane_names`, then the game's box (layered.h, H_BOX_*)."""
    box = [*BOX_GROUPS, *BOX_FRAME, *BOX_LINES, *BOX_TITLE, *(name for row in BOX_ROWS for name in row)]
    return [name_hash(name) for name in (*pane_names(), *box)]


def _colour(rgb) -> int:
    """A colour word as the game's panes hold it: R in the low byte, full alpha."""
    return rgb[0] | rgb[1] << 8 | rgb[2] << 16 | 0xFF000000


def _float_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def _hold_steps(screen: Mapping) -> list[int]:
    """The curated `cursor`, (frames held, rows a step) each, as HOLD_STEPS pairs with 0 for the unused."""
    return _steps(screen["cursor"], "forge_screen.cursor", 0xFFFF)


def _steps(steps, where: str, most: int) -> list[int]:
    """(frames held, units a step) pairs as HOLD_STEPS pairs with 0 for the unused; frames up to `most`."""
    frames = [step[0] for step in steps]
    if not 1 <= len(steps) <= HOLD_STEPS or any(len(step) != 2 for step in steps):
        raise ValueError(f"{where}: 1 to {HOLD_STEPS} [frames, units] pairs")
    if (frames[0] < 1 or any(b <= a for a, b in zip(frames, frames[1:])) or any(units < 1 for _, units in steps)
            or frames[-1] > most):
        raise ValueError(f"{where}: frames from 1 and growing up to {most}, at least one unit a step")
    return [value for step in steps for value in step] + [0] * (2 * (HOLD_STEPS - len(steps)))


# struct fg_dye in layered.h: the group, its priority and the chips a row; the title, Default's plate and word, the
# scale, L and R, SELECT's cue (6), START's cue on the Armor list (3); the targets, their swatch; the chips; the scale's
# point; the cursor; the steps; the messages and the key's word colour; the hashes
DYE_SCREEN = struct.Struct(f"<I2H{4 * 15}H7H6H6H4h{2 * HOLD_STEPS}H2H2xI{len(dye_pane_names())}I")
assert DYE_SCREEN.size == 200 + 4 * len(dye_pane_names())
POINT_HELD_MAX = 0xFF        # struct dye_window's u8 count of the frames a direction is held


def dye_screen_data(screen: Mapping) -> bytes:
    """The colour window's numbers and pane hashes, as struct fg_dye in layered.h (the curated `dye` and
    `select_cue`)."""
    from core.equipment.layered.texts import message_id   # texts.py imports this module
    dye, cue = screen["dye"], screen["select_cue"]
    chips, scale = dye["chips"], dye["scale"]
    start_out = any(not 0 <= value <= limit for value, limit in zip(scale["start"], scale["range"]))
    if not 1 <= chips["columns"] <= CHIPS or start_out or max(scale["range"]) > 0xFF:
        raise ValueError("forge_screen.dye: 1 to 12 chips a row, the point's range under 256 and its start in it")
    keys = [dye["keys"][name] for name in ("fg_dye_L", "fg_dye_R")]
    rects = [dye["title"], dye["default"], dye["default_text"], scale["rect"], *keys, cue[SELECT_PANES[0]],
             *select_key_pieces(screen), cue[SELECT_PANES[4]], cue[SELECT_PANES[5]],
             *(cue["start"][name] for name in CUE_PANES)]
    targets = dye["targets"]
    return DYE_SCREEN.pack(
        name_hash(GROUP_DYE), dye["priority"], chips["columns"], *(value for rect in rects for value in rect),
        targets["x"], targets["y"], targets["pitch"], *dye["swatch"],
        chips["x"], chips["y"], *chips["pitch"], *chips["size"],
        *scale["range"], *scale["start"], *scale["cursor"], *dye["bracket"],
        *_steps(scale["steps"], "forge_screen.dye.scale.steps", POINT_HELD_MAX),
        message_id("dye_keys"), message_id("select_key"), _colour(cue["key_word"]),
        *(name_hash(name) for name in dye_pane_names()))


def _preview_frames(screen: Mapping) -> int:
    frames = screen["weapon_preview_frames"]
    if not 1 <= frames <= PREVIEW_MAX:
        raise ValueError(f"forge_screen.weapon_preview_frames: 1 to {PREVIEW_MAX}")
    return frames


def forge_screen_data(curated: Mapping | None = None) -> bytes:
    """The screens' numbers and pane hashes, as struct forge_screen in layered.h: read from the curated `forge_screen`
    only."""
    screen = forge_settings(curated)
    panes = screen["panes"]
    rows = b""
    for mode in MODES:
        row, buttons = screen["rows"][mode], screen["rows"][mode]["buttons"]
        name = row["name"]
        rows += ROWS_RECORD.pack(row["count"], row["pitch"], row["first_y"], name[1], name[0], name[2], name[3],
                                 buttons["count"], buttons["pitch"], buttons["dy"], 0, buttons["x"])
    filters = b"".join(RECT.pack(*(panes[filter_pane(row, value)] if value < FILTER_VALUES[row] else (0, 0, 0, 0)))
                       for row in range(2) for value in range(max(FILTER_VALUES)))
    pieces = [panes[f"fg_r_{i}"] for i in range(3)]
    button, icons = screen["button"], screen["icons"]
    first, second, bracket_w, bracket_h = button["bracket"]
    head = FORGE_SCREEN.pack(
        *(name_hash(name) for name in GROUPS), *(screen["priority"][name] for name in GROUPS), *screen["camera"],
        rows, filters, *(piece[0] for piece in pieces), *(piece[2] for piece in pieces),
        panes["fg_bar0_0"][1], panes["fg_bar1_0"][1], panes["fg_bar0_0"][3], panes["fg_sel"][3],
        *button["plate"], *button["icon"][:2], *button["mark"][:2], *button["icon"][2:],
        *first, *second, bracket_w, bracket_h,
        *(_colour(screen["colours"][key]) for key in COLOUR_KEYS),
        *icons["armor"], *icons["felyne"], *(icons["weapons"][key] for key in STATE_WEAPONS), icons["mark"],
        _float_bits(icons["disabled"]["u"]), _float_bits(icons["disabled"]["v"]), *button["try_on"],
        screen["materials"]["cut"], screen["materials"]["price_widen"], *screen["camera_full"],
        *(value for state in ("list", "camera") for name in CUE_PANES for value in screen["cue"][state][name]),
        *_hold_steps(screen), _preview_frames(screen))
    hashes = pane_hashes()
    return head + struct.pack(f"<{len(hashes)}I", *hashes) + dye_screen_data(screen)
