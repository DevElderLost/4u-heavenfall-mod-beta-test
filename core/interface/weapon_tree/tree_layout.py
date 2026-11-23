"""The weapon tree's panes in the facility menu's layout (`lyt\\lobby\\ui401`, in core_lobby.arc): six root groups of
copies of the game's own sprites, created hidden with
the layout and shown by the code, which finds every pane by the hash of its name (panes.py) and moves, tints and hides
them. Sprites sit directly in their group (no null per row or cell). The window holds panes.MAX_ROWS x MAX_COLUMNS
cells; each cell has its plate, a link, the two halves of a
trunk, its icon (the 24 px one, scaled), the forge mark (a small hammer), the worn mark, the box mark and the new mark,
and each row a band; the sixth group is the small window "upgrade or craft". Nothing is drawn by us: the pieces are the
list's own frame, bars, plate, cursors, arrows and "NEW" (ui407), the icon sheet's cells (the marks shrunk from two of
them: node_marks.py), the key bar (ui034), the money window's second box beside the money (ui024) and one plain texel
(ui034's own plain panel) stretched into the links, the trunks, the thin cursor and the choice window's edge, and
tinted into the fills. Every rectangle, colour and word is curated (weapon_tree.json).
"""

import json
from collections.abc import Iterator, Mapping

from core.game.data.paths import CURATED_DIR
from core.game.files.gui.lyt import parse_lyt
from core.interface.hud.build import GameFiles
from core.interface.weapon_tree import node_marks
from core.interface.weapon_tree import panes as names
from core.interface.weapon_tree.tree_texts import LANGUAGES, MAKESHOP_ARCS, add_messages, tree_messages

SETTINGS_PATH = CURATED_DIR / "weapon_tree.json"

# The layouts and panes the copies come from (equipment.layered.menu_layout holds the layouts' names).
BAND_PIECES = ("ui407_list00_00", "ui407_list00_20", "ui407_list00_01")
FRAME_PIECES = {"wt_waku0": "ui407_waku00_00", "wt_waku1": "ui407_waku00_01", "wt_waku2": "ui407_waku00_02",
                "wt_waku3": "ui407_waku00_03", "wt_naka": "ui407_naka00", "wt_head0": "ui407_waku00_21",
                "wt_head1": "ui407_waku00_20"}
PLAIN = "ui034_ita20"                 # a panel with no texture of the game's: one colour, whatever its size
ARROW_PIECES = {"wt_arrow_l": "ui407_left00_01", "wt_arrow_r": "ui407_right00_01", "wt_arrow_u": "ui407_up01",
                "wt_arrow_d": "ui407_down01"}
NEW_MARK = "ui407_new"                # a group of ui407: its null's first sprite is the "NEW" label
CURSOR_BRACKET = ("ui407_cursor02_10", "ui407_cursor02_11")
# The money window's second box (ui024_waku01, the lobby's points box): its left end, middle and mirrored right end, and
# the texts the copies take their fonts from: its unit's (12) for the word, its number's (14 x 12, the money's) for the
# price
PRICE_PIECES = ("ui024_ita01_00", "ui024_ita01_02", "ui024_ita01_01")
COST_TEMPLATE, PRICE_TEMPLATE = "ui024_m_00", "ui024_m_suji00_01"
ICON_SHEET = (256, 512)               # cmn_icon_GSM_NOMIP's size: the cells' texels as the region's fractions
ICON_CELL = (0, 208, 24, 24)          # the sheet's 24 px icons start at v = 208 (shape 0's cell, 10 per row, pitch 24).
#                                       The game's call (FUN_00c0de18) writes a cell's corner, not its size
ICON_SHEET_NAME = "{lang}\\lyt\\common\\texture\\cmn_icon_GSM_NOMIP"      # in core_common.arc
STATUS_SHEET_NAME = "lyt\\quest\\texture\\qst_icon_BM_MQ_NOMIP"            # the same, one for every language
TURN_MASK = 0xFF00                    # the origin word's second byte: how the texture is turned in its quad


def load_settings(curated: Mapping | None = None) -> Mapping:
    """The curated `weapon_tree.json`."""
    return curated or json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


