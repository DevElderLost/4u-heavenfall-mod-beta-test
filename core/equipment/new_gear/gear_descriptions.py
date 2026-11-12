"""The descriptions of new hunter gear.

A hunter piece's description is not the message with its id: FUN_005a8630 (armor) and FUN_005a9264 (weapons)
read `*(u16 *)(array + 2 * id)` from one of 20 arrays with exactly one entry per id the game has (pointer table at
0xDF4FE4: armor body, arms, waist, legs, head, Talisman, then the 14 weapon classes). An id past the end of its
list would read whatever follows the array. The block `gear_desc` (equipment/new_gear/gear_desc.s) takes over that read:
below the list's old end the game's array answers, past it the message is the list's first new description plus
the id's distance from the old end. The descriptions of the new ids are appended to the Exp list in id order
(equipment/new_gear/new_texts.py, which fills the gaps), so no array has to be copied: 184 bytes in the extension
instead of 15 KB. Items and Felyne gear need nothing (their description is the message with the id, like their name).
The copy of the pointer table at 0xDF5150 is dead (no code reads it: FUN_005a8414 copies the 0x11C bytes before
it, FUN_005a8a00 the six words after). Update's executable only.
"""

import struct

from core.game.executable.code_space import CodeSpaceError, Layout, load_layout

BASE = 0x100000

# The hook: the `ldrh r1, [r1, #0]` that reads the array entry, in FUN_005a8630 and FUN_005a9264.
READ_ARMOR, READ_WEAPON = 0x5A8684, 0x5A92CC
LDRH_R1_R1 = bytes.fromhex("b010d1e1")  # ldrh r1, [r1]
FIRST_FILE, LAST_FILE = 21, 55          # the Exp files the readers pass (armor 21-26, weapons 42-55)
NOT_HUNTER_GEAR = 0xFFFF                # a table entry no id is below

# Each list's number of ids the game has (its name list and stats table) and of messages in its Exp list.
# Armor in the order of the Exp files 21-26, then the weapon classes in the order of 42-55 (equipment types 7-20).
HUNTER_LISTS = {
    "body": (21, 972, 496), "arms": (22, 956, 480), "waist": (23, 956, 487), "legs": (24, 964, 493),
    "head": (25, 987, 516), "talisman": (26, 18, 18),
    "great_sword": (42, 246, 113), "sword_and_shield": (43, 247, 107), "hammer": (44, 247, 113),
    "lance": (45, 216, 93), "light_bowgun": (46, 185, 85), "heavy_bowgun": (47, 157, 71),
    "long_sword": (48, 227, 107), "switch_axe": (49, 198, 88), "gunlance": (50, 221, 94), "bow": (51, 206, 89),
    "dual_blades": (52, 229, 101), "hunting_horn": (53, 185, 79), "insect_glaive": (54, 160, 60),
    "charge_blade": (55, 125, 55),
}
TABLE_BYTES = 4 * (LAST_FILE - FIRST_FILE + 1)


def description_message(key: str, piece: int) -> int:
    """The message of the Exp list that `piece` of the list `key` shows once it is a new id (past the game's
    ids): the same rule as the block's. Ids the game has keep their array's entry."""
    _, old_end, base = HUNTER_LISTS[key]
    if piece < old_end:
        raise ValueError(f"{key} {piece} is one of the game's {old_end} ids: its description is in the game's array")
    return base + piece - old_end


def supports_gear_descriptions(code: bytes) -> bool:
    """True if both readers have their `ldrh r1, [r1]` where the update's executable has it."""
    return all(bytes(code[at - BASE:at - BASE + 4]) == LDRH_R1_R1 for at in (READ_ARMOR, READ_WEAPON))


def gear_descriptions_table() -> bytes:
    """The block's table: a word per Exp file (old end | first new message - old end << 16)."""
    words = [NOT_HUNTER_GEAR] * (LAST_FILE - FIRST_FILE + 1)
    for file, old_end, base in HUNTER_LISTS.values():
        words[file - FIRST_FILE] = old_end | ((base - old_end) & 0xFFFF) << 16
    return struct.pack(f"<{len(words)}I", *words)


def gear_descriptions_data(layout: Layout) -> bytes:
    """The block's bytes with its table filled in."""
    block = layout.block("gear_desc")
    at = layout.symbol("gear_desc", "table") - block.address
    table = gear_descriptions_table()
    if at + len(table) > len(block.data):
        raise CodeSpaceError("gear_desc: the table does not fit the block")
    return block.data[:at] + table + block.data[at + len(table):]


def patch_gear_descriptions(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (the update's executable) where the descriptions of new hunter gear ids are found. Needs the
    descriptions appended to the Exp lists (equipment/new_gear/new_texts.py). Adds `layout.block("gear_desc")` bytes
    (`gear_desc_size`) to the extension."""
    if not supports_gear_descriptions(code):
        raise CodeSpaceError("unexpected description readers: the hunter gear descriptions need the update's "
                             "executable")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, "gear_desc", gear_descriptions_data(layout))
    for at in (READ_ARMOR, READ_WEAPON):
        layout.hook(out, at, "gear_desc", original=LDRH_R1_R1)
    return bytes(out)


def gear_desc_size(layout: Layout | None = None) -> int:
    """The bytes the patch adds to the executable's free space (code and table)."""
    return len((layout or load_layout()).block("gear_desc").data)
