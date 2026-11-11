"""The gear added to an executable, read as the equipment randomizer's tables (task
i8: it treats the ported monsters' pieces like MH4U's). `add_new_gear(tables, code)` appends to each list of an
EquipmentTables read from the game's places the records new_weapons.py, new_armor.py and new_recipes.py put in the
extension, so that a weapon's or piece's id is still its list index, and writing the tables back writes the new
records where they are.

A new record exists up to the last one that is not all zeros (the blocks are zero filled); an empty record before it is
a hole, an id no piece owns (equipment/ported_gear/blocks.py), and stays in the list so that an id is still its index.
Melee records are read in the older view the randomizer uses (4 bytes before the game's). The upgrade lists are padded
with unwritable records up to the class's record count: the game's upgrade tables are shorter than its stat tables."""

from __future__ import annotations

import struct

from core.game.executable.code_space import BASE_ADDRESS, CLEAN_SIZE, Layout, load_layout
from core.equipment.new_gear.gear_space import ARMOR_ROOM, RECIPE_RECORD
from core.equipment.tables.layout import ARMOR_PARTS, SHARPNESS_RECORD_SIZE, WEAPON_CLASSES
from core.equipment.new_gear.new_weapon_room import FIRST_TYPE, ROOM, ROW_SIZE
from core.equipment.tables.records import (
    Armor, CreateRecipe, MeleeWeapon, RangedWeapon, ShortUpgradeRecipe, SharpnessProfile, UpgradeRecipe,
)

UNWRITTEN = -1          # the offset of a record that stands for an id with no data in the executable
NEVER = 0xFFFFFFFF
OLD_PROFILES = 119


def _placed(code: bytes, layout: Layout, name: str) -> int | None:
    """The file offset of block `name` when `code` holds it (the extension reaches its end), else None."""
    block = layout.block(name)
    start = block.address - BASE_ADDRESS
    return start if len(code) >= start + len(block.data) else None


def _records(code: bytes, start: int, size: int, room: int) -> int:
    """How many records from `start` are not all zeros (up to `room`, ending at the first empty one)."""
    count = 0
    while count < room and any(code[start + count * size:start + (count + 1) * size]):
        count += 1
    return count


def _extent(code: bytes, start: int, size: int, room: int) -> int:
    """How many records from `start` the gear spans: up to the last one that is not all zeros (up to `room`). A
    hole, an id no piece owns, can be an empty record in the middle of the gear (armor), so the first empty one
    does not end it."""
    count = 0
    for k in range(room):
        if any(code[start + k * size:start + (k + 1) * size]):
            count = k + 1
    return count


def add_new_gear(tables, code: bytes, layout: Layout | None = None) -> None:
    """Append the new weapons, upgrade records, sharpness profiles, armor pieces and create recipes of `code` to
    `tables` (an EquipmentTables made from the game's places)."""
    if len(code) <= CLEAN_SIZE:
        return
    layout = layout or load_layout()
    _weapons(tables, code, layout)
    _armor(tables, code, layout)
    _recipes(tables, code, layout)


def _weapons(tables, code: bytes, layout: Layout) -> None:
    rows = _placed(code, layout, "new_weapon_rows")
    if rows is None:
        return
    for wc in WEAPON_CLASSES:
        first, stats, upgrades, _ = struct.unpack_from("<4I", code, rows + (wc.recipe_type - FIRST_TYPE) * ROW_SIZE)
        if first != wc.count:
            continue
        size, usize = wc.record_size, wc.upgrade_record_size
        start = stats - BASE_ADDRESS
        count = _extent(code, start, size, ROOM)
        for k in range(count):
            at = start + k * size
            tables.weapons[wc.key].append(RangedWeapon(at, code[at:at + size]) if wc.ranged
                                          else MeleeWeapon(at - 4, code[at - 4:at - 4 + size]))
        view = UpgradeRecipe if wc.upgrade_materials == 4 else ShortUpgradeRecipe
        records = tables.upgrades[wc.key]
        records += [view(UNWRITTEN, bytes(usize)) for _ in range(wc.count - len(records))]
        for k in range(count):
            at = upgrades - BASE_ADDRESS + k * usize
            records.append(view(at, code[at:at + usize]))
    block = _placed(code, layout, "new_sharpness")
    if block is not None:
        for k in range(_records(code, block, SHARPNESS_RECORD_SIZE, len(layout.block("new_sharpness").data)
                                // SHARPNESS_RECORD_SIZE)):
            at = block + k * SHARPNESS_RECORD_SIZE
            tables.sharpness.append(SharpnessProfile(at, code[at:at + SHARPNESS_RECORD_SIZE]))


def _armor(tables, code: bytes, layout: Layout) -> None:
    pointers, records = _placed(code, layout, "gear_armor_new"), _placed(code, layout, "gear_armor_records")
    if pointers is None or records is None:
        return
    for index, part in enumerate(ARMOR_PARTS):
        first = struct.unpack_from("<I", code, pointers + 8 * part.recipe_type)[0]
        if first != part.count:
            continue
        start = records + index * ARMOR_ROOM * part.record_size
        for k in range(_extent(code, start, part.record_size, ARMOR_ROOM)):
            at = start + k * part.record_size
            tables.armor[part.key].append(Armor(at, code[at:at + part.record_size]))


def _recipes(tables, code: bytes, layout: Layout) -> None:
    for runs_name, records_name, target in (
            ("gear_armor_runs", "gear_armor_recipes", tables.armor_recipes),
            ("gear_weapon_runs", "gear_weapon_recipes", tables.weapon_recipes)):
        runs = _placed(code, layout, runs_name)
        if runs is None or _placed(code, layout, records_name) is None:
            continue
        at = runs
        while at + 8 <= len(code):
            _, length, address = struct.unpack_from("<HHI", code, at)
            if not length:
                break
            for n in range(length):
                start = address - BASE_ADDRESS + n * RECIPE_RECORD
                target.append(CreateRecipe(start, code[start:start + RECIPE_RECORD]))
            at += 8


class _Collector:
    """A stand-in for EquipmentTables that only gathers the records add_new_gear appends."""

    def __init__(self) -> None:
        self.weapons = {wc.key: [] for wc in WEAPON_CLASSES}
        self.upgrades = {wc.key: [] for wc in WEAPON_CLASSES}
        self.armor = {part.key: [] for part in ARMOR_PARTS}
        self.sharpness: list = []
        self.weapon_recipes: list = []
        self.armor_recipes: list = []


def new_gear_records(code: bytes, layout: Layout | None = None) -> list[bytes]:
    """The bytes of every record of the gear added to `code` (hunter weapons, their upgrade records, sharpness
    profiles, armor, create recipes), in a fixed order; empty for an executable with none. It is what the run's
    checksum adds to the game's own tables (tables_digest)."""
    found = _Collector()
    add_new_gear(found, code, layout)
    return [bytes(r.data) for table in (*found.weapons.values(), *found.upgrades.values(), *found.armor.values(),
                                        found.sharpness, found.weapon_recipes, found.armor_recipes)
            for r in table if r.offset != UNWRITTEN]


__all__ = ["UNWRITTEN", "add_new_gear", "new_gear_records"]
