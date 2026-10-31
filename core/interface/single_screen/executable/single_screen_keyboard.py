"""Single-screen mode, the name keyboard (emulator only).

The game's embedded 3DS software keyboard (the new game's hunter and Felyne names, chat, the guild card) is made for the
touch screen. In this mode:

* it opens on the top screen: `FUN_002b5788` stores, for the keyboard's second layout set (the one that holds the
  keys), the screen of its groups (`swkbd + 0x46C`, `mov r2, #7`, the bottom one; `#0` is the top one: `SCREEN_SITE`)
  and the render slots its units are drawn in (`swkbd + 0x464`, a mask of slots, `mov r2, #0x80` = slot 7, the
  bottom screen; `#1` is slot 0, the top: `SLOT_SITE`). Both must change: a unit is drawn only in the passes of its
  slots, and in a pass only the groups of that slot's screen are drawn (the screen alone left the
  keyboard open and invisible);
* it is driven with the pad: block `single_screen_keyboard` hooks the read of the touch point in the keyboard's input
  manager (`FUN_0066762c`, `INPUT_HOOK`) and puts a virtual finger on a key (D-pad moves it, A types, B deletes, START
  confirms). A real touch passes through. The curated names of the keys B and START touch, the finger's start
  point, the numbers of its moves, the mode tabs' hover colour and the controls it never rests on are in
  single_screen.json ("keyboard").

Applied by `patch_single_screen` (interface/single_screen/executable/single_screen.py) on the canonical executable like
every patcher; the hook's resume address and the game functions the block calls are in
game/executable/blocks.py.
"""

import json
import struct
from dataclasses import dataclass
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, load_layout

SETTINGS_FILE = CURATED_DIR / "single_screen.json"
BLOCK = "single_screen_keyboard"

SCREEN_SITE = 0x2B5888                                    # FUN_002b5788: mov r2, #7 (the layouts' second screen)
SCREEN_ORIGINAL = struct.pack("<I", 0xE3A02007)
SCREEN_TOP = struct.pack("<I", 0xE3A02000)                # mov r2, #0
SLOT_SITE = 0x2B5870                                      # FUN_002b5788: mov r2, #0x80 (the layouts' second slot mask)
SLOT_ORIGINAL = struct.pack("<I", 0xE3A02080)
SLOT_TOP = struct.pack("<I", 0xE3A02001)                  # mov r2, #1 (slot 0, the top screen)
INPUT_HOOK = 0x667668                                     # FUN_0066762c: ldrh r4, [r0, #0xB6] (x of the touch point)
INPUT_ORIGINAL = struct.pack("<I", 0xE1D04BB6)

NAME_SIZE = 16                                            # the game compares 16 bytes of a control's name
SCREEN_WIDTH, SCREEN_HEIGHT = 320, 240                    # the touch screen's raw touch coordinates


SLACK_LIMIT, WEIGHT_LIMIT = 50, 16                        # the curated slack (pixels) and weights, at most
SKIP_LIMIT = 4                                            # the names the block can hold (skip_names)
ALLOWED = {"delete", "ok", "start", "slack", "across_weight", "centre_weight", "tab_hover", "skip",
           "backdrop_width"}                              # backdrop_width: the hud side reads it


@dataclass(frozen=True)
class Keyboard:
    """The curated "keyboard" section: the controls B (`delete`) and START (`ok`) touch, by name, the raw touch point
    (x, y) the finger starts nearest to, and how the D-pad picks the next control: a candidate lies in a direction when
    its extent ends no more than `slack` pixels before the hover's edge; its score is the gap ahead plus
    `across_weight` times the gap across plus `centre_weight` times the distance between the middles across.
    `tab_hover` is the colour (as the game stores it, 0xAABBGGRR; written RRGGBB in the file) the hovered mode tab is
    tinted with, and `skip` the names of controls the finger never rests on."""
    delete: str
    ok: str
    start: tuple[int, int]
    slack: int
    across_weight: int
    centre_weight: int
    tab_hover: int
    skip: tuple[str, ...]


