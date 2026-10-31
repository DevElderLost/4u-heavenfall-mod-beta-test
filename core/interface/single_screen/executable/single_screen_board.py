"""Single-screen mode, the Palico board's page counter (emulator only).

The shared page counter `ui036` ("1/5" with its two arrows) is placed by whichever menu shows it: the menu's own code
writes the position of the null `ui036_null00` each time the page changes. The Tablon de camaradas' lists (the Palico
board, the Meownster Hunters' Palico choice and the Casting Machine) do it in FUN_00a206a4, which calls FUN_009f3738
with the literals (-75, 75) (the layout's own null stands at (200, 120): the game moves it 275 left and 45 up) and the
group's hash. The counter then lands at the bottom of the screen, half over the edge of the "Palicoes" panel the mod
puts there.

This patch changes the two literals of that function's pool (the x and the y that FUN_009f3738 reads: `vldr s0` at
0xA20714 and `vldr s1` at 0xA20718) by the curated `board_page.shift` (pixels right and down, `single_screen.json`):
the counter of these lists moves, the other menus' counters (each has its own literals) stay. The words are data in
a literal pool: the version maps carry them unchanged (the update's and both base games' bytes, checked first:
`tests/interface/single_screen/test_single_screen_board.py`).
"""

import json
import struct
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError

SETTINGS_FILE = CURATED_DIR / "single_screen.json"

LOADS = ((0xA20714, 0xED9F0A5D), (0xA20718, 0xEDDF0A5D))   # vldr s0, [pc, #0x174] / vldr s1, [pc, #0x174]
POSITION = 0xA20890                                         # the pool's two floats: x, y of the null
ORIGINAL = (-75.0, 75.0)
SHIFT_LIMIT = 200                                           # pixels, one way or the other


def board_page_shift(path: Path = SETTINGS_FILE) -> tuple[float, float]:
    """How far the counter of the Palico lists moves (single_screen.json, "board_page", "shift": pixels right, down)."""
    where = "single_screen.json, board_page"
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("board_page", {"shift": [0, 0]})
    if not isinstance(record, dict) or set(record) != {"shift"}:
        raise ValueError(f"{where}: an object with \"shift\", nothing else")
    shift = record["shift"]
    if (not isinstance(shift, list) or len(shift) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) <= SHIFT_LIMIT
                       for v in shift)):
        raise ValueError(f"{where}, shift: [right, down], numbers within {SHIFT_LIMIT}")
    return float(shift[0]), float(shift[1])


def supports_board_page(code: bytes) -> bool:
    """True if the function's two loads and two literals are the game's own (the canonical executable, unpatched)."""
    try:
        at = POSITION - BASE_ADDRESS
        return (all(struct.unpack_from("<I", code, a - BASE_ADDRESS)[0] == word for a, word in LOADS)
                and struct.unpack_from("<2f", code, at) == ORIGINAL)
    except (IndexError, struct.error):
        return False


def patch_board_page(code: bytes, shift: tuple[float, float]) -> bytes:
    """`code` where the Palico lists' page counter stands `shift` pixels (right, down) from where the game puts it: the
    layout's units run the other way (a pixel to the right is a smaller x, a pixel down a smaller y)."""
    if not supports_board_page(code):
        raise CodeSpaceError(f"board page counter: the literals at {POSITION:#x} are not the update's (another "
                             "executable, or already patched)")
    out = bytearray(code)
    struct.pack_into("<2f", out, POSITION - BASE_ADDRESS, ORIGINAL[0] - shift[0], ORIGINAL[1] - shift[1])
    return bytes(out)
