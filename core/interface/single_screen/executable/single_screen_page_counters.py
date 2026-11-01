"""Single-screen mode, the page counters two menus place in the wrong spot of the top screen
(emulator only).

The shared page counter `ui036` ("1/2" with its two arrows) is placed by whichever menu shows it: the menu calls
FUN_00288fac(x, y, page, pages, ...), which shows the counter and writes (200 - x, 120 - y) into the null
`ui036_null00` (signed integers turned into floats), with x and y loaded by two instructions right before the call, in
the touch screen's pixels from its top-left corner. In single-screen mode the counter is on the top screen, so a menu
whose own panels moved keeps a counter in the touch screen's place:

* `canteen`: the Canteen's ingredient list (its update code at 0x9C5134: FUN_00a71258 fills the list, FUN_00a721c0 its
  cursor), `mov r1, #0x24` (y 36) at 0x9C5188 and `mov r0, #0x114` (x 276) at 0x9C518C: the bottom-left quarter, where
  the description panel stands in the Canteen (help_top's "canteen" place);
* `gallery`: the room's Gallery (FUN_009c6090, the movie list's update), `mov r1, #0xa` (y 10) at 0x9C6C48 and
  `mov r0, #0x100` (x 256) at 0x9C6C4C: under the movie's preview, while the list's ribbon keeps an empty plank where
  the counter goes on the touch screen.

This patch rewrites each menu's two instructions by its curated shift (`single_screen.json`, "page_counters": whole
pixels right and down): that menu's counter moves, the others' (each passes its own place) stay. A place is a `mov`
of an ARM immediate (an 8-bit value turned right by an even count) or, below zero, a `mvn` of one less than its
negation; a place neither can hold is refused. The words are checked first, with the call they feed; the version maps
carry them unchanged (the update's and both base games' bytes:
`tests/interface/single_screen/test_single_screen_page_counters.py`).
"""

import json
from dataclasses import dataclass
from pathlib import Path
import struct

from core.game.data.paths import CURATED_DIR
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, bl_target

SETTINGS_FILE = CURATED_DIR / "single_screen.json"

PAGE_COUNTER = 0x288FAC                 # FUN_00288fac(x, y, page, pages, ...): shows the counter at (x, y)
MOV, MVN = 0xE3A00000, 0xE3E00000       # mov / mvn rd, #imm (rd in bits 12-15, the immediate's field in bits 0-11)
SHIFT_LIMIT = 300                       # pixels, one way or the other


@dataclass(frozen=True)
class Menu:
    """A menu's call of FUN_00288fac: the instruction loading y and the one loading x (address, the update's word) and
    the call they feed."""
    y_site: int
    y_word: int
    x_site: int
    x_word: int
    call: int

    @property
    def place(self) -> tuple[int, int]:
        """The game's (x, y)."""
        return _immediate(self.x_word), _immediate(self.y_word)


def _immediate(word: int) -> int:
    turn, value = (word >> 8 & 0xF) * 2, word & 0xFF
    return (value >> turn | value << (32 - turn)) & 0xFFFFFFFF if turn else value


CANTEEN = Menu(0x9C5188, 0xE3A01024, 0x9C518C, 0xE3A00F45, 0x9C5190)    # mov r1, #0x24 / mov r0, #0x114
GALLERY = Menu(0x9C6C48, 0xE3A0100A, 0x9C6C4C, 0xE3A00C01, 0x9C6C50)    # mov r1, #0xa / mov r0, #0x100
MENUS = {"canteen": CANTEEN, "gallery": GALLERY}


def arm_immediate(value: int) -> int | None:
    """The 12-bit field of an ARM data-processing immediate holding `value` (8 bits turned right by an even count), or
    None when none does."""
    for rotate in range(16):
        turned = ((value << 2 * rotate) | (value >> (32 - 2 * rotate))) & 0xFFFFFFFF if rotate else value
        if turned < 0x100:
            return rotate << 8 | turned
    return None


def encode_place(word: int, value: int) -> int | None:
    """`word` (a `mov rd, #...`) loading `value` instead: a `mov` of it, or below zero a `mvn` of -value - 1; None when
    neither can hold it."""
    field = arm_immediate(value) if value >= 0 else arm_immediate(-value - 1)
    if field is None:
        return None
    return (MOV if value >= 0 else MVN) | (word & 0xF000) | field


def _place(menu: Menu, shift: tuple[float, float]) -> tuple[int, int]:
    x, y = menu.place
    return x + int(shift[0]), y + int(shift[1])


def page_counter_shifts(path: Path = SETTINGS_FILE) -> dict[str, tuple[float, float]]:
    """How far each menu's counter moves (single_screen.json, "page_counters": menu -> [right, down], whole pixels);
    a menu left out stays where the game puts it."""
    where = "single_screen.json, page_counters"
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("page_counters", {})
    if not isinstance(record, dict) or not set(record) <= set(MENUS):
        raise ValueError(f"{where}: an object of menus ({', '.join(MENUS)}) and their shifts")
    shifts = {}
    for name, shift in record.items():
        if (not isinstance(shift, list) or len(shift) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) and abs(v) <= SHIFT_LIMIT for v in shift)):
            raise ValueError(f"{where}, {name}: [right, down], whole numbers within {SHIFT_LIMIT}")
        menu = MENUS[name]
        for value, word, axis in zip(_place(menu, shift), (menu.x_word, menu.y_word), "xy"):
            if encode_place(word, value) is None:
                raise ValueError(f"{where}, {name}: the counter's {axis} {value} is not an ARM immediate (0-255, or "
                                 "such a value turned by an even count, or one less than the negation of one: try a "
                                 "neighbour)")
        shifts[name] = (float(shift[0]), float(shift[1]))
    return shifts


def supports_page_counters(code: bytes) -> bool:
    """True if every menu's two instructions are the game's own and feed its call to FUN_00288fac (the canonical
    executable, unpatched)."""
    try:
        return all(struct.unpack_from("<I", code, menu.y_site - BASE_ADDRESS)[0] == menu.y_word
                   and struct.unpack_from("<I", code, menu.x_site - BASE_ADDRESS)[0] == menu.x_word
                   and bl_target(code, menu.call) == PAGE_COUNTER for menu in MENUS.values())
    except (IndexError, struct.error):
        return False


def patch_page_counters(code: bytes, shifts: dict[str, tuple[float, float]]) -> bytes:
    """`code` where each menu of `shifts` places its page counter that many whole pixels (right, down) from the game's
    place."""
    if not supports_page_counters(code):
        raise CodeSpaceError("page counters: the words at the menus' calls of FUN_00288fac are not the update's "
                             "(another executable, or already patched)")
    out = bytearray(code)
    for name, shift in shifts.items():
        menu = MENUS[name]
        x, y = _place(menu, shift)
        words = encode_place(menu.x_word, x), encode_place(menu.y_word, y)
        if None in words:
            raise CodeSpaceError(f"page counters, {name}: ({x}, {y}) cannot be ARM immediates")
        struct.pack_into("<I", out, menu.x_site - BASE_ADDRESS, words[0])
        struct.pack_into("<I", out, menu.y_site - BASE_ADDRESS, words[1])
    return bytes(out)
