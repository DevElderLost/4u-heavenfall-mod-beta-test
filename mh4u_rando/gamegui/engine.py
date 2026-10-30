"""The build side of the game GUI engine: from an arrangement (config.py) and the game's layouts, the wrapper nulls in
the layout files and the bytes
of the engine's table; and the canonical patch that places the engine (exefs/asm/game_gui_engine.c) and hooks it.

* **Wrappers** (`wrap_layout`, `wrap_arc`, `engine_files`): each root group of a block gets its children put in one
  null, `<group>_gg` (`Layout.wrap_children`, at (0, 0), scale 1, shown): the engine writes that null's absolute
  position and scale every frame, so everything under the group follows and what the game writes under it stays
  relative to it. A group whose subtree already fills the loader's six levels (`lyt.MAX_DEPTH`, 40 of the game's 2,007
  root groups) cannot take one more level: each pane right under it gets a wrapper of its own instead, and a null whose
  own subtree fills the levels is written directly (its file position and scale in the table, as `_wrap`'s unscaled
  null in hud/single_screen.py), which loses what the game's code or an animation writes to that null itself.
* **The table** (`engine_table`): a header, the names (every group a block or a rule names) sorted by hash, the
  targets (the panes the engine writes, by hash), the screens of one mode in the order `Arrangement.screens_of` gives
  with their rules as name indices, a default place per block and each screen's places. A place holds, besides the
  view, priority and hidden flags, the wrapper's (cx, cy, scale) at a group translate of 0, cx for each screen the
  group may be on at run time (the engine reads the group's own screen bits): the engine adds (scale - 1) * translate,
  so the values come from `geometry.wrapper_null` exactly as the pictures place the block.
* **Hidden parts**: a part block's place carries the hidden flag when `Arrangement.hides` says so (its own `hidden`,
  else its whole block's); the engine collapses the hidden targets of a group with parts to scale 0 and draws the group
  while one of its parts shows.
* **Absolute**: a block whose priority one place sets must have it set in every place of the mode (or its default):
  else a screen that leaves it out would keep the last screen's.

Nothing here imports the randomizer, the equipment, the ported monsters or the code space: the patch takes the code
space's `Layout` (exefs/game_gui.py passes the committed one)."""

import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from ..arc import parse_arc, write_arc
from ..hud.lyt import LYT_TYPE_HASH, MAX_DEPTH, Layout, LytFormatError, Pane, PaneKind, name_hash, parse_lyt
from . import geometry
from .config import RAW_BUTTONS, Arrangement, Placement, Screen

BLOCK = "game_gui_engine"
TABLE = "game_gui_table"
STATE = "game_gui_state"
FRAME_ENTRY, VIEW_ENTRY, PAD_ENTRY = "gui_engine_frame_hook", "gui_engine_view_hook", "gui_engine_pad_hook"
CARD_BLOCK, CARD_ENTRY = "single_screen_card_info", "card_info_pad"     # the pad update's chain before the photo mode
# sMhMain::frame (FUN_00af52a0): the load of the render's GX, after every system's move; uLayout::draw (FUN_00b047c4):
# the shift before the view test (A2, "the screen at draw time")
FRAME_HOOK, FRAME_WORD = 0xAF555C, bytes.fromhex("900294e5")      # ldr r0, [r4, #0x290]
VIEW_HOOK, VIEW_WORD = 0xB0481C, bytes.fromhex("0117a0e1")        # lsl r1, r1, #0xe
WRAPPER_SUFFIX = "_gg"
PART_SUFFIX = "_ggp"                  # a null a part block's panes (or what follows them) are split off into
MAGIC = 0x31454747                    # "GGE1": a table without it leaves the game alone
VIEWS = {"top": 0, "bottom": 7}       # a root group's view bits for each screen (geometry.RUNTIME_SCREENS)
OWN_SCREENS = ("top", "bottom")       # cx[0], cx[1] of a place: the group's own screen at run time
MAX_NAMES = 4096                      # game_gui_engine.c MAX_NAMES (the shown names' bits on its stack)
NO_INDEX = 0xFFFF
# ... the watched hash, then the photo section's offset and count, the photo mode's two pad masks
HEADER = struct.Struct("<15I2fI4I")
# a photo screen: the screen (index + 1), its first kept hash, their count, the raw pad bit that turns the mode on
# there (the screen's own toggle, else the settings')
PHOTO = struct.Struct("<4H")
NAME = struct.Struct("<I4H")
TARGET = struct.Struct("<I2H")
DIRECT = struct.Struct("<4f")
SCREEN = struct.Struct("<8H")
PLACE = struct.Struct("<H2B4f")
KEEP_VIEW, SET_PRIORITY, HIDDEN = 0x10, 0x20, 0x40
STATE_FORMAT = struct.Struct("<4I")   # frames, screen (index + 1), watched group's + 0x44, table groups met


