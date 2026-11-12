"""Select and Start follow the game's own option "START".

The game's option (page 2 of the Options, "Set whether START is used to kick or open the menu."; settings index 0x11,
0 Menu and 1 Kick) decides, always on:

* Menu (the game's default): only Start opens the Game Menu, Select kicks;
* Kick: in a quest Start kicks (the game's own path) and Select opens and closes the Game Menu; in a town both open it.

At the title or with no save loaded Select does nothing. The touch panel's kick is unchanged. Three calls of the
update's executable go through the block `select_kick` (gameplay/select_kick/select_kick.c):

* `SDK_FIX_CALL`, in FUN_00485708 (the SDK's pad step, on its path with an extra pad answering: the New 3DS's ZL, ZR
  and C-stick, or a Circle Pad Pro): the conditional `bl` of FUN_00571e58 (Select becomes Start in the 3DS pad
  status). The block makes that call only in a town with the option at Kick; otherwise it presses the kick or notes
  Select for the menu;
* `HID_FIX_CALL`, in FUN_00485e30 (the same step's path without an extra pad: an Old 3DS alone, or a New 3DS with its
  C-stick off): the conditional `bl` of FUN_00571e4c, the same with the held buttons at +0; the block does the same
  there;
* `OPTION_CALL`, in FUN_005ecf60 (the Game Menu's per-frame logic): the `bl` of FUN_002b02fc (the settings byte that
  stops Start from opening the menu in a quest). The block lets a Select press through when the option is Kick.

`plain` (a mod without Select's kick: Heavenfall Beta with its single-screen module off) keeps the calls for what
other features need of them and leaves Select and Start the game's: the SDK's call is made as it was (Select is a
second Start), and in a town Select also presses the kick's button, which Layered Gear's Armor screen reads as Select
(its colour window); the menu's call answers Kick while a skipped death camera plays or just after START did the touch
screen's Skip, so the START that skips does not open the Game Menu (gameplay/death_camera_skip/death_camera_skip.c,
gameplay/intro_skip/intro_skip.c).

Update's executable only; each call is checked first.
"""

import struct

from core.game.executable.code_space import (
    BASE_ADDRESS, COND_EQ, CodeSpaceError, Layout, bl_target, branch_word, load_layout,
)

BLOCK = "select_kick"

SDK_FIX = 0x571E58                  # FUN_00571e58(status): Select -> Start in the 3DS pad status
SDK_FIX_CALL = 0x4857F0             # in FUN_00485708: the call of FUN_00571e58, on the extra pad's path
HID_FIX = 0x571E4C                  # FUN_00571e4c(status): the same, the held buttons at +0
HID_FIX_CALL = 0x485F40             # in FUN_00485e30: the call of FUN_00571e4c, on the path without the extra pad
OPTION_READ = 0x2B02FC              # FUN_002b02fc(settings, index): the settings byte `index`
OPTION_CALL = 0x5ED0D0              # in FUN_005ecf60: the call of FUN_002b02fc(settings, 0x11)

SDK_ORIGINAL = branch_word(SDK_FIX_CALL, SDK_FIX, link=True, cond=COND_EQ)    # the update's word at SDK_FIX_CALL
HID_ORIGINAL = branch_word(HID_FIX_CALL, HID_FIX, link=True, cond=COND_EQ)    # the update's word at HID_FIX_CALL


def supports_select_kick(code: bytes) -> bool:
    """True if the three calls are where the update's executable has them (not yet patched)."""
    try:
        sdk = struct.unpack_from("<4s", code, SDK_FIX_CALL - BASE_ADDRESS)[0]
        hid = struct.unpack_from("<4s", code, HID_FIX_CALL - BASE_ADDRESS)[0]
        return sdk == SDK_ORIGINAL and hid == HID_ORIGINAL and bl_target(code, OPTION_CALL) == OPTION_READ
    except struct.error:
        return False


def patch_select_kick(code: bytes, layout: Layout | None = None, plain: bool = False) -> bytes:
    """`code` (the update's executable) where Select and Start follow the game's option START. `plain`: they stay the
    game's, and the two calls only give Layered Gear's Armor screen its Select in a town and keep the START that skips
    a death camera out of the Game Menu."""
    if not supports_select_kick(code):
        raise CodeSpaceError("select kick: the calls at "
                             f"{SDK_FIX_CALL:#x} / {HID_FIX_CALL:#x} / {OPTION_CALL:#x} are not the update's "
                             "(another executable, or already patched)")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, BLOCK)
    step = "select_plain_step" if plain else "select_kick_step"
    layout.hook(out, SDK_FIX_CALL, layout.symbol(BLOCK, step), original=SDK_ORIGINAL, cond=COND_EQ)
    layout.hook(out, HID_FIX_CALL, layout.symbol(BLOCK, step + "_hid"), original=HID_ORIGINAL, cond=COND_EQ)
    layout.hook(out, OPTION_CALL, layout.symbol(BLOCK, "select_kick_gate"), calls=OPTION_READ)
    return bytes(out)
