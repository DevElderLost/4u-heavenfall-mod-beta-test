"""How much room the executable's extension holds for new hunter weapons, as facts with no code:
game/executable/blocks.py sizes its blocks from them,
equipment/new_gear/new_weapons.py fills them.

Every class has the same room for new weapons, ROOM: the smallest spare ids of the save's bit arrays (the Insect
Glaive's 40, section "The save" of the doc) is the most any class could use. A class of the game keeps its tables where
they are; its new weapons' records (the game's view of a record, in `new_weapon_stats`) and upgrade records (in
`new_weapon_upgrades`) follow each other in the order of `WEAPON_CLASSES`.
"""

from core.equipment.tables.layout import WEAPON_CLASSES

FEATURE = "new_weapons"
ROOM = 40                    # new weapons per class
SHARPNESS_ROOM = 96          # new sharpness profiles (the game has OLD_PROFILES): the four ported monsters need 60
OLD_PROFILES = 119
SHARPNESS_RECORD_SIZE = 14
ROW_SIZE = 16                # new_weapon_rows: one row per equipment type 7..20 (asm/new_weapons.s)
FIRST_TYPE = 7
TYPES = 14

ROWS_BYTES = ROW_SIZE * TYPES
SHARPNESS_BYTES = SHARPNESS_ROOM * SHARPNESS_RECORD_SIZE


def _areas(size) -> tuple[dict[str, int], int]:
    offsets, total = {}, 0
    for wc in WEAPON_CLASSES:
        offsets[wc.key] = total
        total += ROOM * size(wc)
    return offsets, total


STATS_OFFSETS, STATS_BYTES = _areas(lambda wc: wc.record_size)
UPGRADE_OFFSETS, UPGRADE_BYTES = _areas(lambda wc: wc.upgrade_record_size)