# ----- where each piece lies --------------------------------------------------------------------------------------

def node_origin(settings: Mapping, row: int, column: int) -> tuple[int, int]:
    """The top left corner of the icon of cell (row, column), in screen pixels."""
    window = settings["window"]
    return (window["origin"][0] + column * window["pitch"][0], window["origin"][1] + row * window["pitch"][1])


def piece_rect(settings: Mapping, piece: str, row: int, column: int) -> tuple[int, int, int, int]:
    """The rectangle (x, y, width, height) of a cell's piece (panes.PLATE ... panes.NEW) on the screen."""
    x, y = node_origin(settings, row, column)
    node = settings["node"]
    link, trunk = node["link"], node["trunk"]
    if piece == names.LINK:
        return x - link["length"], y + link["y"], link["length"], link["thickness"]
    if piece == names.TRUNK:                  # from the cell's top to the link's lower edge
        middle = link["y"] + link["thickness"]
        return x + trunk["x"], y + trunk["top"], trunk["thickness"], middle - trunk["top"]
    if piece == names.TRUNK_LOW:              # from the link's upper edge to the cell's bottom
        return x + trunk["x"], y + link["y"], trunk["thickness"], trunk["bottom"] - link["y"]
    key = {names.PLATE: "plate", names.ICON: "icon", names.FORGE: "forge", names.WORN: "worn", names.BOX: "box",
           names.ELEMENT: "element", names.NEW: "new"}[piece]
    dx, dy, width, height = node[key]
    return x + dx, y + dy, width, height


def band_rect(settings: Mapping, row: int, piece: int) -> tuple[int, int, int, int]:
    """A row's band piece: the list's row bar's left part, middle and right part, 18 px high."""
    x, _, width, height = settings["panes"][f"wt_band_{piece}"]
    return x, settings["band"]["first_y"] + row * settings["band"]["pitch"], width, height


def choice_row_rect(settings: Mapping, option: int, piece: int) -> tuple[int, int, int, int]:
    """A piece of an option's row bar in the window "upgrade or craft" (and of the cursor bar over it)."""
    x, _, width, height = settings["panes"][f"wt_ch_row_{piece}"]
    return x, settings["choice"]["first_y"] + option * settings["choice"]["pitch"], width, height


def choice_word_rect(settings: Mapping, option: int) -> tuple[int, int, int, int]:
    """An option's word, over its row bar."""
    x, dy, width, height = settings["choice"]["word"]
    return x, settings["choice"]["first_y"] + option * settings["choice"]["pitch"] + dy, width, height


def _sheet_region(texels) -> tuple[float, float, float, float]:
    x, y, width, height = texels
    return x / ICON_SHEET[0], y / ICON_SHEET[1], width / ICON_SHEET[0], height / ICON_SHEET[1]


def worn_region(settings: Mapping) -> tuple[float, float, float, float]:
    """The E's region of the icon sheet: icon 90's lower right corner, cut to its letter (u, v, width, height)."""
    return _sheet_region(settings["node"]["worn_texels"])


def cursor_rects(settings: Mapping, row: int, column: int) -> dict[str, tuple[int, int, int, int]]:
    """The cursor's panes around cell (row, column): the bracket's two halves and the thin frame's four sides."""
    x, y = node_origin(settings, row, column)
    first, second, width, height = settings["cursor"]["bracket"]
    icon = settings["node"]["icon"]
    pad, thick = settings["cursor"]["frame"]["pad"], settings["cursor"]["frame"]["thickness"]
    left, top = x + icon[0] - pad, y + icon[1] - pad
    wide, tall = icon[2] + 2 * pad, icon[3] + 2 * pad
    rects = {names.CURSOR_BRACKET[0]: (x + first[0], y + first[1], width, height),
             names.CURSOR_BRACKET[1]: (x + second[0], y + second[1], width, height)}
    sides = ((left, top, wide, thick), (left, top + tall - thick, wide, thick), (left, top, thick, tall),
             (left + wide - thick, top, thick, tall))
    return {**rects, **dict(zip(names.CURSOR_FRAME, sides))}


