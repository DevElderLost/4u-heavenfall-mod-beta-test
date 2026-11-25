"""The jukebox's block in the card file: two changes to the
game's code, on an executable patch_jukebox (patch.py) has patched, whose resident block `jukebox_save` holds the
stubs (jukebox_save_stub.s) and the C (jukebox_save.c, jukebox_core.c):

* FUN_002adedc (the card file's writer): its `mov r3, #1` at STORE_AT, after its last copy into the plain file and
  before its sum, becomes `bl jukebox_store_stub`, which writes the jukebox's block into the file's tail
  (jukebox_store) and then does the `mov r3, #1`;
* FUN_002ae018 (the card file's read step): its call of the reader FUN_002adc98 at LOAD_AT becomes `bl
  jukebox_load_stub`, which calls the reader and, when the reader accepted the file, reads the block from it
  (jukebox_load); the step gets the reader's answer.

Update's executable only; the version maps carry it to the base games.
"""

from __future__ import annotations

import struct

from core.game.executable.blocks import GAME_SYMBOLS
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout
from core.music.jukebox.patch import SAVE_CODE

# FUN_002adedc (the card file's writer): `mov r3, #1` after its last copy (FUN_00c1ac78) and before the sum's call
STORE_AT = 0x2ADFDC
MOV_R3_1 = 0xE3A03001
# FUN_002ae018 (the card file's read step): its call of the reader FUN_002adc98, r0 the file task
LOAD_AT = 0x2AE05C
CARD_READ = GAME_SYMBOLS["card_read"]


def _word(code: bytes, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def supports_jukebox_save(code: bytes) -> bool:
    """`code` (the update's executable, canonical) has the instructions the patch replaces."""
    if len(code) < STORE_AT + 4 - BASE_ADDRESS or len(code) < LOAD_AT + 4 - BASE_ADDRESS:
        return False
    return _word(code, STORE_AT) == MOV_R3_1 and bl_target(code, LOAD_AT) == CARD_READ


def patch_jukebox_save(code: bytes, layout: Layout | None = None) -> bytes:
    """`code`, which patch_jukebox has patched, with the card file's two hooks. Refuses an executable where a site is
    not the game's instruction (another version, or patched already) or that lacks the block jukebox_save."""
    if not supports_jukebox_save(code):
        raise CodeSpaceError("unexpected code at the card file's writer or reader: the jukebox needs the update's "
                             "executable, patched once")
    layout = layout or load_layout()
    block = layout.block(SAVE_CODE)
    if bytes(code[block.address - BASE_ADDRESS:block.end - BASE_ADDRESS]) != block.data:
        raise CodeSpaceError("the jukebox's block is not in the executable: patch_jukebox comes first")
    out = bytearray(code)
    layout.hook(out, STORE_AT, layout.symbol(SAVE_CODE, "jukebox_store_stub"), original=struct.pack("<I", MOV_R3_1))
    layout.hook(out, LOAD_AT, layout.symbol(SAVE_CODE, "jukebox_load_stub"), calls=CARD_READ)
    return bytes(out)


__all__ = ["CARD_READ", "LOAD_AT", "MOV_R3_1", "STORE_AT", "patch_jukebox_save", "supports_jukebox_save"]
