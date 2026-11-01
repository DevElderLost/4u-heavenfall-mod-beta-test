"""Single-screen mode, the layout side (emulator only): the layouts that were on the
320x240 touch screen are loaded on the 400x240 top screen, so each one is made smaller and pushed against one edge or
corner.

The settings are curated (curated/single_screen.json, "layouts": name -> factor and anchor, and more, see
`LayoutSetting`). `place_layout` applies one to a parsed layout and the animations that move it,
in these steps (a setting without an anchor does only 0, 3 and 4):

0. wrap each `carry` pane in a null of its own (below) and make the `hide` panes (root groups, or any pane: it and all
   under it) clear (alpha 0 on their sprites and texts), so they are not measured either;

1. scale the whole layout by `factor` around the screen's centre (interface/hud/scale.py's `scale_hud` with
  `Anchor.CENTER`:
   these layouts are centred, their origin is the screen's centre), but for the `unscaled` nulls (below);
2. move the layout so the extent of what shows (`visible_extent`, measured before the scaling and then scaled) touches
   the anchor's edge (both edges for a corner; an anchor on one axis only, like LEFT, centres the other axis). The move
   is an offset on the panes right under the root groups and on their x / y animation keys, the way scale.py moves them;
   With `move` "x" or "y" the move is only along that axis: on the other the layout keeps the game's position (after
   the scaling), not centred (the Canteen's code sets its cursor's y in the layout's own coordinates); with "none" it
   is only scaled (around the centre) and `offset` places it;
3. move each `push` group alone against the same edge (only on the axes the anchor has a side on);
3b. add `offset` (dx, dy), in top-screen pixels (dx > 0 right, dy > 0 down), to the whole layout but its backdrop, on
   the same panes and animation keys step 2 moves (also with no anchor); then move each `nudge` pane alone by its
   (dx, dy), the same pixels, with its animation keys: a root group as `push` does, any other pane by its own position
   (in its parent's units: a wrapper's factor is divided out);
4. insert the `fill` sprite behind its group (a negative `margin` puts it inside the frame);
5. size each `fit` sprite to the box around some groups, grown by a margin (the world map's wood frame and its dim
   layers: the box is that of the placed layout, sprites centred by their origin read by their centre);
6. insert each `layer`: a sprite showing a whole picture (a texture the ARC does not have yet: `patch_arc` adds it, made
   from a PNG of interface/single_screen/layout/images/) right after the sprite `after`, sized to the box around some
   groups like a `fit` (the world map's sheet of paper between its wood and its map).

`pinned`: panes the game's code positions itself at run time (it resets their x / y, so a move written there is
lost). Every shift of steps 2 to 3b that would go to a pinned pane (a pane right under a root group) goes to its direct
children instead (recursively when a child is pinned too; a null's scale is divided out, so the children move by the
same pixels), with their x / y animation keys; the pinned pane keeps the game's position. The scaling is the same.

`carry`: childless panes right under a root group (texts, sprites) whose own y the game's code writes, relative to
their parent (the Canteen's four tab labels, `FUN_00a7bae4`): a shift written to the pane itself is lost, and a pinned
pane has no children to take it. Each is put, at the same place of the draw order, in a new null (`<pane>_ss`, at 0, 0,
scale 1, copied from a plain null of the layout) under the same group: the null takes the shifts and the pane keeps its
coordinates, so what the code writes lands relative to the moved null. Exact at `factor` 1 (the code's y is unscaled).

`wrap`: panes (a null with its children, a sprite or a text) right under a root group whose own position the game's
code writes in the file's own units (the character creation's cursors, which step by fixed amounts from the position
they captured). Each is put, at the same place of the draw order, in a new null (`<pane>_ss`, as `carry`'s) that takes
the factor as its scale and every shift the placing gives the pane; the pane and what is under it keep the file's
coordinates and size, so what the code writes lands on the scaled layout, exact at any factor. The wrapper is an
`unscaled` null for the scaling (below). A null whose subtree reaches the loader's last level (`lyt.MAX_DEPTH`) gets
no wrapper (it would push its deepest pane to a level the game's loader cannot hold): it is itself an `unscaled` null,
so only what the code writes to its own position stays in the file's units.

`unscaled`: nulls under which the game's code writes positions in the layout's own (unscaled) units, e.g. the quest
preview's icon row (x of the icons and their frames, by monster count) and its stack of notes (y). Step 1 leaves
everything under such a null as the file has it and gives the null the factor as its scale (times its own): the
engine multiplies its children's positions and sizes by it, so the layout looks the same and what the code writes is
scaled with it. Needs the anchor (the factor); tracks of the panes under the null are left alone; the null may not be
animated in scale, be a root group nor sit inside another `unscaled` null.

`fit`: sprites that must cover a window instead of the touch screen (the world map, `ui430`: its wood is a 320 x 240
board and its two `kuro` dim layers are 320 x 240 too). After everything above, each is sized and placed (its scale 1,
its origin the corner, whatever the nulls above it scale and move) to cover the box `visible_extent(by_origin=True)`
measures around the named root groups, grown by `margin` (a number or [mx, my]). A `fit` pane may not be in the
groups it is fitted to. Other sprites of the same board are cleared with `hide`.

`layers`: a picture added to a layout (`Layer`): after the `fit`s, a sprite (named `ss_<image>`) showing the whole of a
texture is inserted in the draw order right after the sprite `after` (a copy of it, white), and sized and placed as a
`fit` over the groups `over` grown by `margin`. The texture is named by the settings' `images` (curated "images":
png, texture name) and is made from the PNG, RGBA4444, into each ARC that holds the layout (`patch_arc`; the layout's
texture table gets the name, the game finds the file by it in the same ARC).

The fill: `margin` is one number or [mx, my]; `region` [u, v, w, h] (0-1) is the part of the template's texture it
shows; `template` may be "otherlayout:sprite", a sprite of another layout of the same ARC (`patch_arc` hands those
over, read-only, as `others`): the fill then uses that sprite's texture, added to this layout's texture table (the
game finds it by name, the same ARC) when it is not there.

Coordinates are the layout's own: the origin at the screen's centre and both axes reversed (`screen = (200 - x,
120 - y)` on the top screen), so the screen's left edge is x = +200 and its top y = +120,
as `Anchor.point` has it. The extent assumes what the touch layouts do: a sprite or text is placed by its screen
top-left corner, so it covers x - width .. x and y - height .. y; a null's scale scales its children's positions and
sizes. Hidden sprites and nulls (and the children of a hidden null), sprites whose four corners are transparent and
the touch areas (boundaries) do not count, and each box is cut to the top screen (+-200 x +-120): the rows and
decorations the code places elsewhere, outside the screen, must not decide where the layout ends. A pane that the
game's code shows later is therefore not measured; nor a text whose four colours are transparent.

A layout's own backdrop (`backdrop`: a root group, such as ui409's wooden board, 320 x 240) is left out of both steps
and stretched instead over the whole top screen, where the game showed through on both sides of it (what shows of it
on the touch screen, 320 x 240, decides the stretch: a decoration sticking out does not count). Its priority
stays the game's (`priority_offsets`): the top screen's own panels are drawn over it, and the layout's other groups,
with the setting's `priority` (or their `group_priority`) added by the executable's block
(interface/single_screen/executable/single_screen.py), in front of them.

`fixed`: root groups left exactly as the file has them, like the backdrop but not stretched: not scaled, not measured
for the layout's edge, not moved by the push or the `offset`, and no `priority` of the layout. The DLC scene's top
layouts (`ui520`, `ui540`) are on the top screen already: their wooden frame and cats stay and only the info panel is
made smaller to leave room for the menu that joins it.
"""