# ----- the panes --------------------------------------------------------------------------------------------------

def _rect(settings: Mapping, name: str) -> tuple[int, int, int, int]:
    return tuple(settings["panes"][name])


def _mark_sprite(layout, group: str, template, name: str, rect, colour, texture: int, region) -> None:
    """A sprite like `PaneBuilder.sprite`'s, drawing texture index `texture` of ui401's table (our own: the marks')
    instead of the template's."""
    from core.equipment.layered.menu_layout import to_layout
    pane = layout.insert_sprite(layout.find(group), template, name, to_layout(rect[0], rect[1]), region=region,
                                texture=texture)
    pane.size = (float(rect[2]), float(rect[3]))
    pane.origin = template.origin & 0x100
    pane.scale = (1.0, 1.0)
    pane.visible = True
    pane.colors = [(*colour, *(255,) * (4 - len(colour)))] * 4


def add_tree_panes(data: bytes, sources: Mapping, curated: Mapping | None = None) -> bytes:
    """A ui401 layout with the weapon tree's five groups (unchanged if it has them). `sources`: the language's layouts
    the panes copy (equipment.layered.menu_layout.forge_sources: ui407 and ui034 are the ones used)."""
    from core.equipment.layered.menu_layout import (   # not at import: the equipment package is large
        CURSOR_ROW, FORGE_LAYOUT, FRAME_LAYOUT, GROUP_TEMPLATE, ICON_HOLDER, KEY_BAR, KEY_TEXT, MONEY_LAYOUT, NAME_TEXT,
        PLATE, PaneBuilder,
    )
    layout = parse_lyt(data)
    if any(pane.name == names.GROUP_FRAME for pane in layout.panes):
        return bytes(data)
    settings = load_settings(curated)
    colours, fonts, rooms = settings["colours"], settings["fonts"], settings["rooms"]
    marks = settings["node"]["marks"]
    mark_texture = layout.add_texture(node_marks.TEXTURE)    # first: adding a texture makes earlier panes stale
    build = PaneBuilder(layout, sources)
    template = layout.find(GROUP_TEMPLATE)
    for name in names.GROUPS:
        layout.insert_group(template, name)
        template = layout.find(GROUP_TEMPLATE)

    forge = lambda piece: build.template(FORGE_LAYOUT, piece)       # noqa: E731
    plain = build.template(FRAME_LAYOUT, PLAIN)

    # The frame: the list's own sides and the header's bar; the inside is the plain panel tinted (the list's own fill
    # is a black texel, which no tint changes).
    for name in names.FRAME:
        if name == "wt_naka":
            build.sprite(names.GROUP_FRAME, plain, name, _rect(settings, name), colours["fill"])
        else:
            build.sprite(names.GROUP_FRAME, forge(FRAME_PIECES[name]), name, _rect(settings, name))

    # The bands: each row's list bar in its three pieces, white and translucent (the band's colour tints the wood).
    for row in range(names.MAX_ROWS):
        for piece in range(names.BAND_PIECES):
            build.sprite(names.GROUP_ROWS, forge(BAND_PIECES[piece]), names.band_pane(row, piece),
                         band_rect(settings, row, piece), colours["band"])

    # The cells, a piece at a time so that each piece of every cell lies in front of the one before it.
    icon = forge(ICON_HOLDER).children[0]
    new = forge(NEW_MARK).children[0].children[0]      # the group's null, and its first sprite
    for piece in names.CELL_PIECES:
        for row in range(names.MAX_ROWS):
            for column in range(names.MAX_COLUMNS):
                name, rect = names.cell_pane(row, column, piece), piece_rect(settings, piece, row, column)
                if piece == names.PLATE:
                    build.sprite(names.GROUP_NODES, forge(PLATE), name, rect, colours["plate"])
                elif piece in (names.LINK, names.TRUNK, names.TRUNK_LOW):
                    build.sprite(names.GROUP_NODES, plain, name, rect, colours["link"])
                elif piece == names.ICON:
                    build.sprite(names.GROUP_NODES, icon, name, rect, region=_sheet_region(ICON_CELL))
                elif piece in (names.FORGE, names.BOX, names.ELEMENT):
                    # the element mark holds the first icon's region: the code moves it to the weapon's icon
                    mark = {names.FORGE: "forge", names.BOX: "box", names.ELEMENT: "element"}[piece]
                    picture = node_marks.ELEMENTS[0] if piece == names.ELEMENT else mark
                    _mark_sprite(layout, names.GROUP_NODES, icon, name, rect, colours[mark], mark_texture,
                                 node_marks.region(marks, picture))
                elif piece == names.WORN:
                    build.sprite(names.GROUP_NODES, icon, name, rect, colours["worn"], worn_region(settings))
                else:
                    build.sprite(names.GROUP_NODES, new, name, rect)

    # The texts: the weapon's name and the cursor's row over the header's bar, the keys under the window.
    words, keys = forge(NAME_TEXT), build.template(FRAME_LAYOUT, KEY_TEXT)
    build.text(names.GROUP_NODES, words, names.NAME_TEXT, _rect(settings, names.NAME_TEXT), rooms["name"],
               fonts["name"])
    build.text(names.GROUP_NODES, keys, names.COUNT_TEXT, _rect(settings, names.COUNT_TEXT), rooms["count"],
               fonts["count"], align=1, colour=tuple(colours["count"]))

    # The cursor: the game's bracket, and a thin frame of four plain strips (the code shows one of the two sets).
    rects = cursor_rects(settings, 0, 0)
    for name, piece in zip(names.CURSOR_BRACKET, CURSOR_BRACKET):
        build.sprite(names.GROUP_CURSOR, forge(piece), name, rects[name], colours["cursor"])
    for name in names.CURSOR_FRAME:
        build.sprite(names.GROUP_CURSOR, plain, name, rects[name], colours["cursor"])

    # The key bar with its words, and the arrows at the window's edges.
    build.sprite(names.GROUP_KEYS, build.template(FRAME_LAYOUT, KEY_BAR), names.KEY_BAR,
                 _rect(settings, names.KEY_BAR), colours["key_bar"])
    build.text(names.GROUP_KEYS, keys, names.HINT_TEXT, _rect(settings, names.HINT_TEXT), rooms["hint"], fonts["hint"],
               colour=tuple(colours["hint"]))
    for name in names.ARROWS:
        arrow = forge(ARROW_PIECES[name])
        build.sprite(names.GROUP_KEYS, arrow, name, _rect(settings, name), colours["arrow"])
        layout.find(name).origin = arrow.origin & TURN_MASK     # the quarter turns of the up and down arrows stay

    # The price beside the money: the money window's second box (its points box) copied, its own pieces in its own
    # dark red, without its icon; the word "Cost" where the icon was and the price where its number is, at the box's
    # own fonts.
    for name, piece in zip(names.PRICE_BOX, PRICE_PIECES):
        build.sprite(names.GROUP_KEYS, build.template(MONEY_LAYOUT, piece), name, _rect(settings, name))
    for name, piece, align in ((names.COST_TEXT, COST_TEMPLATE, 0), (names.PRICE_TEXT, PRICE_TEMPLATE, 1)):
        template = build.template(MONEY_LAYOUT, piece)
        key = "cost" if name == names.COST_TEXT else "price"
        build.text(names.GROUP_KEYS, template, name, _rect(settings, name), rooms[key], template.font_size[0],
                   align=align, colour=tuple(colours[key]))
        layout.find(name).font_size = template.font_size

    # The window "upgrade or craft", in front of everything: its fill and thin edge, the title's bar (the header's),
    # each option's row bar (a row's band) with the list's cursor bar over it, then the words.
    choice = settings["choice"]
    build.sprite(names.GROUP_CHOICE, plain, names.CHOICE_BACK, _rect(settings, names.CHOICE_BACK), choice["fill"])
    for name in names.CHOICE_EDGE:
        build.sprite(names.GROUP_CHOICE, plain, name, _rect(settings, name), choice["edge"])
    for name, piece in zip(names.CHOICE_HEAD, ("wt_head0", "wt_head1")):
        build.sprite(names.GROUP_CHOICE, forge(FRAME_PIECES[piece]), name, _rect(settings, name))
    for pane, pieces, colour in ((names.choice_row_pane, BAND_PIECES, choice["bar"]),
                                 (names.choice_cursor_pane, CURSOR_ROW, choice["cursor"])):
        for option in range(names.CHOICE_OPTIONS):
            for piece in range(names.BAND_PIECES):
                build.sprite(names.GROUP_CHOICE, forge(pieces[piece]), pane(option, piece),
                             choice_row_rect(settings, option, piece), colour)
    build.text(names.GROUP_CHOICE, words, names.CHOICE_TITLE, _rect(settings, names.CHOICE_TITLE),
               rooms["choice_title"], fonts["choice"])
    for option in range(names.CHOICE_OPTIONS):
        build.text(names.GROUP_CHOICE, words, names.choice_word_pane(option), choice_word_rect(settings, option),
                   rooms["choice_word"], fonts["choice"], colour=tuple(colours["choice_on"]))
    return layout.to_bytes()


