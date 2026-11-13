"""The interface on a picture of another shape (option cheat_aspect_ratio):
which side of a wider picture each root group keeps to, and the backdrops that grow to cover it. The HUD has its own
anchors (interface/hud/scale.py); this is for everything else, read from the layout files, with the exceptions in the
curated aspect_ratio.json.

* **The side** (`side_of`): where a group's box lies in the game's 400 wide frame. Across the whole frame it stays;
  wholly in one half it goes to that side; across the middle, to the side its centre is on, past a dead zone. Only the
  width: the groups of a tall window lie above and below its middle, and would part.
* **The table** (`anchor_table`): each group's box as the layout loads it, without its translate. The executable adds
  the translate the game gives the group at draw time and asks the same rule (aspect_ratio.c, `aspect_group_x`), so a
  group the code moves to the other column changes side. What moves on its own is left out: the minimap's ARCs, the
  groups the game GUI engine places (it takes the shift in its places, interface/game_gui/engine.py). The HUD's groups
  are in it by their anchors (`hud_entries`): their files move, and the table takes the ratio chosen in the game.
  A group the code moves by writing its first nulls keeps its translate at 0: the data names it (`follow_nulls`), its
  entry says so, and the executable reads those nulls (the list arrows, which serve a list on either side).
* **The windows** (`_windows`): what lies inside a group the rule keeps in the middle stays on it, as the buttons of a
  touch screen's menu on the top screen.
* **The rows** (`move_child_sides`): a root group that holds rows of both sides, like the town's button hints, cannot
  take one side whole. The data names its children, which move in the file, from the side the group takes.
* **The backdrops** (`stretch_backdrops`): a sprite that crosses the whole frame grows from the frame's centre until it
  covers the picture, shown or not as the layout loads, since a fade starts clear. A ground of several sprites, which
  the rule cannot tell from a menu, is named in the data and grows whole.
"""

import json
import math
import re
import struct
from collections.abc import Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

from core.cheats.aspect_table import SETTINGS_FILE
from core.game.files.arc import parse_arc, write_arc
from core.game.files.gui.lanl import LANL_TYPE_HASH, Animations, Property, parse_lanl
from core.game.files.gui.lyt import LYT_TYPE_HASH, Layout, Pane, PaneKind, name_hash, parse_lyt
from core.interface.game_gui import geometry
from core.interface.hud.build import CODE_PATCH_LAYOUTS, HUD_LAYOUTS, LANGUAGES, MAP_ARC, GameFiles, short_name
from core.interface.hud.code_patch import FACE_ANCHOR, FACE_LAYOUT
from core.interface.horn_songs.layout import ANCHOR as HORN_ANCHOR
from core.interface.horn_songs.layout import NAME as HORN_LAYOUT
from core.interface.hud.scale import NO_EDGE, SCREEN_HALF_WIDTH, Anchor, anchor_all

LEFT, CENTRE, RIGHT = -1, 0, 1
SIDES = {"left": LEFT, "centre": CENTRE, "right": RIGHT}
FRAME_WIDTH, FRAME_HEIGHT = geometry.SCREEN_SIZES["top"]
TABLE_LANGUAGE = "eng"      # the groups' names and places are the same in every language
TABLE_HEADER = struct.Struct("<I")          # the count
TABLE_ENTRY = struct.Struct("<I2h")         # struct anchor in aspect_ratio.c: name hash, the box's left and right
HUD_CODES = 16              # aspect_ratio.c: an entry from here on is a HUD group's anchor (`hud_code`)
CORNER_CODES = 32           # aspect_ratio.c: from here on, a corner the data names (`corner_code`)
CORNERS = {anchor.name.lower(): anchor for anchor in Anchor if anchor is not Anchor.IN_PLACE}
# The ARCs under <language>/data/ that hold a sprite across the whole frame (the game's 28 of them); the weapon guide's
# and the monsters' pages hold none, and the minimap's are moved by the executable
BACKDROP_ARC = re.compile(r"(core_\w+|loading_\w+|monnyan_core|v\d\da\d\d_map)\.arc")


