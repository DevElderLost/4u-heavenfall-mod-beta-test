"""Single-screen mode, the farm's status cards with fewer than three carts (emulator only).

FUN_00a84460 (the farm's status panel, ui404's root group `l_jyoutai`, from the farm's refresh FUN_009e2b20) moves the
group by the number of carts so its cards stay at the bottom of the touch screen: it writes the group's translate y as
an integer turned into a float, `mvnne r1, #0x3f` (-64, two carts) at 0xA844B4 and `mvneq r1, #0x83` (-132, one or
none) at 0xA844B8; three carts write 0. In single-screen mode the layout is scaled by its curated factor (ui404, 0.72),
but a root group's translate is not under the layout's nulls, so these drops land in full-size pixels and the cards go
past the bottom of the screen. This patch rewrites the two immediates as the drops times the layout's factor, rounded
to whole pixels (the instruction loads an integer). The words are checked first; the version maps carry them
unchanged (the update's and both base games' bytes: `tests/interface/single_screen/test_single_screen_farm_carts.py`).
"""

import struct

from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError

SITES = ((0xA844B4, 0x13E0103F), (0xA844B8, 0x03E01083))   # mvnne r1, #0x3f (-64) / mvneq r1, #0x83 (-132)
DROPS = (64, 132)                                           # the group's drop for two carts, for one or none
STORE = (0xA844D4, 0xED800A0B)                              # vstr s0, [r0, #0x2c]: the translate y they feed
MVN_MASK = 0xFFFFFF00                                       # the instruction without its 8-bit immediate


def supports_farm_carts(code: bytes) -> bool:
    """True if the two immediates and the store they feed are the game's own (the canonical executable, unpatched)."""
    try:
        return all(struct.unpack_from("<I", code, a - BASE_ADDRESS)[0] == word for a, word in (*SITES, STORE))
    except (IndexError, struct.error):
        return False


def drops(factor: float) -> tuple[int, int]:
    """The drops (two carts, one or none) for a layout at `factor`, in whole pixels."""
    return tuple(int(drop * factor + 0.5) for drop in DROPS)


def patch_farm_carts(code: bytes, factor: float) -> bytes:
    """`code` where the status cards drop by `factor` times the game's pixels with fewer than three carts."""
    if not supports_farm_carts(code):
        raise CodeSpaceError(f"farm carts: the words at {SITES[0][0]:#x} are not the update's (another executable, or "
                             "already patched)")
    if not 0 < factor <= 1:
        raise CodeSpaceError(f"farm carts: factor {factor} (0 to 1)")
    out = bytearray(code)
    for (site, word), drop in zip(SITES, drops(factor)):
        struct.pack_into("<I", out, site - BASE_ADDRESS, word & MVN_MASK | drop - 1)    # mvn: -(imm + 1)
    return bytes(out)