def with_mark_texture(arc: bytes, texture: bytes, lang: str) -> bytes:
    """`arc` with the marks' texture just before its ui401 (the Smithy draws only the textures loaded before the
    layout: with_title_textures); unchanged when it is there already or the archive has no ui401."""
    from core.game.files.arc import ArcEntry, parse_arc, write_arc
    from core.game.files.gui.tex import TEX_TYPE_HASH
    parsed = parse_arc(arc)
    entry_names = [entry.name for entry in parsed.entries]
    ui401 = f"{lang}\\lyt\\lobby\\ui401"
    if node_marks.TEXTURE in entry_names or ui401 not in entry_names:
        return arc
    flags = next(entry.flags for entry in parsed.entries if entry.type_hash == TEX_TYPE_HASH)
    parsed.entries.insert(entry_names.index(ui401), ArcEntry(node_marks.TEXTURE, TEX_TYPE_HASH, texture, flags))
    return write_arc(parsed)


def mark_texture_of(common_arc: bytes, lang: str, curated: Mapping | None = None) -> bytes:
    """The marks' texture, made from the icon sheet and the quest HUD's status sheet of `lang`'s core_common.arc
    (node_marks.py)."""
    from core.game.files.arc import parse_arc
    from core.game.files.gui.tex import parse_tex
    wanted = {node_marks.ICONS: ICON_SHEET_NAME.format(lang=lang), node_marks.STATUS: STATUS_SHEET_NAME}
    entries = {entry.name: entry for entry in parse_arc(common_arc).entries}
    sheets = {key: parse_tex(entries[name].data) for key, name in wanted.items()}
    return node_marks.texture(sheets, load_settings(curated)["node"]["marks"])