import json
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from core.game.files.arc import ArcEntry, parse_arc, write_arc
from core.game.data.paths import CURATED_DIR
from core.interface.hud.build import LANGUAGES, GameFiles
from core.game.files.gui.lanl import LANL_TYPE_HASH, Animations, Property, parse_lanl
from core.game.files.gui.lyt import CONTAINERS, LYT_TYPE_HASH, MAX_DEPTH, Layout, Pane, PaneKind, name_hash, parse_lyt
from core.game.files.gui.png import read_png
from core.interface.hud.scale import SCREEN_HALF_HEIGHT, SCREEN_HALF_WIDTH, Anchor, anchor_all, scale_hud
from core.interface.single_screen.layout.single_screen_frames import Frames, frame_settings, wrap_frames
from core.game.files.gui.tex import RGBA4444, TEX_TYPE_HASH, new_tex

SETTINGS_FILE = CURATED_DIR / "single_screen.json"
# the PNGs of the layers' pictures (interface/single_screen/layout/images/)
IMAGES_DIR = (Path(__file__).resolve().parent / "images")
LAYER_PREFIX = "ss_"     # the name of a layer's sprite is this and the image's name
# The ARCs holding the layouts the mode moves, under <language>/data/: the core ARCs
# (the DLC's and the arena's among them), and the stages' (the quest boards' maps; the Camaradas' rooms, the Caldero de
# fusion: "Facilities on the top screen"), the Meownster Hunters' scene's (monnyan_core.arc: its black bands, "The black
# bands"), the Wyceum's (v05a00_map.arc: ui455 and ui456, which only the game GUI engine places); a stage ARC of
# STAGE_LAYOUTS places only the curated layouts it names (the rooms
# hold the Camaradas' board, ui480 / ui481, and the Palico menus', ui470 / ui471 and the clothes chooser ui415, which
# the creation's binder table puts on the top screen there too: it takes the title's setting, "The Palico menus")
ARCS = ("core_lobby.arc", "core_common.arc", "core_title.arc", "core_dlc.arc", "core_arena.arc",
        "v00a00_map.arc", "v05a01_map.arc", "v05a02_map.arc", "v00a01_map.arc", "v03a01_map.arc", "v04a00_map.arc",
        "v05a00_map.arc", "monnyan_core.arc")
# The weapon guide's pages (ui230 - ui243, one layout each) come in the 17 weapon archives, under <language>/data/;
# only the game GUI engine places them (interface/game_gui/build.py: the Guild's Weapon Controls page), so today's
# mechanism never reads them
WEAPON_ARCS = tuple(f"pl_wp{n:02d}_lyt.arc" for n in range(17))
# The loading screens with the paper characters (ui108, beside the loading picture ui103 / ui104 / ui105), under
# <language>/data/; only the game GUI engine places them
LOADING_ARCS = ("loading_5.arc", "loading_6.arc", "loading_7.arc")
STAGE_LAYOUTS = {"v00a01_map.arc": ("ui480", "ui481", "ui470", "ui471", "ui415"),
                 "v03a01_map.arc": ("ui480", "ui481", "ui470", "ui471", "ui415"),
                 "v04a00_map.arc": ("ui474",)}
FILL_NAME = "ss_fill"    # the name of the sprite a `Fill` inserts
CARRY_SUFFIX = "_ss"     # a `carry` pane's null is named after the pane
# The name keyboard's backdrop: the game's own files, per region
KEYBOARD_ARCS = ("system/swkbd/archive_eu/Common.arc", "system/swkbd/archive_us/Common.arc")
KEYBOARD_BACKDROP = ("BG", "BG_P_bg_00")     # the layout, and its window (320 x 240, centred, the keyboard's grey)
TOUCH_HALF_SIZE = (160.0, 120.0)   # the touch screen (320 x 240): what a backdrop is measured on
TOP_HALF_SIZE = (SCREEN_HALF_WIDTH, SCREEN_HALF_HEIGHT)
# (smallest x, smallest y, largest x, largest y) in layout coordinates
Extent = tuple[float, float, float, float]


@dataclass(frozen=True)
class Fill:
    """A sprite inserted as the first child of `group` (drawn behind its panes), a copy of the layout's sprite
    `template`: over the whole top screen, or over the box around the root groups `over` (once the layout is placed)
    grown by `margin`. `color`: RGBA of its four corners, else the template's."""
    group: str
    template: str
    over: tuple[str, ...] = ()
    margin: float | tuple[float, float] = 0.0   # a number, or (mx, my)
    color: tuple[int, int, int, int] | None = None
    region: tuple[float, float, float, float] | None = None   # (u, v, w, h) of the template's texture, 0-1


@dataclass(frozen=True)
class Fit:
    """The sprite `pane` of the layout, sized and placed to cover the box around what shows of the root groups `over`
    (sprites read by their centre when their origin says so), grown by `margin`, once the layout is placed."""
    pane: str
    over: tuple[str, ...]
    margin: float | tuple[float, float] = 0.0   # a number, or (mx, my)


@dataclass(frozen=True)
class Layer:
    """A picture inserted right after the sprite `after` (a copy of it, white), showing the whole of the texture
    `texture` (its name in the ARC; `png`, a file of IMAGES_DIR, is what the texture is made from), sized to the box
    around what shows of the root groups `over` grown by `margin`, as a `Fit` is. `image` names it in the curated
    "images"; the new sprite is LAYER_PREFIX + image."""
    image: str
    texture: str
    png: str
    after: str
    over: tuple[str, ...]
    margin: float | tuple[float, float] = 0.0   # a number, or (mx, my)


@dataclass(frozen=True)
class Band:
    """A new sprite, a copy of the layout's sprite `pane`, sized and placed over `box` (left, top, right, bottom:
    top-screen pixels, 0-400 by 0-240) and tinted `color` (RGBA of its four corners): a strip of one colour made from a
    sprite the layout has (opaque ones: the texture's alpha stays). `pane` itself stays as it is (`hide` clears it)."""
    pane: str
    box: tuple[float, float, float, float]
    color: tuple[int, int, int, int] = (0, 0, 0, 255)