def keyboard_settings(path: Path = SETTINGS_FILE) -> Keyboard:
    """The keyboard section of single_screen.json, validated."""
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("keyboard")
    if not isinstance(record, dict):
        raise ValueError("single_screen.json, keyboard: a record with delete, ok, start, slack, across_weight, "
                         "centre_weight, tab_hover and skip")
    names = []
    for key in ("delete", "ok"):
        name = record.get(key)
        if not isinstance(name, str) or not name.isascii() or not 0 < len(name) < NAME_SIZE:
            raise ValueError(f"single_screen.json, keyboard, {key}: a control name of 1 to {NAME_SIZE - 1} ASCII "
                             "characters")
        names.append(name)
    start = record.get("start")
    if (not isinstance(start, list) or len(start) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) for v in start)
            or not 0 < start[0] < SCREEN_WIDTH or not 0 < start[1] < SCREEN_HEIGHT):
        raise ValueError(f"single_screen.json, keyboard, start: [x, y] of the {SCREEN_WIDTH} x {SCREEN_HEIGHT} touch "
                         "screen")
    numbers = []
    for key, low, high in (("slack", 0, SLACK_LIMIT), ("across_weight", 1, WEIGHT_LIMIT),
                           ("centre_weight", 0, WEIGHT_LIMIT)):
        value = record.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"single_screen.json, keyboard, {key}: a whole number of {low} to {high}")
        numbers.append(value)
    colour = record.get("tab_hover")
    if not isinstance(colour, str) or len(colour) != 6 or any(c not in "0123456789abcdefABCDEF" for c in colour):
        raise ValueError("single_screen.json, keyboard, tab_hover: a colour written RRGGBB (six hex digits)")
    red, green, blue = (int(colour[at:at + 2], 16) for at in (0, 2, 4))
    skip = record.get("skip")
    if (not isinstance(skip, list) or len(skip) > SKIP_LIMIT
            or any(not isinstance(n, str) or not n.isascii() or not 0 < len(n) < NAME_SIZE for n in skip)):
        raise ValueError(f"single_screen.json, keyboard, skip: at most {SKIP_LIMIT} control names of 1 to "
                         f"{NAME_SIZE - 1} ASCII characters")
    unknown = sorted(set(record) - ALLOWED)
    if unknown:
        raise ValueError(f"single_screen.json, keyboard: unknown key {', '.join(unknown)}")
    return Keyboard(names[0], names[1], (start[0], start[1]), *numbers, 0xFF000000 | blue << 16 | green << 8 | red,
                    tuple(skip))


def supports_keyboard(code: bytes) -> bool:
    """True if the three sites are the game's own (the canonical executable, not yet patched)."""
    try:
        return (code[SCREEN_SITE - BASE_ADDRESS:SCREEN_SITE - BASE_ADDRESS + 4] == SCREEN_ORIGINAL
                and code[SLOT_SITE - BASE_ADDRESS:SLOT_SITE - BASE_ADDRESS + 4] == SLOT_ORIGINAL
                and code[INPUT_HOOK - BASE_ADDRESS:INPUT_HOOK - BASE_ADDRESS + 4] == INPUT_ORIGINAL)
    except IndexError:
        return False


def patch_keyboard(code: bytes, keyboard: Keyboard | None = None, layout: Layout | None = None) -> bytes:
    """`code` (extended) with the name keyboard on the top screen and the virtual finger block hooked into its input
    manager, with the curated names and start point."""
    layout = layout or load_layout()
    keyboard = keyboard or keyboard_settings()
    if not supports_keyboard(code):
        raise CodeSpaceError("name keyboard: the bytes at the screen / slot stores or the touch read are not the "
                             "update's (another executable, or already patched)")
    block = layout.block(BLOCK)
    data = bytearray(block.data)
    for label, name in (("name_delete", keyboard.delete), ("name_ok", keyboard.ok)):
        at = layout.symbol(BLOCK, label) - block.address
        data[at:at + NAME_SIZE] = name.encode("ascii").ljust(NAME_SIZE, b"\0")
    at = layout.symbol(BLOCK, "start_x") - block.address
    struct.pack_into("<ii", data, at, *keyboard.start)
    at = layout.symbol(BLOCK, "nav_slack") - block.address     # doubled pixels, as the block counts
    struct.pack_into("<iii", data, at, 2 * keyboard.slack, keyboard.across_weight, keyboard.centre_weight)
    at = layout.symbol(BLOCK, "tab_colour") - block.address
    struct.pack_into("<II", data, at, keyboard.tab_hover, len(keyboard.skip))     # tab_colour, skip_count
    at = layout.symbol(BLOCK, "skip_names") - block.address
    for index, name in enumerate(keyboard.skip):
        data[at + index * NAME_SIZE:at + (index + 1) * NAME_SIZE] = name.encode("ascii").ljust(NAME_SIZE, b"\0")
    out = bytearray(code)
    out[SCREEN_SITE - BASE_ADDRESS:SCREEN_SITE - BASE_ADDRESS + 4] = SCREEN_TOP
    out[SLOT_SITE - BASE_ADDRESS:SLOT_SITE - BASE_ADDRESS + 4] = SLOT_TOP
    layout.place(out, BLOCK, bytes(data))
    layout.hook(out, INPUT_HOOK, layout.symbol(BLOCK, "keyboard_finger_hook"), original=INPUT_ORIGINAL, link=False)
    return bytes(out)
