"""New items for the ported monsters' materials: ids past the game's
0x790, a table of their records, the icon tints MH Generations has beyond MH4U's, the "ever obtained" bits, and carve
lists that can hold them. Update's executable only; every function takes code.bin and returns the patched bytes.

* `patch_items(code, records)` gives slot i of `records` the id 0x791 + i. A slot is a position, so a run that has
  fewer ported monsters passes `None` for theirs and every other id stays where it was: **ids are append only**, the
  box, pouch and item sets of a save keep them. It copies the item table into the extension (the game's has no slack
  and 130 pool words in 122 functions address it), adds the records, raises the two bounds that refuse an id past the
  table (the name, the pouch quantity), swaps the 14-colour tint table for MH Generations' 17, hooks the "ever
  obtained" bit array so a new id has a bit of its own to open the Smithy's "???" gate, and makes two reads of
  the game that took an item id from a slot that is none (the quest item bar, the ammo panel) stop reading the
  record of that junk id: the game's table range absorbed it, the moved one ends in the extension.
* `patch_carve_tables(code, tables)` adds carve lists: windows of the pointer array the carve records point at.
* core/equipment/new_gear/item_loot.py puts items in a quest's rewards.

Names and descriptions are texts (the item name list is read by id, so appending the new ids' names to itemName in
the language files is all the name needs); the description table is another task's.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass

from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, load_layout
from core.equipment.tables import item_data as data
from core.equipment.tables.item_data import FIRST_NEW_ID, MAX_NEW_ITEMS, RECORD_SIZE

_TABLE_OFFSET = data.ITEM_TABLE - BASE_ADDRESS
_SORT_OFFSET = 6
_NEW_SORT_FIRST = 2260           # the game's sort keys end at 2259 ("(None)")
_MAX_PRICE = 0xFFFFFFFF


@dataclass(frozen=True)
class ItemRecord:
    """A new ordinary item, a monster material. `rarity` as the game shows it (1-10); `shape` the cell of the item
    sheet, `colour` one of the 17
    tints (0-13 MH4U's, 14-16 MH Generations'); `sort` the item box's default order (None: after the game's items, in
    slot order); prices as MH Generations has them (buy is about ten times sell). `type` must be 0 (the game's scans for
    ammo, decorations, coatings and nectars stop at id 0x790) and `flags` 0 for a material."""
    rarity: int
    sell: int
    buy: int
    carry: int = 99
    shape: int = 0
    colour: int = 0
    sort: int | None = None
    type: int = 0
    flags: int = 0

    def check(self) -> None:
        for name, value, low, high in (("rarity", self.rarity, 1, 10), ("carry", self.carry, 1, 99),
                                       ("shape", self.shape, 0, data.MAX_SHAPE),
                                       ("colour", self.colour, 0, data.MAX_COLOUR),
                                       ("sell", self.sell, 0, _MAX_PRICE), ("buy", self.buy, 0, _MAX_PRICE),
                                       ("type", self.type, 0, 0), ("flags", self.flags, 0, 0xFF)):
            if not low <= value <= high:
                raise ValueError(f"item {name} {value} is not in {low}-{high}")
        if self.sort is not None and not 1 <= self.sort <= 0xFFFF:
            raise ValueError(f"item sort key {self.sort} is not in 1-65535")

    def pack(self, sort: int) -> bytes:
        """The 20-byte record: type, rarity - 1, flags, carry limit, shape, colour, sort key, two unused u16, sell
        and buy price."""
        return struct.pack("<BBBBBBHHHII", self.type, self.rarity - 1, self.flags, self.carry, self.shape,
                           self.colour, sort, 0, 0, self.sell, self.buy)


def item_id(slot: int) -> int:
    """The id of slot `slot` of `patch_items`' records."""
    if not 0 <= slot < MAX_NEW_ITEMS:
        raise ValueError(f"item slot {slot} is not in 0-{MAX_NEW_ITEMS - 1}")
    return FIRST_NEW_ID + slot