@dataclass(frozen=True)
class LayoutSetting:
    factor: float = 1.0            # 0-1, of the layout's own size (with an anchor)
    anchor: Anchor | None = None   # the screen edge or corner the visible panes end against (never IN_PLACE); none:
    #                                the layout is not scaled nor moved (hide, fill and the priorities still apply)
    priority: int = 0              # added to the draw priority of its root groups but the backdrop
    backdrop: str | None = None    # a root group stretched over the top screen, not scaled nor moved
    group_priority: Mapping[str, int] = field(default_factory=dict)   # a group's offset replaces `priority` (0: none)
    hide: tuple[str, ...] = ()     # panes (root groups or any other) made clear (alpha 0), before it is measured
    push: tuple[str, ...] = ()     # root groups moved alone to the anchor's edge once the layout is placed
    fill: Fill | None = None
    move: str = "xy"               # the axes the anchor moves the layout on (step 2): "xy", "x", "y" or "none"
    offset: tuple[float, float] = (0.0, 0.0)   # top-screen pixels (right, down), whole layout
    nudge: Mapping[str, tuple[float, float]] = field(default_factory=dict)   # pane -> (right, down) pixels
    pinned: tuple[str, ...] = ()   # panes the game's code positions: their shifts go to their children
    carry: tuple[str, ...] = ()    # childless panes whose y the code writes: wrapped in a null that takes the shifts
    unscaled: tuple[str, ...] = ()   # nulls whose children the code positions in unscaled units: the null scales
    wrap: tuple[str, ...] = ()     # panes the code positions in the file's units: wrapped in a null with the factor
    fit: tuple[Fit, ...] = ()      # sprites sized to the box around some groups, once the layout is placed
    layers: tuple[Layer, ...] = ()  # pictures inserted after a sprite, sized to such a box (after the fits)
    fixed: tuple[str, ...] = ()    # root groups left as the file has them: not scaled, measured nor moved
    bands: tuple[Band, ...] = ()   # sprites cut to a box of the screen and tinted (after the layers)


MARGIN_LIMIT = 50      # a fill's margin goes from -MARGIN_LIMIT (inside a frame) up
OFFSET_LIMIT = 400     # offsets and nudges, in pixels, one way or the other
_KEYS = {"factor", "anchor", "priority", "backdrop", "group_priority", "hide", "push", "fill", "move", "offset",
         "nudge", "pinned", "carry", "unscaled", "wrap", "fit", "layers", "fixed", "bands"}
_FILL_KEYS = {"group", "template", "over", "margin", "color", "region"}
_FIT_KEYS = {"pane", "over", "margin"}
_LAYER_KEYS = {"image", "after", "over", "margin"}
_BAND_KEYS = {"pane", "box", "color"}
TEXTURE_NAME_LIMIT = 63     # an ARC entry's name is 64 bytes with its end
CENTRED = 4            # a sprite's origin (low byte): x, y is its centre, not its corner


def _names(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"single_screen.json, {where}: must be a list of names")
    return tuple(value)


def _whole(value: object, where: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"single_screen.json, {where}: must be a whole number of {low} to {high}")
    return value


def _pixels(value: object, where: str) -> tuple[float, float]:
    if (not isinstance(value, list) or len(value) != 2 or any(isinstance(v, bool) or not isinstance(v, int | float)
                                                              or abs(v) > OFFSET_LIMIT for v in value)):
        raise ValueError(f"single_screen.json, {where}: must be [dx, dy], two numbers of pixels "
                         f"(at most {OFFSET_LIMIT})")
    return float(value[0]), float(value[1])


def _margin(value: object, where: str) -> float | tuple[float, float]:
    """A margin: a number or [mx, my], each -MARGIN_LIMIT or more."""
    values = value if isinstance(value, list) else [value]
    if (isinstance(value, list) and len(value) != 2) or any(
            isinstance(v, bool) or not isinstance(v, int | float) or not -MARGIN_LIMIT <= v for v in values):
        raise ValueError(f"single_screen.json, {where}: margin must be a number or [mx, my], each {-MARGIN_LIMIT} "
                         f"or more")
    return tuple(float(v) for v in value) if isinstance(value, list) else float(value)


def _load_fit(records: object, name: str) -> tuple[Fit, ...]:
    where = f"{name}, fit"
    if not isinstance(records, list):
        raise ValueError(f"single_screen.json, {where}: must be a list of {{pane, over, margin}}")
    fits = []
    for record in records:
        if not isinstance(record, dict) or not {"pane", "over"} <= set(record) <= _FIT_KEYS:
            raise ValueError(f"single_screen.json, {where}: each needs pane and over, and may have margin")
        if not isinstance(record["pane"], str):
            raise ValueError(f"single_screen.json, {where}: pane must be a name")
        over = _names(record["over"], f"{where}, over")
        if not over:
            raise ValueError(f"single_screen.json, {where}: over needs at least one root group")
        fits.append(Fit(record["pane"], over, _margin(record.get("margin", 0), where)))
    return tuple(fits)


def _load_layers(records: object, name: str, images: Mapping[str, object]) -> tuple[Layer, ...]:
    where = f"{name}, layers"
    if not isinstance(records, list):
        raise ValueError(f"single_screen.json, {where}: must be a list of {{image, after, over, margin}}")
    layers = []
    for record in records:
        if not isinstance(record, dict) or not {"image", "after", "over"} <= set(record) <= _LAYER_KEYS:
            raise ValueError(f"single_screen.json, {where}: each needs image, after and over, and may have margin")
        if not isinstance(record["image"], str) or not isinstance(record["after"], str):
            raise ValueError(f"single_screen.json, {where}: image and after must be names")
        image = images.get(record["image"])
        if not isinstance(image, dict):
            raise ValueError(f"single_screen.json, {where}: no image {record['image']!r} in \"images\"")
        png, texture = image.get("png"), image.get("texture")
        if (not isinstance(png, str) or not png.endswith(".png") or "/" in png or "\\" in png
                or png.startswith(".")):
            raise ValueError(f"single_screen.json, images, {record['image']}: png must be the name of a file of "
                             f"interface/single_screen/layout/images/")
        if (not isinstance(texture, str) or not texture or not texture.isascii()
                or len(texture) > TEXTURE_NAME_LIMIT):
            raise ValueError(f"single_screen.json, images, {record['image']}: texture must be an ASCII name of "
                             f"{TEXTURE_NAME_LIMIT} characters at most")
        over = _names(record["over"], f"{where}, over")
        if not over:
            raise ValueError(f"single_screen.json, {where}: over needs at least one root group")
        layers.append(Layer(record["image"], texture, png, record["after"], over,
                            _margin(record.get("margin", 0), where)))
    return tuple(layers)


def _load_bands(records: object, name: str) -> tuple[Band, ...]:
    where = f"{name}, bands"
    if not isinstance(records, list):
        raise ValueError(f"single_screen.json, {where}: must be a list of {{pane, box, color}}")
    bands = []
    for record in records:
        if not isinstance(record, dict) or not {"pane", "box"} <= set(record) <= _BAND_KEYS:
            raise ValueError(f"single_screen.json, {where}: each needs pane and box, and may have color")
        if not isinstance(record["pane"], str):
            raise ValueError(f"single_screen.json, {where}: pane must be a name")
        box = record["box"]
        width, height = 2 * SCREEN_HALF_WIDTH, 2 * SCREEN_HALF_HEIGHT
        if (not isinstance(box, list) or len(box) != 4
                or any(isinstance(v, bool) or not isinstance(v, int | float) for v in box)
                or not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height):
            raise ValueError(f"single_screen.json, {where}: box must be [left, top, right, bottom] pixels of the "
                             f"{width:g} x {height:g} top screen, right and bottom past left and top")
        color = record.get("color", [0, 0, 0, 255])
        if not isinstance(color, list) or len(color) != 4:
            raise ValueError(f"single_screen.json, {where}: color must be 4 numbers (RGBA)")
        bands.append(Band(record["pane"], tuple(float(v) for v in box),
                          tuple(_whole(v, f"{where}, color", 0, 255) for v in color)))
    return tuple(bands)


