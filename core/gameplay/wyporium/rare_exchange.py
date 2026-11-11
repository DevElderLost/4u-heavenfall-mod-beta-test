"""The Wyporium's Rare Materials Exchange (option rare_exchange): a fifth line in its menu, "Rare Materials Exchange",
and the two screens behind it (rare_exchange.c).

The Wyporium is facility 17 of the lobby; its function FUN_009b6d84 keeps its state at obj + 0xAA64 (0-11 are the
game's) and its menu is the facility menu's menu 9 (four lines; a request open) or 10 (three). The patch:

* adds the line to both: the per-menu tables of the facility menu (line counts, (file, message) of the line) and the
  cursor's configuration (the line count the cursor wraps at), and the compare that tells the two menus apart;
* hooks FUN_009b6d84 where the line must be told from the game's: the bright mask (the three-line menu's line 3 is ours,
  where the four-line menu has Requests), the menu's cursor (A on our line sets state 12), the help of the highlighted
  line, the state switch's default case (state 12 runs the screens) and the old state's cases (leaving state 12 closes
  them);
* places the block rare_exchange (the code), and rare_exchange_data (exchange_data.py).

The texts and panes are RomFS files (exchange_texts.py): the pipeline writes them.
"""

import struct
from collections.abc import Collection, Mapping

from core.equipment.layered.layered_rules import Items
from core.equipment.ported_gear.curated import mh4u_item_names
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, branch_word, load_layout
from core.gameplay.wyporium.exchange_data import exchange_data
from core.gameplay.wyporium.exchange_texts import SHOP_FILE, message_id

# The facility menu's tables (equipment/layered/layered_equipment.py): lines of each menu, and (file, message) of each.
MENU_COUNTS = 0xE045A0
MENU_LINES = 0xDF2814
MENU_SIZE, LINE_SIZE = 28, 4
FOUR_LINES, THREE_LINES = 9, 10          # the Wyporium's menus: with Requests, without
# The cursor's configurations (FUN_009c99cc): the line count first
CURSOR_FOUR, CURSOR_THREE = 0xEE7FCC, 0xEE7FE0
COMPARE = 0x9B72A4                       # cmp r0, #4: the cursor's line count tells menu 9 from menu 10
CMP_4, CMP_5 = 0xE3500004, 0xE3500005

STATE_DEFAULT = 0x9B6DE8                 # b 0x9B7A38: the state switch's default case
TAIL = 0x9B7A38
BRIGHT = 0x9B6FDC                        # bic r9, r9, #8: no request open, line 3 dim
BIC_R9_8 = 0xE3C99008
MENU_A = 0x9B6FEC                        # bl FUN_009eb38c: the menu's cursor
MENU_CURSOR = 0x9EB38C
HELP = 0x9B7014                          # cmp r0, #0: the highlighted line's help, by line
CMP_0 = 0xE3500000
LEAVE = 0x9B7A7C                         # b 0x9B7B80: the old state's cases, for states 6 and above
LEAVE_DEFAULT = 0x9B7B80


def _word(code: bytes, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def _line(menu: int, line: int) -> int:
    return MENU_LINES + menu * MENU_SIZE + line * LINE_SIZE


def supports_rare_exchange(code: bytes) -> bool:
    """True if every place the patch changes holds what the update's executable has there."""
    if len(code) < CURSOR_THREE + 4 - BASE_ADDRESS:
        return False
    words = {COMPARE: CMP_4, BRIGHT: BIC_R9_8, HELP: CMP_0,
             STATE_DEFAULT: struct.unpack("<I", branch_word(STATE_DEFAULT, TAIL))[0],
             LEAVE: struct.unpack("<I", branch_word(LEAVE, LEAVE_DEFAULT))[0], CURSOR_FOUR: 4, CURSOR_THREE: 3,
             _line(FOUR_LINES, 4): 0, _line(THREE_LINES, 3): 0}
    if any(_word(code, at) != word for at, word in words.items()):
        return False
    counts = code[MENU_COUNTS - BASE_ADDRESS:MENU_COUNTS - BASE_ADDRESS + THREE_LINES + 1]
    return counts[FOUR_LINES] == 4 and counts[THREE_LINES] == 3


def patch_rare_exchange(code: bytes, layout: Layout | None = None, item_ids: Mapping[str, int] | None = None,
                        ported: Collection[str] = ()) -> bytes:
    """`code` with the Wyporium's Rare Materials Exchange line and its screens. `item_ids`: the run's new items by
    English name (the ported monsters' gear, MH XX's materials), which the rows of their rare items and pools name;
    `ported`: the keys of the ported monsters in the run (a row of a monster not in it is left out)."""
    if not supports_rare_exchange(code):
        raise CodeSpaceError("unexpected code at the Wyporium's menu: the Rare Materials Exchange needs the update's "
                             "executable")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, "rare_exchange")
    size = len(layout.block("rare_exchange_data").data)
    layout.place(out, "rare_exchange_data", exchange_data(Items(mh4u_item_names(), item_ids or {}, ported), size))

    def symbol(name: str) -> int:
        return layout.symbol("rare_exchange", name)

    def put(at: int, word: int) -> None:
        struct.pack_into("<I", out, at - BASE_ADDRESS, word)

    name = message_id("name")
    struct.pack_into("<2H", out, _line(FOUR_LINES, 4) - BASE_ADDRESS, SHOP_FILE, name)
    struct.pack_into("<2H", out, _line(THREE_LINES, 3) - BASE_ADDRESS, SHOP_FILE, name)
    out[MENU_COUNTS - BASE_ADDRESS + FOUR_LINES] = 5
    out[MENU_COUNTS - BASE_ADDRESS + THREE_LINES] = 4
    put(CURSOR_FOUR, 5)
    put(CURSOR_THREE, 4)
    put(COMPARE, CMP_5)
    layout.hook(out, STATE_DEFAULT, symbol("exchange_state"), link=False, original=branch_word(STATE_DEFAULT, TAIL))
    layout.hook(out, BRIGHT, symbol("exchange_bright"), original=struct.pack("<I", BIC_R9_8))
    layout.hook(out, MENU_A, symbol("exchange_menu_a"), calls=MENU_CURSOR)
    layout.hook(out, HELP, symbol("exchange_help"), link=False, original=struct.pack("<I", CMP_0))
    layout.hook(out, LEAVE, symbol("exchange_leave"), link=False, original=branch_word(LEAVE, LEAVE_DEFAULT))
    return bytes(out)
