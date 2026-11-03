"""The single-screen mode's executable side (emulator only): layouts of the touch
screen loaded on the top screen, and their draw order there.

* Screen: each layout's screen byte in its loader list (0 top, 1 bottom) and the code that forces it to the bottom at
  run time, every byte checked first (`SCREEN_PATCHES`).
* Draw order: block `single_screen_priority` hooks the start of FUN_00ae63c8(group, layer, priority), the only writer
  of a group's layer and priority, and adds an offset to the priority of the groups listed in
  `single_screen_priorities` (their name hashes), so a moved layout is drawn in front of the top screen's own.
* The new game's character creation: ui800 and ui415 on the top screen and its 3D model in the strip left of them
  (interface/single_screen/executable/single_screen_creation.py, merged here: `SCREEN_PATCHES`, the camera block, the
  name boards shown on the main menu only, the pad's left / right between the Aceptar and Atrás buttons).
* The yes / no boxes: ui006 stays on the bottom screen (its help panel is every menu's); block `single_screen_prompt`,
  called from the pad update every frame, moves its groups to the top screen while a yes / no prompt is open, and the
  description panel alone (`help_top`) to a free strip of the top screen while a touch menu is.
* The Canteen's pay buttons (ui006) stand in a row on the top screen with the panel (a `help_top` place's `groups`), and
  the pay choice's cursor takes the pad's left / right (block `single_screen_pay`).
* The new game's touch-panel layout choice (A / B) is skipped and B taken
  (interface/single_screen/executable/single_screen_layout.py).
* The name keyboard: opens on the top screen, driven with the pad by a virtual finger
  (interface/single_screen/executable/single_screen_keyboard.py).
* The World Map (ui430): on the top screen, opened with X and driven with the pad
  (interface/single_screen/executable/single_screen_world_map.py).
* The facilities' menus (the Wyporio's ui405, "Mi set" ui417, the talisman choice ui474, the Camaradas' board ui481):
  on the top screen by their loader bytes and binding loops
  (interface/single_screen/executable/single_screen_facilities.py, merged here).
* The Arena's team and weapon choice (ui497, placed by the game GUI engine): the info panels' places its scene's code
  writes, from rodata tables (interface/single_screen/executable/single_screen_quests.py, `patch_arena_choice`), and its
  pad (interface/single_screen/executable/single_screen_arena.py).
* The Palico menus of the board: "Main Palico Info" (ui471) on the top screen
  (interface/single_screen/executable/single_screen_palico.py, merged here), and the frames that make the shared panels
  smaller there (interface/single_screen/executable/single_screen_frames.py).
* The layouts of the game GUI arrangement (the help theme: the Ayuda topics menu ui560, the help window ui011; the
  multiplayer menus ui490, ui501-ui504, ui511, ui530, ui060; the quests and Arena theme: the quest board ui413, the
  Arena's ui495-ui498): placed by the game GUI engine (`engine_table`, interface/game_gui/build.py), their screen bytes
  the game's.
* The Meownster Hunters' minigame: on the top screen by its scene's three loaders
  (interface/single_screen/executable/single_screen_monnyan.py, merged here: `SCREEN_PATCHES`).
* The layouts add panes the game's pools were not sized for: the GUI manager's null pool is made larger
  (interface/single_screen/executable/single_screen_pools.py, curated `gui_pools`).

The run applies it with `patch_single_screen` (setting `single_screen`, emulator only; probes:
research/probes/single_screen_probe.py), on the canonical executable like every patcher;
its blocks are the product's (game/executable/blocks.py).
"""

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.files.gui.lyt import name_hash
from core.game.executable.blocks import SINGLE_SCREEN_ROOM, SINGLE_SCREEN_TABLE_SIZE
from core.interface.single_screen.executable import single_screen_creation as creation
from core.interface.single_screen.executable import single_screen_quests as quests
from core.interface.single_screen.executable import single_screen_arena as arena_pad
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, branch_word, load_layout
from core.interface.single_screen.executable.single_screen_layout import (
    patch_layout_choice, patch_layout_load, supports_layout_choice, supports_layout_load
)
from core.interface.single_screen.executable.single_screen_keyboard import patch_keyboard, supports_keyboard
from core.interface.single_screen.executable import single_screen_world_map as world_map
from core.interface.single_screen.executable import single_screen_others as others
from core.interface.single_screen.executable import single_screen_facilities as facilities
from core.interface.single_screen.executable import single_screen_palico as palico
from core.interface.single_screen.executable.single_screen_frames import patch_frames
from core.interface.single_screen.executable import single_screen_multiplayer as multiplayer
from core.interface.single_screen.executable import single_screen_monnyan as monnyan
from core.interface.single_screen.executable.single_screen_map_hint import patch_map_hint
from core.interface.single_screen.executable.single_screen_minimap import patch_minimap
from core.interface.single_screen.executable.single_screen_card_info import patch_card_info
from core.interface.single_screen.executable.single_screen_board import (
    board_page_shift, patch_board_page, supports_board_page,
)
from core.interface.single_screen.executable.single_screen_page_counters import (
    page_counter_shifts, patch_page_counters, supports_page_counters,
)
from core.interface.single_screen.executable.single_screen_farm_carts import patch_farm_carts, supports_farm_carts
from core.interface.single_screen.executable.single_screen_pools import gui_pool_nulls, patch_pools, supports_pools
from core.interface.game_gui import engine as game_gui_engine
from core.interface.game_gui.game_gui import patch_game_gui