@dataclass(frozen=True)
class AnchorRules:
    edge_margin: float              # a box this close to both sides of the frame crosses the whole of it
    half_margin: float              # a box may pass the middle by this much and still lie in its half
    dead_zone: float                # a box across the middle whose centre is this close to it stays
    keep_centred: tuple[str, ...]   # root groups that stay (patterns)
    sides: Mapping[str, int]        # root groups whose side the data says, wherever they lie
    keep_width: tuple[str, ...]     # panes that cross the frame but are no backdrop (patterns)
    stretch_groups: tuple[str, ...]  # root groups that are a ground of several sprites, which grow together (patterns)
    sub_view_margin: float          # a sub-view (the forge's preview) this close to the frame's side goes to it
    window_width: float             # a group the rule keeps in the middle, this wide, holds what lies inside it
    window_margin: float            # how far past the window's box a group may reach and still lie inside it
    child_sides: Mapping[str, int] = field(default_factory=dict)  # children of a root group, which move in the file
    follow_nulls: tuple[str, ...] = ()  # root groups the code moves by writing their first nulls (patterns)
    corners: Mapping[str, Anchor] = field(default_factory=dict)  # root groups that keep to a corner of the picture


def _number(raw: dict, key: str) -> float:
    value = raw.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        raise ValueError(f"aspect_ratio.json: anchors: {key} must be a number, 0 or more")
    return float(value)


def _patterns(raw: dict, key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"aspect_ratio.json: anchors: {key} must list names or patterns")
    return tuple(value)


def _sides(raw: dict, key: str) -> dict[str, int]:
    sides = raw.get(key)
    if not isinstance(sides, dict):
        raise ValueError(f"aspect_ratio.json: anchors: {key} must map panes to left, centre or right")
    for pane, side in sides.items():
        if side not in SIDES:
            raise ValueError(f"aspect_ratio.json: anchors: {key}: {pane} must be left, centre or right")
    return {pane: SIDES[side] for pane, side in sides.items()}


def _corners(raw: dict, key: str) -> dict[str, Anchor]:
    corners = raw.get(key)
    if not isinstance(corners, dict):
        raise ValueError(f"aspect_ratio.json: anchors: {key} must map root groups to a corner or an edge")
    for group, corner in corners.items():
        if corner not in CORNERS:
            raise ValueError(f"aspect_ratio.json: anchors: {key}: {group} must be one of {', '.join(CORNERS)}")
    return {group: CORNERS[corner] for group, corner in corners.items()}


def load_anchor_rules(path: Path = SETTINGS_FILE) -> AnchorRules:
    """The curated rules. Raises ValueError naming the key of anything the mod cannot use."""
    raw = json.loads(Path(path).read_text(encoding="utf-8")).get("anchors")
    if not isinstance(raw, dict):
        raise ValueError("aspect_ratio.json: anchors must be an object")
    return AnchorRules(_number(raw, "edge_margin"), _number(raw, "half_margin"), _number(raw, "dead_zone"),
                       _patterns(raw, "keep_centred"), _sides(raw, "sides"),
                       _patterns(raw, "keep_width"), _patterns(raw, "stretch_groups"), _number(raw, "sub_view_margin"),
                       _number(raw, "window_width"), _number(raw, "window_margin"), _sides(raw, "child_sides"),
                       _patterns(raw, "follow_nulls"), _corners(raw, "corners"))


def side_of(low: float, high: float, rules: AnchorRules) -> int:
    """The side (LEFT, CENTRE, RIGHT) a box from `low` to `high` pixels of the 400 wide frame keeps to. The same rule as
    aspect_ratio.c's `side_of`."""
    middle = FRAME_WIDTH / 2
    if low <= rules.edge_margin and high >= FRAME_WIDTH - rules.edge_margin:
        return CENTRE
    if high <= middle + rules.half_margin:
        return LEFT
    if low >= middle - rules.half_margin:
        return RIGHT
    centre = (low + high) / 2 - middle
    return LEFT if centre < -rules.dead_zone else RIGHT if centre > rules.dead_zone else CENTRE


def edge_move(side: int, edge: tuple[float, float]) -> float:
    """How far a group on `side` moves on an interface `edge` = (width, height) times the game's, in layout units: a
    layout's x grows to the left."""
    return -side * SCREEN_HALF_WIDTH * (edge[0] - 1)


