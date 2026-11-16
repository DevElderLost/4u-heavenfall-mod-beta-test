"""The cheats Interruptible Flex and Whetstone Sharpening Cancel: the hunter's flex after a drink or a meal ends at once
on a tilt of a stick or a press of
A, B, X or Y, and his sharpening on a press of B, each while its Mod Settings option is on. From the players' Gateway
codes for the USA update; here as the block `action_cancel` (cheats/action_cancel/action_cancel.c) and its data block.

This function changes, in the update's executable (canonical):

- FUN_00b1471c, the hunter's update: its call of FUN_00b670c0, the frame of the hunter's action (UPDATE_CALL), goes to
  the block, which ends the flex or the sharpening the way they end themselves (FUN_00b1d7b4) when the player's input
  asks for it, then makes the game's call.

The gate: each cheat is on while its option's value (mod_options_state.values, as mod_options_stub.s's gates read
it) is not the first of its list. The options are the rows FLEX_OPTION and WHETSTONE_OPTION of mod_options.py
OPTION_IDS; until a row is there its id is NO_OPTION and that cheat never runs. Reads only the variable, so a mod
without Mod Settings has both off. Update's executable only; the version maps carry it to the base games.
"""

import struct

from core.game.executable.blocks import GAME_SYMBOLS
from core.game.executable.code_space import CodeSpaceError, Layout, bl_target, load_layout

BLOCK, DATA = "action_cancel", "action_cancel_data"
STATE = "mod_options_state"             # the options' values the block reads (interface/mod_settings/mod_options.c)
UPDATE_CALL = 0xB14A98                  # FUN_00b1471c, the hunter's update: bl FUN_00b670c0(hunter)
RUN_ACTION = 0xB670C0                   # FUN_00b670c0(hunter): the frame of the hunter's action, by its group
# The game's functions the block names (blocks.py GAME_SYMBOLS), checked against what the executable has
GAME_NAMES = {"hunter_run_action": RUN_ACTION}

# The Mod Settings rows that turn each cheat on (keys of mod_options.py OPTION_IDS). Placeholders: no such row exists
# yet, so both cheats are off until the rows are added under these names (or these names are changed to the rows').
FLEX_OPTION, WHETSTONE_OPTION = "cheat_interruptible_flex", "cheat_whetstone_cancel"
NO_OPTION = 0xFF                        # an id the block takes as "no option": the cheat never runs (action_cancel.c)


def option_ids(ids: dict[str, int] | None = None) -> tuple[int, int]:
    """The ids of the flex's and the sharpening's options in `ids` (default mod_options.py OPTION_IDS), NO_OPTION for
    a row it does not have."""
    if ids is None:
        from core.interface.mod_settings.mod_options import OPTION_IDS as ids
    return ids.get(FLEX_OPTION, NO_OPTION), ids.get(WHETSTONE_OPTION, NO_OPTION)


def action_cancel_data(options: tuple[int, int]) -> bytes:
    """The block `action_cancel_data` (action_cancel.c struct action_cancel_data): the two options' ids."""
    from core.interface.mod_settings.mod_options import MAX_OPTIONS
    if len(options) != 2 or not all(isinstance(i, int) and (0 <= i < MAX_OPTIONS or i == NO_OPTION)
                                    for i in options):
        raise ValueError(f"the cheats' options {options!r}: two ids of mod_options.py OPTION_IDS (or NO_OPTION)")
    return struct.pack("<2I", *options)


def supports_action_cancel(code: bytes) -> bool:
    """True if the hunter's update calls the action's frame where the update's executable does."""
    try:
        return bl_target(code, UPDATE_CALL) == RUN_ACTION and \
            all(GAME_SYMBOLS[name] == address for name, address in GAME_NAMES.items())
    except (struct.error, IndexError):
        return False


def patch_action_cancel(code: bytes, layout: Layout | None = None,
                        options: tuple[int, int] | None = None) -> bytes:
    """`code` (the update's executable) where the hunter's update ends the flex and the sharpening on the player's
    input, each while its option is on. `options`: the two options' ids (flex, sharpening); default option_ids()."""
    if not supports_action_cancel(code):
        raise CodeSpaceError("unexpected call in the hunter's update: the action cancels need the update's executable")
    layout = layout or load_layout()
    data = action_cancel_data(option_ids() if options is None else options)
    out = bytearray(code)
    layout.place(out, BLOCK)
    layout.place(out, DATA, data)
    layout.reserve(out, STATE)
    layout.hook(out, UPDATE_CALL, BLOCK, calls=RUN_ACTION)
    return bytes(out)


__all__ = ["BLOCK", "DATA", "FLEX_OPTION", "NO_OPTION", "RUN_ACTION", "UPDATE_CALL", "WHETSTONE_OPTION",
           "action_cancel_data", "option_ids", "patch_action_cancel", "supports_action_cancel"]