SETTINGS_FILE = CURATED_DIR / "single_screen.json"

# the game GUI engine's two sites (interface/game_gui/engine.py): sMhMain::frame's load before the render,
# uLayout::draw's shift
ENGINE_SITES = ((game_gui_engine.FRAME_HOOK, game_gui_engine.FRAME_WORD),
                (game_gui_engine.VIEW_HOOK, game_gui_engine.VIEW_WORD))
PRIORITY_HOOK = 0xAE63C8             # FUN_00ae63c8(group, layer, priority): ldr r3, [r0, #0x18]
PRIORITY_ORIGINAL = struct.pack("<I", 0xE5903018)

# ui006 (yes / no boxes, menu help) up only while a prompt is open: block single_screen_prompt, run every frame
PAD_UPDATE_HOOK = 0x694CE0           # FUN_00694ccc, the pad update: bl FUN_005b8284
PAD_UPDATE_CALLEE = 0x5B8284
GROUP_CHANGED = 0xAE65B0             # FUN_00ae65b0(group)
GUI_POINTER = 0x1057534
UI006_OWNER = 0x109CDC8              # its ten group pointers, button kinds at +0x1F8, bound at +0x21F
UI006_TABLE = 0xDF9E8C               # its binder table: 12-byte entries, name hash first
UI006_GROUPS = 10

# The Canteen's pay choice (FUN_009fcd68, its cursor; one caller): the call of the cursor step takes the pad's left and
# right as up and down (block single_screen_pay)
PAY_PAD_HOOK = 0x9FCDBC              # bl FUN_005e70bc(cursor, count, pressed, 1, 2)
PAY_PAD_CALLEE = 0x5E70BC

# the boot's choose-character scene: the hunter's and the Felyne's x, one float
# literal each (single reader: a `vldr`); positive = screen right
HUNTER_X = 0xBDFF80
HUNTER_X_ORIGINAL = struct.pack("<f", 40.0)
FELYNE_X = 0xBDFF88
FELYNE_X_ORIGINAL = struct.pack("<f", -60.0)
# their turns (rotation y, a word stored at model + 0x24; 65536 = 360 degrees; the game's own: hunter -5, Felyne +10)
HUNTER_TURN = 0xBE03B4
HUNTER_TURN_ORIGINAL = struct.pack("<I", 0xFC73)
FELYNE_TURN = 0xBE03CC
FELYNE_TURN_ORIGINAL = struct.pack("<I", 0x071C)
CAMERA_Z = 0xBE12A4                  # the camera's eye z (FUN_00be1078's literals; eye x 0, models at z 0)
CAMERA_Z_ORIGINAL = struct.pack("<f", 305.0)
CHARACTER_LITERALS = ((HUNTER_X, HUNTER_X_ORIGINAL), (FELYNE_X, FELYNE_X_ORIGINAL), (HUNTER_TURN, HUNTER_TURN_ORIGINAL),
                      (FELYNE_TURN, FELYNE_TURN_ORIGINAL), (CAMERA_Z, CAMERA_Z_ORIGINAL))
CHARACTER_SHIFT_MAX = 110            # the hunter clips past about x 150

# the touch menu bar's shift: the floats FUN_0028bfa0
# and FUN_0028beac read, by the bar's place and a second index: on top 0, 0; at the bottom 36, 30
BAR_SHIFT_TABLE = 0xDF53C8
BAR_SHIFT_ORIGINAL = struct.pack("<2f", 36.0, 30.0)
BAR_SHIFT_AT_BOTTOM = BAR_SHIFT_TABLE + 8