@dataclass(frozen=True)
class Target:
    """A pane right under a root group that the engine writes: the build's wrapper (`direct` None), or a null whose
    subtree fills the loader's levels, written directly from its file values `direct` = (x, y, scale x, scale y).
    `block`: the part block whose place it takes (None: the block that holds the group)."""
    pane: str
    direct: tuple[float, float, float, float] | None = None
    block: str | None = None


# A wrapper's null record from + 0x0C (after hash, name and size): x, y, z 0, scale 1, 1, opaque white, + 0x24 0,
# + 0x28 1.0, shown: the game's most common null (4,078 of the 5,000 nulls of the Spanish layouts); 34 layouts have
# no null at all, so every wrapper is copied from this one
WRAPPER_RECORD = struct.pack("<3f2f4BIfI", 0.0, 0.0, 0.0, 1.0, 1.0, 255, 255, 255, 255, 0, 1.0, 1)


def _template() -> Pane:
    """The wrapper's template: the null of a layout of one group and one null with WRAPPER_RECORD."""
    from ..hud.lyt import END, HEADER, MAGIC, RECORD_SIZES, VERSION
    kinds = ((PaneKind.GROUP, 0, "gg_donor"), (PaneKind.NULL, 1, "gg_donor_null"))
    table = HEADER.size
    strings_at = table + 8 + sum(RECORD_SIZES[kind] for kind, _, _ in kinds)
    strings = bytearray()
    panes = bytearray(struct.pack("<II", kinds[0][0], kinds[0][1]))
    for i, (kind, _depth, name) in enumerate(kinds):
        record = bytearray(RECORD_SIZES[kind])
        struct.pack_into("<III", record, 0, name_hash(name), strings_at + len(strings), RECORD_SIZES[kind])
        strings += name.encode() + b"\x00"
        if kind == PaneKind.NULL:
            record[0x0C:0x0C + len(WRAPPER_RECORD)] = WRAPPER_RECORD
        following = (kinds[i + 1][0], kinds[i + 1][1]) if i + 1 < len(kinds) else (END, 0)
        struct.pack_into("<II", record, len(record) - 8, *following)
        panes += record
    data = bytearray(HEADER.pack(MAGIC, VERSION, 1, 0, 1, 0, 0, 0, 0, table, table, 0))
    data += panes + strings
    struct.pack_into("<I", data, 0x2C, len(data))
    return parse_lyt(bytes(data)).find("gg_donor_null")


def _deepest(pane: Pane) -> int:
    return max(p.depth for p in pane.walk())


