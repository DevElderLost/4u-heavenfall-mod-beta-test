"""The update's executable as new items need it: facts with no
code. blocks.py sizes its blocks from them, new_items.py patches with them.

The game's item table has no slack, so the new records live in a copy in the extension (ids 0x791 and up); every
reader reaches the table through a literal word holding its address, and each of those words is repointed.
"""

ITEM_TABLE = 0xF029E4            # VA: 20-byte records by item id (offset 0xE029E4 in code.bin)
RECORD_SIZE = 20
ITEM_COUNT = 1937                # ids 0-1936; 0 is "--------", 0x790 (1936) the "(None)" sentinel
NONE_ID = 0x790
FIRST_NEW_ID = NONE_ID + 1       # the first id past the game's table
# ids 0x791-0xA00: the immediate `cmp #0xA00` of the raised bounds reaches it (the ported monsters' items below 0x900,
# the rare materials of XX's monsters from 0x900: curated/xx_materials.json)
MAX_NEW_ITEMS = 624
LAST_NEW_ID = NONE_ID + MAX_NEW_ITEMS
TABLE_BYTES = (ITEM_COUNT + MAX_NEW_ITEMS) * RECORD_SIZE

# The pool words of .text holding ITEM_TABLE (130 of them, in 122 functions: every field of the record has readers,
# and nothing but these words addresses the table; tests/equipment/new_gear/test_new_items.py scans the update for
# them). 1.0 has 130 too; [24] lies in a function 1.1 rewrote, paired by hand in tools/build/version_maps_manual.json
#
TABLE_WORDS = (
    0x22820C, 0x298E64, 0x2A2AE4, 0x2C5FB0, 0x2CBC1C, 0x2F5C08,
    0x2F67F4, 0x2F7640, 0x589ADC, 0x58F130, 0x5938F8, 0x5E5908,
    0x5E597C, 0x5E599C, 0x5E59D4, 0x5E59F0, 0x5E5AEC, 0x5E5B10,
    0x5E645C, 0x5E6518, 0x5EE410, 0x5EEB40, 0x5F8EFC, 0x5F8F38,
    0x5F9708, 0x5F9B24, 0x5FAF78, 0x603078, 0x60790C, 0x60F36C,
    0x60F8C8, 0x641DDC, 0x641F38, 0x69CD94, 0x69FA24, 0x6A7B34,
    0x6ABD54, 0x6B1950, 0x6B5F40, 0x6FAD5C, 0x87C3D4, 0x8E96EC,
    0x92EAD0, 0x97BEFC, 0x9BE278, 0x9D8EC8, 0x9D9A30, 0x9DA3E0,
    0x9DA930, 0x9DD004, 0x9E572C, 0x9E7530, 0x9ED154, 0x9F692C,
    0xA01070, 0xA07CD8, 0xA09774, 0xA0F6D8, 0xA0F7D8, 0xA143D0,
    0xA20FDC, 0xA35460, 0xA3B574, 0xA4ACF8, 0xA4CB74, 0xA59114,
    0xA591CC, 0xA59474, 0xA5CB48, 0xA5D40C, 0xA60AF4, 0xA774F4,
    0xA79B24, 0xA876FC, 0xA98E48, 0xAA4870, 0xAA9120, 0xAAD868,
    0xAAE8F0, 0xAAF588, 0xAB1770, 0xAB186C, 0xAB8174, 0xAB88DC,
    0xABB700, 0xABFCD4, 0xABFFAC, 0xAC1810, 0xACD904, 0xACF04C,
    0xAD1A44, 0xB10CB0, 0xB156D8, 0xB1E648, 0xB322F8, 0xB40E5C,
    0xB41C40, 0xB4313C, 0xB5A86C, 0xB6D924, 0xB7F668, 0xB820B0,
    0xB88BB8, 0xB892D0, 0xB89C14, 0xB8E67C, 0xB962F8, 0xB977D0,
    0xB9844C, 0xB99C60, 0xB9D330, 0xBA085C, 0xC0DD20, 0xC0DEBC,
    0xC0E318, 0xC1AD2C, 0xC1D0A4, 0xC1E5F8, 0xC1F8D4, 0xC20584,
    0xC20638, 0xC21C08, 0xC21CC4, 0xC21FB0, 0xC230D0, 0xC2421C,
    0xC246E0, 0xC25604, 0xC2610C, 0xCA83E0,
)