def _load_fill(record: object, name: str) -> Fill:
    where = f"{name}, fill"
    if not isinstance(record, dict) or not {"group", "template"} <= set(record) <= _FILL_KEYS:
        raise ValueError(f"single_screen.json, {where}: needs group and template, and may have over, margin and "
                         f"color")
    for key in ("group", "template"):
        if not isinstance(record[key], str):
            raise ValueError(f"single_screen.json, {where}: {key} must be a name")
    margin = _margin(record.get("margin", 0), where)
    region = record.get("region")
    if region is not None:
        if (not isinstance(region, list) or len(region) != 4 or any(
                isinstance(v, bool) or not isinstance(v, int | float) or not 0 <= v <= 1 for v in region)
                or region[2] <= 0 or region[3] <= 0):
            raise ValueError(f"single_screen.json, {where}: region must be [u, v, w, h], numbers of 0 to 1 "
                             f"(w and h above 0)")
        region = tuple(float(v) for v in region)
    color = record.get("color")
    if color is not None:
        if not isinstance(color, list) or len(color) != 4:
            raise ValueError(f"single_screen.json, {where}: color must be 4 numbers (RGBA)")
        color = tuple(_whole(value, f"{where}, color", 0, 255) for value in color)
    return Fill(record["group"], record["template"], _names(record.get("over", []), f"{where}, over"),
                margin, color, region)