def _split_parts(layout: Layout, group: str, parts: Sequence[tuple[str, Sequence[str]]]) -> dict[str, str]:
    """Each part (block id, its panes) of the root group `group` split off into a null of its own right under the
    group (`Layout.split_off`, named `<first pane>_ggp`), and what follows a part in its null into another one, so each
    part is one pane right under the group and the draw order is kept. Returns the parts' nulls -> block ids."""
    out: dict[str, str] = {}
    places = []
    for block_id, panes in parts:
        found = [layout.find(name) for name in panes]
        parent = found[0].parent
        if parent is None or parent.kind != PaneKind.NULL or parent.parent is None or parent.parent.name != group:
            raise ValueError(f"part block {block_id}: {panes[0]} is not in a null right under {group}")
        names = [child.name for child in parent.children]
        at = sorted(names.index(pane.name) if pane.parent is parent else -1 for pane in found)
        if at[0] < 0 or at != list(range(at[0], at[0] + len(at))):
            raise ValueError(f"part block {block_id}: its panes must be siblings in a row under {parent.name}")
        places.append((parent.name, at[0], at[-1], block_id, names))
    ends: dict[str, int] = {}                    # per null: how many of its first children it still holds
    for parent_name, first, last, block_id, names in sorted(places, key=lambda p: (p[0], -p[1])):
        end = ends.get(parent_name, len(names))
        if last >= end:
            raise ValueError(f"part block {block_id}: its panes are in another part block too")
        if last + 1 < end:                       # what follows the part stays the whole block's, in a null of its own
            layout.split_off(layout.find(names[last + 1]), names[last + 1] + PART_SUFFIX)
        if first == 0:                           # the part is all the null holds now: the null is the part's
            out[parent_name] = block_id
        else:
            layout.split_off(layout.find(names[first]), names[first] + PART_SUFFIX)
            out[names[first] + PART_SUFFIX] = block_id
        ends[parent_name] = first
    return out


def wrap_layout(layout: Layout, groups: Iterable[str], parts: Mapping[str, Sequence[tuple[str, Sequence[str]]]]
                | None = None) -> dict[str, tuple[Target, ...]]:
    """Put wrapper nulls into `layout` (in place) for each root group of `groups`; returns each group's targets (none
    for a group with no panes). `parts`: group -> its part blocks (id, panes), each split off (`_split_parts`) and
    wrapped on its own, a target with the block's id. Raises KeyError for a group the layout lacks, ValueError when a
    pane would pass the loader's last level or a name is taken."""
    out: dict[str, tuple[Target, ...]] = {}
    for group in groups:
        root = layout.find(group)
        if root.kind != PaneKind.GROUP or root.parent is not None:
            raise ValueError(f"{group}: not a root group of the layout")
        if parts and parts.get(group):
            owners = _split_parts(layout, group, parts[group])
            targets = []
            for child_name in [child.name for child in layout.find(group).children]:
                child = layout.find(child_name)
                if _deepest(child) + 1 > MAX_DEPTH:
                    raise ValueError(f"{group}: {child_name} would pass the loader's last level")
                name = child_name + WRAPPER_SUFFIX
                layout.wrap_in_null(child, name, _template(), subtree=child.kind == PaneKind.NULL)
                targets.append(Target(name, block=owners.get(child_name)))
            out[group] = tuple(targets)
            continue
        if not root.children:
            out[group] = ()
            continue
        if _deepest(root) + 1 <= MAX_DEPTH:
            name = group + WRAPPER_SUFFIX
            layout.wrap_children(root, name, _template())
            out[group] = (Target(name),)
            continue
        targets = []
        for child_name in [child.name for child in root.children]:
            child = layout.find(child_name)
            if not child_name:
                raise ValueError(f"{group}: a pane without a name right under it cannot be wrapped")
            if _deepest(child) + 1 <= MAX_DEPTH:
                name = child_name + WRAPPER_SUFFIX
                layout.wrap_in_null(child, name, _template(), subtree=child.kind == PaneKind.NULL)
                targets.append(Target(name))
            elif child.kind == PaneKind.NULL:
                targets.append(Target(child_name, (*child.position, *child.scale)))
            else:
                raise ValueError(f"{group}: {child_name} fills the loader's levels and is not a null")
        out[group] = tuple(targets)
    return out


