"""The Cheats group's damage multipliers: the damage this player's hits
deal to monsters and the damage this player's hunter takes, each multiplied by the factor of its own row of Mod
Settings (the value's float payload in curated mod_settings.json; the first value, x1, is the game's own).

These functions change, in the update's executable (canonical):

- FUN_00921f74(uEnemy, region, total, flag), a hit's damage into the monster's damage of the frame: its call of
  FUN_0092bf98 (DEALT_CALL), the hit's final damage, goes through the stub, which multiplies a hit of this player's
  (the rule of Damage Numbers, interface/damage_numbers/hit_owner.h). The call of FUN_00921f74 itself, Damage
  Numbers' hook, stays free;
- FUN_00b1ac40(hunter, change, out), the hunter's damage with Guts and the death: its `mov r1, r10` (CHECK_SITE)
  goes through the stub, which scales the change it keeps for its Guts test and passes on, and its call of
  FUN_00b6b4bc (KEPT_CALL) skips that function's own hook, so the change is scaled once;
- FUN_00b6b4bc(hunter, change), the hunter's health change (18 calls, FUN_00b1ac40's among them): its `mov r5, r1`
  (ADD_SITE) goes through the stub, which scales a loss of this console's hunter.

Online the damage to a monster changes only on the console that runs it,
so the dealt factor acts there; the health is each console's own hunter's. Each multiplier's option is the number of
its row in Mod Settings (mod_options.py OPTION_IDS), handed in by the caller; one without a number is not hooked.
"""

import struct
from collections.abc import Mapping

from core.cheats.gates import NO_OPTION, option_numbers
from core.game.executable.blocks import GAME_SYMBOLS
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout

# The rows (their keys in mod_options.py OPTION_IDS), in damage_multipliers.c's order
DEALT, TAKEN = "cheat_damage_dealt", "cheat_damage_taken"
CHEATS = (DEALT, TAKEN)

STUB, CODE, DATA = "damage_multipliers_stub", "damage_multipliers", "damage_multipliers_data"
STATE, CARRY = "mod_options_state", "damage_taken_carry"

DAMAGE_RATE = 0x92BF98                  # FUN_0092bf98(uEnemy, total, flag, 1): a hit's final damage
DEALT_CALL = 0x921F9C                   # in FUN_00921f74: bl FUN_0092bf98
HEALTH_ADD = 0xB6B4BC                   # FUN_00b6b4bc(hunter, change): the hunter's health change
HEALTH_ADD_WORDS = (0xE92D4FF0, 0xE1A05001, 0xE1A04000)     # push {r4-r11, lr}; mov r5, r1; mov r4, r0
ADD_SITE = HEALTH_ADD + 4               # its `mov r5, r1`
CHECK_SITE, CHECK_WORD = 0xB1AC74, 0xE1A0100A   # FUN_00b1ac40: mov r1, r10, before its call of FUN_00b6b4bc
KEPT_CALL = 0xB1AC80                    # FUN_00b1ac40: bl FUN_00b6b4bc
# The game's functions the stub names (blocks.py GAME_SYMBOLS), checked against the addresses above
GAME_NAMES = {"monster_damage_rate": DAMAGE_RATE, "hunter_health_body": HEALTH_ADD + 8,
              "hunter_is_local": 0xD04FBC}


def _word(code: bytes, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def supports_damage_multipliers(code: bytes) -> bool:
    """True if the three functions have the update's words at the sites (not patched yet)."""
    try:
        return bl_target(code, DEALT_CALL) == DAMAGE_RATE and bl_target(code, KEPT_CALL) == HEALTH_ADD and \
            _word(code, CHECK_SITE) == CHECK_WORD and \
            all(_word(code, HEALTH_ADD + 4 * k) == word for k, word in enumerate(HEALTH_ADD_WORDS)) and \
            all(GAME_SYMBOLS[name] == address for name, address in GAME_NAMES.items())
    except (struct.error, IndexError):
        return False


def multipliers_data(options: Mapping[str, int]) -> bytes:
    """The block `damage_multipliers_data` (struct damage_multipliers_data): each row's option, NO_OPTION without
    one."""
    return struct.pack("<2B2x", *(options.get(key, NO_OPTION) for key in CHEATS))


def patch_damage_multipliers(code: bytes, option_ids: Mapping[str, int], layout: Layout | None = None) -> bytes:
    """`code` (the update's executable, extended or not) with the multipliers whose row `option_ids` names (DEALT,
    TAKEN: their rows' numbers in Mod Settings, e.g. mod_options.py OPTION_IDS); `code` itself when it names neither."""
    options = option_numbers(option_ids, CHEATS)
    if not options:
        return code
    if not supports_damage_multipliers(code):
        raise CodeSpaceError("unexpected code at the damage's sites: the multipliers need the update's executable")
    layout = layout or load_layout()
    out = bytearray(code)
    for name in (STUB, CODE):
        layout.place(out, name)
    layout.place(out, DATA, multipliers_data(options))
    layout.reserve(out, STATE, CARRY)
    at = lambda label: layout.symbol(STUB, label)  # noqa: E731
    if DEALT in options:
        layout.hook(out, DEALT_CALL, at("damage_dealt_hook"), calls=DAMAGE_RATE)
    if TAKEN in options:
        layout.hook(out, CHECK_SITE, at("damage_taken_check"), original=struct.pack("<I", CHECK_WORD))
        layout.hook(out, KEPT_CALL, at("health_add_kept"), calls=HEALTH_ADD)
        layout.hook(out, ADD_SITE, at("damage_taken_add"), original=struct.pack("<I", HEALTH_ADD_WORDS[1]))
    return bytes(out)


__all__ = ["CHEATS", "DEALT", "TAKEN", "multipliers_data", "patch_damage_multipliers", "supports_damage_multipliers"]
