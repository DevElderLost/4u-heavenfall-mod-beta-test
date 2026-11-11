"""One more item in the haul of every expedition of the Meownster Hunters: Foreign Scrap at the low level, Foreign
Scrap+ at the high level (curated/
xx_materials.json "foreign_scraps", `expedition`).

One hook in the game's claim function FUN_00aab770, at the instruction that loads the haul's count: meownster_scrap.c
adds one entry to the haul there (only for the Meownster Hunters' own facility, not the Housekeeper's route). The two
item ids and their count are a data block this patcher writes. Canonical (update) addresses; the version maps do the
base games.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping

from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, load_layout

BLOCK = "meownster_scrap"
DATA = "meownster_scrap_data"
HOOK_SYMBOL = "meownster_extra_hook"
SITE = 0xAABAA8                  # `ldr r0, [sp, #0x6c]` of FUN_00aab770: the haul's count, after the per-quest loop
SITE_WORD = 0xE59D006C
# The claim's two reward-list tables (literal-pool words of FUN_00aab770): the check that this is the claim
POOLS = {0xAABB10: 0xEDF2E8, 0xAABB14: 0xEDF5B8}


def _word(code: bytes, address: int) -> int:
    return struct.unpack_from("<I", code, address - BASE_ADDRESS)[0]


def supports_meownster_scrap(code: bytes) -> bool:
    """Whether `code` has the claim function as the update's executable (the site and the two pool words)."""
    return len(code) >= max(POOLS) - BASE_ADDRESS + 4 and _word(code, SITE) == SITE_WORD and all(
        _word(code, at) == word for at, word in POOLS.items())


def extra_data(expedition: Mapping, item_ids: Mapping[str, int]) -> bytes:
    """The data block: the item of the low and the high level and how many of it (curated `expedition`; `item_ids`: the
    run's items by English name). Raises CodeSpaceError for a name the run lacks."""
    ids = []
    for level in ("low", "high"):
        name = expedition[level]
        if name not in item_ids:
            raise CodeSpaceError(f"meownster_scrap: the run has no item called {name!r}")
        ids.append(item_ids[name])
    return struct.pack("<4H", ids[0], ids[1], int(expedition.get("count", 1)), 0)


def patch_meownster_scrap(code: bytes, expedition: Mapping, item_ids: Mapping[str, int],
                          layout: Layout | None = None) -> bytes:
    """`code` with each expedition of the Meownster Hunters bringing one more item besides its haul."""
    if not supports_meownster_scrap(code):
        raise CodeSpaceError("unexpected code at the Meownster Hunters' claim: the extra item needs the update's "
                             "executable")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, BLOCK)
    layout.place(out, DATA, extra_data(expedition, item_ids))
    layout.hook(out, SITE, layout.symbol(BLOCK, HOOK_SYMBOL), original=struct.pack("<I", SITE_WORD))
    return bytes(out)
