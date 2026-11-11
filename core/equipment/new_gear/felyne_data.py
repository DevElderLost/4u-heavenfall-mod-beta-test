"""Felyne (Palico) gear past the game's last id: where the executable reads the tables, and the blocks the added
pieces need. Data and finders only, so that
game/executable/blocks.py can declare the blocks; new_felyne.py patches the executable.

The game keeps three stats tables (weapons 179 records, bodies 174, heads 168) one after the other, then another
structure, and three create-recipe tables (also one after the other) that end at a record whose first byte is 0xFF.
Nothing can grow in place at the end of a table, so adding pieces moves what has to move and grows what can:

* weapons stay and grow into the room the bodies leave (their literals are not touched);
* bodies and heads move to the extension (3 + 2 literals and a pointer pair each, three `cmp #0xAE` bounds);
* head recipes stay and grow into the room the body recipes leave; body and weapon recipes move (one literal each).

`locate` finds the tables again wherever they are, the way the game does (it follows the literals), so
EquipmentTables.read sees the added pieces and a game in progress can be fixed.
"""

import struct
from dataclasses import dataclass

from core.equipment.tables.layout import PALICO_TABLES, RECIPE_RECORD_SIZE

BASE = 0x100000                    # virtual address of code.bin's first byte
WINDOW = 200                       # ids per piece type in the save's bit arrays
FEATURE = "felyne_gear"            # the blocks' feature (game/executable/blocks.py)

TABLE = {t.key: t for t in PALICO_TABLES}
MAX_NEW = {key: WINDOW - table.count for key, table in TABLE.items()}     # weapon 21, head 32, body 26
KINDS = tuple(TABLE)

# The literal-pool words that hold each table's address (virtual addresses of the words).
WEAPON_POOL = 0x2F4760             # one of the 11 words that hold the weapons' (never repointed)
STATS_POOL = {"body": (0x2F4764, 0x2F54DC), "head": (0x2F4768, 0x2F54E0, 0x2F8698)}
# The pointer pair {body, head}: the game reads the tables through it too (data, 7 readers)
PAIR = {"body": 0xF3ED74, "head": 0xF3ED78}
RECIPE_POOL = {"body": 0x2F80F8, "head": 0x2F80FC, "weapon": 0x2F8100}

STATS_MOVED = ("body", "head")
RECIPES_MOVED = ("body", "weapon")


def va(offset: int) -> int:
    return offset + BASE


def block_name(key: str, what: str) -> str:
    return f"felyne_{key}_{what}"


def recipe_room(key: str) -> int:
    """Records a recipe table can hold: the game's (the (None) piece's too), one for each new piece, the end."""
    return TABLE[key].recipe_count + MAX_NEW[key] + 1


def block_specs() -> tuple[tuple[str, int], ...]:
    """(block name, bytes) of what the added pieces take in the extension: the moved stats and recipes."""
    return (
        *((block_name(key, "stats"), WINDOW * TABLE[key].record_size) for key in STATS_MOVED),
        *((block_name(key, "recipes"), recipe_room(key) * RECIPE_RECORD_SIZE) for key in RECIPES_MOVED),
    )


@dataclass(frozen=True)
class Location:
    """Where a kind of piece is now: its stats table (`count` records) and its create recipes (`recipe_count`
    records, the (None) piece's first, without the 0xFF end)."""
    offset: int
    count: int
    recipe_offset: int
    recipe_count: int


def word(code: bytes, address: int) -> int:
    """The u32 at virtual address `address`; 0 outside the executable."""
    at = address - BASE
    return struct.unpack_from("<I", code, at)[0] if 0 <= at and at + 4 <= len(code) else 0


def _moved(code: bytes, address: int) -> int | None:
    """The offset a pool word points at when it is not the game's table (a table moved into the executable)."""
    value = word(code, address)
    return value - BASE if BASE <= value < BASE + len(code) else None


def _used(code: bytes, offset: int, size: int, floor: int) -> int:
    """Records of a stats table up to the last one that is not all zeros (never fewer than `floor`)."""
    count = floor
    for i in range(floor, WINDOW):
        if any(code[offset + i * size:offset + (i + 1) * size]):
            count = i + 1
    return count


def _listed(code: bytes, offset: int) -> int:
    """Records before the 0xFF that ends a create recipe table."""
    count = 0
    while offset + (count + 1) * RECIPE_RECORD_SIZE <= len(code) and code[offset + count * RECIPE_RECORD_SIZE] != 0xFF:
        count += 1
    return count


def locate(code: bytes) -> dict[str, Location]:
    """The Felyne tables of `code`, followed from the literals the way the game's readers do: the game's own
    places in a clean executable (and in one that is not the game's), the moved ones after new_felyne.py."""
    body_stats, body_recipes = _moved(code, STATS_POOL["body"][0]), _moved(code, RECIPE_POOL["body"])
    stats_moved = body_stats not in (None, TABLE["body"].offset)
    recipes_moved = body_recipes not in (None, TABLE["body"].recipe_offset)
    found = {}
    for key, table in TABLE.items():
        offset, count = table.offset, table.count
        recipe_offset, recipe_count = table.recipe_offset, table.recipe_count
        if stats_moved:
            pool = WEAPON_POOL if key == "weapon" else STATS_POOL[key][0]
            offset = _moved(code, pool) or offset
            count = _used(code, offset, table.record_size, table.count)
        if recipes_moved:
            recipe_offset = _moved(code, RECIPE_POOL[key]) or recipe_offset
            recipe_count = _listed(code, recipe_offset)
        found[key] = Location(offset, count, recipe_offset, recipe_count)
    return found
