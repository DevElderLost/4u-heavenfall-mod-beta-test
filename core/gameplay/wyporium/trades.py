"""The Wyporium's trade table with the trades of MH XX's new materials.

The game's "Trade Materials" list is one table in `.data` (16-byte rows `{u16 received, u16 quest, {u16 item, s16
count} x 3}`, ended by a received item of 0xFFFF) that no neighbour leaves room to grow. `patch_trades` reads it from
the executable, adds one row per new item of the materials file that has a trade (`obtain["trade"]`) after the game's
last row (one block per monster), writes the longer table into the extension's block `wyporium_trades`, repoints the
three literal-pool words that address it and raises the one fixed row count (`cmp r4, #0x81` in the hub build) to
rows + 1.
Canonical (update) addresses; the version maps do the base games.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from dataclasses import dataclass

from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout

FEATURE = "wyporium_trades"
BLOCK = "wyporium_trades"
TABLE = 0xEE76A2                 # the game's table
ROW = 16
GAME_ROWS = 128
END = 0xFFFF                     # a received item that ends the table
# The three literal-pool words holding TABLE: (address, the function or code that reads them)
POOL_WORDS = ((0xA5332C, "FUN_00a53160 (the list builder)"),
              (0x9DD704, "FUN_009dd4c8 (the hub build's obtained bits)"),
              (0x9B7928, "the Wyporium menu at 0x9B6F40 (dims the line)"))
COUNT_CMP = 0x9DD6E4             # `cmp r4, #0x81` of FUN_009dd4c8: the rows it walks, the terminator included
COUNT_CMP_WORD = 0xE3540081
# The three calls of FUN_00c21fe0 (the quest cleared check) that read a row's quest, one per reader of the pool words:
# the list builder, the hub build's obtained bits and the menu's bright line (trade_rows.c)
ROW_READERS = (0xA531FC, 0x9DD6C0, 0x9B6F6C)
QUEST_CLEARED = 0xC21FE0
MARKER_QUEST = 0xFFF0            # a new row's quest is this + its rank index (0 low, 1 high, 2 G): trade_rows.c
CODE_BLOCK = "wyporium_trade_rows"
DATA_BLOCK = "wyporium_trade_rows_data"
DATA_SIZE = 16                   # the lists of what opens the high and the G rank: 2 x 4 u16 (rank_unlock.h)
MAX_NEW_ROWS = 112               # one per new item of the materials file (ids from 0x900); the compare holds 0xFF rows
BLOCK_SIZE = ROW * (GAME_ROWS + MAX_NEW_ROWS + 1)
RANK_ORDER = ("low", "high", "G")
GAME_ROW_FIELDS = "<HH6H"


@dataclass(frozen=True)
class Row:
    received: int
    quest: int
    gives: tuple[tuple[int, int], ...] = ()      # (item, count), up to 3

    def pack(self) -> bytes:
        pairs = list(self.gives) + [(0, 0)] * (3 - len(self.gives))
        return struct.pack(GAME_ROW_FIELDS, self.received, self.quest, *(v for pair in pairs for v in pair))

    @classmethod
    def unpack(cls, raw: bytes, at: int = 0) -> "Row":
        received, quest, *rest = struct.unpack_from(GAME_ROW_FIELDS, raw, at)
        pairs = tuple((rest[i], rest[i + 1] if rest[i + 1] < 0x8000 else rest[i + 1] - 0x10000)
                      for i in (0, 2, 4) if rest[i])
        return cls(received, quest, pairs)


def _word(code: bytes, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def supports_trades(code: bytes) -> bool:
    """True if `code` still has what `patch_trades` changes: the three pool words on the table, the row count's
    compare, the three calls that read a row's quest and the table's terminator where the game keeps it."""
    try:
        return all(_word(code, at) == TABLE for at, _ in POOL_WORDS) and _word(code, COUNT_CMP) == COUNT_CMP_WORD \
            and all(bl_target(code, at) == QUEST_CLEARED for at in ROW_READERS) \
            and struct.unpack_from("<H", code, TABLE - BASE_ADDRESS + GAME_ROWS * ROW)[0] == END
    except struct.error:
        return False


def game_rows(code: bytes) -> list[Row]:
    """The game's rows, read from the executable (the terminator excluded)."""
    base = TABLE - BASE_ADDRESS
    rows = []
    while True:
        if len(rows) > GAME_ROWS:
            raise CodeSpaceError("the trade table has no terminator")
        if struct.unpack_from("<H", code, base + len(rows) * ROW)[0] == END:
            return rows
        rows.append(Row.unpack(code, base + len(rows) * ROW))


def row_ranks(rows: list[Row], quest_stars: Mapping[int, int]) -> list[str]:
    """The rank (low, high, G) of each row's quest: by the quest's stars in the knowledge base (1-3 low, 4-7 high, 8-10
    G); a quest the knowledge base lacks (the Caravan's) takes the rank of the row before it, the first rows low."""
    out, rank = [], "low"
    for row in rows:
        stars = quest_stars.get(row.quest)
        if stars is not None:
            rank = "low" if stars <= 3 else "high" if stars <= 7 else "G"
        out.append(rank)
    return out