# `cmp rN, #0x790` of the two readers that refuse an id past the table: the item name's getter FUN_005a8508 (an id past
# it shows the name of id 0) and the pouch quantity FUN_002af87c (returns 0, so a carved material would take a pouch
# slot for each piece). (address, original word). The bound becomes LAST_NEW_ID.
NAME_BOUND = (0x5A8508, 0xE3510E79)       # cmp r1, #0x790
POUCH_BOUND = (0x2AF894, 0xE3550E79)      # cmp r5, #0x790

# Two places where the game reads an item record by an id it took from a hunter's memory at a slot that is not one. The
# game's table range absorbs any u16 id (it
# ends before the .bss does); the moved table ends in the extension, so on a 3DS such a read is a data abort. Both are
# in place word patches that keep what the game shows. (address, original word, new word).
#
# The quest item bar (FUN_00b8e2a8): its five panes take a slot of the hunter's pouch from a list of five halfwords,
# 0xFF for none; the first is the selected item's *id* (the game stores the id where the other four hold slots), so an
# item with an id past 45 (a trap, a bomb, a Farcaster) made the pane read the pouch at 0x236 + 4 x id as an item
# id. The loop's "no pane here" test, `cmp r0, #0xff` / `moveq r6, #0` / `moveq r8, r6` / `beq`, becomes
# `cmp r0, #46` (the pouch's slot count) and the same instructions on "higher or same": an index past the pouch draws
# no pane, as 0xFF always did, and a slot (0-45, so an id below 46) reads the pouch as before.
SELECTOR_SLOTS = 46
SELECTOR_PATCH = (
    (0xB8E764, 0xE35000FF, 0xE350002E),    # cmp r0, #0xff      -> cmp r0, #46
    (0xB8E768, 0x03A06000, 0x23A06000),    # moveq r6, #0       -> movcs r6, #0
    (0xB8E76C, 0x01A08006, 0x21A08006),    # moveq r8, r6       -> movcs r8, r6
    (0xB8E770, 0x0A000005, 0x2A000005),    # beq 0xb8e78c      -> bcs 0xb8e78c
)
# The ammo / coating panel (FUN_00b9813c, once a frame): the slot at player + 0x51c is 0xFF when none is selected
# (every weapon without coatings or ammo). The guarded getter FUN_00b3d538 answers 0 for it, but the type test that
# follows reads the pouch again, at slot 0xFF, 0x344 bytes past its 46 slots. Its `ldrh r0, [r0, r1]` becomes
# `mov r0, r5`, the guarded id: the same for a real slot, and the record of item 0 (type 0, not drawn) for 0xFF.
AMMO_PANEL_PATCH = (
    (0xB98290, 0xE19000B1, 0xE1A00005),    # ldrh r0, [r0, r1]  -> mov r0, r5
)
ID_PATCHES = SELECTOR_PATCH + AMMO_PANEL_PATCH

# The icon tints: the u32 table the constructor of cItem builds in .bss (14 words, ABGR), read through two literal
# words only (FUN_005e5980, FUN_005e64b0), and MH Generations' three more (its constructor, 0xB8333C: colours 14-16)
COLOUR_TABLE = 0x108A1B4
COLOUR_WORDS = (0x5E59A0, 0x5E64BC)
# The one other word holding COLOUR_TABLE: the literal of cItem's constructor (FUN_00d5a9bc), which only writes the 14
# tints. It stays pointing at the game's table on purpose.
COLOUR_CONSTRUCTOR_WORD = 0xD5ACFC
COLOURS = (
    0xFFF5F5F5, 0xFF5C50E1, 0xFF83BF69, 0xFFFFBB9F, 0xFF65CFF7, 0xFFD1A3C3, 0xFFF0DF9B,
    0xFF659AF7, 0xFF9D88F8, 0xFF6DD5AD, 0xFFAAAAAA, 0xFF2E97C1, 0xFFC7EB57, 0xFF3B8955,
    0xFF000099, 0xFF993300, 0xFF660066,
)
MAX_COLOUR = len(COLOURS) - 1
MAX_SHAPE = 119                  # cells of the common icon sheet's item area (24 px, 10 per row)

