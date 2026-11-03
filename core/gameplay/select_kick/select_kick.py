"""Select kicks, Start opens the menu (option select_kick).

The game gives Select no button of its own: the SDK's pad step (FUN_00485708) turns a held SELECT into START in the
3DS pad status (FUN_00571e58), so Select opens the Game Menu like Start. Four words of the update's executable give
Select the kick instead, the button the touch panel's "Special Attack" presses:

* `SDK_FIX_CALL`, in FUN_00485708: the call of FUN_00571e58 becomes a `nop`, so SELECT stays HID bit 4;
* `RAW_READ_TEST` / `RAW_READ_SET`, in FUN_005b8460 (the raw pad read, which maps HID bits to the pad object's raw
  word at +0x8C): `tst r0, #8` / `orrne r4, r4, #8` (START) become `and ip, r0, #0xC` / `orr r4, r4, ip`, so SELECT is
  raw bit 4 beside START's raw 8 (ip is free there and the next instruction sets the flags again);
* `RAW_MASKS` entry 13, in the table of FUN_00694ccc (the pad update, raw word -> the game layout at +0x30C): the mask
  0, which no button could set, becomes 4. Its game bit is 0x1, which the hunter's input (FUN_00b169bc) reads as the
  kick.

Start keeps raw 8 and the game layout's 0x8000 (the Game Menu). The game's own option "START kicks" (settings index
0x11) is untouched. Update's executable only; every word is checked first.
"""

import struct

from core.game.executable.code_space import BASE_ADDRESS, COND_ALWAYS, COND_EQ, CodeSpaceError, branch_word

SDK_FIX = 0x571E58                  # FUN_00571e58(status): SELECT -> START in the pad status
SDK_FIX_CALL = 0x4857F0             # in FUN_00485708: bleq FUN_00571e58
RAW_READ_TEST = 0x5B84F0            # in FUN_005b8460: tst r0, #8
RAW_READ_SET = 0x5B84F4             # orrne r4, r4, #8
RAW_MASKS = 0xFB8260                # FUN_00694ccc's table: 16 raw masks, each giving the game bit of the table after it
RAW_MASK_ENTRY = 13                 # the entry whose game bit is 0x1 (kick) and whose mask is 0
SELECT_RAW_BIT = 0x4                # HID SELECT (4) in the raw word
RAW_MASK_AT = RAW_MASKS + 4 * RAW_MASK_ENTRY

NOP = 0xE320F000
# ARM instructions built from their fields
R0, R4, IP = 0, 4, 12
START_BITS = 0x8
SELECT_AND_START = SELECT_RAW_BIT | START_BITS


def and_imm(rd: int, rn: int, imm: int) -> int:
    return COND_ALWAYS << 28 | 0x2000000 | rn << 16 | rd << 12 | imm


def orr_reg(rd: int, rn: int, rm: int) -> int:
    return COND_ALWAYS << 28 | 0x1800000 | rn << 16 | rd << 12 | rm


# the update's words (retail), checked on the EUR and USA base games through the version maps
RETAIL = {
    SDK_FIX_CALL: int.from_bytes(branch_word(SDK_FIX_CALL, SDK_FIX, link=True, cond=COND_EQ), "little"),
    RAW_READ_TEST: 0xE3100008,      # tst r0, #8
    RAW_READ_SET: 0x13844008,       # orrne r4, r4, #8
    RAW_MASK_AT: 0,
}
PATCHED = {
    SDK_FIX_CALL: NOP,
    RAW_READ_TEST: and_imm(IP, R0, SELECT_AND_START),
    RAW_READ_SET: orr_reg(R4, R4, IP),
    RAW_MASK_AT: SELECT_RAW_BIT,
}


def _word(code: bytes, address: int) -> int:
    return struct.unpack_from("<I", code, address - BASE_ADDRESS)[0]


def supports_select_kick(code: bytes) -> bool:
    """True if every word the patch changes is the game's own (the canonical executable, not yet patched)."""
    try:
        return all(_word(code, address) == word for address, word in RETAIL.items())
    except struct.error:
        return False


def patch_select_kick(code: bytes) -> bytes:
    """`code` where Select is the kick and only Start opens the Game Menu."""
    if not supports_select_kick(code):
        raise CodeSpaceError("select kick: the words at "
                             f"{SDK_FIX_CALL:#x} / {RAW_READ_TEST:#x} / {RAW_MASK_AT:#x} are not the update's "
                             "(another executable, or already patched)")
    out = bytearray(code)
    for address, word in PATCHED.items():
        struct.pack_into("<I", out, address - BASE_ADDRESS, word)
    return bytes(out)