SCREEN_PATCHES: dict[str, tuple[tuple[int, bytes, bytes], ...]] = {
    # the quest list: the lobby list's byte (FUN_00c0ff8c, index 2); its binder FUN_009e6910 keeps the loader's screen
    "ui409": ((0xEFE002, b"\x01", b"\x00"),),
    # the Canteen's ingredients: the lobby list's byte (index 6), and FUN_009e32e8, which moves its 17 groups to
    # *(gui + 0x246) (the bottom) on every visit: `ldrb r1, [r1, #0x246]` -> `#0x245` (the top)
    "ui419": ((0xEFE006, b"\x01", b"\x00"),
              (0x9E3408, struct.pack("<I", 0xE5D11246), struct.pack("<I", 0xE5D11245))),
    # the page indicator "1/3": the common list's byte (FUN_00c10740, index 24 of the paths at 0xEFDC60, bytes 0xEFDCE8)
    # and its binder table (FUN_00595c30 -> FUN_00584c08, 0xDFBF00: yazi00, yazi01, yazi02, kind byte at +4), whose
    # kind 1 would put the groups back on the bottom at every bind
    "ui036": ((0xEFDD00, b"\x01", b"\x00"),
              (0xDFBF04, b"\x01", b"\x00"), (0xDFBF10, b"\x01", b"\x00"), (0xDFBF1C, b"\x01", b"\x00")),
    # the Guild's help pages (Hunter Info, Monster List: the topic's paper, title tab and text): the common list's byte
    # (FUN_00c10740, index 13) and its binder table (FUN_00584c08 at 0xDFB3FC: ui032's seven root groups, kind byte at
    # +4), whose kind 1 would put the groups back on the bottom at every bind
    "ui032": ((0xEFDCE8 + 13, b"\x01", b"\x00"),
              *((0xDFB3FC + 12 * n + 4, b"\x01", b"\x00") for n in range(7))),
    # the generic dialog (the creation's "back?" confirms, the shops' yes / no, the save's spinner): the common list's
    # byte (index 26) and its binder table (FUN_0058e280 -> FUN_00584c08 at every opening, 0xDFA9A0: l_bg, YN_window,
    # YN_window_1, loading), whose kind 2 would put the groups back on the bottom
    "ui015": ((0xEFDD02, b"\x01", b"\x00"),
              (0xDFA9A4, b"\x02", b"\x00"), (0xDFA9B0, b"\x02", b"\x00"), (0xDFA9BC, b"\x02", b"\x00"),
              (0xDFA9C8, b"\x02", b"\x00")),
}
SCREEN_PATCHES.update(creation.SCREEN_PATCHES)       # the character creation's ui800 and ui415
SCREEN_PATCHES.update(world_map.SCREEN_PATCHES)          # the world map's ui430
SCREEN_PATCHES.update(others.SCREEN_PATCHES)             # "Contenido adicional" (ui521, ui541) and "Gestos y frases"
SCREEN_PATCHES.update(facilities.SCREEN_PATCHES)         # the Wyporio's ui405, Mi set's ui417, ui474, the board's ui481
SCREEN_PATCHES.update(palico.SCREEN_PATCHES)             # the Palico menus' "Main Palico Info" (ui471)
SCREEN_PATCHES.update(multiplayer.SCREEN_PATCHES)        # the hall's member list (ui500)
SCREEN_PATCHES.update(monnyan.SCREEN_PATCHES)            # the Meownster Hunters' minigame (ui700...)


def top_screen_layouts(path: Path = SETTINGS_FILE) -> tuple[str, ...]:
    """The curated layouts loaded on the top screen (single_screen.json, "top_screen")."""
    names = tuple(json.loads(Path(path).read_text(encoding="utf-8"))["top_screen"])
    unknown = [name for name in names if name not in SCREEN_PATCHES]
    if unknown:
        raise ValueError(f"single_screen.json, top_screen: no screen patch for {', '.join(unknown)}")
    return names


