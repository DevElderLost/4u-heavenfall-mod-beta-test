"""Single-screen mode, the "[X] World Map" hint on the top screen's top right corner (emulator only), layout side.

The hint is a new root group of the lobby's `ui430` layout (the world map's, loaded on the top screen): a small panel
made of the sprites of the game's own top-right row `ui013_assign_bace_Rs` (the mirror of the panel at the top left),
the button's icon (a cell of the texture `cmn_win00_ID`, the button the curated `world_map.open` names) and a text pane
for the World Map's name. The game never draws the string a layout file holds in a text pane (it fills them at run time
from its messages), so the pane holds only blank room and the executable's block fills it with the game's own name of
the language, the curated lobby message. The game creates the group, hidden, with the layout and never touches it (no
binder names it); the block (exefs/single_screen_map_hint.py) shows and hides it. Everything is curated
(single_screen.json, "world_map_hint"): the box, each part's rectangle in pixels from the box's top-left
corner, the templates (`layout:pane`, panes of the same ARC, whose textures are added to the host's table), the text's
room and font scale, the message and a `scale` that shrinks the box, every rectangle and the font together (the
rectangles stay the panel's own 116 x 17 design; the screen pixels of `right` and `top` do not scale). The group is
added after the layout is placed (hud/single_screen.py), so the placing neither scales nor moves it.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..arc import parse_arc, write_arc
from ..data.paths import CURATED_DIR
from .build import LANGUAGES, GameFiles
from .lyt import LYT_TYPE_HASH, Layout, Pane, PaneKind, parse_lyt

SETTINGS_FILE = CURATED_DIR / "single_screen.json"
SCREEN_WIDTH, SCREEN_HEIGHT = 400.0, 240.0
BUTTONS = ("X", "Y")
Rect = tuple[float, float, float, float]    # left, top, width, height, in pixels from the box's top-left corner
_KEYS = {"layout", "group", "right", "top", "size", "scale", "sprites", "icon", "text", "message"}
_SPRITE_KEYS = {"name", "template", "rect"}
_ICON_KEYS = {"template", "rect", "regions"}
_TEXT_KEYS = {"template", "rect", "font_scale", "spaces"}
_MESSAGE_KEYS = {"file", "id"}
LOBBY_FILES = 0x20         # the game's lobby message files (FUN_005a882c refuses a file from here on)
SCALE_LIMITS = (0.1, 1.0)  # a hint's `scale` only shrinks the panel the rectangles describe


def check_right(right: float, width: float, text_left: float, fail) -> float:
    """`right` (a hint's distance from the screen's right edge, pixels) is a number the panel can have: positive or zero
    leaves the box on the screen, negative pushes its end past the edge, but the
    word must still start on the screen: the text rectangle's left edge (`text_left` pixels into the box of `width`
    pixels) must lie left of x = 400. `fail(where, what)` makes the error."""
    if SCREEN_WIDTH - right - width + text_left >= SCREEN_WIDTH:
        raise fail(", right", f"a panel whose word starts on the screen (at most {width - text_left:g} pixels past it)")
    return right


def scale_rect(rect: Rect, scale: float) -> Rect:
    """`rect` (left, top, width, height) with every value times `scale`: a part of a panel drawn at that scale from the
    panel's top-left corner."""
    return rect[0] * scale, rect[1] * scale, rect[2] * scale, rect[3] * scale


@dataclass(frozen=True)
class HintSprite:
    """A sprite of the panel: the new pane is `<group>_<name>`, a copy of `template` ("layout:pane") sized `rect`."""
    name: str
    template: str
    rect: Rect


@dataclass(frozen=True)
class MapHint:
    """The curated "world_map_hint" section. The panel is designed as a box of `size` pixels (the rectangles of its
    parts are in that box) and drawn at `scale` times that (`box`) from its top-left corner, which sits `right` pixels
    from the screen's right edge (that of the drawn box) and `top` pixels from its top; `sprites` are drawn first, then
    the icon (`icon_template` showing the cell `icon_regions[button]`, u, v, width, height of the texture, 0-1) and the
    text pane (the template's font times `text_font_scale` times `scale`, `text_spaces` blank characters of room; its
    colours are the template's: a text pane's fourth colour is its shadow, which must stay dark). The block fills the
    pane with message `message_id` of the lobby message file `message_file` (the game's own, in the player's language;
    0 is Lobby_<language>). `scale` has no default in the file; 1 (the dataclass's) draws the panel as designed."""
    layout: str
    group: str
    right: float
    top: float
    size: tuple[float, float]
    sprites: tuple[HintSprite, ...]
    icon_template: str
    icon_rect: Rect
    icon_regions: Mapping[str, tuple[float, float, float, float]]
    text_template: str
    text_rect: Rect
    text_font_scale: float
    text_spaces: int
    message_file: int
    message_id: int
    scale: float = 1.0

    @property
    def box(self) -> tuple[float, float]:
        """The panel's size on the screen, pixels: `size` times `scale`."""
        return self.size[0] * self.scale, self.size[1] * self.scale

    @property
    def text_pane(self) -> str:
        """The text pane's name: the one the layout gets and the block looks up by its hash."""
        return f"{self.group}_text"


