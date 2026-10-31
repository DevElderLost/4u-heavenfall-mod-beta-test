"""Single-screen mode, the Canteen's page counter (emulator only).

The shared page counter `ui036` ("1/2" with its two arrows) is placed by whichever menu shows it. The Canteen's
ingredient list (its update code at 0x9C5134: FUN_00a71258 fills the list, FUN_00a721c0 its cursor) calls
FUN_00288fac, which shows the counter, with its place as two immediates: `mov r1, #0x24` (y 36) at 0x9C5188 and
`mov r0, #0x114` (x 276) at 0x9C518C, in the touch screen's pixels from its top-left corner (FUN_00288fac writes
(200 - x, 120 - y) into the null `ui036_null00`). On the top screen that is the bottom-left quarter, where the
description panel stands in the Canteen (help_top's "canteen" place).

This patch rewrites the two immediates by the curated `canteen_page.shift` (whole pixels right and down,
`single_screen.json`): the Canteen's counter moves, the other menus' counters (each passes its own place) stay. A
place an ARM immediate cannot hold (an 8-bit value turned right by an even count) is refused. The words are checked
first, with the call they feed; the version maps carry them unchanged (the update's and both base games' bytes:
`tests/interface/single_screen/test_single_screen_canteen_page.py`).
"""

import json
import struct
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, bl_target

SETTINGS_FILE = CURATED_DIR / "single_screen.json"

SITES = ((0x9C5188, 0xE3A01024), (0x9C518C, 0xE3A00F45))    # mov r1, #0x24 (y) / mov r0, #0x114 (x)
CALL = 0x9C5190                                              # bl FUN_00288fac (x, y, page, pages, 0, 0)
PAGE_COUNTER = 0x288FAC                                      # FUN_00288fac: shows the counter at (x, y)
ORIGINAL = (276, 36)                                         # x, y
MOV_R0, MOV_R1 = 0xE3A00000, 0xE3A01000
SHIFT_LIMIT = 200                                            # pixels, one way or the other


def arm_immediate(value: int) -> int | None:
    """The 12-bit field of an ARM data-processing immediate holding `value` (8 bits turned right by an even count), or
    None when none does."""
    for rotate in range(16):
        turned = ((value << 2 * rotate) | (value >> (32 - 2 * rotate))) & 0xFFFFFFFF if rotate else value
        if turned < 0x100:
            return rotate << 8 | turned
    return None


def _place(shift: tuple[float, float]) -> tuple[int, int]:
    return ORIGINAL[0] + int(shift[0]), ORIGINAL[1] + int(shift[1])


def canteen_page_shift(path: Path = SETTINGS_FILE) -> tuple[float, float]:
    """How far the Canteen's counter moves (single_screen.json, "canteen_page", "shift": whole pixels right, down)."""
    where = "single_screen.json, canteen_page"
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("canteen_page", {"shift": [0, 0]})
    if not isinstance(record, dict) or set(record) != {"shift"}:
        raise ValueError(f"{where}: an object with \"shift\", nothing else")
    shift = record["shift"]
    if (not isinstance(shift, list) or len(shift) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) and abs(v) <= SHIFT_LIMIT for v in shift)):
        raise ValueError(f"{where}, shift: [right, down], whole numbers within {SHIFT_LIMIT}")
    for value, axis in zip(_place(shift), "xy"):
        if value < 0 or arm_immediate(value) is None:
            raise ValueError(f"{where}, shift: the counter's {axis} {value} is not an ARM immediate (0-255, or such a "
                             "value turned by an even count: try a neighbour)")
    return float(shift[0]), float(shift[1])


def supports_canteen_page(code: bytes) -> bool:
    """True if the two immediates are the game's own and feed the call to FUN_00288fac (the canonical executable,
    unpatched)."""
    try:
        return (all(struct.unpack_from("<I", code, a - BASE_ADDRESS)[0] == word for a, word in SITES)
                and bl_target(code, CALL) == PAGE_COUNTER)
    except (IndexError, struct.error):
        return False


def patch_canteen_page(code: bytes, shift: tuple[float, float]) -> bytes:
    """`code` where the Canteen's page counter stands `shift` whole pixels (right, down) from where the game puts it."""
    if not supports_canteen_page(code):
        raise CodeSpaceError(f"canteen page counter: the words at {SITES[0][0]:#x} are not the update's (another "
                             "executable, or already patched)")
    x, y = _place(shift)
    fields = arm_immediate(x), arm_immediate(y)
    if x < 0 or y < 0 or None in fields:
        raise CodeSpaceError(f"canteen page counter: ({x}, {y}) cannot be ARM immediates")
    out = bytearray(code)
    (y_site, _), (x_site, _) = SITES
    struct.pack_into("<I", out, y_site - BASE_ADDRESS, MOV_R1 | fields[1])
    struct.pack_into("<I", out, x_site - BASE_ADDRESS, MOV_R0 | fields[0])
    return bytes(out)
