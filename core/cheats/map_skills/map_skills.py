"""Capture Guru and Autotracker always on, from the players' Gateway codes for the USA update, each gated during play by
its own option of Mod Settings
(interface/mod_settings/mod_options.c `mod_option_value`): with the option off the game runs as without them.

The minimap asks FUN_00d04f58(hunter, skill), the game's "has skill", in two places; the hooks, in the update's
executable (canonical), send those calls to the block `map_skills_stub` (cheats/map_skills/map_skills_stub.s), which
answers yes while the cheat is on and makes the game's call while it is off:

- FUN_00b9b390, a large monster's mark on the minimap: skill 0xBF, Capture Guru (CAPTURE_GURU_CALL), the mark blinks
  when the monster can be captured;
- FUN_00b9651c, whether the minimap shows the large monsters: skill 0xBD, Autotracker (AUTOTRACKER_CALL).

No other place of the game asks for those two skills, so the cheats change the minimap only. The version maps carry it
to the base games. Each cheat's option is the number of its row in Mod Settings (mod_options.py OPTION_IDS), handed
in by the caller; a cheat without one is not hooked.
"""

import struct
from collections.abc import Mapping

from core.cheats.gates import NO_OPTION, option_numbers
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout

# The cheats' options (their keys in mod_options.py OPTION_IDS), in map_skills.c's
# order
CAPTURE_GURU = "cheat_capture_guru"
AUTOTRACKER = "cheat_autotracker"
CHEATS = (CAPTURE_GURU, AUTOTRACKER)

STUB, CODE, DATA = "map_skills_stub", "map_skills", "map_skills_data"

HAS_SKILL = 0xD04F58                # FUN_00d04f58(hunter, skill): `mov r0, r0`, then the game's has_skill
CAPTURE_GURU_CALL = 0xB9B41C        # in FUN_00b9b390: has skill 0xBF (Capture Guru)
AUTOTRACKER_CALL = 0xB96538         # in FUN_00b9651c: has skill 0xBD (Autotracker)
SKILL_SETUP = ((0xB9B418, 0xE3A010BF), (0xB96520, 0xE3A010BD))     # the calls' `mov r1, #0xBF`, `mov r1, #0xBD`
# (option, the call, the stub's entry)
HOOKS = ((CAPTURE_GURU, CAPTURE_GURU_CALL, "capture_guru_hook"), (AUTOTRACKER, AUTOTRACKER_CALL, "autotracker_hook"))


def supports_map_skills(code: bytes) -> bool:
    """True if both calls ask the update's "has skill" for their skill (not patched yet)."""
    if len(code) < CAPTURE_GURU_CALL + 4 - BASE_ADDRESS:
        return False
    return all(bl_target(code, at) == HAS_SKILL for _, at, _ in HOOKS) and \
        all(struct.unpack_from("<I", code, at - BASE_ADDRESS)[0] == word for at, word in SKILL_SETUP)


def skills_data(options: Mapping[str, int]) -> bytes:
    """The block `map_skills_data` (struct map_skills_data): each cheat's option, NO_OPTION without one."""
    return struct.pack("<2B2x", *(options.get(key, NO_OPTION) for key in CHEATS))


def patch_map_skills(code: bytes, option_ids: Mapping[str, int], layout: Layout | None = None) -> bytes:
    """`code` (the update's executable, extended or not) with the minimap's skill cheats whose option `option_ids`
    names (CAPTURE_GURU, AUTOTRACKER: their rows' numbers in Mod Settings, e.g. mod_options.py OPTION_IDS); `code`
    itself when it names neither."""
    options = option_numbers(option_ids, CHEATS)
    if not options:
        return code
    if not supports_map_skills(code):
        raise CodeSpaceError("unexpected code at the minimap's skill calls: the cheats need the update's executable")
    layout = layout or load_layout()
    out = bytearray(code)
    for name in (STUB, CODE):
        layout.place(out, name)
    layout.place(out, DATA, skills_data(options))
    for key, at, entry in HOOKS:
        if key in options:
            layout.hook(out, at, layout.symbol(STUB, entry), calls=HAS_SKILL)
    return bytes(out)