def unwrap_snapshot(snapshot) -> int:
    """Takes the engine's wrapper nulls (`<name>_gg`, `wrap_layout`) out of a snapshot's groups, in place: a copy taken
    from a single-screen game (the recorder in a probe's session) holds the layouts the build wrapped, which match no
    file of the game; unwrapped it is the game's own tree again, as the pictures read the normal-mode recordings. The
    wrapper's panes go one level up, in its place; its own place (the engine's) goes with it. A part's null
    (`<pane>_ggp`, `_split_parts`) gives its panes back to the null before it, where the game has them. Returns how
    many nulls were taken out."""
    taken = 0

    def lift(pane) -> None:
        pane.depth -= 1
        for child in pane.children:
            lift(child)

    def strip(panes: list) -> list:
        nonlocal taken
        out = []
        for pane in panes:
            if pane.kind == "null" and (pane.name or "").endswith(WRAPPER_SUFFIX):
                taken += 1
                for child in pane.children:
                    lift(child)
                out.extend(pane.children)
            else:
                out.append(pane)
        merged = []
        for pane in out:
            if pane.kind == "null" and (pane.name or "").endswith(PART_SUFFIX) and merged \
                    and merged[-1].kind == "null":
                taken += 1
                merged[-1].children.extend(pane.children)
            else:
                merged.append(pane)
        return merged

    for group in snapshot.groups():
        group.panes = strip(group.panes)
    return taken


def wrap_arc(raw: bytes, wanted: Mapping[str, Iterable[str]],
             parts: Mapping[str, Mapping[str, Sequence[tuple[str, Sequence[str]]]]] | None = None
             ) -> tuple[bytes, dict[str, tuple[Target, ...]]]:
    """The ARC with the root groups `wanted` (layout name -> groups) of each layout it holds wrapped, and their
    targets (`parts`: layout name -> wrap_layout's parts); an ARC with none of them comes back unchanged."""
    arc = parse_arc(raw)
    targets: dict[str, tuple[Target, ...]] = {}
    for entry in arc.entries:
        name = entry.name.replace("/", "\\").split("\\")[-1]
        if entry.type_hash != LYT_TYPE_HASH or name not in wanted:
            continue
        layout = parse_lyt(entry.data)
        try:
            targets |= wrap_layout(layout, wanted[name], (parts or {}).get(name))
        except (KeyError, LytFormatError, ValueError) as error:
            raise ValueError(f"layout {name}: {error}") from None
        entry.data = layout.to_bytes()
    return (write_arc(arc) if targets else raw), targets


def wanted_groups(arrangement: Arrangement) -> dict[str, tuple[str, ...]]:
    """Layout name -> the root groups of every block of it."""
    out: dict[str, list[str]] = {}
    for block in arrangement.blocks.values():
        if not block.part:
            out.setdefault(block.layout, []).extend(block.groups)
    return {name: tuple(groups) for name, groups in out.items()}


def wanted_parts(arrangement: Arrangement) -> dict[str, dict[str, list[tuple[str, tuple[str, ...]]]]]:
    """Layout name -> root group -> its part blocks (id, panes): wrap_layout's `parts`."""
    out: dict[str, dict[str, list[tuple[str, tuple[str, ...]]]]] = {}
    for block in arrangement.blocks.values():
        if block.part:
            out.setdefault(block.layout, {}).setdefault(block.groups[0], []).append((block.id, block.part))
    return out