def _word(code: bytes, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def _put(code: bytearray, at: int, value: int) -> None:
    struct.pack_into("<I", code, at - BASE_ADDRESS, value)


def _bound(word: int) -> int:
    """`cmp rN, #imm` of `word` with the immediate raised to the last new id (an 8-bit value rotated right by an
    even amount: 0x790 is 0x79 << 4, 0xA00 is 0xA << 8)."""
    last = data.LAST_NEW_ID
    for rotation in range(16):
        shift = 2 * rotation
        low = ((last << shift) | (last >> (32 - shift))) & 0xFFFFFFFF if shift else last
        if low < 0x100:
            return (word & ~0xFFF) | rotation << 8 | low
    raise CodeSpaceError(f"{last:#x} is not an ARM immediate")


def supports_new_items(code: bytes) -> bool:
    """True if the update's executable still has what `patch_items` changes: the pool words of the table, the two
    bounds, the first instructions of the bit array's readers and the words of the two junk-id fixes."""
    try:
        return all(_word(code, at) == data.ITEM_TABLE for at in data.TABLE_WORDS) \
            and _word(code, data.NAME_BOUND[0]) == data.NAME_BOUND[1] \
            and _word(code, data.POUCH_BOUND[0]) == data.POUCH_BOUND[1] \
            and _word(code, data.OBTAINED_GET) == data.OBTAINED_GET_FIRST \
            and _word(code, data.OBTAINED_SET) == data.OBTAINED_SET_FIRST \
            and all(_word(code, at) == original for at, original, _ in data.ID_PATCHES) \
            and all(_word(code, at) == data.COLOUR_TABLE for at in data.COLOUR_WORDS) \
            and len(code) >= _TABLE_OFFSET + data.ITEM_COUNT * RECORD_SIZE
    except struct.error:
        return False


def game_sort_keys(code: bytes) -> set[int]:
    """The sort keys of the game's items (and of the new ones when `code` is already patched)."""
    return {struct.unpack_from("<H", code, _TABLE_OFFSET + i * RECORD_SIZE + _SORT_OFFSET)[0]
            for i in range(data.ITEM_COUNT)}


def patch_items(code: bytes, records: Sequence[ItemRecord | None], layout: Layout | None = None,
                groups: Sequence[int | None] | None = None) -> tuple[bytes, list[int]]:
    """`code` with the item table moved into the extension and `records` added (slot i is id 0x791 + i; `None`
    leaves the slot's id unused), and the ids given, in order. Nothing is changed when `records` is empty.

    "Ever obtained" bits: by default slot i stands on `OBTAINED_BITS[i]` (none from the 59th on). With `groups` (one
    entry per slot: a group number below `len(OBTAINED_BITS)`, or None for no bit) the slots of one group share one
    bit, so obtaining any of them counts as having obtained all: the Smithy's gate on the first material of a recipe
    opens when any item of the group has been obtained (the ported monsters: one group per monster and rank)."""
    if not records:
        return bytes(code), []
    if len(records) > MAX_NEW_ITEMS:
        raise ValueError(f"{len(records)} new items: at most {MAX_NEW_ITEMS}")
    if not supports_new_items(code):
        raise CodeSpaceError("unexpected item table readers: new items need the update's executable (or it is "
                             "already patched)")
    taken = game_sort_keys(code)
    packed, sorts = bytearray(), set()
    for slot, record in enumerate(records):
        if record is None:
            packed += bytes(RECORD_SIZE)
            continue
        record.check()
        sort = _NEW_SORT_FIRST + slot if record.sort is None else record.sort
        if sort in taken or sort in sorts:
            raise ValueError(f"item sort key {sort} is already taken")
        sorts.add(sort)
        packed += record.pack(sort)
    layout = layout or load_layout()
    out = bytearray(code)
    table = bytearray(code[_TABLE_OFFSET:_TABLE_OFFSET + data.ITEM_COUNT * RECORD_SIZE]) + packed
    layout.place(out, "item_table", bytes(table).ljust(data.TABLE_BYTES, b"\0"))
    for at in data.TABLE_WORDS:
        _put(out, at, layout.address("item_table"))
    for at, original in (data.NAME_BOUND, data.POUCH_BOUND):
        _put(out, at, _bound(original))
    for at, _, word in data.ID_PATCHES:
        _put(out, at, word)
    layout.place(out, "item_colours", struct.pack(f"<{len(data.COLOURS)}I", *data.COLOURS))
    for at in data.COLOUR_WORDS:
        _put(out, at, layout.address("item_colours"))
    if groups is None:
        bits = [data.OBTAINED_BITS[slot] if slot < len(data.OBTAINED_BITS) else data.NO_BIT
                for slot in range(len(records))]
    else:
        if len(groups) != len(records) or any(g is not None and not 0 <= g < len(data.OBTAINED_BITS) for g in groups):
            raise ValueError(f"item groups {list(groups)}: one per slot, each below {len(data.OBTAINED_BITS)}")
        bits = [data.NO_BIT if group is None else data.OBTAINED_BITS[group] for group in groups]
    layout.place(out, "item_obtained")
    layout.place(out, "item_obtained_bits", struct.pack(f"<{len(bits)}H", *bits).ljust(2 * MAX_NEW_ITEMS, b"\xff"))
    for at, first, entry in ((data.OBTAINED_GET, data.OBTAINED_GET_FIRST, "get_entry"),
                             (data.OBTAINED_SET, data.OBTAINED_SET_FIRST, "set_entry")):
        layout.hook(out, at, layout.symbol("item_obtained", entry), original=struct.pack("<I", first), link=False)
    return bytes(out), [item_id(slot) for slot, record in enumerate(records) if record is not None]


# ---- carve lists -----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Carve:
    """One row of a carve list: the share of carves (percent, a list adds up to 100) that give `qty` of `item`."""
    chance: int
    item: int
    qty: int = 1


CarveTable = tuple[Sequence[Carve], Sequence[Carve], Sequence[Carve]]   # low, high and G rank


def carve_list(code: bytes, index: int) -> list[Carve]:
    """The carve list at entry `index` of the pointer array `code` has (the game's, or the patched copy)."""
    base = _word(code, data.CARVE_WORDS[0])
    pointer = _word(code, base + 4 * index)
    out, at = [], pointer - BASE_ADDRESS
    if not pointer:
        return out
    while bytes(code[at:at + 4]) != data.CARVE_END:
        chance, qty, item = struct.unpack_from("<BBH", code, at)
        out.append(Carve(chance, item, qty))
        at += 4
    return out


def _check_carves(table: CarveTable) -> None:
    if len(table) != 3:
        raise ValueError("a carve table has three lists: low, high and G rank")
    for rows in table:
        if not rows or len(rows) > 16:
            raise ValueError(f"a carve list has 1-16 rows, not {len(rows)}")
        for row in rows:
            if not 1 <= row.chance <= 100 or not 1 <= row.qty <= 0xFE or not 1 <= row.item <= 0xFFFF:
                raise ValueError(f"carve row {row} out of range")
        if sum(row.chance for row in rows) != 100:
            raise ValueError(f"a carve list adds up to {sum(row.chance for row in rows)}, not 100")


def patch_carve_tables(code: bytes, tables: Sequence[CarveTable | None], layout: Layout | None = None
                       ) -> tuple[bytes, list[int | None]]:
    """`code` with the carve pointer array copied and a window of four entries added for each table of `tables`
    (the quest's carve rank 0-3 is added to a carve record's u16: rank 0 repeats the low-rank list, the game's own
    keeps a test list there), and each window's first entry, the u16 a carve record points at (`None` for a `None`
    table, so that slots keep their windows). Rows are `Carve(chance, item, qty)`; item ids may be new ones."""
    if not any(table is not None for table in tables):
        return bytes(code), [None] * len(tables)
    if len(tables) > data.MAX_CARVE_TABLES:
        raise ValueError(f"{len(tables)} carve tables: at most {data.MAX_CARVE_TABLES}")
    if len(code) <= data.CARVE_POINTERS - BASE_ADDRESS or \
            not all(_word(code, at) == data.CARVE_POINTERS for at in data.CARVE_WORDS):
        raise CodeSpaceError("unexpected carve pointer readers: new carve lists need the update's executable (or it "
                             "is already patched)")
    layout = layout or load_layout()
    lists_at = layout.address("carve_lists")
    pointers = bytearray(code[data.CARVE_POINTERS - BASE_ADDRESS:data.CARVE_POINTERS - BASE_ADDRESS
                              + 4 * data.CARVE_COUNT])
    lists, placed = bytearray(), {}

    def address(rows: Sequence[Carve]) -> int:
        key = tuple(rows)
        if key not in placed:
            placed[key] = lists_at + len(lists)
            lists.extend(b"".join(struct.pack("<BBH", row.chance, row.qty, row.item) for row in rows))
            lists.extend(data.CARVE_END)
        return placed[key]

    indices: list[int | None] = []
    for slot, table in enumerate(tables):
        if table is None:
            pointers += bytes(4 * data.CARVE_WINDOW)
            indices.append(None)
            continue
        _check_carves(table)
        low, high, g = table
        pointers += struct.pack("<4I", address(low), address(low), address(high), address(g))
        indices.append(data.CARVE_COUNT + data.CARVE_WINDOW * slot)
    if len(lists) > data.CARVE_LIST_BYTES:
        raise ValueError(f"the carve lists take {len(lists)} bytes: the block has {data.CARVE_LIST_BYTES}")
    out = bytearray(code)
    layout.place(out, "carve_lists", bytes(lists).ljust(data.CARVE_LIST_BYTES, b"\0"))
    layout.place(out, "carve_pointers", bytes(pointers).ljust(data.CARVE_POINTER_BYTES, b"\0"), pointers=True)
    for at in data.CARVE_WORDS:
        _put(out, at, layout.address("carve_pointers"))
    return bytes(out), indices
