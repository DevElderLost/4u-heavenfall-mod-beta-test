"""The cheats a player turns on and off during play, each by its own option of Mod Settings
(interface/mod_settings/mod_options.c `mod_option_value`). A
cheat's patch takes the options' numbers (mod_options.py OPTION_IDS: a key, its row's number) and writes the cheat's
into its data block; its code reads that option every time the game reaches the hook, and with the option off the game
runs as without the cheat. A cheat whose key the numbers do not name is not hooked.
"""

from collections.abc import Mapping

from core.interface.mod_settings.mod_options import MAX_OPTIONS

NO_OPTION = 0xFF            # the C's: a cheat without an option (its hooks are not installed)


def option_numbers(option_ids: Mapping[str, int], cheats: tuple[str, ...]) -> dict[str, int]:
    """The numbers of `option_ids` that are `cheats`' options, in `cheats`' order; a number out of Mod Settings' room
    is refused."""
    chosen = {key: option_ids[key] for key in cheats if key in option_ids}
    for key, number in chosen.items():
        if not (isinstance(number, int) and 0 <= number < MAX_OPTIONS):
            raise ValueError(f"{key}: option number {number!r} is not one of Mod Settings' 0-{MAX_OPTIONS - 1}")
    return chosen