def forced_side(group: str, rules: AnchorRules) -> int | None:
    """The side the data says for a root group; None: the rule's."""
    if group in rules.sides:
        return rules.sides[group]
    return CENTRE if any(fnmatchcase(group, pattern) for pattern in rules.keep_centred) else None


def group_span(layout: Layout, root: Pane) -> tuple[float, float] | None:
    """(left, right) in the frame's pixels of what the root group shows as its layout loads, at a translate of 0: the
    executable adds the game's. None when it shows nothing."""
    box = geometry.union(found for _, found in geometry.file_boxes(layout, [root.name], "top", cut=False))
    if box is None:
        return None
    return box[0] + root.position[0], box[2] + root.position[0]


def hud_owned_layouts() -> set[str]:
    """The layouts whose files the HUD's edges already move, or the code places (interface/hud/build.py; the target
    face's copy of its touch panel, code_patch.face_params; the Hunting Horn's songs, horn_songs/layout.py)."""
    return {*(name for layouts in HUD_LAYOUTS.values() for name in layouts),
            *(name for layouts in CODE_PATCH_LAYOUTS.values() for name in layouts), FACE_LAYOUT, HORN_LAYOUT}


def _whole_box(root: Pane) -> geometry.Box | None:
    """The box of every sprite of a root group, shown or not as the layout loads: a window often starts hidden."""
    sprites = list(_sprites(root, geometry.Frame().child(root.position)))
    return geometry.union(_box(*sprite) for sprite in sprites) if sprites else None


def _box_under_first_nulls(root: Pane) -> geometry.Box | None:
    """The box of what lies under a root group's first nulls (each the first child of the one above), with them at 0 and
    at their full size: the executable adds where the game has them."""
    pane = root
    while pane.children and pane.children[0].kind == PaneKind.NULL:
        pane = pane.children[0]
    sprites = list(_sprites(pane, geometry.Frame()))
    return geometry.union(_box(*sprite) for sprite in sprites) if sprites else None


def _windows(layout: Layout, rules: AnchorRules, skip_groups: Collection[str]) -> list[tuple[Pane, geometry.Box]]:
    """The root groups the rule keeps in the middle, wide enough to hold others: what is drawn on them must stay on
    them. Not a ground across the whole frame, which holds a menu's columns; nor a group the data names or the engine
    moves."""
    windows = []
    for root in layout.roots:
        if root.name in skip_groups or forced_side(root.name, rules) is not None:
            continue
        box = _whole_box(root)
        if box is None or box[2] - box[0] < rules.window_width \
                or (box[0] <= rules.edge_margin and box[2] >= FRAME_WIDTH - rules.edge_margin):
            continue
        if side_of(box[0], box[2], rules) == CENTRE:
            windows.append((root, box))
    return windows


def _in_a_window(root: Pane, windows: Iterable[tuple[Pane, geometry.Box]], rules: AnchorRules) -> bool:
    box = _whole_box(root)
    margin = rules.window_margin
    return box is not None and any(
        other is not root and box[0] >= window[0] - margin and box[1] >= window[1] - margin
        and box[2] <= window[2] + margin and box[3] <= window[3] + margin for other, window in windows)


def anchor_entries(layouts: Mapping[str, Layout], rules: AnchorRules,
                   skip_groups: Collection[str] = ()) -> dict[str, tuple[int, int]]:
    """Root group -> what the table says of it: its box's left and right in whole pixels, or the data's side twice (a
    box is never empty, so the executable can tell), or for a group of `follow_nulls` the box under its first nulls with
    the numbers swapped. A group that stays whatever the game does is left out, and so are one across the whole frame (a
    ground, which must not jump if the game slides it) and one inside a window."""
    owned = hud_owned_layouts()
    out: dict[str, tuple[int, int]] = {}
    for name, layout in layouts.items():
        if name in owned:
            continue
        windows = _windows(layout, rules, skip_groups)
        for root in layout.roots:
            if root.name in skip_groups:
                continue
            if root.name in rules.corners:
                out[root.name] = (corner_code(rules.corners[root.name]),) * 2
                continue
            forced = forced_side(root.name, rules)
            if forced is not None:
                if forced != CENTRE:
                    out[root.name] = (forced, forced)
                continue
            if any(fnmatchcase(root.name, pattern) for pattern in rules.follow_nulls):
                box = _box_under_first_nulls(root)
                if box is not None:
                    out[root.name] = (min(math.ceil(box[2]), 0x7FFF), max(math.floor(box[0]), -0x8000))
                continue
            span = group_span(layout, root)
            if span is not None and not (span[0] <= rules.edge_margin and span[1] >= FRAME_WIDTH - rules.edge_margin) \
                    and not _in_a_window(root, windows, rules):
                low, high = math.floor(span[0]), math.ceil(span[1])
                out[root.name] = (max(low, -0x8000), min(high, 0x7FFF))
    return out