def character_shift(path: Path = SETTINGS_FILE) -> float:
    """How far the choose-character models move right (single_screen.json, "character_shift")."""
    value = json.loads(Path(path).read_text(encoding="utf-8")).get("character_shift", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= CHARACTER_SHIFT_MAX:
        raise ValueError(f"single_screen.json, character_shift: a number from 0 to {CHARACTER_SHIFT_MAX}")
    return value


def prompt_stay_bottom(path: Path = SETTINGS_FILE) -> tuple[str, ...]:
    """The ui006 groups left on the touch screen during a prompt (single_screen.json, "prompt_stay_bottom")."""
    names = json.loads(Path(path).read_text(encoding="utf-8")).get("prompt_stay_bottom", [])
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("single_screen.json, prompt_stay_bottom: a list of group names")
    return tuple(names)


# The description panel (ui006_help00 / help01) on the top screen: the block scans the GUI's group list once for the
# names of a table, each with the bits of what it
# takes part in, and decides from the bits.
HELP_PLACES = 24                     # the most places the curated "help_top" may list (the block's help_places room)
PLACE_BITS = range(2, 30)            # the scan bits the places' when and unless lists share (place_masks)
HELP_SCAN = 128                      # the most distinct group names the block's scan table holds
HELP_EXTRAS = 16                     # the most (place, other ui006 group) shifts the block's extra table holds
PLACE_SIZE = 16                      # a place's record: when mask, unless mask, x, y (float)
EXTRA_SIZE = 16                      # an extra's record: place index, ui006 table index, x, y (float)
BIT_MENU, BIT_STAY = 1, 2            # a creation menu group, a group that keeps the panel on the touch screen
BIT_NO_MENU = 1 << 30                # a group of creation_prompt.unless: no creation menu while it is shown
NO_PANEL = 1 << 31                   # in a place's unless word (never a scan bit): the place leaves the panel down
HELP_FLAGS = ("layered_preview.shown",)    # the one variable flag the block reads (layered_preview + 9)
GAME_MODES = 32                      # the game modes (the game control's byte +0x2B) quest_kinds has a bit for


def place_masks(places) -> list[tuple[int, int]]:
    """Each place's (when mask, unless mask), in order: a scan bit of its own for a non-empty `when` (a group in it),
    another for a non-empty `unless` (a group in it, or a flag), 0 for an empty list (the block takes a when of 0 as
    always and an unless of 0 as never). The bits are PLACE_BITS, one each; CodeSpaceError when they run out."""
    free = iter(PLACE_BITS)
    out = []
    for place in places:
        try:
            when = 1 << next(free) if place.when else 0
            unless = 1 << next(free) if place.unless or place.flags else 0
        except StopIteration:
            raise CodeSpaceError(f"help_top: the places' when and unless lists need more than the "
                                 f"{len(PLACE_BITS)} scan bits the block has (at {place.name})") from None
        out.append((when, unless))
    return out


@dataclass(frozen=True)
class HelpPlace:
    """A strip of the top screen the panel may take: the first place whose `when` is empty or has a group shown, and
    whose `unless` has none shown (nor a flag of `flags` set), puts it there, `shift` pixels right and down from the
    layout's own place. `groups`: other ui006 groups (the Canteen's pay buttons) that go to the top screen with the
    panel while this place is chosen, each at its own shift (name, (dx, dy)); every other group stays down. `panel`
    false: the place leaves the description panel itself down (a menu whose own panels fill the strips: only its
    `groups` come up). `quest`: the place may be taken in a quest (a game mode of HelpTop.quest_scenes); every other
    place is skipped there."""
    name: str
    when: tuple[str, ...]
    unless: tuple[str, ...]
    flags: tuple[str, ...]
    shift: tuple[float, float]
    groups: tuple[tuple[str, tuple[float, float]], ...] = ()
    panel: bool = True
    quest: bool = False


@dataclass(frozen=True)
class HelpTop:
    """The curated `help_top`: the panel's group, the groups that move with it (`also`), its places in order, the
    groups that keep it on the touch screen while shown, and the game modes (the game control's byte +0x2B) that are a
    quest, where only the places marked `quest` may be taken."""
    group: str = ""
    also: tuple[str, ...] = ()
    places: tuple[HelpPlace, ...] = ()
    stay_bottom: tuple[str, ...] = ()
    quest_scenes: tuple[int, ...] = ()


def _strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(name, str) and name for name in value):
        raise ValueError(f"{where}: a list of names")
    return tuple(value)


def _shift(value: object, where: str) -> tuple[float, float]:
    if (not isinstance(value, list) or len(value) != 2 or any(
            isinstance(n, bool) or not isinstance(n, int | float) or abs(n) > creation.SHIFT_LIMIT for n in value)):
        raise ValueError(f"{where}: [dx, dy] pixels (at most {creation.SHIFT_LIMIT})")
    return float(value[0]), float(value[1])


def help_top(path: Path = SETTINGS_FILE) -> HelpTop:
    """The curated `help_top` of single_screen.json (none: the panel stays on the touch screen)."""
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("help_top")
    if record is None:
        return HelpTop()
    where = "single_screen.json, help_top"
    if not isinstance(record, dict) or not {"group", "places", "stay_bottom"} <= set(record) <= {
            "group", "also", "places", "stay_bottom", "quest_scenes"}:
        raise ValueError(f"{where}: needs group, places and stay_bottom (and may have also, quest_scenes), "
                         f"nothing else")
    modes = record.get("quest_scenes", [])
    if not isinstance(modes, list) or not all(
            isinstance(n, int) and not isinstance(n, bool) and 0 <= n < GAME_MODES for n in modes):
        raise ValueError(f"{where}, quest_scenes: game modes (0 to {GAME_MODES - 1})")
    group = record["group"]
    if not isinstance(group, str) or not group:
        raise ValueError(f"{where}, group: a ui006 group name")
    places = []
    if not isinstance(record["places"], list):
        raise ValueError(f"{where}, places: a list")
    for item in record["places"]:
        if not isinstance(item, dict) or not {"name", "when", "unless", "shift"} <= set(item) <= {
                "name", "when", "unless", "unless_flags", "shift", "groups", "panel", "quest"} or not isinstance(
                item["name"], str):
            raise ValueError(f"{where}, places: name, when, unless and shift (and unless_flags, groups, panel, quest) "
                             f"each")
        at = f"{where}, place {item['name']}"
        if not isinstance(item.get("panel", True), bool):
            raise ValueError(f"{at}, panel: true or false")
        if not isinstance(item.get("quest", False), bool):
            raise ValueError(f"{at}, quest: true or false")
        groups = item.get("groups", {})
        if not isinstance(groups, dict) or not all(isinstance(name, str) and name for name in groups):
            raise ValueError(f"{at}, groups: ui006 group name -> [dx, dy] pixels")
        places.append(HelpPlace(item["name"], _strings(item["when"], f"{at}, when"),
                                _strings(item["unless"], f"{at}, unless"),
                                _strings(item.get("unless_flags", []), f"{at}, unless_flags"),
                                _shift(item["shift"], f"{at}, shift"),
                                tuple((name, _shift(value, f"{at}, groups, {name}"))
                                      for name, value in groups.items()), item.get("panel", True),
                                item.get("quest", False)))
    return HelpTop(group, _strings(record.get("also", []), f"{where}, also"), tuple(places),
                   _strings(record["stay_bottom"], f"{where}, stay_bottom"), tuple(modes))


