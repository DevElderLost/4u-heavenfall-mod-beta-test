"""Single-screen mode, the town minimap on the top screen (emulator only),
layout side.

The town's map (the lobby's `ui422`, loaded on the touch screen) is placed for the top screen by its curated layout
setting (single_screen.json, "layouts", "ui422": hud/single_screen.py), and stays loaded on the touch screen; the
executable's block (exefs/single_screen_minimap.py) moves its groups to the top screen while the player has it on. This
module adds, to each language's core_lobby.arc:

* the state: a new root group of the map's layout (`state_group`, a hidden null in it, nothing drawn) that the game
  creates hidden with the layout and never touches (no binder names it); the block keeps the on / off state in its
  shown bit, so the minimap is off whenever the lobby's layouts load;
* the frame: nine sprites (a 9-slice: corners at 1:1, edges and middle stretched) behind the map, the first children
  of the map's group (`ui422_map`), cut from a panel of the game's own texture (the "Ayuda" window's picture panel,
  `cmn_help_ID` of core_common.arc, named from the layout like the hints name their glyphs' texture). They surround
  the placed map sprite (`around`) at the curated `border`, rounded out to whole screen pixels so the corners stay
  sharp; the frame shows, moves and hides with the map's group;
* the hint: a panel like the "[X] Map" one (hud/single_screen_hint.py), a new root group of its host layout (`ui430`,
  on the top screen) made of copies of the game's own top-right row, the button's picture and a blank text pane the
  block fills with the game's own word (a lobby message, curated), at the curated `scale` like the X hint. The glyph is
  the game's own too: a copy of the X hint's icon sprite showing the cell `region` of the texture it already has
  (`cmn_win00_ID`, where the L button is), so nothing of the mod goes into the ARC but the groups and the frame's
  panes.

* the label: the town's place name (the balloon that says "Val Habar", `ui421_midasi_mura` of the layout `ui421`, shown
  on the touch screen with the town) follows the map to the top screen. This module wraps everything under its group in
  a frame null (hud/single_screen_frames.py's), and the block's label unit (exefs/single_screen_label.py) scales that
  null and moves it to the map's top left (`at`) while the label is on the top screen, and shrinks the group's
  shop-name bar (`hide`) to nothing there.

Everything is curated (single_screen.json, "minimap"). The groups and the frame are added after the
layouts are placed, so the placing neither scales nor moves them (the frame is measured on the placed map).
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from ..arc import parse_arc, write_arc
from .build import LANGUAGES, GameFiles
from .lyt import LYT_TYPE_HASH, Layout, Pane, PaneKind, parse_lyt
from .single_screen import SETTINGS_FILE, _plain_null
from .single_screen_frames import FRAME_SUFFIX, wrap_frames
from .single_screen_hint import SCALE_LIMITS, HintSprite, Rect, check_right, scale_rect

SCREEN_WIDTH, SCREEN_HEIGHT = 400.0, 240.0
BUTTONS = ("L",)              # the buttons the block can read (exefs/single_screen_minimap.py has their bits)
MAX_GROUPS = 8                # the block's room for the groups that follow the state
LOBBY_FILES = 32              # the lobby's message files (FUN_005a882c's file, 0-31)
ARC_NAME = "core_lobby.arc"
BORDER_LIMIT = 50             # pixels a frame may reach beyond the map
SNAP = 1e-3                   # a frame edge within this of a whole pixel counts as on it (float32 layouts)
_KEYS = {"button", "layout", "groups", "state_group", "frame", "hint", "label"}
_LABEL_KEYS = {"layout", "group", "scale", "at", "hide"}
LABEL_SCALE_LIMITS = (0.3, 1.0)   # the label's scale: from a third to its own size
_FRAME_KEYS = {"group", "around", "prefix", "texture", "texture_size", "region", "slice", "border"}
_HINT_KEYS = {"layout", "group", "right", "top", "size", "scale", "sprites", "icon", "text", "message"}
# the frame's nine sprites in the order they are drawn (the middle, the edges, the corners) with their column and row
# of the 3 x 3 grid the cut makes
FRAME_PIECES = (("c", 1, 1), ("t", 1, 0), ("b", 1, 2), ("l", 0, 1), ("r", 2, 1), ("tl", 0, 0), ("tr", 2, 0),
                ("bl", 0, 2), ("br", 2, 2))
_SPRITE_KEYS = {"name", "template", "rect"}
_ICON_KEYS = {"template", "rect", "region"}
_TEXT_KEYS = {"template", "rect", "font_scale", "spaces"}
_MESSAGE_KEYS = {"file", "id"}


@dataclass(frozen=True)
class MinimapHint:
    """The panel: designed as a box of `size` pixels and drawn at `scale` times that (`box`), `right` pixels from the
    screen's right edge and `top` from its top; the `sprites` drawn first, then the icon (a copy of `icon_template`
    sized `icon_rect`, showing the cell `icon_region`, u, v, width, height 0-1, of the template's own texture) and the
    text pane (the template's font times `text_font_scale` times `scale`, `text_spaces` blank characters of room); every
    rectangle is in the designed box and scaled with it. The block fills the pane with message `message_id` of the
    lobby message file `message_file` (the game's own, in the player's language)."""
    layout: str
    group: str
    right: float
    top: float
    size: tuple[float, float]
    sprites: tuple[HintSprite, ...]
    icon_template: str
    icon_rect: Rect
    icon_region: tuple[float, float, float, float]
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


@dataclass(frozen=True)
class MinimapFrame:
    """The curated "minimap", "frame": a 9-slice of the game's own panel around the placed map. `group` (a root group
    of the map's layout) gets nine sprites named `<prefix>_<piece>` as its first children, cut from the texture
    `texture` (a name of the layout's table; `texture_size` pixels) out of its `region` (left, top, width, height,
    texels): `slice` (left, top, right, bottom, texels) is how much of each side is a corner and an edge (corners are
    drawn 1:1, pixels for texels; edges and the middle are stretched). The frame surrounds the sprite `around`
    (placed, a pane by its corner) grown by `border` (left, top, right, bottom, pixels), its edges rounded out to
    whole pixels."""
    group: str
    around: str
    prefix: str
    texture: str
    texture_size: tuple[int, int]
    region: tuple[int, int, int, int]
    slice: tuple[int, int, int, int]
    border: tuple[float, float, float, float]


@dataclass(frozen=True)
class MinimapLabel:
    """The curated "minimap", "label": the town's place name, the root group `group` of the layout `layout` (another
    layout than the map's, loaded with the town on the touch screen). While the minimap is on the block moves it to the
    top screen and draws it `scale` times its size, moved by `at` (pixels): what the touch screen draws at the screen
    position (x, y) when the group is on the top screen as it stands (the place name's balloon covers x 39-126, y 71-89
    there) goes to (`scale` x + `at`[0], `scale` y + `at`[1]). The curated `at` is from the top-left corner of the
    map's block (the game GUI arrangement: `arranged_label` adds it), so the name follows the map. `hide` is the name
    of the group's one pane that has no room on the top screen (the touch screen's shop-name bar, 154 layout units
    under the balloon, would land over the small map's bottom edge): a null directly under the group, which the unit
    shrinks to nothing there and restores below."""
    layout: str
    group: str
    scale: float
    at: tuple[float, float]
    hide: str

    @property
    def frame(self) -> str:
        """The name of the null the layout side puts under the group, the one the block scales and moves."""
        return self.group + FRAME_SUFFIX


@dataclass(frozen=True)
class Minimap:
    """The curated "minimap" section: the `button` that turns the minimap on and off, the map's `layout`, its root
    `groups` that go to the top screen while it is on (the first one's shown bit tells that the game shows the map),
    the `state_group` added to that layout, the `hint`, the `frame` around the map (none: no frame) and the place name's
    `label` (none: it stays on the touch screen)."""
    button: str
    layout: str
    groups: tuple[str, ...]
    state_group: str
    hint: MinimapHint
    frame: MinimapFrame | None = None
    label: MinimapLabel | None = None

    @property
    def follow(self) -> tuple[str, ...]:
        """The root groups the block moves to the top screen with the map: the map's, then the label's."""
        return (*self.groups, self.label.group) if self.label else self.groups


def _fail(where: str, what: str) -> ValueError:
    return ValueError(f"single_screen.json, minimap{where}: {what}")


def _number(value: object, where: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        raise _fail(where, f"a number from {low} to {high}")
    return float(value)


def _whole(value: object, where: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise _fail(where, f"a whole number from {low} to {high}")
    return value


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


def _numbers(value: object, where: str, count: int, low: float, high: float) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != count:
        raise _fail(where, f"a list of {count} numbers")
    return tuple(_number(item, where, low, high) for item in value)


def _wholes(value: object, where: str, count: int, low: int, high: int) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != count:
        raise _fail(where, f"a list of {count} whole numbers")
    return tuple(_whole(item, where, low, high) for item in value)


def _frame(record: object, groups: tuple[str, ...]) -> MinimapFrame:
    record = _keys(record, _FRAME_KEYS, ", frame")
    group = _name(record["group"], ", frame, group")
    if group not in groups:
        raise _fail(", frame, group", "one of the groups that move with the map")
    size = _wholes(record["texture_size"], ", frame, texture_size", 2, 8, 4096)
    x, y, width, height = _wholes(record["region"], ", frame, region", 4, 0, 4096)
    if not width or not height or x + width > size[0] or y + height > size[1]:
        raise _fail(", frame, region", "a rectangle inside the texture")
    left, top, right, bottom = _wholes(record["slice"], ", frame, slice", 4, 1, 4096)
    if left + right >= width or top + bottom >= height:
        raise _fail(", frame, slice", "sides that leave a middle in the region")
    border = _numbers(record["border"], ", frame, border", 4, 0, BORDER_LIMIT)
    return MinimapFrame(group, _name(record["around"], ", frame, around"), _name(record["prefix"], ", frame, prefix"),
                        _name(record["texture"], ", frame, texture"), (size[0], size[1]), (x, y, width, height),
                        (left, top, right, bottom), (border[0], border[1], border[2], border[3]))


def _label(record: object, taken: list[str]) -> MinimapLabel:
    """The label; `taken`: the names of the groups the section already holds (the label's must be another one)."""
    record = _keys(record, _LABEL_KEYS, ", label")
    group = _name(record["group"], ", label, group")
    if group in taken:
        raise _fail(", label, group", "a group that differs from the map's, the state's and the hint's")
    at = _numbers(record["at"], ", label, at", 2, -SCREEN_WIDTH, SCREEN_WIDTH)
    hide = _name(record["hide"], ", label, hide")
    if hide in (group, group + FRAME_SUFFIX):
        raise _fail(", label, hide", "a pane under the group, not the group or its frame null")
    return MinimapLabel(_name(record["layout"], ", label, layout"), group,
                        _number(record["scale"], ", label, scale", *LABEL_SCALE_LIMITS), (at[0], at[1]), hide)


def _hint(record: object) -> MinimapHint:
    record = _keys(record, _HINT_KEYS, ", hint")
    size = record["size"]
    if not isinstance(size, list) or len(size) != 2:
        raise _fail(", hint, size", "[width, height]")
    box = (_number(size[0], ", hint, size", 1, SCREEN_WIDTH), _number(size[1], ", hint, size", 1, SCREEN_HEIGHT))
    if not isinstance(record["sprites"], list) or not record["sprites"]:
        raise _fail(", hint, sprites", "a list of sprites")
    sprites = []
    for item in record["sprites"]:
        item = _keys(item, _SPRITE_KEYS, ", hint, sprites")
        sprites.append(HintSprite(_name(item["name"], ", hint, sprites, name"),
                                  _template(item["template"], ", hint, sprites"),
                                  _rect(item["rect"], ", hint, sprites, rect", box)))
    names = [s.name for s in sprites] + ["icon", "text"]
    if len(set(names)) != len(names):
        raise _fail(", hint, sprites", "names that differ from each other and from icon and text")
    icon = _keys(record["icon"], _ICON_KEYS, ", hint, icon")
    region = icon["region"]
    if not isinstance(region, list) or len(region) != 4:
        raise _fail(", hint, icon, region", "[u, v, width, height]")
    u, v, w, h = (_number(x, ", hint, icon, region", 0, 1) for x in region)
    if u + w > 1 or v + h > 1 or not w or not h:
        raise _fail(", hint, icon, region", "a region inside the texture")
    text = _keys(record["text"], _TEXT_KEYS, ", hint, text")
    message = _keys(record["message"], _MESSAGE_KEYS, ", hint, message")
    scale = _number(record["scale"], ", hint, scale", *SCALE_LIMITS)
    text_rect = _rect(text["rect"], ", hint, text, rect", box)
    right = check_right(_number(record["right"], ", hint, right", -SCREEN_WIDTH, SCREEN_WIDTH), box[0] * scale,
                        text_rect[0] * scale, lambda where, what: _fail(", hint" + where, what))
    return MinimapHint(_name(record["layout"], ", hint, layout"), _name(record["group"], ", hint, group"), right,
                       _number(record["top"], ", hint, top", 0, SCREEN_HEIGHT), box, tuple(sprites),
                       _template(icon["template"], ", hint, icon"), _rect(icon["rect"], ", hint, icon, rect", box),
                       (u, v, w, h),
                       _template(text["template"], ", hint, text"), text_rect,
                       _number(text["font_scale"], ", hint, text, font_scale", 0.1, 2),
                       _whole(text["spaces"], ", hint, text, spaces", 1, 64),
                       _whole(message["file"], ", hint, message, file", 0, LOBBY_FILES - 1),
                       _whole(message["id"], ", hint, message, id", 0, 0xFFFF), scale)


def minimap_settings(path: Path = SETTINGS_FILE) -> Minimap:
    """The minimap section of single_screen.json, validated."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    record = _keys(data.get("minimap"), _KEYS, "")
    if record["button"] not in BUTTONS:
        raise _fail(", button", f"one of {', '.join(BUTTONS)}")
    groups = record["groups"]
    if not isinstance(groups, list) or not 1 <= len(groups) <= MAX_GROUPS - 1:
        raise _fail(", groups", f"a list of 1 to {MAX_GROUPS - 1} root groups (the label's follows them)")
    groups = tuple(_name(group, ", groups") for group in groups)
    state = _name(record["state_group"], ", state_group")
    hint = _hint(record["hint"])
    names = [*groups, state, hint.group]
    if len(set(names)) != len(names):
        raise _fail("", "groups, state_group and the hint's group must all differ")
    label = _label(record["label"], names)
    return Minimap(record["button"], _name(record["layout"], ", layout"), groups, state, hint,
                   _frame(record["frame"], groups), label)


def _find(layouts: Mapping[str, Layout], spec: str) -> Pane:
    """The pane a "layout:pane" names, in the ARC's layouts: KeyError naming the layout or the pane that is missing."""
    layout_name, pane_name = spec.split(":")
    if layout_name not in layouts:
        raise KeyError(f"{spec}: no layout {layout_name}")
    return layouts[layout_name].find(pane_name)


def add_state_group(layout: Layout, minimap: Minimap) -> None:
    """Add the state group to the map's layout: an empty root group but for one hidden null (nothing to draw). Refuses
    a layout that lacks one of the curated groups or already has the state group."""
    for name in minimap.groups:
        if not any(pane.name == name and pane.kind == PaneKind.GROUP for pane in layout.roots):
            raise KeyError(f"{minimap.layout} has no root group {name}")
    if any(pane.name == minimap.state_group for pane in layout.panes):
        raise ValueError(f"{minimap.state_group} is already in the layout")
    null = next((pane for pane in layout.panes if pane.kind == PaneKind.NULL), None)
    if null is None:
        raise ValueError(f"{minimap.layout} has no null to copy")
    group = layout.insert_group(layout.roots[0], minimap.state_group)
    layout.insert_null(group, layout.find(null.name), f"{minimap.state_group}_null", (0.0, 0.0), visible=False)


def _sprite_box(pane: Pane) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) in top-screen pixels of the sprite `pane`, which is placed by its corner: its position
    through every parent (a null's scale scales what is under it), its size by its own scale and theirs."""
    x, y = pane.position
    width, height = pane.size[0] * pane.scale[0], pane.size[1] * pane.scale[1]
    parent = pane.parent
    while parent is not None:
        sx, sy = parent.scale if parent.kind == PaneKind.NULL else (1.0, 1.0)
        x, y = parent.position[0] + sx * x, parent.position[1] + sy * y
        width, height = width * sx, height * sy
        parent = parent.parent
    return (SCREEN_WIDTH / 2 - x, SCREEN_HEIGHT / 2 - y, SCREEN_WIDTH / 2 - x + abs(width),
            SCREEN_HEIGHT / 2 - y + abs(height))


def add_minimap_frame(layout: Layout, frame: MinimapFrame, scale: float = 1.0) -> None:
    """Add the frame's nine sprites to `layout` (the map's layout) as the first children of its group, around the
    sprite `frame.around`. `scale`: the scale the map is drawn at, which the frame's pixels are divided by (the game GUI
    engine draws the map's block at its arranged scale: the border and the corners keep their size on the screen, the
    corners at 1:1); at 1 the layout is placed already and the edges are rounded out to whole screen pixels. Refuses,
    before changing anything, a layout without the group or the sprite (KeyError), a map that is not a sprite placed by
    its corner, a map too small for the cut and a frame already there (ValueError)."""
    if scale <= 0:
        raise ValueError(f"the map's scale must be above 0, not {scale}")
    if not any(pane.name == frame.group for pane in layout.roots):
        raise KeyError(f"the layout has no root group {frame.group}")
    around = layout.find(frame.around)
    if around.kind != PaneKind.SPRITE or around.origin != 0:
        raise ValueError(f"{frame.around} must be a sprite placed by its corner")
    names = {piece: f"{frame.prefix}_{piece}" for piece, _c, _r in FRAME_PIECES}
    if any(pane.name in names.values() for pane in layout.panes):
        raise ValueError(f"the frame {frame.prefix} is already in the layout")
    left, top, right, bottom = _sprite_box(around)
    unit = 1.0 / scale                      # one screen pixel in the layout's units
    border = [value * unit for value in frame.border]
    if scale == 1.0:
        edges = (math.floor(left - border[0] + SNAP), math.floor(top - border[1] + SNAP),
                 math.ceil(right + border[2] - SNAP), math.ceil(bottom + border[3] - SNAP))
    else:
        edges = (left - border[0], top - border[1], right + border[2], bottom + border[3])
    sl, st, sr, sb = (value * unit for value in frame.slice)
    if edges[2] - edges[0] < sl + sr or edges[3] - edges[1] < st + sb:
        raise ValueError(f"{frame.around} is too small for a frame cut {frame.slice}")
    rx, ry, rw, rh = frame.region
    tw, th = frame.texture_size
    cl, ct, cr, cb = frame.slice
    xs = (edges[0], edges[0] + sl, edges[2] - sr, edges[2])                     # columns and rows of the grid
    ys = (edges[1], edges[1] + st, edges[3] - sb, edges[3])
    us = (rx, rx + cl, rx + rw - cr, rx + rw)                                   # the same grid in the texture
    vs = (ry, ry + ct, ry + rh - cb, ry + rh)
    texture = layout.add_texture(frame.texture)
    # each piece goes in as the group's first child, so they go in the reverse of the order they are drawn in
    for piece, column, row in reversed(FRAME_PIECES):
        group, template = layout.find(frame.group), layout.find(frame.around)      # (stale after each insertion)
        position = (SCREEN_WIDTH / 2 - xs[column] - group.position[0], SCREEN_HEIGHT / 2 - ys[row] - group.position[1])
        region = (us[column] / tw, vs[row] / th, (us[column + 1] - us[column]) / tw, (vs[row + 1] - vs[row]) / th)
        sprite = layout.insert_sprite(group, template, names[piece], position, region, texture, first=True)
        sprite.size = (xs[column + 1] - xs[column], ys[row + 1] - ys[row])
        sprite.origin = 0
        sprite.scale = (1.0, 1.0)
        sprite.colors = [(255, 255, 255, 255)] * 4
        sprite.visible = True


def add_minimap_hint(layout: Layout, others: Mapping[str, Layout], hint: MinimapHint) -> None:
    """Add the hint's group to `layout` (its host, placed already): the panel's sprites, the icon showing its cell of
    the template's own texture and a blank text pane for the block to fill. `others`: the ARC's layouts by name, only
    read (the templates' sources). Refuses a group already there and a template that does not exist, before changing
    anything."""
    if any(pane.name == hint.group for pane in layout.panes):
        raise ValueError(f"{hint.group} is already in the layout")
    scale = hint.scale
    sprites = [(f"{hint.group}_{s.name}", _find(others, s.template), scale_rect(s.rect, scale), None)
               for s in hint.sprites]
    sprites.append((f"{hint.group}_icon", _find(others, hint.icon_template), scale_rect(hint.icon_rect, scale),
                    hint.icon_region))
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


def add_label_frame(layout: Layout, label: MinimapLabel) -> str:
    """Put everything under the label's group in `layout` (the label's layout) in one frame null, `label.frame`, at
    (0, 0) and scale 1, the group's only child: nothing moves, and the block scales and moves the null (the way the
    Palico menus' frames work). Returns the null's name. Refuses a layout without the root group (KeyError), a group
    without panes under it, one without the null `label.hide` among its children and a group already wrapped
    (ValueError)."""
    group = next((g for g in layout.roots if g.name == label.group), None)
    if group is None:
        raise KeyError(f"the layout has no root group {label.group}")
    if not group.children:
        raise ValueError(f"{label.group} has no panes to carry")
    if any(pane.name == label.frame for pane in layout.panes):
        raise ValueError(f"{label.frame} is already in the layout")
    if not any(c.name == label.hide and c.kind == PaneKind.NULL for c in group.children):
        raise ValueError(f"{label.group} has no null {label.hide} among its children")
    return wrap_frames(layout, [label.group], _plain_null(parse_lyt(layout.to_bytes())))[0]


def minimap_arc(raw: bytes, minimap: Minimap, scale: float = 1.0) -> bytes:
    """The ARC with the state group and the frame in the map's layout (for a map drawn at `scale`: add_minimap_frame),
    the hint in its host and the label's group wrapped in its frame null (in its own layout, when the ARC has one). An
    ARC without the map's layout or the hint's host is returned as it was."""
    arc = parse_arc(raw)
    entries = {e.name.split("\\")[-1]: e for e in arc.entries if e.type_hash == LYT_TYPE_HASH}
    hint = minimap.hint
    if minimap.layout not in entries or hint.layout not in entries:
        return raw
    others = {name: parse_lyt(entry.data) for name, entry in entries.items()}
    layout = parse_lyt(entries[minimap.layout].data)
    add_state_group(layout, minimap)
    if minimap.frame is not None:
        add_minimap_frame(layout, minimap.frame, scale)
    entries[minimap.layout].data = layout.to_bytes()
    host = parse_lyt(entries[hint.layout].data) if hint.layout != minimap.layout else layout
    add_minimap_hint(host, others, hint)
    entries[hint.layout].data = host.to_bytes()
    label = minimap.label
    if label is not None and label.layout in entries:
        named = parse_lyt(entries[label.layout].data)
        add_label_frame(named, label)
        entries[label.layout].data = named.to_bytes()
    return write_arc(arc)


def arranged_scale(minimap: Minimap) -> float:
    """The scale the game GUI engine draws the map at in single-screen mode: its block's where the arrangement shows it
    (gamegui/config.py, `shown_placement`; the arrangement moves and sizes it); 1 when no block places it."""
    from ..gamegui.config import load_arrangement
    place = load_arrangement().shown_placement(minimap.groups[0])
    return place.scale if place is not None and place.scale is not None else 1.0


def arranged_label(minimap: Minimap) -> MinimapLabel | None:
    """The place name with its `at` on the top screen: the curated `at` is from the top-left corner of the map's block
    where the arrangement shows it (`shown_placement`: its x, y), so the name follows the map wherever the arrangement
    puts it; as curated when no block places the map."""
    from ..gamegui.config import load_arrangement
    label = minimap.label
    place = load_arrangement().shown_placement(minimap.groups[0]) if label is not None else None
    if place is None or place.x is None or place.y is None:
        return label
    return replace(label, at=(place.x + label.at[0], place.y + label.at[1]))


def minimap_files(rom: GameFiles, files: Mapping[str, bytes] | None = None,
                  minimap: Minimap | None = None, scale: float | None = None) -> dict[str, bytes]:
    """(RomFS path -> ARC) of each language's core_lobby.arc with the minimap's state group, frame and hint: from the
    copy in `files` (the run's earlier interface files, the "[X] Map" hint included) or the game's. The curated
    settings by default, the frame for the arranged map's scale (`arranged_scale`) unless `scale` is given."""
    minimap = minimap or minimap_settings()
    scale = arranged_scale(minimap) if scale is None else scale
    out = {}
    for language in LANGUAGES:
        path = f"{language}/data/{ARC_NAME}"
        out[path] = minimap_arc((files or {}).get(path) or rom.read(path), minimap, scale)
    return out