def monster_order(materials) -> dict[str, int]:
    """XX monster -> its place in the order of the new rows: the materials file's order, a deviant right after his base
    (and after the deviants before him)."""
    names = list(materials.monsters)
    base_of = lambda name: materials.monsters[name].base or name      # noqa: E731
    ordered = sorted(names, key=lambda name: (names.index(base_of(name)), name != base_of(name), names.index(name)))
    return {name: place for place, name in enumerate(ordered)}


def new_rows(materials, trade_rank=None) -> list[Row]:
    """The rows of the materials' new items that have a trade, in the order they take after the game's rows: one block
    per monster (`monster_order`), inside it by rank (low, high, G) then item id. A row is `{received = the item, quest
    = the rank's marker (trade_rows.c: the row opens with its rank), (given, 1)}`."""
    from core.gameplay.wyporium import wyporium_data
    trade_rank = trade_rank or wyporium_data.trade_rank
    place = monster_order(materials)
    keyed = []
    for item in materials.new:
        if isinstance(item.obtain, Mapping) and "trade" in item.obtain:
            rank = RANK_ORDER.index(trade_rank(item))
            row = Row(materials.id(item), MARKER_QUEST + rank, ((item.obtain["trade"], 1),))
            keyed.append(((place[item.monster], rank, row.received), row))
    return [row for _, row in sorted(keyed, key=lambda pair: pair[0])]


def patch_trades(code: bytes, materials, layout: Layout | None = None, trade_rank=None, by_rank: bool = True) -> bytes:
    """`code` (the update's executable) with the table of `materials`' trades added: the longer table in the block, the
    pool words of FUN_00a53160, FUN_009dd4c8 and the menu at 0x9B6F40 repointed to it, the row count of
    FUN_009dd4c8 raised, and the three calls that read a row's quest sent to `trade_row_open` (trade_rows.c).
    Nothing changes when no item has a trade. `by_rank` (option layered_by_rank): a new row opens with its rank; False:
    every new row is open from the start."""
    new = new_rows(materials, trade_rank)
    if not new:
        return bytes(code)
    if len(new) > MAX_NEW_ROWS:
        raise CodeSpaceError(f"{len(new)} new trades: at most {MAX_NEW_ROWS}")
    if not supports_trades(code):
        raise CodeSpaceError("unexpected trade table readers: new trades need the update's executable (or it is "
                             "already patched)")
    game = game_rows(code)
    if len(game) != GAME_ROWS:
        raise CodeSpaceError(f"the trade table has {len(game)} rows, not {GAME_ROWS}")
    rows = game + new
    count = len(rows) + 1
    if count > 0xFF:
        raise CodeSpaceError(f"{count} rows do not fit the compare's immediate")
    layout = layout or load_layout()
    out = bytearray(code)
    table = b"".join(row.pack() for row in rows) + struct.pack(GAME_ROW_FIELDS, END, 0, 0, 0, 0, 0, 0, 0)
    layout.place(out, BLOCK, table.ljust(BLOCK_SIZE, b"\0"))
    for at, _ in POOL_WORDS:
        struct.pack_into("<I", out, at - BASE_ADDRESS, layout.address(BLOCK))
    struct.pack_into("<I", out, COUNT_CMP - BASE_ADDRESS, (COUNT_CMP_WORD & ~0xFF) | count)
    layout.place(out, CODE_BLOCK)
    layout.place(out, DATA_BLOCK, rows_data(by_rank))
    for at in ROW_READERS:
        layout.hook(out, at, layout.symbol(CODE_BLOCK, "trade_row_open"), calls=QUEST_CLEARED)
    return bytes(out)


def rows_data(by_rank: bool = True) -> bytes:
    """The block DATA_BLOCK: what opens the high and the G rank (curated layered_looks.json `rank_unlocks`, the lists
    Layered Gear and the exchange read), as trade_rows.c reads them; `by_rank` False: every rank open (UNLOCK_OPEN)."""
    from core.equipment.layered.layered_rules import rank_unlock_words
    from core.equipment.layered.looks import load_curated
    words = rank_unlock_words(load_curated()["rank_unlocks"], by_rank)
    data = struct.pack(f"<{len(words)}H", *words)
    if len(data) != DATA_SIZE:
        raise CodeSpaceError(f"the rank unlock lists take {len(data)} bytes, the block holds {DATA_SIZE}")
    return data


# ----- the game's trades as data -----------------------------------------------------------------------------------

TICKETS = (0x378, 0x379, 0x6B8, 0x6B9)     # Accolade, Accolade G, Conqueror's Seal, Conqueror's Seal G


def game_trades(rows: list[Row], ranks: list[str], names: Mapping[int, str]) -> dict[str, dict]:
    """generated/wyporium_trades.json's "trades" from the game's rows: received item (text) -> {"name", "give" (the
    item handed over: the row's first item that is no ticket), "give_name", "rank" (1-3: the row's, `row_ranks`),
    "quest" (id), "ticket" (when the row asks one)}. `names`: item id -> English name."""
    out = {}
    for row, rank in zip(rows, ranks):
        gives = [item for item, _ in row.gives if item not in TICKETS]
        tickets = [item for item, _ in row.gives if item in TICKETS]
        if not gives:
            continue
        out[str(row.received)] = {"name": names[row.received], "give": gives[0], "give_name": names[gives[0]],
                                  "rank": RANK_ORDER.index(rank) + 1, "quest": row.quest,
                                  **({"ticket": tickets[0]} if tickets else {})}
    return out
