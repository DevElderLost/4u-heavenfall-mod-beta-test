"""The block rare_exchange_data: what rare_exchange.c reads.

A header (the D_shop messages the screens show, what opens the high and the G rank, where the rest is), the rows (a
rare item, its rank, its pool, the message of its owners, the items it asks) and the pools (item ids). The rows are
generated/rare_exchange.json's: an MH4U row always, a ported monster's row only when he is in the run (`items.ported`;
layered_rules.Items resolves the names).
"""

import struct
from collections.abc import Mapping

from core.equipment.layered.layered_rules import Items, rank_unlock_words
from core.equipment.layered.looks import load_curated as load_layered
from core.gameplay.wyporium.exchange_texts import MESSAGES, message_id, owners_message
from core.gameplay.wyporium.wyporium_data import load_rare_exchange

MAGIC = 0x47484358                      # "XCHG"
RANKS = 3
UNLOCK_ROOM = 4
# magic, rows, pool words, the messages, the unlock lists (2 x 4), the pad that aligns rows_at, rows_at, pools_at
# (rare_exchange.c, struct xhead)
HEADER = struct.Struct(f"<I2H{len(MESSAGES)}H{(RANKS - 1) * UNLOCK_ROOM}H{len(MESSAGES) % 2 * 2}x2I")
assert HEADER.size == 44
# item, rank (0-2), pool length, first pool word, owners' message, units, a pad (xrow)
ROW = struct.Struct("<HBBHHBx")
MAX_POOL = 24                           # rare_exchange.c POOL_MAX


class ExchangeDataError(ValueError):
    pass


def exchange_rows(items: Items, exchange: Mapping | None = None) -> list[tuple[int, int, list[int], int, int]]:
    """(rare item id, rank 0-2, pool ids, the owners' first message, the items it asks) of the rows this run has, in the
    file's order: a ported monster's row needs him in the run (`items.ported`; None: any whose names resolve), the
    item and at least one item of the pool (a pool item the run lacks, a second name of one item and the rare item
    itself are left out). The monster decides, not the names:
    a run without him can hold items of the same names. A
    scrap's row asks `scrap_units`, any other the rank's `units`."""
    exchange = exchange or load_rare_exchange()
    rows = []
    for row in exchange["rows"]:
        if row.get("ported") and items.ported is not None and row["ported"] not in items.ported:
            continue
        item = items.resolve(row["item"])
        # each item once (the screens cap what is handed over per place, rare_exchange.c), never the rare item itself
        pool = list(dict.fromkeys(i for i in (items.resolve(p) for p in row["pool"]) if i is not None and i != item))
        if item is None or not pool:
            continue
        if len(pool) > MAX_POOL:
            raise ExchangeDataError(f"{row['name']}: {len(pool)} items in the pool, the screen holds {MAX_POOL}")
        units = exchange["scrap_units"] if row.get("scrap") else exchange["units"][row["rank"] - 1]
        rows.append((item, row["rank"] - 1, pool, owners_message(tuple(row["owners"]), exchange), units))
    return rows


def exchange_data(items: Items, size: int, exchange: Mapping | None = None) -> bytes:
    """The block, `size` bytes (zero padded); an ExchangeDataError when it does not fit."""
    exchange = exchange or load_rare_exchange()
    rows = exchange_rows(items, exchange)
    row_bytes, pool_words = bytearray(), []
    for item, rank, pool, owners, units in rows:
        row_bytes += ROW.pack(item, rank, len(pool), len(pool_words), owners, units)
        pool_words += pool
    if len(exchange["units"]) != RANKS:
        raise ExchangeDataError(f"units: {len(exchange['units'])} ranks, not {RANKS}")
    unlock = rank_unlock_words(load_layered()["rank_unlocks"])
    messages = [message_id(key) for key in MESSAGES]
    rows_at = HEADER.size
    pools_at = rows_at + len(row_bytes)
    head = HEADER.pack(MAGIC, len(rows), len(pool_words), *messages, *unlock, rows_at, pools_at)
    data = bytearray(head) + row_bytes + struct.pack(f"<{len(pool_words)}H", *pool_words)
    if len(data) > size:
        raise ExchangeDataError(f"the exchange takes {len(data)} bytes, more than the block rare_exchange_data "
                                f"({size}): raise its size in game/executable/blocks.py")
    return bytes(data) + bytes(size - len(data))
