"""Single-screen mode, the size of the GUI manager's null pane pool (emulator only).

The GUI manager (`*(gui + 0x100)`) builds its pools from a table of seven sizes: FUN_00c0d854 copies the table at
`TABLE` into the manager and FUN_00b031b8 allocates a pool from each word (groups, nulls, sprites, windows, texts,
boundaries, and the extra panes beyond their sum). A pool hands out its objects in order and never checks the index:
past its size the allocation returns a null pointer, which the layout loader (FUN_00b03a2c) writes through, one record
per pane. The Gathering Hall and room scenes load about 7,000 nulls of the game's 7,200 (every text pane takes one
too), and the mod's layouts add about 250 (the wrappers of `wrap` and `carry`, the frames, the hints, the players'
box): the last layouts of the room's list got null pointers.

This patch raises the null pool's word (the curated `gui_pools.nulls` of single_screen.json); the pane pool is sized
by the manager from the other words, so it grows with it. Nothing else changes: the word is data, so no branch or
address is involved and the version maps carry it unchanged (it is in .rodata, which does not move between the
update and the base games).
"""

import json
import struct
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError

SETTINGS_FILE = CURATED_DIR / "single_screen.json"

TABLE = 0xE065BC                      # the manager's pool sizes, read by FUN_00c0d854 (copied from here at 0xC10580)
TABLE_ORIGINAL = struct.pack("<7I", 1536, 7200, 18000, 0, 5000, 1200, 2048)   # groups, nulls, sprites, windows, texts,
NULL_POOL = TABLE + 4                 # boundaries, extra panes; the null pool's word is the second
NULLS_MIN = 7200                      # the game's own size: a smaller pool would break its own layouts
NULLS_MAX = 16384                     # a sanity limit: each null costs 0x5C bytes of the game's heap (with its pane)


def gui_pool_nulls(path: Path = SETTINGS_FILE) -> int:
    """The null pool's size (single_screen.json, "gui_pools", "nulls")."""
    where = "single_screen.json, gui_pools"
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("gui_pools")
    if not isinstance(record, dict) or set(record) != {"nulls"}:
        raise ValueError(f"{where}: an object with \"nulls\", nothing else")
    nulls = record["nulls"]
    if isinstance(nulls, bool) or not isinstance(nulls, int) or not NULLS_MIN <= nulls <= NULLS_MAX:
        raise ValueError(f"{where}, nulls: a whole number from {NULLS_MIN} (the game's) to {NULLS_MAX}")
    return nulls


def supports_pools(code: bytes) -> bool:
    """True if the manager's size table is the game's own (the canonical executable, not yet patched)."""
    at = TABLE - BASE_ADDRESS
    return code[at:at + len(TABLE_ORIGINAL)] == TABLE_ORIGINAL


def patch_pools(code: bytes, nulls: int) -> bytes:
    """`code` where the GUI manager's null pool holds `nulls` objects (FUN_00b031b8 sizes the pane pool from it)."""
    if not supports_pools(code):
        raise CodeSpaceError(f"GUI pools: the size table at {TABLE:#x} is not the update's (another executable, or "
                             "already patched)")
    out = bytearray(code)
    struct.pack_into("<I", out, NULL_POOL - BASE_ADDRESS, nulls)
    return bytes(out)