def hud_code(anchor: Anchor) -> int:
    """What the table says of a group of the HUD's, twice: its anchor's x and y signs, each + 1, in two bits each."""
    x, y = anchor.value
    return HUD_CODES + ((x + 1) << 2 | y + 1)


def corner_code(anchor: Anchor) -> int:
    """What the table says of a group the data keeps to a corner of the picture (`corners`), twice: the anchor's signs
    as `hud_code`'s, from CORNER_CODES on. Its files are the game's, so the executable takes it from the 400 x 240
    frame, not from the installer's ratio."""
    return hud_code(anchor) - HUD_CODES + CORNER_CODES


def hud_entries(layouts: Mapping[str, Layout]) -> dict[str, tuple[int, int]]:
    """Root group -> what the table says of each group of the HUD. Its files are at the sides of the installer's ratio
    (scale.py), and so are the target face, which the code places beside the item selector (code_patch.face_params),
    and the Hunting Horn's songs under the minimap (horn_songs/layout.py); the executable takes them from there to the
    ratio chosen in the game. What stays in place is left out."""
    specs = [(name, spec) for by_arc in (HUD_LAYOUTS, CODE_PATCH_LAYOUTS) for by_layout in by_arc.values()
             for name, spec in by_layout.items()]
    out: dict[str, tuple[int, int]] = {}
    for name, spec in [*specs, (FACE_LAYOUT, FACE_ANCHOR), (HORN_LAYOUT, HORN_ANCHOR)]:
        if name in layouts:
            anchors = spec if isinstance(spec, Mapping) else anchor_all(layouts[name], spec)
            out.update((group, (hud_code(anchor),) * 2) for group, anchor in anchors.items()
                       if anchor is not Anchor.IN_PLACE)
    return out


def anchor_table(entries: Mapping[str, tuple[int, int]]) -> bytes:
    """The block `aspect_anchors` (struct anchors in aspect_ratio.c): the entries sorted by name hash. Refuses more than
    the block holds and two names with one hash."""
    from core.game.executable.blocks import ASPECT_ANCHORS_SIZE
    hashes: dict[int, str] = {}
    for name in entries:
        other = hashes.setdefault(name_hash(name), name)
        if other != name:
            raise ValueError(f"{name} and {other} have one name hash")
    size = TABLE_HEADER.size + TABLE_ENTRY.size * len(entries)
    if size > ASPECT_ANCHORS_SIZE:
        raise ValueError(f"too many groups for the anchors' table: {size} bytes, its block holds {ASPECT_ANCHORS_SIZE}")
    table = bytearray(TABLE_HEADER.pack(len(entries)))
    for key in sorted(hashes):
        table += TABLE_ENTRY.pack(key, *entries[hashes[key]])
    return bytes(table)


# ---- the backdrops ------------------------------------------------------------------------------------------------

def _sprites(pane: Pane, frame: geometry.Frame) -> Iterator[tuple[Pane, geometry.Frame]]:
    """Every sprite under `pane`, shown or not, with the frame of what is above it."""
    for child in pane.children:
        if child.kind == PaneKind.NULL:
            yield from _sprites(child, frame.child(child.position, child.scale))
        elif child.kind == PaneKind.SPRITE:
            yield child, frame


def _growth(low: float, high: float, size: float, factor: float) -> float:
    """How much a box must grow from the frame's centre for its nearer side to reach `factor` times the half frame."""
    half = min(size / 2 - low, high - size / 2)
    return max(1.0, factor * size / 2 / half) if half > 0 else 1.0