def engine_files(read, arrangement: Arrangement, paths: Iterable[str],
                 files: Mapping[str, bytes] | None = None) -> tuple[dict[str, bytes], dict[str, tuple[Target, ...]],
                                                                     dict[str, Layout]]:
    """(RomFS path -> ARC with the blocks' groups wrapped, group -> targets, layout name -> the layout as the game has
    it) for the ARCs `paths`; `read(path)` gives the game's bytes, `files` the run's copies made so far (taken first).
    The same layout in several ARCs (languages) must get the same targets."""
    files = files or {}
    wanted = wanted_groups(arrangement)
    out: dict[str, bytes] = {}
    targets: dict[str, tuple[Target, ...]] = {}
    layouts: dict[str, Layout] = {}
    for path in paths:
        raw = files.get(path) or read(path)
        for entry in parse_arc(raw).entries:
            name = entry.name.replace("/", "\\").split("\\")[-1]
            if entry.type_hash == LYT_TYPE_HASH and name in wanted and name not in layouts:
                layouts[name] = parse_lyt(entry.data)
        patched, found = wrap_arc(raw, wanted, wanted_parts(arrangement))
        for group, value in found.items():
            if targets.setdefault(group, value) != value:
                raise ValueError(f"{group}: its layout differs between ARCs ({path})")
        if patched != raw:
            out[path] = patched
    return out, targets, layouts


# ---- the table ---------------------------------------------------------------------------------------------------

def _place_values(placement: Placement, box: geometry.Box | None, declared: str) -> tuple[float, tuple, float]:
    """(scale, cx per own screen, cy): the wrapper null's values at a group translate of 0."""
    if box is None:
        box = (0.0, 0.0, 0.0, 0.0)
    ox, oy = geometry.screen_centre(declared)
    corner = (ox - box[0], oy - box[1])      # the box's top-left corner in layout units: the same on either screen
    cx, cy = [], set()
    for own in OWN_SCREENS:
        px, py = geometry.screen_centre(own)
        moved = (px - corner[0], py - corner[1], px - corner[0], py - corner[1])
        affine = geometry.placement_transform(moved, own, placement.x, placement.y, placement.scale, placement.screen)
        (wx, wy), scale = geometry.wrapper_null(affine, (0.0, 0.0))
        cx.append(wx + 0.0)
        cy.add(wy + 0.0)
    if len(cy) != 1:
        raise ValueError("the two screens' centres differ in height: cy would depend on the group's screen")
    return scale, tuple(cx), cy.pop()


def _identity(placement: Placement) -> bool:
    return placement.x is None and placement.y is None and placement.scale in (None, 1.0)