# The "ever obtained" bit array of the save (data + 0xF220, one bit per id, 61 words): FUN_00c1ac90 sets a bit when an
# item enters the box, FUN_00c1bef8 reads it (the Smithy's "???" gate and story checks), both only for ids up to
# 0x790. A new id gets the bit of an id nothing can obtain or gate on (below), or none.
OBTAINED_SET = 0xC1AC90          # first instruction `push {r4, r5, lr}`
OBTAINED_SET_FIRST = 0xE92D4030
OBTAINED_GET = 0xC1BEF8          # first instruction `add r0, r1, #0xf000`
OBTAINED_GET_FIRST = 0xE2810A0F
NO_BIT = 0xFFFF
# Bits for the new ids, in order: the 43 "dummy" / "Invalid Message" ids no recipe, carve, loot or kit names (the
# cleanest first; 84 is a real consumable), then the 15 spare bits of the array's last word (ids 1937-1951)
OBTAINED_BITS = (
    375, 1253, 1487, 1488, 1489, 1490, 1491, 1492, 1873, 1889, 1890, 1891, 1892, 1894,
    1909, 1910, 1911, 1912, 1913, 1914, 1915, 1916, 878, 880,
    841, 845, 846, 847, 848, 849, 850, 851, 856, 858, 859, 862, 865, 867, 868, 869, 871, 872, 873,
    *range(1937, 1952),
)

# The carve lists: the pointer array of FUN_00926044 and the three readers like it (a window of four entries per
# carve table: the quest's carve rank 0-3 added to the record's u16), read through four literal words
CARVE_POINTERS = 0x1002A5C
CARVE_COUNT = 1124
CARVE_WORDS = (0x684BB0, 0x912298, 0x926374, 0x9358FC)
CARVE_WINDOW = 4
MAX_CARVE_TABLES = 32            # windows added past the game's 1124 entries
CARVE_POINTER_BYTES = (CARVE_COUNT + CARVE_WINDOW * MAX_CARVE_TABLES) * 4
CARVE_LIST_BYTES = 6144          # the new lists: 4 bytes an entry and a 4-byte end, shared when identical
CARVE_END = b"\xff\xff\x00\x00"

# The part-break reward lists (FUN_0068effc): the table of a monster's
# first window
# (new_id_data.ID_TABLES "part_records", an s32 per id, -1: none) and a pointer array of 1396 entries to rows of
# (chance u16, item u16, qty u16) ended by 0xFFFF. The reader adds the quest's carve rank (1-3) and 4 x the reward bit
# (0-7) to the window, and compares the sum with a bound; both its words are repointed.
BREAK_TABLE = 0xF384D0
BREAK_POINTERS = 0xF386C0
BREAK_COUNT = 1396
BREAK_ARRAY_WORD = 0x68F068
BREAK_BOUND = (0x68F064, BREAK_COUNT - 1)
BREAK_WINDOW = 4                 # entries per reward bit: ranks 0-3 (rank 0 is never asked; the game holds the high)
BREAK_BITS = 8                   # reward bits a monster has (em+0x7987 is a byte)
BREAK_TABLE_ENTRIES = BREAK_BITS * BREAK_WINDOW
MAX_BREAK_TABLES = 5             # monsters with a table of their own, a place each (curated.ORDER has five)
BREAK_POINTER_BYTES = (BREAK_COUNT + BREAK_TABLE_ENTRIES * MAX_BREAK_TABLES) * 4
BREAK_LIST_BYTES = 1536          # the new lists: 6 bytes a row and a 2-byte end, shared when identical
BREAK_END = b"\xff\xff"

# The shiny drops: FUN_00911f58 reads a list of the carve pointer
# array at `array[effect_base_a[monster id] + carve rank (1-3) + 4 x variant]`, the s16 per monster id of this table
# (new_id_data.ID_TABLES "effect_base_a", -1: the monster drops nothing). A new id's variant is always 0.
SHINY_TABLE = 0x1003DDC