def _grow_tracks(animations: Iterable[Animations], group: Pane, pane: Pane, frame: geometry.Frame,
                 grow_x: float, grow_y: float) -> None:
    """What an animation writes to a grown sprite, in the same units as the sprite."""
    group_hash, pane_hash = name_hash(group.name), name_hash(pane.name)
    for file in animations:
        for track in file.tracks:
            if (track.group_hash, track.pane_hash) != (group_hash, pane_hash) or not track.is_float:
                continue
            if track.prop == Property.WIDTH:
                track.transform(grow_x)
            elif track.prop == Property.HEIGHT:
                track.transform(grow_y)
            elif track.prop == Property.X:
                track.transform(grow_x, frame.x * (grow_x - 1) / frame.scale_x)
            elif track.prop == Property.Y:
                track.transform(grow_y, frame.y * (grow_y - 1) / frame.scale_y)


def _box(pane: Pane, frame: geometry.Frame) -> geometry.Box:
    return geometry.bounds(geometry.quad("top", frame, pane.position, pane.size, pane.scale, 0.0, pane.origin))


def _growths(box: geometry.Box, edge: tuple[float, float], rules: AnchorRules) -> tuple[float, float]:
    """How much a box grows in each axis: only one that crosses the whole width of the frame, and in height only if it
    crosses the whole height too."""
    if not (box[0] <= rules.edge_margin and box[2] >= FRAME_WIDTH - rules.edge_margin):
        return 1.0, 1.0
    tall = box[1] <= rules.edge_margin and box[3] >= FRAME_HEIGHT - rules.edge_margin
    return (_growth(box[0], box[2], FRAME_WIDTH, edge[0]),
            _growth(box[1], box[3], FRAME_HEIGHT, edge[1]) if tall else 1.0)


def stretch_backdrops(layout: Layout, skip_groups: Collection[str], edge: tuple[float, float], rules: AnchorRules,
                      animations: Iterable[Animations] = ()) -> int:
    """Each sprite of `layout` that crosses the whole width of the frame (and is no pane of `keep_width`), and every
    sprite of a group of `stretch_groups` by what the whole group needs, grown to cover an interface `edge` times the
    game's, in place, with its animation tracks. Returns how many grew. A touch screen's ground, 320 wide, is not one; a
    sprite of the frame's width that is not as tall keeps its height."""
    grown = 0
    for root in layout.roots:
        if root.name in skip_groups:
            continue
        sprites = list(_sprites(root, geometry.Frame().child(root.position)))
        together = None
        if sprites and any(fnmatchcase(root.name, pattern) for pattern in rules.stretch_groups):
            together = _growths(geometry.union(_box(*sprite) for sprite in sprites), edge, rules)
        for pane, frame in sprites:
            if together is None and any(fnmatchcase(pane.name, pattern) for pattern in rules.keep_width):
                continue
            grow_x, grow_y = together or _growths(_box(pane, frame), edge, rules)
            if grow_x == 1.0 and grow_y == 1.0:
                continue
            x, y = frame.point(pane.position)
            pane.position = ((x * grow_x - frame.x) / frame.scale_x, (y * grow_y - frame.y) / frame.scale_y)
            pane.size = (pane.size[0] * grow_x, pane.size[1] * grow_y)
            _grow_tracks(animations, root, pane, frame, grow_x, grow_y)
            grown += 1
    return grown


def move_child_sides(layout: Layout, edge: tuple[float, float], rules: AnchorRules) -> int:
    """Each child of a root group that `child_sides` names, moved to its side of an interface `edge` times the game's,
    in place, from the side the data gives the group, which the executable moves whole. Returns how many moved. The
    game's code writes these rows' text and visibility, never their place."""
    moved = 0
    for root in layout.roots:
        group_side = forced_side(root.name, rules) or CENTRE
        for child in root.children:
            side = next((side for name, side in rules.child_sides.items() if fnmatchcase(child.name, name)), None)
            if side is not None and side != group_side and edge[0] != 1.0:
                way = edge_move(side, edge) - edge_move(group_side, edge)
                child.position = (child.position[0] + way, child.position[1])
                moved += 1
    return moved


