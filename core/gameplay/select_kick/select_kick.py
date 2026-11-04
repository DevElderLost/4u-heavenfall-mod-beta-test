"""Select and Start follow the game's own option "START".

The game's option (page 2 of the Options, "Set whether START is used to kick or open the menu."; settings index 0x11,
0 Menu and 1 Kick) decides, always on:

* Menu (the game's default): only Start opens the Game Menu, Select kicks;
* Kick: in a quest Start kicks (the game's own path) and Select opens and closes the Game Menu; in a town both open it.

At the title or with no save loaded Select does nothing. The touch panel's kick is unchanged. Two calls of the update's
executable go through the block `select_kick` (gameplay/select_kick/select_kick.c):

* `SDK_FIX_CALL`, in FUN_00485708 (the SDK's pad step): the conditional `bl` of FUN_00571e58 (Select becomes Start in
  the 3DS pad status). The block makes that call only in a town with the option at Kick; otherwise it presses the kick
  or notes Select for the menu;
* `OPTION_CALL`, in FUN_005ecf60 (the Game Menu's per-frame logic): the `bl` of FUN_002b02fc (the settings byte that
  stops Start from opening the menu in a quest). The block lets a Select press through when the option is Kick.

Update's executable only; each call is checked first.
"""

import struct

from core.game.executable.code_space import (
    BASE_ADDRESS, COND_EQ, CodeSpaceError, Layout, bl_target, branch_word, load_layout,
)

BLOCK = "select_kick"

SDK_FIX = 0x571E58                  # FUN_00571e58(status): Select -> Start in the 3DS pad status
SDK_FIX_CALL = 0x4857F0             # in FUN_00485708: the call of FUN_00571e58, taken when the SDK's own step ran
OPTION_READ = 0x2B02FC              # FUN_002b02fc(settings, index): the settings byte `index`
OPTION_CALL = 0x5ED0D0              # in FUN_005ecf60: the call of FUN_002b02fc(settings, 0x11)

SDK_ORIGINAL = branch_word(SDK_FIX_CALL, SDK_FIX, link=True, cond=COND_EQ)    # the update's word at SDK_FIX_CALL


def supports_select_kick(code: bytes) -> bool:
    """True if both calls are where the update's executable has them (not yet patched)."""
    try:
        sdk = struct.unpack_from("<4s", code, SDK_FIX_CALL - BASE_ADDRESS)[0]
        return sdk == SDK_ORIGINAL and bl_target(code, OPTION_CALL) == OPTION_READ
    except struct.error:
        return False


def patch_select_kick(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (the update's executable) where Select and Start follow the game's option START."""
    if not supports_select_kick(code):
        raise CodeSpaceError("select kick: the calls at "
                             f"{SDK_FIX_CALL:#x} / {OPTION_CALL:#x} are not the update's "
                             "(another executable, or already patched)")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, BLOCK)
    layout.hook(out, SDK_FIX_CALL, layout.symbol(BLOCK, "select_kick_step"), original=SDK_ORIGINAL, cond=COND_EQ)
    layout.hook(out, OPTION_CALL, layout.symbol(BLOCK, "select_kick_gate"), calls=OPTION_READ)
    return bytes(out)