@dataclass(frozen=True)
class HelpTables:
    """What the block's tables hold: the scan table (name hash, bits; a 0 hash ends it), the places' records, how many
    there are, which ui006 table entries are the panel (bit n: entry n), the bits the variable flag sets and the extra
    table (place index, ui006 table index, x, y per record) with its count; the quest words: bit n of `quest_kinds` for
    game mode n a quest, bit i of `quest_places` for place i one a quest may take."""
    scan: bytes
    places: bytes
    count: int
    help_mask: int
    flag_mask: int
    extras: bytes = b""
    extra_count: int = 0
    quest_kinds: int = 0
    quest_places: int = 0


def help_tables(code: bytes, top: HelpTop, menu: creation.CreationPrompt) -> HelpTables:
    """The block's scan and place tables for the curated `top` and creation `menu`; the sizes the block holds and the
    names of ui006's binder table are checked here."""
    if len(top.places) > HELP_PLACES:
        raise CodeSpaceError(f"help_top: {len(top.places)} places, the block holds {HELP_PLACES}")
    hashes = [struct.unpack_from("<I", code, UI006_TABLE + 12 * n - BASE_ADDRESS)[0] for n in range(UI006_GROUPS)]
    help_mask = 0
    for name in ((top.group, *top.also) if top.group else ()):
        if name_hash(name) not in hashes:
            raise CodeSpaceError(f"help_top: {name!r} is not in ui006's binder table")
        help_mask |= 1 << hashes.index(name_hash(name))
    bits: dict[int, int] = {}
    for name in menu.groups:
        bits[name_hash(name)] = bits.get(name_hash(name), 0) | BIT_MENU
    for name in menu.unless:
        bits[name_hash(name)] = bits.get(name_hash(name), 0) | BIT_NO_MENU
    for name in top.stay_bottom:
        bits[name_hash(name)] = bits.get(name_hash(name), 0) | BIT_STAY
    records, extras, flag_mask = [], [], 0
    masks = place_masks(top.places)
    for index, place in enumerate(top.places):
        seen = set()
        for name, shift in place.groups:
            if name_hash(name) not in hashes:
                raise CodeSpaceError(f"help_top, place {place.name}: {name!r} is not in ui006's binder table")
            at = hashes.index(name_hash(name))
            if help_mask >> at & 1 or at in seen:
                raise CodeSpaceError(f"help_top, place {place.name}: {name!r} is the panel or listed twice")
            seen.add(at)
            extras.append(struct.pack("<IIff", index, at, 0.0 - shift[0], 0.0 - shift[1]))
        when, unless = masks[index]
        for name in place.when:
            bits[name_hash(name)] = bits.get(name_hash(name), 0) | when
        for name in place.unless:
            bits[name_hash(name)] = bits.get(name_hash(name), 0) | unless
        for flag in place.flags:
            if flag not in HELP_FLAGS:
                raise CodeSpaceError(f"help_top, place {place.name}: no flag {flag!r} (the block reads {HELP_FLAGS})")
            flag_mask |= unless
        # 0.0 - n: no negative zero for a shift of 0 (the block compares the floats' bits to the group's)
        records.append(struct.pack("<IIff", when, unless | (0 if place.panel else NO_PANEL),
                                   0.0 - place.shift[0], 0.0 - place.shift[1]))
    if len(bits) > HELP_SCAN:
        raise CodeSpaceError(f"{len(bits)} group names to scan for, the block's table holds {HELP_SCAN}")
    if len(extras) > HELP_EXTRAS:
        raise CodeSpaceError(f"help_top: {len(extras)} shifts of other ui006 groups, the block holds {HELP_EXTRAS}")
    scan = b"".join(struct.pack("<II", group, mask) for group, mask in bits.items())
    return HelpTables(scan.ljust(8 * (HELP_SCAN + 1), b"\0"), b"".join(records).ljust(PLACE_SIZE * HELP_PLACES, b"\0"),
                      len(records), help_mask, flag_mask, b"".join(extras).ljust(EXTRA_SIZE * HELP_EXTRAS, b"\0"),
                      len(extras), sum(1 << mode for mode in set(top.quest_scenes)),
                      sum(1 << index for index, place in enumerate(top.places) if place.quest))