def engine_table(arrangement: Arrangement, mode: str, targets: Mapping[str, tuple[Target, ...]],
                 layouts: Mapping[str, Layout], own_screens: Mapping[str, str], watch: str | None = None) -> bytes:
    """The engine's table for `mode`'s screens. `targets`: group -> its targets (engine_files; a block without any
    may only change screen, priority and visibility); `layouts`: the layouts as the game has them (the reference
    boxes); `own_screens`: layout name -> the screen the game shows it on ("top" / "bottom"), which the reference box
    is cut to; `watch`: a group whose + 0x44 the engine's state copies every frame (probes)."""
    screens = arrangement.screens_of(mode)
    block_ids = list(arrangement.blocks)
    block_index = {block_id: n for n, block_id in enumerate(block_ids)}
    if len(block_ids) >= NO_INDEX:
        raise ValueError("too many blocks")
    owner = arrangement.owners()
    names = set(owner) | {group for screen in screens for group in screen.when.groups()}
    by_hash: dict[int, str] = {}
    for name in names:
        other = by_hash.setdefault(name_hash(name), name)
        if other != name:
            raise ValueError(f"{name} and {other} have one name hash")
    ordered = [by_hash[h] for h in sorted(by_hash)]
    if len(ordered) > MAX_NAMES:
        raise ValueError(f"{len(ordered)} group names, the engine holds {MAX_NAMES}")
    index = {name: n for n, name in enumerate(ordered)}

    # the places: per block its default, per screen the blocks it names (sorted by block)
    boxes = {}
    for block_id, block in arrangement.blocks.items():
        declared = own_screens.get(block.layout)
        if declared not in OWN_SCREENS:
            raise ValueError(f"block {block_id}: the screen of layout {block.layout} is not given")
        layout = layouts.get(block.layout)
        only, skip = arrangement.box_panes(block_id)
        box = geometry.reference_box(layout, block.groups, declared, only, skip) if layout is not None else None
        boxes[block_id] = (box, declared)
    with_targets = {target.block or owner[group] for group, found in targets.items() if group in owner
                    for target in found}

    def effective(screen: Screen | None, block_id: str) -> tuple[Placement, str]:
        """(placement, the block whose box it places): a part block's own x, y and scale on its group's screen, or
        its whole block's place when it sets none (`Arrangement.follows`); its hiding is its own when it says one, else
        its whole block's (`Arrangement.hides`)."""
        if not arrangement.blocks[block_id].part:
            return arrangement.final(screen, block_id, mode), block_id
        whole = arrangement.whole_of(block_id).id
        whole_place = arrangement.final(screen, whole, mode)
        hidden = arrangement.hides(screen, block_id, mode)
        if arrangement.follows(screen, block_id, mode):
            return replace(whole_place, hidden=hidden), whole
        return replace(arrangement.final(screen, block_id, mode), screen=whole_place.screen, hidden=hidden), block_id

    def place(block_id: str, screen: Screen | None, where: str) -> bytes:
        placement, boxed = effective(screen, block_id)
        box, declared = boxes[boxed]
        if not _identity(placement) or placement.screen is not None:
            if box is None and not _identity(placement):
                raise ValueError(f"{where}, block {block_id}: nothing of it shows as its layout loads (no box)")
            if block_id not in with_targets and not _identity(placement):
                raise ValueError(f"{where}, block {block_id}: x, y or scale need its wrapper nulls (no targets)")
        scale, cx, cy = _place_values(placement, box, declared)
        flags = KEEP_VIEW if placement.screen is None else VIEWS[placement.screen]
        if placement.priority is not None:
            flags |= SET_PRIORITY
        if placement.hidden:
            flags |= HIDDEN
        return PLACE.pack(block_index[block_id], flags, placement.priority or 0, scale, *cx, cy)

    for block_id in block_ids:
        sets = [arrangement.final(screen, block_id).priority is not None for screen in screens]
        sets.append(arrangement.final(None, block_id, mode).priority is not None)
        if any(sets) and not all(sets):
            raise ValueError(f"block {block_id}: a priority set on some screens of {mode} but not all: give it a "
                             "default priority")
    defaults = b"".join(place(block_id, None, "default") for block_id in block_ids)
    entries = bytearray()
    screen_records = bytearray()
    terms: list[int] = []
    count = 0
    for screen in screens:
        record = []
        for group_list in (screen.when.all, screen.when.any, screen.when.none):
            record += [len(terms), len(group_list)]
            terms += [index[group] for group in group_list]
        # a part block's place changes with its whole block's too (it follows it, or keeps its group's screen)
        listed = set(screen.blocks) | {part.id for block_id in screen.blocks for part in arrangement.parts_of(block_id)}
        moved = sorted(listed, key=block_index.__getitem__)
        record += [count, len(moved)]
        for block_id in moved:
            entries += place(block_id, screen, f"screen {screen.id}")
        count += len(moved)
        screen_records += SCREEN.pack(*record)
    if max(len(terms), count, 1) >= 0x10000:
        raise ValueError("too many rule terms or places")

    names_bytes, target_bytes, direct_bytes = bytearray(), bytearray(), bytearray()
    target_count = direct_count = 0
    for name in ordered:
        block_id = owner.get(name)
        found = targets.get(name, ()) if block_id is not None else ()
        names_bytes += NAME.pack(name_hash(name), NO_INDEX if block_id is None else block_index[block_id],
                                 target_count, len(found), 0)
        for target in found:
            direct = NO_INDEX
            if target.direct is not None:
                direct = direct_count
                direct_bytes += DIRECT.pack(*target.direct)
                direct_count += 1
            target_bytes += TARGET.pack(name_hash(target.pane), direct,
                                        NO_INDEX if target.block is None else block_index[target.block])
            target_count += 1
    # the photo mode: a record per screen that asks for it, then the hashes of the groups it keeps drawn
    photo_records, photo_hashes = bytearray(), []
    photo_screens = [(n + 1, screen) for n, screen in enumerate(screens) if screen.photo is not None]
    photo = arrangement.settings.photo
    toggle = dismiss = 0
    if photo_screens:
        if photo is None:
            raise ValueError("a screen asks for the photo mode, the settings give it no buttons")
        toggle = RAW_BUTTONS[photo.toggle]
        dismiss = sum(RAW_BUTTONS[button] for button in photo.dismiss)
    for number, screen in photo_screens:
        if len(photo_hashes) + len(screen.photo) >= 0x10000:
            raise ValueError("too many photo mode groups")
        own = toggle if screen.photo_toggle is None else RAW_BUTTONS[screen.photo_toggle]
        photo_records += PHOTO.pack(number, len(photo_hashes), len(screen.photo), own)
        photo_hashes += [name_hash(name) for name in screen.photo]
    sections = [names_bytes, target_bytes, direct_bytes, screen_records, struct.pack(f"<{len(terms)}H", *terms),
                defaults, bytes(entries), bytes(photo_records) + struct.pack(f"<{len(photo_hashes)}I", *photo_hashes)]
    offsets, at = [], HEADER.size
    for section in sections:
        at = -(-at // 4) * 4
        offsets.append(at)
        at += len(section)
    header = HEADER.pack(MAGIC, len(ordered), target_count, direct_count, len(screens), len(terms), len(block_ids),
                         count, *offsets[:7], *(geometry.screen_centre(s)[0] for s in OWN_SCREENS),
                         name_hash(watch) if watch else 0, offsets[7], len(photo_screens), toggle, dismiss)
    out = bytearray(header)
    for offset, section in zip(offsets, sections):
        out += bytes(offset - len(out)) + section
    return bytes(out)


# ---- the executable ----------------------------------------------------------------------------------------------

def patch_engine(code: bytes, table: bytes, layout, pad_hook: int | None = None) -> bytes:
    """`code` (the canonical executable, extended) with the engine's block, its table (padded to the block's room;
    refused when larger) and its two hooks: sMhMain::frame's load before the render and uLayout::draw's view shift,
    each checked to hold the game's instruction first. `layout`: the code space's Layout (exefs/code_space.py).
    With `pad_hook` (the pad update's call, which the guild card's block already took: exefs/single_screen.py) the photo
    mode's entry is chained after that block: it calls the block and then reads the pad words the chain left; the hook
    refuses a call that is not the card's."""
    block = layout.block(TABLE)
    room = block.end - block.address
    if len(table) > room:
        raise ValueError(f"the engine's table takes {len(table)} bytes, its block holds {room}")
    out = bytearray(code)
    layout.place(out, TABLE, table + bytes(room - len(table)))
    layout.place(out, BLOCK)
    layout.hook(out, FRAME_HOOK, layout.symbol(BLOCK, FRAME_ENTRY), original=FRAME_WORD)
    layout.hook(out, VIEW_HOOK, layout.symbol(BLOCK, VIEW_ENTRY), original=VIEW_WORD)
    if pad_hook is not None:
        layout.hook(out, pad_hook, layout.symbol(BLOCK, PAD_ENTRY), calls=layout.symbol(CARD_BLOCK, CARD_ENTRY))
    return bytes(out)


def read_state(data: bytes) -> dict[str, int]:
    """The engine's state variable (16 bytes read from `game_gui_state`): frames run, the screen chosen (index + 1,
    0 none), the watched group's + 0x44 and the table's groups met in the last frame."""
    frames, screen, watch, groups = STATE_FORMAT.unpack(data[:STATE_FORMAT.size])
    return {"frames": frames, "screen": screen, "watch_flags": watch, "groups": groups}
