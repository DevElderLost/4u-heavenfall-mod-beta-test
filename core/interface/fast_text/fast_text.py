"""Fast text (option fast_text): holding B runs through the conversation windows at high speed.

FUN_005a9310 drives the text of the conversation windows (ui005_kaiwa) and is the only caller of the
typewriter. Each of its three calls goes through the block `fast_text` (interface/fast_text/fast_text.s), which, while B
is held, shows every page at once and presses A every other frame. Update's
executable only.
"""

from core.game.executable.code_space import CodeSpaceError, Layout, bl_target, load_layout

MESSAGE_UPDATE = 0x5A9310  # FUN_005a9310(pressed, ?, out, manual)
# Its callers: FUN_0025ec00, FUN_009aeecc and FUN_00be2f60 (the conversation of the story events).
CALLS = (0x25EC50, 0x9AF038, 0xBE31BC)


def supports_fast_text(code: bytes) -> bool:
    """True if the calls are where the update's executable has them."""
    return all(bl_target(code, at) == MESSAGE_UPDATE for at in CALLS)


def patch_fast_text(code: bytes, layout: Layout | None = None, gated: bool = False) -> bytes:
    """`code` (the update's executable) where holding B runs through the conversations. `gated`: each call goes through
    the gate of the START menu's options (interface/mod_settings/mod_options_stub.s), which makes the game's own call
    while the option is off."""
    if not supports_fast_text(code):
        raise CodeSpaceError("unexpected calls to FUN_005a9310: fast text needs the update's executable")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, "fast_text")
    for at in CALLS:
        layout.hook(out, at, layout.symbol("mod_options_stub", "gate_fast_text") if gated else "fast_text",
                    calls=MESSAGE_UPDATE)
    return bytes(out)
