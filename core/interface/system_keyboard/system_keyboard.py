"""Typing with the system keyboard (option system_keyboard).

MH4U types names, chat and guild card texts with a keyboard of its own (FUN_002b5788 opens it, FUN_002b58e8 polls it
once a frame), which the emulator cannot fill from the computer's keyboard. With the option on, the poll goes to the
block `system_keyboard` (system_keyboard.c), which runs the 3DS system keyboard (the library applet 0x401) through the
SDK's own calls, the ones the game uses for its other applets: the emulator shows its text box, the PC port its own
keyboard. The text typed goes where the game's keyboard leaves it, and the poll answers as the game's does. The hook is
FUN_002b58e8's first instruction, to the gate of the START menu's options (`gate_system_keyboard`). Update's
executable only.
"""

from core.game.executable.code_space import CodeSpaceError, Layout, load_layout

BLOCK = "system_keyboard"
GATE = "gate_system_keyboard"

KEYBOARD_POLL, POLL_WORD = 0x2B58E8, 0xE92D4070     # FUN_002b58e8(manager): push {r4, r5, r6, lr}

# The SDK's calls the block makes, each with its first word: FUN_0056f340 PrepareToStartLibraryApplet, FUN_0056ea78
# StartLibraryApplet, FUN_0010ab9c the wait for the applet's answer, FUN_00111864 svcCreateMemoryBlock, FUN_0047eff4
# the memory block's close
SDK = ((0x56F340, 0xE92D47F0), (0x56EA78, 0xE92D5FFF), (0x10AB9C, 0xE92D4FFF), (0x111864, 0xE52D0004),
       (0x47EFF4, 0xE92D4070))
APT_CALLS = tuple(at for at, _ in SDK)

# The keyboard manager (FUN_002b5788's first argument) and the game's keyboard, as system_keyboard.c reads them
M_KEYBOARD, M_MAX_LENGTH, M_TEXT = 0x2FBC, 0x2FC4, 0x2FC8
K_CONFIG = 0x1C
# The applet's configuration (0x400 bytes): where it answers
CONFIG_RETURN_CODE, CONFIG_TEXT_OFFSET, CONFIG_TEXT_LENGTH = 0x138, 0x144, 0x148


def _word(code: bytes, at: int) -> int:
    from core.game.executable.code_space import BASE_ADDRESS
    return int.from_bytes(code[at - BASE_ADDRESS:at - BASE_ADDRESS + 4], "little")


def supports_system_keyboard(code: bytes) -> bool:
    """True if the poll and the SDK's calls are the update's (the canonical executable, not patched yet)."""
    return all(_word(code, at) == word for at, word in ((KEYBOARD_POLL, POLL_WORD), *SDK))


def patch_system_keyboard(code: bytes, layout: Layout | None = None, gated: bool = False) -> bytes:
    """`code` (the update's executable) where the game's keyboard is the system keyboard. `gated`: the poll goes through
    the gate of the START menu's options (interface/mod_settings/mod_options_stub.s), which runs the game's own poll
    while the option is off."""
    if not supports_system_keyboard(code):
        raise CodeSpaceError("unexpected keyboard poll or SDK calls: the system keyboard needs the update's executable")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, BLOCK)
    target = layout.symbol("mod_options_stub", GATE) if gated else layout.symbol(BLOCK, "system_keyboard_poll")
    layout.hook(out, KEYBOARD_POLL, target, original=POLL_WORD.to_bytes(4, "little"), link=False)
    return bytes(out)


__all__ = ["APT_CALLS", "KEYBOARD_POLL", "patch_system_keyboard", "supports_system_keyboard"]