def weapon_tree_files(rom: GameFiles, files: Mapping[str, bytes] | None = None) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of every language's core_lobby.arc, core_arena.arc and core_result.arc: our messages
    appended to E_makeshop in each, and the weapon tree's panes in the lobby's ui401. An ARC already in `files` (an
    earlier step's) is changed as it is, the others start from the game's. Layered Gear's texts come first when both
    are on: its `add_messages` takes only the game's own file (tree_texts.py)."""
    from core.equipment.layered.menu_layout import with_ui401
    files = files or {}
    for lang in LANGUAGES:
        common = files.get(f"{lang}/data/core_common.arc") or rom.read(f"{lang}/data/core_common.arc")
        title = files.get(f"{lang}/data/core_title.arc") or rom.read(f"{lang}/data/core_title.arc")
        messages = tree_messages(lang)
        for arc_name in MAKESHOP_ARCS:
            path = f"{lang}/data/{arc_name}"
            arc = add_messages(files.get(path) or rom.read(path), lang, messages)
            if arc_name == "core_lobby.arc":
                arc = with_ui401(arc, lang, common, title, add_tree_panes)
                arc = with_mark_texture(arc, mark_texture_of(common, lang), lang)
            yield path, arc


__all__ = ["add_tree_panes", "band_rect", "choice_row_rect", "choice_word_rect", "cursor_rects", "load_settings",
           "node_origin", "piece_rect", "weapon_tree_files", "worn_region"]