def prompt_stay_mask(code: bytes, names) -> int:
    """The bit mask (bit n: entry n of ui006's binder table) of the groups `names`, found by name hash in `code`."""
    hashes = [struct.unpack_from("<I", code, UI006_TABLE + 12 * n - BASE_ADDRESS)[0] for n in range(UI006_GROUPS)]
    mask = 0
    for name in names:
        if name_hash(name) not in hashes:
            raise CodeSpaceError(f"prompt_stay_bottom: {name!r} is not in ui006's binder table")
        mask |= 1 << hashes.index(name_hash(name))
    return mask


def patch_screens(code: bytes, layouts) -> bytes:
    """`code` with each layout of `layouts` (names of SCREEN_PATCHES) loaded on the top screen."""
    out = bytearray(code)
    for name in layouts:
        if name not in SCREEN_PATCHES:
            raise CodeSpaceError(f"no screen patch for layout {name!r}")
        for address, old, new in SCREEN_PATCHES[name]:
            at = address - BASE_ADDRESS
            if out[at:at + len(old)] != old:
                raise CodeSpaceError(f"{name} at {address:#x}: {out[at:at + len(old)].hex()} is not the update's "
                                     f"{old.hex()} (another executable, or already patched)")
            out[at:at + len(new)] = new
    return bytes(out)


def patch_character_models(code: bytes, shift: float) -> bytes:
    """`code` with the choose-character scene's hunter and Felyne `shift` world units to the screen's right, each
    turned by the change of its bearing from the camera so it faces it as the game has it."""
    out = bytearray(code)
    for address, old in CHARACTER_LITERALS:
        at = address - BASE_ADDRESS
        if out[at:at + 4] != old:
            raise CodeSpaceError(f"character model literal at {address:#x}: {out[at:at + 4].hex()} is not the "
                                 f"update's {old.hex()} (another executable, or already patched)")
    if not shift:
        return bytes(code)
    camera_z = struct.unpack("<f", CAMERA_Z_ORIGINAL)[0]
    for x_at, x_old, turn_at, turn_old in ((HUNTER_X, HUNTER_X_ORIGINAL, HUNTER_TURN, HUNTER_TURN_ORIGINAL),
                                           (FELYNE_X, FELYNE_X_ORIGINAL, FELYNE_TURN, FELYNE_TURN_ORIGINAL)):
        x = struct.unpack("<f", x_old)[0]
        bearing = math.atan((x + shift) / camera_z) - math.atan(x / camera_z)
        turn = (struct.unpack("<I", turn_old)[0] - round(bearing * 0x10000 / math.tau)) & 0xFFFF
        struct.pack_into("<f", out, x_at - BASE_ADDRESS, x + shift)
        struct.pack_into("<I", out, turn_at - BASE_ADDRESS, turn)
    return bytes(out)


def patch_bar_shift(code: bytes) -> bytes:
    """`code` with the shift of the touch menu bar at the bottom at 0: FUN_0028bfa0 and FUN_0028beac read it from this
    table for the groups' second translate, and it moved the groups on the top screen too."""
    at = BAR_SHIFT_AT_BOTTOM - BASE_ADDRESS
    if code[at:at + len(BAR_SHIFT_ORIGINAL)] != BAR_SHIFT_ORIGINAL:
        raise CodeSpaceError(f"touch bar shift at {BAR_SHIFT_AT_BOTTOM:#x}: {code[at:at + 8].hex()} is not the "
                             f"update's {BAR_SHIFT_ORIGINAL.hex()} (another executable, or already patched)")
    return code[:at] + bytes(len(BAR_SHIFT_ORIGINAL)) + code[at + len(BAR_SHIFT_ORIGINAL):]


def priority_table(offsets: dict[int, int]) -> bytes:
    """Block `single_screen_priorities`: the count, then {name hash, offset} per group, zero-padded."""
    if len(offsets) > SINGLE_SCREEN_ROOM:
        raise CodeSpaceError(f"{len(offsets)} groups: the priority table holds {SINGLE_SCREEN_ROOM}")
    pairs = b"".join(struct.pack("<Ii", group, offset) for group, offset in offsets.items())
    return (struct.pack("<I", len(offsets)) + pairs).ljust(SINGLE_SCREEN_TABLE_SIZE, b"\0")


