"""The jukebox's menu in the executable: the house Felyne's menu gets the line
"Jukebox" and the facility a state 10 that runs it (jukebox_menu.c, its hook stubs jukebox_menu_stub.s, units of the
block `jukebox`). Five changes to the game's code, each a `bl` that returns to the next instruction:

* FUN_00aa8074 (the facility's entry): its call of FUN_00aa771c, which fills the menu's lines, calls jukebox_lines,
  which makes our line (action 7) the last;
* FUN_009db3ac (the menu drawn): `mov r1, #0xb` after the lines calls jukebox_menu_line_stub (our line's frame and
  text);
* FUN_009db608 (the cursor line's help): `mov r2, #0` calls jukebox_help_stub (our line's help);
* FUN_00aa8298 (the facility's update), A on a line: `ldrb r0, [r1, r0]` (the line's action) calls
  jukebox_pick_menu_stub, which enters state 10 for our line;
* FUN_00aa8298's state switch: `cmp r0, #0xa` calls jukebox_state_stub, which runs state 10.

It also sets the page counter's place in jukebox_data (the game's, or single-screen mode's) and the way back it takes
on a wider picture (single-screen mode). Update's executable only,
on one patch.patch_jukebox has patched; the version maps carry it to the base games.
"""

from __future__ import annotations

import struct

from core.game.executable import packs
from core.game.executable.blocks import JUKEBOX_DATA_SIZE, JUKEBOX_MENU_DATA_SIZE
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout
from core.music.jukebox.patch import CODE, COMMAND_PICK, DATA, supports_jukebox

MENU = "jukebox_menu"           # the menu's variable
# FUN_00aa8074 (the facility's entry): `bl FUN_00aa771c` (r0 the lobby object), the menu's lines
LINES_CALL = 0xAA8198
HOUSEKEEPER_LINES = 0xAA771C
# FUN_009db3ac (the menu drawn): `mov r1, #0xb` after its lines (r11 the lobby object)
MENU_DRAWN = 0x9DB590
MOV_R1_0XB = 0xE3A0100B
# FUN_009db608 (the cursor line's help): `mov r2, #0` before the line's action is read (r4 the facility's state)
LINE_HELP = 0x9DB66C
MOV_R2_0 = 0xE3A02000
# FUN_00aa8298 (the facility's update): `ldrb r0, [r1, r0]`, the action of the line A was pressed on (r5 the lobby
# object), and `cmp r0, #0xa`, its state switch's bound
LINE_PICK = 0xAA83DC
LDRB_R0_R1_R0 = 0xE7D10000
STATE_SWITCH = 0xAA82AC
CMP_R0_0XA = 0xE350000A
# The page counter's place (FUN_00288fac's x and y) as the game's lists of ui443 pass it
COUNTER = (256, 10)
COUNTER_AT = JUKEBOX_DATA_SIZE - JUKEBOX_MENU_DATA_SIZE    # jukebox_data's counter_x
COUNTER_WAY_AT = JUKEBOX_DATA_SIZE - 2 * 2                 # jukebox_data's counter_sides, counter_fitted


def _word(code: bytes, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def supports_jukebox_menu(code: bytes) -> bool:
    """`code` (the update's executable, canonical) has the instructions the menu's patch replaces."""
    if len(code) < LINE_PICK + 4 - BASE_ADDRESS:
        return False
    return (bl_target(code, LINES_CALL) == HOUSEKEEPER_LINES and _word(code, MENU_DRAWN) == MOV_R1_0XB
            and _word(code, LINE_HELP) == MOV_R2_0 and _word(code, LINE_PICK) == LDRB_R0_R1_R0
            and _word(code, STATE_SWITCH) == CMP_R0_0XA)


def patch_jukebox_menu(code: bytes, layout: Layout | None = None, counter: tuple[int, int] | None = None,
                       counter_way: tuple[int, int] = (0, 0)) -> bytes:
    """`code`, which patch.patch_jukebox has patched, with the jukebox's menu: its five hooks, its variable, the page
    counter's place `counter` (default COUNTER, the game's) and its way back on a wider picture `counter_way` (sides,
    fitted pixels: build.counter_way). Refuses an executable without the jukebox's engine, one where a site is not the
    game's instruction, or one patched already."""
    layout = layout or load_layout()
    called = bl_target(code, COMMAND_PICK)      # the engine's entry, or its stub (the block is the town's pack's)
    if supports_jukebox(code) or \
            layout.symbol(CODE, "jukebox_command_pick") not in (called, packs.stub_target(code, called)):
        raise CodeSpaceError("the jukebox's menu needs an executable patch_jukebox has patched")
    if not supports_jukebox_menu(code):
        raise CodeSpaceError("unexpected code at the house Felyne's menu: already patched, or not the update's "
                             "executable")
    x, y = COUNTER if counter is None else counter
    out = bytearray(code)
    layout.reserve(out, MENU)
    struct.pack_into("<2h", out, layout.address(DATA) + COUNTER_AT - BASE_ADDRESS, x, y)
    struct.pack_into("<2h", out, layout.address(DATA) + COUNTER_WAY_AT - BASE_ADDRESS, *counter_way)
    layout.hook(out, LINES_CALL, layout.symbol(CODE, "jukebox_lines"), calls=HOUSEKEEPER_LINES)
    layout.hook(out, MENU_DRAWN, layout.symbol(CODE, "jukebox_menu_line_stub"),
                original=struct.pack("<I", MOV_R1_0XB))
    layout.hook(out, LINE_HELP, layout.symbol(CODE, "jukebox_help_stub"), original=struct.pack("<I", MOV_R2_0))
    layout.hook(out, LINE_PICK, layout.symbol(CODE, "jukebox_pick_menu_stub"),
                original=struct.pack("<I", LDRB_R0_R1_R0))
    layout.hook(out, STATE_SWITCH, layout.symbol(CODE, "jukebox_state_stub"), original=struct.pack("<I", CMP_R0_0XA))
    return bytes(out)


__all__ = ["COUNTER", "COUNTER_AT", "COUNTER_WAY_AT", "LINES_CALL", "LINE_HELP", "LINE_PICK", "MENU", "MENU_DRAWN",
           "STATE_SWITCH", "patch_jukebox_menu", "supports_jukebox_menu"]
