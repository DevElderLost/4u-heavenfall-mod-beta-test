"""How much room the executable's extension holds for new hunter weapons, as facts with no code:
game/executable/blocks.py sizes its blocks from them,
equipment/new_gear/new_weapons.py fills them.

Every class has the same room for new weapons, ROOM. The save marks an id in three bit arrays, and a class's own bits
end 40 (the Insect Glaive) to 73 ids past its last; the ids past them are marked on bits no piece of the game uses
(equipment/new_gear/weapon_marks.py; section "The save" of the doc), up to 82 per class (`weapon_marks.mark_room`).
ROOM is 80: Astalos and three more ports of his size after the 40 ids the first five ported monsters took. A class of
the game keeps its tables where they are; its new weapons' records (the game's view of a record, in
`new_weapon_stats`) and upgrade records (in `new_weapon_upgrades`) follow each other in the order of `WEAPON_CLASSES`.
"""

from core.equipment.tables.layout import WEAPON_CLASSES

FEATURE = "new_weapons"
ROOM = 80                    # new weapons per class (at most weapon_marks.mark_room)
SHARPNESS_ROOM = 120         # new sharpness profiles (the game has OLD_PROFILES): the nine monsters need up to 98
OLD_PROFILES = 119
SHARPNESS_RECORD_SIZE = 14
ROW_SIZE = 16                # new_weapon_rows: one row per equipment type 7..20 (asm/new_weapons.s)
FIRST_TYPE = 7
TYPES = 14

ROWS_BYTES = ROW_SIZE * TYPES
SHARPNESS_BYTES = SHARPNESS_ROOM * SHARPNESS_RECORD_SIZE

# The marks of the ids past a class's own bits (equipment/new_gear/weapon_marks.py, weapon_marks.c): the table the C
# reads (a row per weapon type: u16 capacity, first, size, 0; then the armor windows: u16 first bit, bits) and the
# stubs on the six functions that read or write a mark
MARK_WINDOWS = 5             # the armor parts, types 1-5
MARK_ROW_SIZE, MARK_WINDOW_SIZE = 8, 4
MARK_TABLE_BYTES = MARK_ROW_SIZE * TYPES + MARK_WINDOW_SIZE * MARK_WINDOWS
MARK_ACCESSORS = 6
MARK_STUB_SIZE = 32
MARK_STUBS_BYTES = MARK_STUB_SIZE * MARK_ACCESSORS
MARK_DEFINES = (f"MARK_FIRST_TYPE={FIRST_TYPE}", f"MARK_TYPES={TYPES}", f"MARK_WINDOWS={MARK_WINDOWS}")


def _areas(size) -> tuple[dict[str, int], int]:
    offsets, total = {}, 0
    for wc in WEAPON_CLASSES:
        offsets[wc.key] = total
        total += ROOM * size(wc)
    return offsets, total


STATS_OFFSETS, STATS_BYTES = _areas(lambda wc: wc.record_size)
UPGRADE_OFFSETS, UPGRADE_BYTES = _areas(lambda wc: wc.upgrade_record_size)
