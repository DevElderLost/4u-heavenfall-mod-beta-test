"""The cheats that stay in the installer: the debug cheat cheat_insta_kill, and the aspect ratio
(cheat_aspect_allowed, cheat_aspect_ratio; its own module, cheats/aspect_ratio.py). The players' Gateway / Citra cheat
codes for the update (1.1) that a player turns on and off during play (3D, bloom and depth of field, the frame rate,
the field of view, the online fix, weapons' true attack) are rows of the START menu's Mod Settings page
(interface/mod_settings/mod_options.py).

Insta kill sends two calls of the hunter's attack to the block `insta_kill` (cheats/insta_kill.c), which multiplies and
caps the weapon's attack. Every setting at its neutral value leaves the executable as it was. Update's executable (the
canonical one) only; carried to the base games by the version maps.
"""

import struct
from typing import Any

from core.cheats.aspect_ratio import patch_aspect_ratio, supports_aspect_ratio
from core.game.data.tuning import tuning
from core.game.executable.code_space import CodeSpaceError, Layout, bl_target, load_layout

# Insta kill: FUN_002f8f34(table, hunter, stat, flag), a stat of the hunter's equipment (6: the weapon's attack), and
# the two calls that ask it for the attack: the hunter's attack in a hit (FUN_00b1ea88) and in the equipment's status
# screen (FUN_00af8b80). Both go to the block `insta_kill`, which calls it and multiplies the value.
HUNTER_GEAR_STAT = 0x2F8F34
ATTACK_CALLS = (0xB1EAC8, 0xAF8BB0)
INSTA_KILL, INSTA_KILL_DATA = "insta_kill", "insta_kill_data"


def float_bits(value: int | float) -> int:
    """The IEEE single of `value` (an angle, a frame rate), as the game keeps it."""
    return struct.unpack("<I", struct.pack("<f", value))[0]


def wants_cheats(settings: Any) -> bool:
    """Some cheat of the installer is not at its neutral value."""
    return bool(settings.cheat_insta_kill or settings.aspect_on)


def supports_cheats(code: bytes) -> bool:
    """True if every site holds the word the game has (a site in a hole of a game version holds a trap word)."""
    return all(bl_target(code, at) == HUNTER_GEAR_STAT for at in ATTACK_CALLS) and \
        supports_aspect_ratio(code, menu=False)


def insta_kill_data() -> bytes:
    """The block `insta_kill_data`: the attack's multiplier and cap (curated tuning.json, section cheats)."""
    multiplier, cap = tuning("cheats", "insta_kill_attack_multiplier"), tuning("cheats", "insta_kill_attack_cap")
    if not (isinstance(multiplier, int) and isinstance(cap, int) and multiplier > 0 and 0 < cap < 0x8000):
        raise ValueError("tuning.json cheats: insta_kill_attack_multiplier must be a whole number above 0 and "
                         "insta_kill_attack_cap one from 1 to 32767")
    return struct.pack("<2i", multiplier, cap)


def patch_cheats(code: bytes, settings: Any, layout: Layout | None = None, anchors: bytes | None = None) -> bytes:
    """`code` (the update's executable) with the installer's cheats `settings` turns on; `code` itself when none is.
    `anchors`: the aspect ratio's table of the interface's groups (interface/hud/anchors.py)."""
    if not wants_cheats(settings):
        return code
    if not supports_cheats(code):
        raise CodeSpaceError("unexpected code at the cheats' sites: they need the update's executable")
    out = bytearray(code)
    if settings.cheat_insta_kill:
        layout = layout or load_layout()
        layout.place(out, INSTA_KILL)
        layout.place(out, INSTA_KILL_DATA, insta_kill_data())
        for at in ATTACK_CALLS:
            layout.hook(out, at, INSTA_KILL, calls=HUNTER_GEAR_STAT)
    if settings.aspect_on:
        return patch_aspect_ratio(bytes(out), settings.cheat_aspect_ratio.value, layout, anchors, menu=False)
    return bytes(out)
