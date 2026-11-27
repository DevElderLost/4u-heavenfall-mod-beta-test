"""The cheat Charge Blade Guard Point: the Charge Blade's morph
from guarding becomes the morph after a sword attack, whose motion has the guard point, with and without the stick.
From the players' Gateway codes for the USA update ("CB Fix Guard Point", parts 1 and 2), gated during play by its own
option of Mod Settings (interface/mod_settings/mod_options.c `mod_option_value`): with the option off the game runs as
without it.

This function changes, in the update's executable (canonical):

- FUN_00b1c6f0(hunter, group, number, flags), the start of the hunter's action: its first instruction (START,
  `push {r4-r12, lr}`) branches to the block `guard_point_stub` (cheats/guard_point/guard_point_stub.s), which asks
  `guard_point_action` (guard_point.c) for the number to start: for the local hunter's Charge Blade, group 4's 0x0B
  (the morph from guarding) becomes 0x06 (the morph after an attack) and 0x1C (the same with the stick) 0x1B.

The Charge Blade's group 4 frame (FUN_00cc30c0, a jump table on the number: CHARGE_BLADE_FRAME) runs the four as
FUN_00cc73cc(hunter, from_guard, lunge) (MORPHS). The version maps carry the patch to the base games. The cheat's
option is the number of its row in Mod Settings (mod_options.py OPTION_IDS), handed in by the caller; without one it
is not hooked.
"""

import struct
from collections.abc import Mapping

from core.cheats.gates import NO_OPTION, option_numbers
from core.game.executable.blocks import GAME_SYMBOLS
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, load_layout

# The cheat's option (its key in mod_options.py OPTION_IDS)
GUARD_POINT_OPTION = "cheat_cb_guard_point"
CHEATS = (GUARD_POINT_OPTION,)

STUB, CODE, DATA = "guard_point_stub", "guard_point", "guard_point_data"

# FUN_00b1c6f0(hunter, group, number, flags), the start of the hunter's action: its first instruction
START = 0xB1C6F0
START_WORD = struct.pack("<I", 0xE92D5FF0)      # push {r4-r12, lr}
# The game's code the stub goes on to (blocks.py GAME_SYMBOLS), checked against what the patch hooks
GAME_NAMES = {"hunter_start_action_body": START + 4}

# The Charge Blade's group 4 frame (the class's vtable + 0xD4) and its actions
CHARGE_BLADE_FRAME = 0xCC30C0
MORPH_ACTION = 0xCC73CC             # FUN_00cc73cc(hunter, from_guard, lunge)
WEAPON_GROUP = 4
# The action's number: (from_guard, lunge) of FUN_00cc73cc
MORPHS = {0x06: (0, 0), 0x0B: (1, 0), 0x1B: (0, 1), 0x1C: (1, 1)}
SWAPS = {0x0B: 0x06, 0x1C: 0x1B}    # what the cheat starts instead (guard_point.c)


def supports_guard_point(code: bytes) -> bool:
    """True if the action's start begins with the update's instruction (not patched yet)."""
    at = START - BASE_ADDRESS
    return len(code) >= at + 4 and bytes(code[at:at + 4]) == START_WORD and \
        all(GAME_SYMBOLS[name] == address for name, address in GAME_NAMES.items())


def guard_point_data(options: Mapping[str, int]) -> bytes:
    """The block `guard_point_data` (guard_point.c struct guard_point_data): the cheat's option, NO_OPTION without
    one."""
    return struct.pack("<B3x", options.get(GUARD_POINT_OPTION, NO_OPTION))


def patch_guard_point(code: bytes, option_ids: Mapping[str, int], layout: Layout | None = None) -> bytes:
    """`code` (the update's executable, extended or not) with the cheat when `option_ids` names its option
    (GUARD_POINT_OPTION: its row's number in Mod Settings, e.g. mod_options.py OPTION_IDS); `code` itself when it
    does not."""
    options = option_numbers(option_ids, CHEATS)
    if not options:
        return code
    if not supports_guard_point(code):
        raise CodeSpaceError("unexpected code at the hunter's action start: the cheat needs the update's executable")
    layout = layout or load_layout()
    out = bytearray(code)
    for name in (STUB, CODE):
        layout.place(out, name)
    layout.place(out, DATA, guard_point_data(options))
    layout.hook(out, START, layout.symbol(STUB, "guard_point_hook"), original=START_WORD, link=False)
    return bytes(out)


__all__ = ["CHARGE_BLADE_FRAME", "CHEATS", "CODE", "DATA", "GUARD_POINT_OPTION", "MORPHS", "MORPH_ACTION", "START",
           "START_WORD", "STUB", "SWAPS", "WEAPON_GROUP", "guard_point_data", "patch_guard_point",
           "supports_guard_point"]
