"""Fast gathering (option fast_gathering): the hunter gathers, mines, catches bugs, carves and fishes faster.

The Speed Gatherer skill raises the hunter's mPlayerSpeed in the gathering action (FUN_00b56708) and takes a
quarter off its real-time timer; the block `fast_gathering` (gameplay/fast_gathering/fast_gathering.s) does both by
GATHER_SPEED, on top of the skill, for the local hunter: the motion speed call of the hunter's frame update
scales mPlayerSpeed while the action is one of ACTIONS, and the skill check right after the timer is set
divides the timer. Update's executable only.
"""

import struct

from core.game.executable.code_space import CodeSpaceError, Layout, bl_target, load_layout

GATHER_SPEED = 2.0  # how many times faster (2.0 = 200 %); the Speed Gatherer skill multiplies on top

# act_no of the hunter's actions (pl_st = act_st = 0) that go faster.
ACTIONS = (
    77,             # gathering point (herbs, mushrooms...)
    78,             # gathering, second kind (same function, kind 1)
    81,             # mining and bone piles
    82,             # bug catching
    83, 84,         # carving
    148, 149, 150,  # the other kinds of the gathering function (FUN_00b56708, kinds 6, 7, 9)
    91, 92, 93, 94, 95, 96,  # fishing (91, 92 and 96 measured; the rest are its other steps)
)
MAX_ACTIONS = 15  # the block's table: 16 halfwords, 0-terminated

MOTION_SPEED = 0xB06624       # FUN_00b06624(hunter, speed in s0)
MOTION_SPEED_CALL = 0xB14B1C  # in the hunter's frame update
HAS_SKILL = 0xD04F5C          # FUN_00d04f5c(hunter, skill)
TIMER_CALL = 0xB56A3C         # in FUN_00b56708, right after pw->mTimer is set: has_skill(hunter, 188 Speed Gatherer)


def supports_fast_gathering(code: bytes) -> bool:
    """True if the two calls are where the update's executable has them."""
    return bl_target(code, MOTION_SPEED_CALL) == MOTION_SPEED and bl_target(code, TIMER_CALL) == HAS_SKILL


def fast_gathering_data(layout: Layout, speed: float = GATHER_SPEED) -> bytes:
    """The block's bytes with `speed`, its inverse and ACTIONS."""
    if speed <= 0:
        raise ValueError(f"gathering speed {speed} must be positive")
    if len(ACTIONS) > MAX_ACTIONS or 0 in ACTIONS:
        raise ValueError(f"at most {MAX_ACTIONS} actions, none of them 0")
    block = layout.block("fast_gathering")
    data = bytearray(block.data)
    for label, value in (("speed", struct.pack("<f", speed)), ("inverse", struct.pack("<f", 1 / speed)),
                         ("actions", struct.pack(f"<{MAX_ACTIONS + 1}H", *ACTIONS,
                                                 *[0] * (MAX_ACTIONS + 1 - len(ACTIONS))))):
        at = layout.symbol("fast_gathering", label) - block.address
        data[at:at + len(value)] = value
    return bytes(data)


def patch_fast_gathering(code: bytes, layout: Layout | None = None, speed: float = GATHER_SPEED) -> bytes:
    """`code` (the update's executable) where the local hunter's gathering actions are `speed` times faster."""
    if not supports_fast_gathering(code):
        raise CodeSpaceError("unexpected calls in the hunter's update: fast gathering needs the update's executable")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, "fast_gathering", fast_gathering_data(layout, speed))
    layout.hook(out, MOTION_SPEED_CALL, "fast_gathering", calls=MOTION_SPEED)
    layout.hook(out, TIMER_CALL, layout.symbol("fast_gathering", "timer"), calls=HAS_SKILL)
    return bytes(out)