def stretch_arc(raw: bytes, edge: tuple[float, float], rules: AnchorRules) -> bytes:
    """The ARC with its backdrops grown (`stretch_backdrops`) and its rows at their sides (`move_child_sides`), the
    HUD's layouts left alone; `raw` itself when nothing changes."""
    arc = parse_arc(raw)
    entries = [e for e in arc.entries if e.type_hash == LYT_TYPE_HASH and short_name(e.name) not in hud_owned_layouts()]
    if not entries:
        return raw
    animation_entries = [e for e in arc.entries if e.type_hash == LANL_TYPE_HASH]
    animations = [parse_lanl(e.data) for e in animation_entries]
    changed = False
    for entry in entries:
        layout = parse_lyt(entry.data)
        grown = stretch_backdrops(layout, (), edge, rules, animations)
        if move_child_sides(layout, edge, rules) or grown:
            entry.data = layout.to_bytes()
            changed = True
    if not changed:
        return raw
    for entry, file in zip(animation_entries, animations):
        entry.data = file.to_bytes()
    return write_arc(arc)


def backdrop_paths(mod_dir: Path) -> list[Path]:
    """Every file `backdrop_files` can leave in a mod folder."""
    paths = []
    for language in LANGUAGES:
        folder = Path(mod_dir) / "romfs" / language / "data"
        if folder.is_dir():
            paths += [path for path in folder.iterdir() if BACKDROP_ARC.fullmatch(path.name)]
    return paths


def remove_backdrop_files(mod_dir: Path) -> None:
    for path in backdrop_paths(mod_dir):
        path.unlink(missing_ok=True)


def backdrop_files(rom: GameFiles, files: Mapping[str, bytes], edge: tuple[float, float],
                   rules: AnchorRules) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of every ARC whose backdrops grow on an interface `edge` times the game's. `files`: the
    run's copies so far, taken first."""
    if edge == NO_EDGE:
        return
    for path in rom.walk():
        parts = path.split("/")
        if len(parts) == 3 and parts[0] in LANGUAGES and parts[1] == "data" and BACKDROP_ARC.fullmatch(parts[2]):
            raw = files.get(path) or rom.read(path)
            stretched = stretch_arc(raw, edge, rules)
            if stretched is not raw:
                yield path, stretched


# ---- in a run -----------------------------------------------------------------------------------------------------

def run_anchor_table(rom: GameFiles, files: Mapping[str, bytes], rules: AnchorRules,
                     skip_groups: Collection[str] = ()) -> bytes:
    """The block `aspect_anchors` of a run: `files`, the run's copies, taken first, so a layout single-screen mode
    placed in its file is read where it placed it."""
    layouts: dict[str, Layout] = {}
    for path in rom.walk():
        parts = path.split("/")
        if len(parts) != 3 or parts[:2] != [TABLE_LANGUAGE, "data"] or not parts[2].endswith(".arc") \
                or MAP_ARC.fullmatch(parts[2]):
            continue
        for entry in parse_arc(files.get(path) or rom.read(path)).entries:
            if entry.type_hash == LYT_TYPE_HASH:
                layouts.setdefault(short_name(entry.name), parse_lyt(entry.data))
    return anchor_table({**anchor_entries(layouts, rules, skip_groups), **hud_entries(layouts)})


def interface_anchors(rom: GameFiles, files: Mapping[str, bytes], edge: tuple[float, float],
                      skip_groups: Collection[str] = ()) -> tuple[dict[str, bytes], bytes | None]:
    """What a run's interface takes from a picture of another shape: (RomFS path -> ARC with its backdrops grown, over
    `files`, the run's copies so far; the block `aspect_anchors`). At the game's own shape only the block: the list in
    the game can choose another. `skip_groups`: the root groups the game GUI engine places."""
    rules = load_anchor_rules()
    grown = dict(backdrop_files(rom, files, edge, rules))
    return grown, run_anchor_table(rom, {**files, **grown}, rules, skip_groups)


def blocks_side(groups: Iterable[str], low: float, high: float, rules: AnchorRules) -> int:
    """The side of a block of the game GUI engine, its box from `low` to `high` on the top screen where a place puts it:
    the data's when it names one of the block's root groups, else the rule's."""
    for group in groups:
        forced = forced_side(group, rules)
        if forced is not None:
            return forced
    return side_of(low, high, rules)