def _fail(where: str, what: str) -> ValueError:
    return ValueError(f"single_screen.json, world_map_hint{where}: {what}")


def _number(value: object, where: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        raise _fail(where, f"a number from {low} to {high}")
    return float(value)


def _name(value: object, where: str) -> str:
    if not isinstance(value, str) or not value or not value.isascii():
        raise _fail(where, "a non-empty ASCII name")
    return value


def _template(value: object, where: str) -> str:
    text = _name(value, where)
    if text.count(":") != 1 or not all(text.split(":")):
        raise _fail(where, '"layout:pane"')
    return text


def _rect(value: object, where: str, box: tuple[float, float]) -> Rect:
    if not isinstance(value, list) or len(value) != 4:
        raise _fail(where, "[left, top, width, height]")
    left, top, width, height = (_number(v, where, 0, 400) for v in value)
    if width <= 0 or height <= 0 or left + width > box[0] or top + height > box[1]:
        raise _fail(where, f"a rectangle inside the {box[0]:g} x {box[1]:g} box")
    return left, top, width, height


def _keys(record: object, wanted: set[str], where: str) -> dict:
    if not isinstance(record, dict) or set(record) != wanted:
        raise _fail(where, f"a record with {', '.join(sorted(wanted))}, nothing else")
    return record


def map_hint_settings(path: Path = SETTINGS_FILE) -> MapHint:
    """The world_map_hint section of single_screen.json, validated."""
    record = _keys(json.loads(Path(path).read_text(encoding="utf-8")).get("world_map_hint"), _KEYS, "")
    size = record["size"]
    if not isinstance(size, list) or len(size) != 2:
        raise _fail(", size", "[width, height]")
    box = (_number(size[0], ", size", 1, SCREEN_WIDTH), _number(size[1], ", size", 1, SCREEN_HEIGHT))
    sprites = []
    if not isinstance(record["sprites"], list) or not record["sprites"]:
        raise _fail(", sprites", "a list of sprites")
    for item in record["sprites"]:
        item = _keys(item, _SPRITE_KEYS, ", sprites")
        sprites.append(HintSprite(_name(item["name"], ", sprites, name"), _template(item["template"], ", sprites"),
                                  _rect(item["rect"], ", sprites, rect", box)))
    names = [s.name for s in sprites] + ["icon", "text"]
    if len(set(names)) != len(names):
        raise _fail(", sprites", "names that differ from each other and from icon and text")
    icon = _keys(record["icon"], _ICON_KEYS, ", icon")
    regions = icon["regions"]
    if not isinstance(regions, dict) or set(regions) != set(BUTTONS):
        raise _fail(", icon, regions", f"a cell for each button: {', '.join(BUTTONS)}")
    cells = {}
    for button, cell in regions.items():
        if not isinstance(cell, list) or len(cell) != 4:
            raise _fail(", icon, regions", "[u, v, width, height]")
        u, v, w, h = (_number(x, ", icon, regions", 0, 1) for x in cell)
        if u + w > 1 or v + h > 1 or not w or not h:
            raise _fail(", icon, regions", "a cell inside the texture")
        cells[button] = (u, v, w, h)
    text = _keys(record["text"], _TEXT_KEYS, ", text")
    scale = _number(text["font_scale"], ", text, font_scale", 0.1, 2)
    spaces = text["spaces"]
    if isinstance(spaces, bool) or not isinstance(spaces, int) or not 1 <= spaces <= 64:
        raise _fail(", text, spaces", "a whole number of characters from 1 to 64")
    message = _keys(record["message"], _MESSAGE_KEYS, ", message")
    file, ident = message["file"], message["id"]
    if isinstance(file, bool) or not isinstance(file, int) or not 0 <= file < LOBBY_FILES:
        raise _fail(", message, file", f"a lobby message file, 0 to {LOBBY_FILES - 1}")
    if isinstance(ident, bool) or not isinstance(ident, int) or not 0 <= ident <= 0xFFFF:
        raise _fail(", message, id", "a message number, 0 to 65535")
    hint_scale = _number(record["scale"], ", scale", *SCALE_LIMITS)
    text_rect = _rect(text["rect"], ", text, rect", box)
    right = check_right(_number(record["right"], ", right", -SCREEN_WIDTH, SCREEN_WIDTH), box[0] * hint_scale,
                        text_rect[0] * hint_scale, _fail)
    return MapHint(_name(record["layout"], ", layout"), _name(record["group"], ", group"), right,
                   _number(record["top"], ", top", 0, SCREEN_HEIGHT), box, tuple(sprites),
                   _template(icon["template"], ", icon"), _rect(icon["rect"], ", icon, rect", box), cells,
                   _template(text["template"], ", text"), text_rect,
                   scale, spaces, file, ident, hint_scale)


def _find(layouts: Mapping[str, Layout], spec: str) -> Pane:
    """The pane a "layout:pane" names, in the ARC's layouts: KeyError naming the layout or the pane that is missing."""
    layout_name, pane_name = spec.split(":")
    if layout_name not in layouts:
        raise KeyError(f"{spec}: no layout {layout_name}")
    return layouts[layout_name].find(pane_name)


def add_map_hint(layout: Layout, others: Mapping[str, Layout], hint: MapHint, button: str) -> None:
    """Add the hint's group to `layout` (the host, placed already) with the icon of `button` and a blank text pane for
    the block to fill. `others`: the ARC's layouts by name, only read (the templates' sources). Refuses a group already
    there, an unknown button and a template that does not exist, before changing anything."""
    if button not in hint.icon_regions:
        raise ValueError(f"the hint has no icon for the button {button!r}")
    if any(pane.name == hint.group for pane in layout.panes):
        raise ValueError(f"{hint.group} is already in the layout")
    scale = hint.scale
    sprites = [(f"{hint.group}_{s.name}", _find(others, s.template), scale_rect(s.rect, scale), None)
               for s in hint.sprites]
    sprites.append((f"{hint.group}_icon", _find(others, hint.icon_template), scale_rect(hint.icon_rect, scale),
                    hint.icon_regions[button]))
    text = _find(others, hint.text_template)
    if text.kind != PaneKind.TEXT or any(t.kind != PaneKind.SPRITE for _n, t, _r, _c in sprites):
        raise ValueError("the panel and the icon copy sprites, the word a text")
    textures = [layout.add_texture(t.layout.textures[t.texture]) for _n, t, _r, _c in sprites]
    group = layout.insert_group(layout.roots[0], hint.group)
    left = SCREEN_WIDTH - hint.right - hint.box[0]

    def place(rect: Rect) -> tuple[float, float]:
        """Layout units of a (scaled) rectangle's corner: x grows to the left, a pane is placed by its corner."""
        return SCREEN_WIDTH / 2 - (left + rect[0]), SCREEN_HEIGHT / 2 - (hint.top + rect[1])

    for (name, template, rect, region), texture in zip(sprites, textures):
        pane = layout.insert_sprite(group, template, name, place(rect), region, texture)
        pane.size = (rect[2], rect[3])
        pane.origin = 0
        pane.scale = (1.0, 1.0)
        pane.visible = True
        group = layout.find(hint.group)
    text_rect = scale_rect(hint.text_rect, scale)
    pane = layout.insert_text(group, text, hint.text_pane, place(text_rect), text_rect[2:], " " * hint.text_spaces)
    font = hint.text_font_scale * scale
    pane.font_size = (text.font_size[0] * font, text.font_size[1] * font)


def hint_arc(raw: bytes, hint: MapHint, button: str) -> bytes:
    """The ARC with the hint in its host layout; an ARC without the host is returned as it was."""
    arc = parse_arc(raw)
    entries = {e.name.split("\\")[-1]: e for e in arc.entries if e.type_hash == LYT_TYPE_HASH}
    if hint.layout not in entries:
        return raw
    others = {name: parse_lyt(entry.data) for name, entry in entries.items()}
    layout = parse_lyt(entries[hint.layout].data)
    add_map_hint(layout, others, hint, button)
    entries[hint.layout].data = layout.to_bytes()
    return write_arc(arc)


def map_hint_files(rom: GameFiles, files: Mapping[str, bytes] | None = None, hint: MapHint | None = None,
                   button: str | None = None) -> dict[str, bytes]:
    """(RomFS path -> ARC) of each language's core_lobby.arc with the hint: from the copy in `files` (the run's earlier
    interface files, single-screen's placed layouts included) or the game's. The curated hint and the button of
    `world_map.open` by default."""
    from ..exefs.single_screen_world_map import world_map_settings
    hint = hint or map_hint_settings()
    button = button or world_map_settings().open
    out = {}
    for language in LANGUAGES:
        path = f"{language}/data/core_lobby.arc"
        out[path] = hint_arc((files or {}).get(path) or rom.read(path), hint, button)
    return out
