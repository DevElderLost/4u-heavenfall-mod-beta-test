"""START does what the touch screen's Skip does (option skip_monster_intro, a row of the START menu's Mod Settings
only).

While the game offers a skip (a monster's intro cutscene, or an event camera it lets the player skip), the touch menu
bar's third button is Skip. Its input, FUN_002951fc, calls that button's handler FUN_00292ea4(position, button, kind)
once a frame; that call goes through the block `intro_skip` (gameplay/intro_skip/intro_skip.c), which makes it and then,
when START was pressed in a quest, makes the calls a touch of Skip makes, after the same checks. Through the START
menu's gate (`gated`) it does so only with the option on. Single-screen mode hides the touch screen, so START is the way
to the game's own skip there.

A skipped cutscene's music and sounds stop, for START and the
touch alike: the event player's frame FUN_0019dfb8 calls FUN_0030cb5c while it skips and FUN_0030cd10 at the event's
end; both calls go through the block too (`intro_skip_music`, `intro_skip_end`), which makes them and then fades out
every live voice of the event's two stream queues.

Update's executable only; the calls are checked first.
"""

import struct

from core.game.executable.code_space import CodeSpaceError, Layout, bl_target, load_layout

BLOCK = "intro_skip"

BUTTON_HANDLER = 0x292EA4   # FUN_00292ea4(position, button, kind): the frame of a touch bar button of kind 7, 8, 9, 0xB
BUTTON_CALL = 0x296114      # in FUN_002951fc (the touch bar's input): its call of that handler
SKIP_SOUND = 0x30CB5C       # FUN_0030cb5c(sound control): fades the event players' streams out, stops the sounds
SKIP_SOUND_CALL = 0x19EADC  # in FUN_0019dfb8 (the event player's frame): its call of it while the event skips
END_SOUND = 0x30CD10        # FUN_0030cd10(sound control): the sound control's part of an event's end
END_SOUND_CALL = 0x19EDC0   # in FUN_0019dfb8: its call of it when the event ends

# Each call the patch takes: (its place, the game's function it calls, the block's entry, the START menu's gate)
CALLS = ((BUTTON_CALL, BUTTON_HANDLER, "intro_skip_button", "gate_intro_skip"),
         (SKIP_SOUND_CALL, SKIP_SOUND, "intro_skip_music", "gate_intro_music"),
         (END_SOUND_CALL, END_SOUND, "intro_skip_end", "gate_intro_end"))

# Constants of the game's format, shared with intro_skip.c and its tests
BAR_SKIP_OF = 0xCF          # the touch bar's byte: which skip its Skip button stands for
SKIP_CAMERA = 1             # an event camera the camera manager lets the player skip
SKIP_CUTSCENE = 2           # a cutscene the event player lets the player skip (a monster's intro)
KIND_SKIP = 0xB             # a touch bar button's kind: Skip
PAD_GUI_PRESSED = 0x348     # the pad object's GUI buttons pressed this frame (u32); START is 0x400
START_FRAMES = 2            # death_camera_skip_state after a skip: the menu's gate counts it down
EVENT_SKIPPING = 0x17       # the event player's byte: the event plays to its end as skipped
SOUND_EVENT_MUSIC = 0x1680  # the sound control's handle of the event music's queue (bgm_ev_st)
SOUND_EVENT_SOUND = 0x1684  # the sound control's handle of the event sounds' queue (se_ev_st)
DRIVER_VOICES = 0x5B98      # the sound driver's stream voices: DRIVER_VOICE_SIZE bytes each, DRIVER_VOICE_COUNT of them
DRIVER_VOICE_SIZE = 0x3A8
DRIVER_VOICE_COUNT = 0x900C
VOICE_ACTIVE = 0x4          # a voice's bytes and words: active, phase, queue handle, request
VOICE_PHASE = 0x5
VOICE_QUEUE = 0x8
VOICE_REQUEST = 0xC
SKIP_FADE = 1000            # FUN_0030cb5c's fade-out, which the block's fades copy


def supports_intro_skip(code: bytes) -> bool:
    """True if the calls are where the update's executable has them (not yet patched)."""
    try:
        return all(bl_target(code, at) == calls for at, calls, _, _ in CALLS)
    except (struct.error, IndexError, ValueError):
        return False


def patch_intro_skip(code: bytes, layout: Layout | None = None, gated: bool = False) -> bytes:
    """`code` (the update's executable) where START does what the touch screen's Skip does. `gated`: the call goes
    through the gate of the START menu's options (interface/mod_settings/mod_options_stub.s), which makes the game's own
    call while the option is off."""
    if not supports_intro_skip(code):
        raise CodeSpaceError("intro skip: the calls at " + ", ".join(f"{at:#x}" for at, _, _, _ in CALLS)
                             + " are not the update's (another executable, or already patched)")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, BLOCK)
    for at, calls, entry, gate in CALLS:
        target = layout.symbol("mod_options_stub", gate) if gated else layout.symbol(BLOCK, entry)
        layout.hook(out, at, target, calls=calls)
    return bytes(out)
