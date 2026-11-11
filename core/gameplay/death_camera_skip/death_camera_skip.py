"""START skips a slain monster's death camera (option skip_death_camera, a row of the START menu's Mod Settings only).

The camera manager's frame (FUN_00c006f4) plays the death camera, an event camera sequence of kind 0xD, and calls
FUN_00c03d70(manager, slot, 1) once a frame while it plays; when that call returns 0 the manager ends the camera
itself (frees the slot and its camera list, and the hunter's camera comes back). That call goes through the block
`death_camera_skip` (gameplay/death_camera_skip/death_camera_skip.c), which returns 0 when START was pressed.
Through the START menu's gate (`gated`) it does so only with the option on.

Update's executable only; the call is checked first.
"""

import struct

from core.game.executable.code_space import CodeSpaceError, Layout, bl_target, load_layout

BLOCK = "death_camera_skip"

CAMERA_PLAY = 0xC03D70      # FUN_00c03d70(manager, slot, n): one frame of an event camera; 0 when it is over
PLAY_CALL = 0xC00858        # in FUN_00c006f4: the call for a frame of a camera sequence (the death camera)

# Constants of the game's format, shared with death_camera_skip.c and its tests
SLOT_KIND = 0xCC            # an event camera slot's kind (byte; the manager's +0x1124 for slot 0)
KIND_DEATH = 0xD            # the monster's death camera
PAD_GUI_PRESSED = 0x348     # the pad object's GUI buttons pressed this frame (u32); START is 0x400
START_FRAMES = 2            # death_camera_skip_state while the camera plays: the menu's gate counts it down


def supports_death_camera_skip(code: bytes) -> bool:
    """True if the call is where the update's executable has it (not yet patched)."""
    try:
        return bl_target(code, PLAY_CALL) == CAMERA_PLAY
    except (struct.error, IndexError, ValueError):
        return False


def patch_death_camera_skip(code: bytes, layout: Layout | None = None, gated: bool = False) -> bytes:
    """`code` (the update's executable) where START ends the death camera. `gated`: the call goes through the gate of
    the START menu's options (interface/mod_settings/mod_options_stub.s), which makes the game's own call while the
    option is off."""
    if not supports_death_camera_skip(code):
        raise CodeSpaceError(f"death camera skip: the call at {PLAY_CALL:#x} is not the update's "
                             "(another executable, or already patched)")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, BLOCK)
    entry = layout.symbol("mod_options_stub", "gate_death_camera") if gated else layout.symbol(BLOCK,
                                                                                               "death_camera_step")
    layout.hook(out, PLAY_CALL, entry, calls=CAMERA_PLAY)
    return bytes(out)