def patch_priorities(code: bytes, offsets: dict[int, int], layout: Layout | None = None) -> bytes:
    """`code` (extended) where the groups of `offsets` (name hash -> offset) are drawn with that offset added to their
    priority."""
    layout = layout or load_layout()
    table = priority_table(offsets)
    out = bytearray(code)
    layout.place(out, "single_screen_priority")
    layout.place(out, "single_screen_priorities", table)
    layout.hook(out, PRIORITY_HOOK, layout.symbol("single_screen_priority", "priority_hook"),
                original=PRIORITY_ORIGINAL, link=False)
    return bytes(out)


def prompt_menu_tables(code: bytes, menu: creation.CreationPrompt) -> tuple[bytes, bytes]:
    """The block's `menu_hashes` (the name hashes of `menu.groups`, a 0 word after them) and `menu_shift` (per entry of
    ui006's binder table the layout-unit x, y floats: both grow to the screen's left and top, so the curated pixels are
    negated)."""
    hashes = [struct.unpack_from("<I", code, UI006_TABLE + 12 * n - BASE_ADDRESS)[0] for n in range(UI006_GROUPS)]
    shift = [0.0] * (2 * UI006_GROUPS)
    for name, dx, dy in menu.shift:
        if name_hash(name) not in hashes:
            raise CodeSpaceError(f"creation_prompt: {name!r} is not in ui006's binder table")
        at = hashes.index(name_hash(name))
        shift[2 * at], shift[2 * at + 1] = -dx, -dy
    listed = [name_hash(name) for name in menu.groups]
    return (struct.pack(f"<{creation.MENU_GROUPS + 1}I", *listed, *[0] * (creation.MENU_GROUPS + 1 - len(listed))),
            struct.pack(f"<{2 * UI006_GROUPS}f", *shift))


def patch_prompt_screen(code: bytes, stay_bottom=(), layout: Layout | None = None,
                        menu: creation.CreationPrompt | None = None, top: HelpTop | None = None) -> bytes:
    """`code` (extended) where ui006, loaded on the bottom screen, is on the top one while a yes / no prompt is open,
    except its groups named in `stay_bottom` (left alone); with `menu` (the curated creation prompt) also while one of
    its groups is shown, each ui006 group then at the place `menu` gives it; with `top` (the curated help_top) the
    description panel alone goes to the first free place of `top` while a touch menu is open."""
    layout = layout or load_layout()
    block = layout.block("single_screen_prompt")
    data = bytearray(block.data)
    menu = menu or creation.CreationPrompt()
    tables = help_tables(code, top or HelpTop(), menu)
    _hashes, shift = prompt_menu_tables(code, menu)

    def put(symbol: str, value: bytes) -> None:
        at = layout.symbol("single_screen_prompt", symbol) - block.address
        data[at:at + len(value)] = value

    put("stay_mask", struct.pack("<I", prompt_stay_mask(code, stay_bottom)))
    put("help_mask", struct.pack("<I", tables.help_mask))
    put("flag_mask", struct.pack("<I", tables.flag_mask))
    put("help_count", struct.pack("<I", tables.count))
    put("menu_shift", shift)
    put("help_places", tables.places)
    put("extra_count", struct.pack("<I", tables.extra_count))
    put("extra_table", tables.extras)
    put("scan_table", tables.scan)
    put("quest_kinds", struct.pack("<I", tables.quest_kinds))
    put("quest_places", struct.pack("<I", tables.quest_places))
    out = bytearray(code)
    layout.place(out, "single_screen_prompt", bytes(data))
    layout.hook(out, PAD_UPDATE_HOOK, layout.symbol("single_screen_prompt", "prompt_screen"), calls=PAD_UPDATE_CALLEE)
    return bytes(out)


def supports_pay_pad(code: bytes) -> bool:
    """True if the pay choice's call of the cursor step is the game's own (the canonical executable, unpatched)."""
    try:
        return code[PAY_PAD_HOOK - BASE_ADDRESS:PAY_PAD_HOOK - BASE_ADDRESS + 4] == branch_word(
            PAY_PAD_HOOK, PAY_PAD_CALLEE, link=True)
    except IndexError:
        return False