def load_layout_settings(path: Path = SETTINGS_FILE) -> dict[str, LayoutSetting]:
    """Layout name -> setting, from the file's "layouts" (its other keys are the executable side's). Raises
    ValueError for anything the code cannot use."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records, images = data["layouts"], data.get("images", {})
    if not isinstance(images, dict):
        raise ValueError("single_screen.json, images: must map names to {png, texture, ...}")
    settings = {}
    for name, record in records.items():
        if not isinstance(record, dict) or not set(record) <= _KEYS:
            raise ValueError(f"single_screen.json, {name}: must be an object with only {sorted(_KEYS)}")
        if ("factor" in record) != ("anchor" in record):
            raise ValueError(f"single_screen.json, {name}: factor and anchor go together (or neither)")
        factor, anchor = record.get("factor", 1), None
        if "factor" in record:
            if isinstance(factor, bool) or not isinstance(factor, int | float) or not 0 < factor <= 1:
                raise ValueError(f"single_screen.json, {name}: factor must be above 0 and at most 1, not {factor!r}")
            anchor = Anchor.__members__.get(str(record["anchor"]).upper())
            if anchor is None or anchor is Anchor.IN_PLACE:
                raise ValueError(f"single_screen.json, {name}: unknown anchor {record['anchor']!r}")
        priority = _whole(record.get("priority", 0), f"{name}, priority", -255, 255)
        backdrop = record.get("backdrop")
        if backdrop is not None and not isinstance(backdrop, str):
            raise ValueError(f"single_screen.json, {name}: backdrop must be a root group's name")
        group_priority = record.get("group_priority", {})
        if not isinstance(group_priority, dict):
            raise ValueError(f"single_screen.json, {name}: group_priority must map root groups to offsets")
        group_priority = {group: _whole(value, f"{name}, group_priority, {group}", -255, 255)
                          for group, value in group_priority.items()}
        push = _names(record.get("push", []), f"{name}, push")
        if push and anchor is None:
            raise ValueError(f"single_screen.json, {name}: push needs the anchor whose edge it moves to")
        fill = _load_fill(record["fill"], name) if "fill" in record else None
        move = record.get("move", "xy")
        if move not in ("xy", "x", "y", "none"):
            raise ValueError(f"single_screen.json, {name}: move must be \"xy\", \"x\", \"y\" or \"none\", "
                             f"not {move!r}")
        if move != "xy" and anchor is None:
            raise ValueError(f"single_screen.json, {name}: move needs the anchor it moves to")
        unscaled = _names(record.get("unscaled", []), f"{name}, unscaled")
        if unscaled and anchor is None:
            raise ValueError(f"single_screen.json, {name}: unscaled needs the factor and anchor that scale the layout")
        wrap = _names(record.get("wrap", []), f"{name}, wrap")
        offset = _pixels(record["offset"], f"{name}, offset") if "offset" in record else (0.0, 0.0)
        nudge = record.get("nudge", {})
        if not isinstance(nudge, dict):
            raise ValueError(f"single_screen.json, {name}: nudge must map panes to [dx, dy]")
        nudge = {group: _pixels(value, f"{name}, nudge, {group}") for group, value in nudge.items()}
        settings[name] = LayoutSetting(float(factor), anchor, priority, backdrop, group_priority,
                                       _names(record.get("hide", []), f"{name}, hide"), push, fill,
                                       move, offset, nudge, _names(record.get("pinned", []), f"{name}, pinned"),
                                       _names(record.get("carry", []), f"{name}, carry"), unscaled, wrap,
                                       _load_fit(record.get("fit", []), name),
                                       _load_layers(record.get("layers", []), name, images),
                                       _names(record.get("fixed", []), f"{name}, fixed"),
                                       _load_bands(record.get("bands", []), name))
    return settings


def visible_boxes(layout: Layout, clip: bool = True, skip: Iterable[str] = (), only: str | None = None,
                  half_size: tuple[float, float] = TOP_HALF_SIZE,
                  by_origin: bool = False) -> list[tuple[Pane, Extent]]:
    """(pane, box) of every sprite and text that shows when the layout loads, the box in layout coordinates, cut to a
    screen of `half_size` (the top screen's by default) unless `clip` is false. `skip`: root groups left out; `only`:
    the one root group measured; `by_origin`: a sprite whose origin says "centre" (the world map's clouds) is read by
    its centre, not its corner (off by default: the layouts tuned so far read every sprite by its corner)."""
    boxes: list[tuple[Pane, Extent]] = []
    skip = set(skip)
    half_width, half_height = half_size

    def walk(pane: Pane, x: float, y: float, scale_x: float, scale_y: float) -> None:
        for child in pane.children:
            if child.kind == PaneKind.BOUNDARY or child.visible is False:
                continue
            child_x = x + scale_x * child.position[0]
            child_y = y + scale_y * child.position[1]
            if child.kind == PaneKind.NULL:
                walk(child, child_x, child_y, scale_x * child.scale[0], scale_y * child.scale[1])
                continue
            if child.kind in (PaneKind.SPRITE, PaneKind.TEXT) and all(color[3] == 0 for color in child.colors):
                continue
            if child.kind == PaneKind.SPRITE:
                width = child.size[0] * child.scale[0] * scale_x
                height = child.size[1] * child.scale[1] * scale_y
            else:
                width, height = child.size[0] * scale_x, child.size[1] * scale_y
            if not width or not height:
                continue
            box = (child_x - abs(width), child_y - abs(height), child_x, child_y)
            if by_origin and child.kind == PaneKind.SPRITE and child.origin & 0xFF == CENTRED:
                box = (child_x - abs(width) / 2, child_y - abs(height) / 2,
                       child_x + abs(width) / 2, child_y + abs(height) / 2)
            if clip:
                box = (max(box[0], -half_width), max(box[1], -half_height),
                       min(box[2], half_width), min(box[3], half_height))
                if box[0] >= box[2] or box[1] >= box[3]:
                    continue
            boxes.append((child, box))

    for group in layout.roots:
        if group.name not in skip and only in (None, group.name):
            walk(group, *group.position, 1.0, 1.0)
    return boxes


def visible_extent(layout: Layout, clip: bool = True, skip: Iterable[str] = (), only: str | None = None,
                   half_size: tuple[float, float] = TOP_HALF_SIZE, by_origin: bool = False) -> Extent | None:
    """The box around what shows when the layout loads (`visible_boxes`' panes), in layout coordinates; None when
    nothing shows."""
    boxes = [box for _, box in visible_boxes(layout, clip, skip, only, half_size, by_origin)]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _shift_towards(low: float, high: float, side: int, half_screen: float) -> float:
    """How far to move [low, high] so its largest end (side 1) or smallest end (side -1) is at the screen's edge
    (`half_screen` from the centre), or its middle (side 0) at the centre."""
    if side == 0:
        return -(low + high) / 2
    return side * half_screen - (high if side == 1 else low)


def _root(layout: Layout, name: str, what: str) -> Pane:
    for group in layout.roots:
        if group.name == name:
            return group
    raise KeyError(f"no root group named {name} ({what})")


def _fill_template(layout: Layout, template: str, others: Mapping[str, Layout]) -> Pane:
    """The sprite a fill copies: of this layout, or "otherlayout:sprite" of one of `others`."""
    source, _, sprite = template.rpartition(":")
    if source:
        if source not in others:
            raise KeyError(f"no layout named {source} in the ARC (the fill's template {template})")
        layout = others[source]
    found = next((p for p in layout.panes if p.name == sprite and p.kind == PaneKind.SPRITE), None)
    if found is None:
        where = f" in {source}" if source else ""
        raise KeyError(f"no sprite named {sprite}{where} (the fill's template)")
    return found


def _check_names(layout: Layout, setting: LayoutSetting, others: Mapping[str, Layout]) -> None:
    """Refuse a setting naming a group, pane or sprite the layout does not have, before anything is changed."""
    names = {"push": setting.push, "fixed": setting.fixed}
    if setting.fill is not None:
        names["fill"] = (setting.fill.group, *setting.fill.over)
        _fill_template(layout, setting.fill.template, others)
    for what, groups in names.items():
        for name in groups:
            _root(layout, name, what)
    for what, panes in {"hide": setting.hide, "pinned": setting.pinned, "carry": setting.carry,
                        "unscaled": setting.unscaled, "wrap": setting.wrap, "nudge": tuple(setting.nudge)}.items():
        for name in panes:
            if not any(pane.name == name for pane in layout.panes):
                raise KeyError(f"no pane named {name} ({what})")
    for name in setting.carry:
        pane = layout.find(name)
        if pane.depth != 1 or pane.kind in CONTAINERS:
            raise ValueError(f"carry: {name} must be a childless pane right under a root group")
    for name in setting.wrap:
        pane = layout.find(name)
        if pane.depth != 1 or pane.kind not in (PaneKind.NULL, PaneKind.SPRITE, PaneKind.TEXT):
            raise ValueError(f"wrap: {name} must be a null, sprite or text right under a root group")
    for fit in setting.fit:
        pane = next((p for p in layout.panes if p.name == fit.pane), None)
        if pane is None:
            raise KeyError(f"no pane named {fit.pane} (fit)")
        if pane.kind != PaneKind.SPRITE:
            raise ValueError(f"fit: {fit.pane} must be a sprite")
        for name in fit.over:
            _root(layout, name, "fit")
        if _group_of(pane).name in fit.over:
            raise ValueError(f"fit: {fit.pane} is in {_group_of(pane).name}, the group it is fitted to")


def _group_of(pane: Pane) -> Pane:
    """The root group a pane belongs to."""
    while pane.parent is not None:
        pane = pane.parent
    return pane


def _fit(layout: Layout, fits: Iterable[Fit]) -> None:
    """Size and place each `fit` sprite over the box around its groups (see `Fit`): its scale is 1, its origin the
    corner, and its size and position are chosen so that, with the position and scale of the panes above it, it
    covers the box."""
    for fit in fits:
        _cover(layout.find(fit.pane), _margin_box(layout, fit.over, fit.margin, f"the fit of {fit.pane}"))


def _bands(layout: Layout, bands: Iterable[Band]) -> None:
    """Add each band: a new sprite (`band_name`), a copy of the band's sprite after it under the same parent, sized and
    placed over its box and tinted (see `Band`). A pane of its own, because the game's code may move a named pane after
    the layout loads (the Meownster trip's set-up widens the cloth's four sprites by their name hashes). The screen's
    pixels are the layout's reversed: x = 200 - layout x, y = 120 - layout y."""
    for index, band in enumerate(bands):
        template = layout.find(band.pane)
        if template.kind != PaneKind.SPRITE:
            raise ValueError(f"the band {band.pane} is not a sprite")
        pane = layout.insert_sprite(template.parent, template, band_name(band, index), template.position,
                                    behind=template)
        left, top, right, bottom = band.box
        _cover(pane, (SCREEN_HALF_WIDTH - right, SCREEN_HALF_HEIGHT - bottom,
                      SCREEN_HALF_WIDTH - left, SCREEN_HALF_HEIGHT - top))
        pane.colors = [band.color] * 4


def band_name(band: Band, index: int) -> str:
    """The name of the sprite the `index`-th band of a layout adds."""
    return f"{band.pane}_band{index}"


def _margin_box(layout: Layout, over: Iterable[str], margin: float | tuple[float, float], what: str) -> Extent:
    """The box `visible_extent(by_origin=True)` measures around the root groups `over`, grown by `margin`."""
    over = tuple(over)
    extents = [extent for name in over if (extent := visible_extent(layout, only=name, by_origin=True))]
    if not extents:
        raise KeyError(f"nothing shows of {', '.join(over)}: {what} has nothing to cover")
    mx, my = (margin, margin) if isinstance(margin, int | float) else margin
    box = (min(e[0] for e in extents) - mx, min(e[1] for e in extents) - my,
           max(e[2] for e in extents) + mx, max(e[3] for e in extents) + my)
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError(f"{what}: the margin {margin} leaves the box over {', '.join(over)} empty")
    return box


def _cover(pane: Pane, box: Extent) -> None:
    """Size and place the sprite `pane` (scale 1, the corner as its origin) so that it covers `box`, whatever the
    position and scale of the panes above it."""
    chain, above = [], pane.parent
    while above is not None:
        chain.append(above)
        above = above.parent
    x, y, scale_x, scale_y = 0.0, 0.0, 1.0, 1.0       # the frame the pane's own position is relative to
    for above in reversed(chain):
        x, y = x + scale_x * above.position[0], y + scale_y * above.position[1]
        if above.kind == PaneKind.NULL:
            scale_x, scale_y = scale_x * above.scale[0], scale_y * above.scale[1]
    pane.origin = 0
    pane.scale = (1.0, 1.0)
    pane.size = ((box[2] - box[0]) / scale_x, (box[3] - box[1]) / scale_y)
    pane.position = ((box[2] - x) / scale_x, (box[3] - y) / scale_y)
    pane.visible = True


def _layers(layout: Layout, layers: Iterable[Layer]) -> None:
    """Insert each layer's sprite right after its `after` sprite and cover its box (see `Layer`)."""
    for layer in layers:
        template = layout.find(layer.after)
        if template.kind != PaneKind.SPRITE:
            raise ValueError(f"the layer {layer.image} goes after {layer.after}, which is not a sprite")
        if _group_of(template).name in layer.over:
            raise ValueError(f"the layer {layer.image} may not cover the group of {layer.after}")
        box = _margin_box(layout, layer.over, layer.margin, f"the layer {layer.image}")
        texture = layout.add_texture(layer.texture)
        template = layout.find(layer.after)      # (the panes are new after the texture table grew)
        pane = layout.insert_sprite(template.parent, template, LAYER_PREFIX + layer.image, (0.0, 0.0),
                                    (0.0, 0.0, 1.0, 1.0), texture, behind=template)
        pane.colors = [(255, 255, 255, 255)] * 4
        _cover(pane, box)


def _plain_null(layout: Layout) -> Pane:
    """A null with no scale, tint nor offset of its own (z 0, scale 1, opaque white), the template of a wrapper."""
    return layout.plain_null()


def _carry(layout: Layout, names: Iterable[str]) -> None:
    """Wrap each `carry` pane in a null of its own (see the module's text)."""
    for name in names:
        layout.wrap_in_null(layout.find(name), name + CARRY_SUFFIX, _plain_null(layout))


def _wrap(layout: Layout, names: Iterable[str]) -> tuple[str, ...]:
    """Wrap each `wrap` pane (and what is under it) in a null of its own, like `carry`'s; returns the names the scaling
    treats as `unscaled` (see the module's text): the wrappers, and the panes left unwrapped. A null whose subtree
    reaches the loader's last level (`MAX_DEPTH`) cannot be wrapped: the wrapper would push its deepest pane to a level
    the game's loader cannot hold. It takes the
    factor as its own scale and keeps its subtree's numbers instead, which lands what the code writes under it on the
    scaled layout like a wrapper does; what the code writes to its own position stays in the file's units."""
    unscaled = []
    for name in names:
        pane = layout.find(name)
        if max(p.depth for p in pane.walk()) + 1 > MAX_DEPTH:
            unscaled.append(name)
            continue
        layout.wrap_in_null(pane, name + CARRY_SUFFIX, _plain_null(layout), subtree=pane.kind == PaneKind.NULL)
        unscaled.append(name + CARRY_SUFFIX)
    return tuple(unscaled)


def _hide(group: Pane) -> None:
    """Make every sprite and text of the pane and everything under it clear (alpha 0 on the four corners):
    they draw nothing whatever the code shows."""
    for pane in group.walk():
        if pane.kind in (PaneKind.SPRITE, PaneKind.TEXT):
            pane.colors = [(r, g, b, 0) for r, g, b, _ in pane.colors]


def _shift_targets(pane: Pane, shift: tuple[float, float],
                   pinned: Collection[str]) -> list[tuple[Pane, tuple[float, float]]]:
    """The panes that take a move of `pane`: itself, or its children when it is pinned (the same pixels: a null's
    scale is divided out), recursively."""
    if pane.name not in pinned:
        return [(pane, shift)]
    sx, sy = pane.scale if pane.kind == PaneKind.NULL else (1.0, 1.0)
    inner = (shift[0] / sx if sx else shift[0], shift[1] / sy if sy else shift[1])
    return [target for child in pane.children for target in _shift_targets(child, inner, pinned)]


def _move_groups(groups: Iterable[Pane], animations: Iterable[Animations], shift: tuple[float, float],
                 pinned: Collection[str] = ()) -> None:
    """Move the root groups by `shift`: the panes right under each group and their x / y animation tracks (those of
    the children of a `pinned` pane, instead of its own)."""
    targets: dict[int, dict[int, tuple[float, float]]] = {}
    for group in groups:
        moves: dict[int, tuple[float, float]] = {}
        for pane in group.walk():
            if pane.depth == 1:
                for target, by in _shift_targets(pane, shift, pinned):
                    target.position = (target.position[0] + by[0], target.position[1] + by[1])
                    moves.setdefault(name_hash(target.name), by)
        targets[name_hash(group.name)] = moves
    for file in animations:
        for track in file.tracks:
            by = targets.get(track.group_hash, {}).get(track.pane_hash)
            if by is not None and track.prop in (Property.X, Property.Y):
                track.transform(1.0, by[0] if track.prop == Property.X else by[1])


def _nudge(layout: Layout, animations: Iterable[Animations], name: str, shift: tuple[float, float],
           pinned: Collection[str] = ()) -> None:
    """Move the pane `name` alone by `shift` (layout coordinates): a root group as `_move_groups` does; any other pane
    by its own position and its x / y animation tracks, the shift divided by the scales of the nulls above it (a
    wrapper's factor), or its children when it is pinned."""
    group = next((group for group in layout.roots if group.name == name), None)
    if group is not None:
        _move_groups([group], animations, shift, pinned)
        return
    pane = layout.find(name)
    scale_x, scale_y, root, parent = 1.0, 1.0, pane, pane.parent
    while parent is not None:
        if parent.kind == PaneKind.NULL and parent.depth > 0:
            scale_x, scale_y = scale_x * parent.scale[0], scale_y * parent.scale[1]
        root, parent = parent, parent.parent
    inner = (shift[0] / scale_x if scale_x else shift[0], shift[1] / scale_y if scale_y else shift[1])
    moves: dict[int, tuple[float, float]] = {}
    for target, by in _shift_targets(pane, inner, pinned):
        target.position = (target.position[0] + by[0], target.position[1] + by[1])
        moves.setdefault(name_hash(target.name), by)
    for file in animations:
        for track in file.tracks:
            by = moves.get(track.pane_hash) if track.group_hash == name_hash(root.name) else None
            if by is not None and track.prop in (Property.X, Property.Y):
                track.transform(1.0, by[0] if track.prop == Property.X else by[1])


def _left_alone(setting: LayoutSetting) -> tuple[str, ...]:
    """The root groups the placing neither scales, measures nor moves: the backdrop (which is stretched instead) and the
    `fixed` ones."""
    names = [] if setting.backdrop is None else [setting.backdrop]
    return tuple(names + [name for name in setting.fixed if name not in names])


def place_layout(layout: Layout, animations: Iterable[Animations], setting: LayoutSetting,
                 others: Mapping[str, Layout] | None = None) -> tuple[float, float]:
    """Apply the setting: hide its `hide` groups, stretch the backdrop, scale the layout (and the tracks of
    `animations` that move its root groups) and push it against its anchor, push the `push` groups on their own to
    that edge, and insert the `fill`. Returns the (x, y) move applied after the scaling, in layout coordinates. A
    layout with nothing visible is only scaled; one without an anchor is neither scaled nor moved (the `offset` and
    `nudge` still apply). The returned move does not include them. `others`: the ARC's other layouts by name, only
    read (a fill's template "otherlayout:sprite")."""
    animations = list(animations)
    others = others or {}
    _check_names(layout, setting, others)
    # the template's colours before `hide` may clear it (a fill that replaces the sprite it copies)
    colors = None if setting.fill is None else _fill_template(layout, setting.fill.template, others).colors
    _carry(layout, setting.carry)
    wrappers = _wrap(layout, setting.wrap)
    for name in setting.hide:
        _hide(layout.find(name))
    skip = _left_alone(setting)
    if setting.backdrop is not None:
        _cover_screen(layout, setting.backdrop)
    shift = (0.0, 0.0)
    if setting.anchor is not None:
        shift = _place(layout, animations, setting, skip, wrappers)
        for name in setting.push:
            _push(layout, animations, name, setting.anchor, setting.pinned)
    if setting.offset != (0.0, 0.0):    # screen pixels to layout coordinates: both axes are reversed
        _move_groups([group for group in layout.roots if group.name not in skip], animations,
                     (-setting.offset[0], -setting.offset[1]), setting.pinned)
    for name, (dx, dy) in setting.nudge.items():
        _nudge(layout, animations, name, (-dx, -dy), setting.pinned)
    if setting.fill is not None:
        _insert_fill(layout, setting.fill, others, colors)
    _fit(layout, setting.fit)
    _layers(layout, setting.layers)
    _bands(layout, setting.bands)
    return shift


def _place(layout: Layout, animations: list[Animations], setting: LayoutSetting,
           skip: tuple[str, ...], wrappers: tuple[str, ...] = ()) -> tuple[float, float]:
    """Scale the layout around the screen's centre and move it against the anchor; returns the move."""
    extent = visible_extent(layout, skip=skip)
    anchors = anchor_all(layout, Anchor.CENTER)
    for name in skip:
        del anchors[name]
    scale_hud(layout, animations, setting.factor, anchors, (*setting.unscaled, *wrappers))
    if extent is None:
        return 0.0, 0.0
    extent = tuple(value * setting.factor for value in extent)   # the scaling is around the origin
    side_x, side_y = setting.anchor.value
    shift = (_shift_towards(extent[0], extent[2], side_x, SCREEN_HALF_WIDTH) if "x" in setting.move else 0.0,
             _shift_towards(extent[1], extent[3], side_y, SCREEN_HALF_HEIGHT) if "y" in setting.move else 0.0)
    if shift != (0.0, 0.0):
        _move_groups([group for group in layout.roots if group.name not in skip], animations, shift, setting.pinned)
    return shift


def _push(layout: Layout, animations: list[Animations], name: str, anchor: Anchor,
          pinned: Collection[str] = ()) -> None:
    """Move the root group `name` alone so what shows of it touches the anchor's edge, on the axes where the anchor
    has a side."""
    group = _root(layout, name, "push")
    extent = visible_extent(layout, only=name)
    if extent is None:
        return
    side_x, side_y = anchor.value
    shift = (_shift_towards(extent[0], extent[2], side_x, SCREEN_HALF_WIDTH) if side_x else 0.0,
             _shift_towards(extent[1], extent[3], side_y, SCREEN_HALF_HEIGHT) if side_y else 0.0)
    if shift != (0.0, 0.0):
        _move_groups([group], animations, shift, pinned)


def _insert_fill(layout: Layout, fill: Fill, others: Mapping[str, Layout], colors) -> None:
    """Insert the fill's sprite as the first child of its group, sized and placed over what it covers, with the
    template's `colors` unless the fill names its own."""
    if fill.over:
        extents = [extent for name in fill.over if (extent := visible_extent(layout, only=name)) is not None]
        if not extents:
            raise KeyError(f"nothing shows of {', '.join(fill.over)}: the fill has nothing to cover")
        mx, my = (fill.margin, fill.margin) if isinstance(fill.margin, int | float) else fill.margin
        box = (min(e[0] for e in extents) - mx, min(e[1] for e in extents) - my,
               max(e[2] for e in extents) + mx, max(e[3] for e in extents) + my)
        if box[0] >= box[2] or box[1] >= box[3]:
            raise ValueError(f"the fill's margin {fill.margin} leaves the rectangle over {', '.join(fill.over)} "
                             f"empty")
    else:
        box = (-SCREEN_HALF_WIDTH, -SCREEN_HALF_HEIGHT, SCREEN_HALF_WIDTH, SCREEN_HALF_HEIGHT)
    template = _fill_template(layout, fill.template, others)
    texture = None
    if template.layout is not layout:    # the other layout's texture, by name, in this layout's table
        texture = layout.add_texture(template.layout.textures[template.texture])
    group = _root(layout, fill.group, "fill")
    x, y = group.position
    pane = layout.insert_sprite(group, template, FILL_NAME, (box[2] - x, box[3] - y), fill.region, texture,
                                first=True)
    pane.size = (box[2] - box[0], box[3] - box[1])
    pane.origin = 0     # placed by its top-left corner, whatever the template's (ui801_bg is centred)
    pane.scale = (1.0, 1.0)
    pane.visible = True
    pane.colors = list(colors) if fill.color is None else [fill.color] * 4


def _cover_screen(layout: Layout, name: str) -> None:
    """Stretch the root group `name` so what shows of it, on the touch screen, spans the whole top screen."""
    _root(layout, name, "backdrop")
    extent = visible_extent(layout, only=name, half_size=TOUCH_HALF_SIZE)
    if extent is None:
        raise KeyError(f"nothing of {name} shows: it cannot be a backdrop")
    group = layout.find(name)
    scale = (2 * SCREEN_HALF_WIDTH / (extent[2] - extent[0]), 2 * SCREEN_HALF_HEIGHT / (extent[3] - extent[1]))
    centre = ((extent[0] + extent[2]) / 2, (extent[1] + extent[3]) / 2)
    for pane in group.walk():
        if pane is group:
            continue
        x, y = pane.position
        if pane.depth == 1:   # placed from the group's position: x' = s (gx + x - c) - gx
            x = scale[0] * (group.position[0] + x - centre[0]) - group.position[0]
            y = scale[1] * (group.position[1] + y - centre[1]) - group.position[1]
            pane.position = (x, y)
        else:
            pane.position = (x * scale[0], y * scale[1])
        if pane.size is not None and pane.kind != PaneKind.NULL:
            pane.size = (pane.size[0] * scale[0], pane.size[1] * scale[1])


def priority_offsets(layout: Layout, setting: LayoutSetting) -> dict[int, int]:
    """Name hash -> priority offset of the layout's root groups: the table of the executable's draw order block
    (interface/single_screen/executable/single_screen.py). A group's offset is its `group_priority`, else the layout's
    `priority` (0 for the backdrop); groups with offset 0 are left out, so the table is empty when the setting adds
    nothing."""
    for name in setting.group_priority:
        _root(layout, name, "group_priority")
    offsets = {}
    for group in layout.roots:
        default = 0 if group.name == setting.backdrop or group.name in setting.fixed else setting.priority
        offset = setting.group_priority.get(group.name, default)
        if offset:
            offsets[name_hash(group.name)] = offset
    return offsets


@cache
def layer_texture(png: str) -> bytes:
    """The TEX file (RGBA4444, one mip) of the picture `png` of IMAGES_DIR: its pixels as the PNG has them (the PNG is
    made with 4-bit channels, tools/inspect/world_map_paper.py, so nothing is lost)."""
    width, height, rgba = read_png((IMAGES_DIR / png).read_bytes())
    tex = new_tex(width, height, RGBA4444)
    tex.set_region(0, 0, width, height, rgba)
    return tex.to_bytes()


def arc_settings(arc: str, settings: Mapping[str, LayoutSetting]) -> dict[str, LayoutSetting]:
    """The settings the ARC named `arc` (a name of ARCS) places: all of them, but only its own in a stage ARC of
    STAGE_LAYOUTS."""
    return {name: setting for name, setting in settings.items()
            if arc not in STAGE_LAYOUTS or name in STAGE_LAYOUTS[arc]}


def patch_arc(raw: bytes, settings: Mapping[str, LayoutSetting], frames: Frames | None = None,
              arc_name: str = "") -> bytes:
    """The ARC with every layout of `settings` that it holds placed, together with the animations of the ARC
    that move them, and then, with `frames` (the curated frames) and the ARC's name, each root group of a frame set put
    in its frame null (interface/single_screen/layout/single_screen_frames.py: the layouts the frames name in that ARC);
    the other layouts are as they were. An ARC with none of them is returned unchanged. A setting naming a group or
    sprite its layout lacks raises KeyError, with the layout's name."""
    arc = parse_arc(raw)
    entries = {e.name.split("\\")[-1]: e for e in arc.entries if e.type_hash == LYT_TYPE_HASH}
    framed = {name: frames.roots(name, arc_name) for name in entries} if frames is not None else {}
    framed = {name: roots for name, roots in framed.items() if roots}
    names = [name for name in entries if name in settings or name in framed]
    if not names:
        return raw
    # the ARC's layouts as they are, for the templates taken from another layout
    others = {name: parse_lyt(entry.data) for name, entry in entries.items()}
    animation_entries = [e for e in arc.entries if e.type_hash == LANL_TYPE_HASH]
    animations = [parse_lanl(e.data) for e in animation_entries]
    for name in names:
        layout = parse_lyt(entries[name].data)
        try:
            if name in settings:
                place_layout(layout, animations, settings[name], others)
            if name in framed:      # after the placing: its moves go to the panes right under the root groups
                wrap_frames(layout, framed[name], _plain_null(parse_lyt(layout.to_bytes())))
        except KeyError as error:
            raise KeyError(f"layout {name}: {error.args[0]}") from None
        entries[name].data = layout.to_bytes()
    for entry, file in zip(animation_entries, animations):
        entry.data = file.to_bytes()
    held = {entry.name for entry in arc.entries}
    for name in names:
        # the textures of the layers, right before their layout: the game loads an ARC's entries in order and a
        # layout takes its textures when it loads; after it,
        # white
        for layer in settings[name].layers if name in settings else ():
            if layer.texture not in held:
                held.add(layer.texture)
                at = arc.entries.index(entries[name])
                arc.entries.insert(at, ArcEntry(layer.texture, TEX_TYPE_HASH, layer_texture(layer.png)))
    return write_arc(arc)


def single_screen_files(rom: GameFiles, files: Mapping[str, bytes] | None = None,
                        settings: Mapping[str, LayoutSetting] | None = None,
                        frames: Frames | None = None) -> tuple[dict[str, bytes], dict[int, int]]:
    """The run's files of the mode: (RomFS path -> ARC with its layouts placed and the frames' nulls in, for each of
    ARCS that holds one, in the five languages; the draw order offsets, name hash -> offset, of the executable's table).
    An ARC already in `files` (an earlier interface file's copy) is placed as it is; the others start from the base
    game's. `settings` and `frames`: the curated ones by default; a layout or framed group found in none of the ARCs
    raises ValueError."""
    files = files or {}
    settings = load_layout_settings() if settings is None else settings
    frames = frame_settings() if frames is None else frames
    out: dict[str, bytes] = {}
    offsets: dict[int, int] = {}
    found: set[str] = set()
    for language in LANGUAGES:
        for name in ARCS:
            path = f"{language}/data/{name}"
            raw = files.get(path) or rom.read(path)
            here = arc_settings(name, settings)
            for entry in parse_arc(raw).entries:
                layout_name = entry.name.split("\\")[-1]
                if entry.type_hash != LYT_TYPE_HASH:
                    continue
                if layout_name in here:
                    found.add(layout_name)
                    offsets |= priority_offsets(parse_lyt(entry.data), here[layout_name])
                framed = frames.roots(layout_name, name)
                if framed:
                    found |= set(framed) & {root.name for root in parse_lyt(entry.data).roots}
            patched = patch_arc(raw, here, frames, name)
            if patched != raw:
                out[path] = patched
    missing = (set(settings) | set(frames.groups())) - found
    if missing:
        raise ValueError(f"single_screen.json: layouts or framed groups in none of {', '.join(ARCS)}: "
                         f"{', '.join(sorted(missing))}")
    return out, offsets


def keyboard_backdrop_width(path: Path = SETTINGS_FILE) -> int:
    """The curated width (320 to 400 pixels; 320 is the layout's own) the name keyboard's backdrop is widened to."""
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("keyboard")
    width = record.get("backdrop_width") if isinstance(record, dict) else None
    if isinstance(width, bool) or not isinstance(width, int) or not 320 <= width <= 400:
        raise ValueError("single_screen.json, keyboard, backdrop_width: a whole number of pixels, 320 to 400")
    return width


def keyboard_backdrop_files(rom: GameFiles, width: int | None = None) -> dict[str, bytes]:
    """(RomFS path -> ARC) of the name keyboard's Common.arc with its backdrop window widened to `width` (the curated
    one by default; the window stays centred, so it grows to both sides), for each region's folder the game has. The
    keyboard's layouts are 320 wide and sit in the middle of the 400-wide top screen, where the scene shows at the
    sides. A width of 320 changes nothing. Raises KeyError when the layout or its window is not there, ValueError when
    the game has no keyboard archive."""
    width = keyboard_backdrop_width() if width is None else width
    if width <= 320:
        return {}
    out = {}
    for path in KEYBOARD_ARCS:
        try:
            raw = rom.read(path)
        except (FileNotFoundError, KeyError):
            continue
        arc = parse_arc(raw)
        entries = {e.name.split("\\")[-1]: e for e in arc.entries if e.type_hash == LYT_TYPE_HASH}
        layout_name, pane_name = KEYBOARD_BACKDROP
        if layout_name not in entries:
            raise KeyError(f"{path}: no layout {layout_name}")
        layout = parse_lyt(entries[layout_name].data)
        pane = layout.find(pane_name)
        pane.size = (float(width), pane.size[1])
        entries[layout_name].data = layout.to_bytes()
        out[path] = write_arc(arc)
    if not out:
        raise ValueError(f"no keyboard archive in the game ({', '.join(KEYBOARD_ARCS)})")
    return out


def single_screen_paths(mod_dir: Path) -> list[Path]:
    """Every file the mode can leave in a mod folder."""
    return ([Path(mod_dir) / "romfs" / language / "data" / name for language in LANGUAGES
             for name in ARCS + WEAPON_ARCS + LOADING_ARCS]
            + [Path(mod_dir) / "romfs" / path for path in KEYBOARD_ARCS])


def remove_single_screen_files(mod_dir: Path) -> None:
    for path in single_screen_paths(mod_dir):
        path.unlink(missing_ok=True)
