"""The cheats of the quest's timers, from the players' Gateway codes for the USA update, each gated during play by its
own option of Mod
Settings (interface/mod_settings/mod_options.c `mod_option_value`): with the option off the game runs as without them.

* Skip Quest End Timer (SKIP_QUEST_END): holding A and B makes the countdown after a quest's end run `skip_speed` times
  faster (curated tuning.json, cheats.quest_end_skip_speed);
* No Time Limit on Rewards Screen (REWARDS_NO_LIMIT): the quest result scene's timer stops on its steps 1 and 2, and
  there the scene shows no countdown number; the other steps keep their limit and their countdown.

The hooks, in the update's executable (canonical), go to the blocks `quest_timers_stub` and `quest_timers`
(cheats/quest_timers/quest_timers_stub.s, quest_timers.c):

- FUN_0065c1b4, the quest's end: its load of the frame time (END_TIME, `vldr s1, [r0, #0x5c]`) takes the cheat's;
- FUN_00accd24, the quest result scene: its sum of the timer's fraction and the frame time (REWARDS_TICK,
  `vadd.f32 s0, s0, s1`) keeps the fraction on a frozen step;
- FUN_00ab88f4, the result scene's countdown: its first instruction (REWARDS_NUMBER, `push {r4, lr}`) branches to a
  stub that returns at once on a frozen step, so FUN_002ed5d0 does not show the number there.

The version maps carry it to the base games. Each cheat's option is the number of its row in Mod Settings
(mod_options.py OPTION_IDS), handed in by the caller; a cheat without one is not hooked.
"""

import struct
from collections.abc import Mapping

from core.cheats.gates import NO_OPTION, option_numbers
from core.game.data.tuning import tuning
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, load_layout

# The cheats' options (their keys in mod_options.py OPTION_IDS), in quest_timers.c's
# order
SKIP_QUEST_END = "cheat_skip_quest_end"
REWARDS_NO_LIMIT = "cheat_rewards_no_limit"
CHEATS = (SKIP_QUEST_END, REWARDS_NO_LIMIT)

STUB, CODE, DATA = "quest_timers_stub", "quest_timers", "quest_timers_data"

# FUN_0065c1b4 (the quest's end; step 2 of FUN_0065af38): `vldr s1, [r0, #0x5c]`, the main object's frame time
END_TIME = 0x65C42C
END_TIME_WORD = struct.pack("<I", 0xEDD00A17)
# FUN_00accd24 (the quest result scene): `vadd.f32 s0, s0, s1`, its timer's fraction plus the frame time
REWARDS_TICK = 0xAD0D30
REWARDS_TICK_WORD = struct.pack("<I", 0xEE300A20)
# FUN_00ab88f4(scene) (the result scene's countdown, which FUN_002ed5d0 shows): its first instruction, `push {r4, lr}`
REWARDS_NUMBER = 0xAB88F4
REWARDS_NUMBER_WORD = struct.pack("<I", 0xE92D4010)


def supports_quest_timers(code: bytes) -> bool:
    """True if the three sites hold the update's instructions (not patched yet)."""
    def word(at: int) -> bytes:
        return bytes(code[at - BASE_ADDRESS:at - BASE_ADDRESS + 4])
    return len(code) >= REWARDS_TICK + 4 - BASE_ADDRESS and word(END_TIME) == END_TIME_WORD and \
        word(REWARDS_TICK) == REWARDS_TICK_WORD and word(REWARDS_NUMBER) == REWARDS_NUMBER_WORD


def skip_speed() -> float:
    """How many times faster the countdown after a quest runs while A and B are held (curated tuning.json)."""
    speed = tuning("cheats", "quest_end_skip_speed")
    if not (isinstance(speed, (int, float)) and 1 <= speed <= 64):
        raise ValueError("tuning.json cheats: quest_end_skip_speed must be a number from 1 to 64")
    return float(speed)


def timers_data(options: Mapping[str, int]) -> bytes:
    """The block `quest_timers_data` (struct quest_timers_data): each cheat's option (NO_OPTION without one) and the
    countdown's speed."""
    return struct.pack("<2B2xf", *(options.get(key, NO_OPTION) for key in CHEATS), skip_speed())


def patch_quest_timers(code: bytes, option_ids: Mapping[str, int], layout: Layout | None = None) -> bytes:
    """`code` (the update's executable, extended or not) with the cheats of the quest's timers whose option
    `option_ids` names (SKIP_QUEST_END, REWARDS_NO_LIMIT: their rows' numbers in Mod Settings, e.g. mod_options.py
    OPTION_IDS); `code` itself when it names neither."""
    options = option_numbers(option_ids, CHEATS)
    if not options:
        return code
    if not supports_quest_timers(code):
        raise CodeSpaceError("unexpected code at the quest timers' sites: they need the update's executable")
    layout = layout or load_layout()
    out = bytearray(code)
    for name in (STUB, CODE):
        layout.place(out, name)
    layout.place(out, DATA, timers_data(options))
    if SKIP_QUEST_END in options:
        layout.hook(out, END_TIME, layout.symbol(STUB, "quest_end_hook"), original=END_TIME_WORD)
    if REWARDS_NO_LIMIT in options:
        layout.hook(out, REWARDS_TICK, layout.symbol(STUB, "rewards_tick_hook"), original=REWARDS_TICK_WORD)
        layout.hook(out, REWARDS_NUMBER, layout.symbol(STUB, "rewards_number_hook"), original=REWARDS_NUMBER_WORD,
                    link=False)
    return bytes(out)