def patch_pay_pad(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (extended) where the Canteen's pay choice also steps its cursor on the pad's left and right (block
    `single_screen_pay`): the call of the cursor step in FUN_009fcd68 goes through the block."""
    layout = layout or load_layout()
    if not supports_pay_pad(code):
        raise CodeSpaceError(f"pay choice: the call at {PAY_PAD_HOOK:#x} is not the update's (another executable, or "
                             "already patched)")
    out = bytearray(code)
    layout.place(out, "single_screen_pay")
    layout.hook(out, PAY_PAD_HOOK, layout.symbol("single_screen_pay", "pay_pad"), calls=PAY_PAD_CALLEE)
    return bytes(out)


def supports_single_screen(code: bytes) -> bool:
    """True if every byte the mode changes is the game's own (the canonical executable, not yet patched)."""
    try:
        return (all(code[a - BASE_ADDRESS:a - BASE_ADDRESS + len(old)] == old
                    for edits in SCREEN_PATCHES.values() for a, old, _new in edits)
                and all(code[a - BASE_ADDRESS:a - BASE_ADDRESS + 4] == old for a, old in CHARACTER_LITERALS)
                and code[BAR_SHIFT_AT_BOTTOM - BASE_ADDRESS:][:8] == BAR_SHIFT_ORIGINAL
                and creation.supports_creation_camera(code)
                and creation.supports_creation_panel(code)
                and creation.supports_creation_boards(code)
                and creation.supports_creation_pad(code)
                and supports_keyboard(code)
                and supports_pay_pad(code)
                and world_map.supports_world_map(code)
                and code[PRIORITY_HOOK - BASE_ADDRESS:PRIORITY_HOOK - BASE_ADDRESS + 4] == PRIORITY_ORIGINAL
                and code[PAD_UPDATE_HOOK - BASE_ADDRESS:PAD_UPDATE_HOOK - BASE_ADDRESS + 4]
                == branch_word(PAD_UPDATE_HOOK, PAD_UPDATE_CALLEE, link=True)
                and supports_layout_choice(code)
                and supports_layout_load(code)
                and quests.supports_arena_choice(code)
                and arena_pad.supports_arena_pad(code)
                and supports_pools(code)
                and supports_board_page(code)
                and supports_page_counters(code)
                and supports_farm_carts(code)
                and all(code[a - BASE_ADDRESS:a - BASE_ADDRESS + 4] == word for a, word in ENGINE_SITES))
    except IndexError:
        return False


def farm_status_factor() -> float:
    """The curated factor of the farm's status layout (ui404), which its cart drops take
    (interface/single_screen/executable/single_screen_farm_carts.py); 1 when it is not scaled."""
    from core.interface.single_screen.layout.single_screen import load_layout_settings
    setting = load_layout_settings().get("ui404")
    return setting.factor if setting else 1.0


def patch_single_screen(code: bytes, offsets: dict[int, int], layout: Layout | None = None,
                        engine_table: bytes | None = None) -> bytes:
    """`code` (extended) in single-screen mode, with the curated settings: their `top_screen` layouts loaded on the
    top screen, the groups of `offsets` (name hash -> priority offset,
    interface/single_screen/layout/single_screen.priority_offsets of the placed layouts) drawn in front, ui006 on the
    top screen while a prompt is open, the touch menu bar's shift at 0, the choose-character models moved right, the
    new game's touch-panel layout choice skipped (B: interface/single_screen/executable/single_screen_layout.py) and a
    save's layout replaced by B when a quest loads (interface/single_screen/executable/single_screen_panels.c), the
    Canteen's pay choice moving with the
    pad's left / right, the name keyboard on the top screen with the pad's virtual finger, X for the world map and its
    "[X] Map" hint, the town minimap on the top screen with its button and hint, and the frames of the Palico menus
    (interface/single_screen/executable/single_screen_frames.py), and the guild card hidden and shown with Y (its hint
    included), and the GUI manager's null pool made larger for the panes the layouts add
    (interface/single_screen/executable/single_screen_pools.py). With `engine_table` (interface/game_gui/build.py: the
    arranged layouts), the game GUI engine places the arranged blocks
    (interface/game_gui/game_gui.py)."""
    layout = layout or load_layout()
    out = patch_pools(patch_character_models(patch_screens(code, top_screen_layouts()), character_shift()),
                      gui_pool_nulls())
    out = patch_bar_shift(out)
    out = creation.patch_creation_panel(creation.patch_creation_camera(out, layout=layout))
    out = creation.patch_creation_boards(out, layout=layout)
    out = creation.patch_creation_pad(out, layout)
    out = patch_priorities(out, offsets, layout)
    out = patch_prompt_screen(out, prompt_stay_bottom(), layout, creation.creation_prompt(), help_top())
    out = patch_layout_load(patch_layout_choice(out), layout)
    out = patch_board_page(out, board_page_shift())
    out = patch_page_counters(out, page_counter_shifts())
    out = patch_farm_carts(out, farm_status_factor())
    # the Arena's select scene: ui497 is on the top screen in single-screen mode (the engine's block)
    out = arena_pad.patch_arena_pad(quests.patch_arena_choice(out), layout)
    out = patch_pay_pad(out, layout)
    out = patch_keyboard(out, layout=layout)
    out = world_map.patch_world_map(out, PAD_UPDATE_HOOK, layout)
    out = patch_map_hint(out, PAD_UPDATE_HOOK, layout)
    out = patch_minimap(out, PAD_UPDATE_HOOK, layout)
    out = patch_frames(out, PAD_UPDATE_HOOK, layout)
    out = patch_card_info(out, PAD_UPDATE_HOOK, layout)
    if engine_table is not None:
        out = patch_game_gui(out, engine_table, layout, PAD_UPDATE_HOOK)
    return out
