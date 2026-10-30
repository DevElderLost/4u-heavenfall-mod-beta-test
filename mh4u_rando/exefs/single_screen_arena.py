"""Single-screen mode, the Arena's team and weapon choice on the pad.

The select scene (`ui497`, FUN_00654850) is made for the touch screen: its four big buttons (items, equipment, status,
skill info) open the scene's modes 1-4 by touch, and the pad only steps the weapon set. The block `single_screen_arena`
(exefs/asm/single_screen_arena.c) gives the pad a cursor between the weapon choice and the four buttons: three calls of
the weapon choice (kind 1, phase 1) go through it.

* `TOUCH_HOOK`: `bl FUN_0065178c(scene)`, the touch list's handler; the block runs it and, unless it saw a touch, moves
  the cursor with the D-pad, presses a button with A (the touch's own result) and closes the open mode with B;
* `PAD_HOOK`: `bl FUN_00650c44(scene)`, the pad of the mode shown; the block hides left and right from it while the
  cursor is on a button;
* `FRAME_HOOK`: the `sub r0, r0, #1` of FUN_0065303c (run every frame by FUN_006531f4) that turns the mode into the
  entry of the frame's table (`ui497_sel_flame_00`: single_screen_quests.FRAME_TABLE); in the weapon choice the block
  gives the cursor's button, so the game's own selection frame is the cursor.

The curated "arena_choice" `up` (single_screen.json: five buttons, 1-4, one for each weapon set) is the button the
D-pad's up goes to from each weapon set; it is the 8-byte block `single_screen_arena_up`.
"""

import json
from pathlib import Path

from ..data.paths import CURATED_DIR
from .code_space import BASE_ADDRESS, CodeSpaceError, Layout, branch_word, load_layout

SETTINGS_FILE = CURATED_DIR / "single_screen.json"
BLOCK, TABLE = "single_screen_arena", "single_screen_arena_up"
TOUCH_HOOK = 0x64F8E4                              # bl FUN_0065178c(scene): the touch list's handler
TOUCH_CALLEE = 0x65178C
PAD_HOOK = 0x64FA10                                # bl FUN_00650c44(scene): the pad of the mode shown
PAD_CALLEE = 0x650C44
FRAME_HOOK = 0x653064                              # FUN_0065303c: sub r0, r0, #1 (the mode's index in the frame table)
FRAME_ORIGINAL = bytes.fromhex("010040e2")
SETS, BUTTONS = 5, 4                               # the weapon sets (the touch list's indices 0-4), the mode buttons

# (address, the game's bytes) of every site the block hooks
ARENA_PAD_SITES = ((TOUCH_HOOK, branch_word(TOUCH_HOOK, TOUCH_CALLEE, link=True)),
                   (PAD_HOOK, branch_word(PAD_HOOK, PAD_CALLEE, link=True)),
                   (FRAME_HOOK, FRAME_ORIGINAL))


def up_buttons(path: Path = SETTINGS_FILE) -> tuple[int, ...]:
    """The button (1-4, left to right) D-pad up goes to from each of the five weapon sets (single_screen.json,
    "arena_choice", `up`). Raises ValueError for anything but five whole numbers 1-4."""
    where = "single_screen.json, arena_choice, up"
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("arena_choice")
    up = record.get("up") if isinstance(record, dict) else None
    if (not isinstance(up, list) or len(up) != SETS
            or not all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= BUTTONS for v in up)):
        raise ValueError(f"{where}: must be {SETS} whole numbers from 1 to {BUTTONS}, the button above each weapon set")
    return tuple(up)


def supports_arena_pad(code: bytes) -> bool:
    """True if the three sites of the select scene's weapon choice hold the game's own bytes (the canonical
    executable, not yet patched)."""
    try:
        return all(code[address - BASE_ADDRESS:address - BASE_ADDRESS + len(old)] == old
                   for address, old in ARENA_PAD_SITES)
    except IndexError:
        return False


def patch_arena_pad(code: bytes, layout: Layout | None = None, up: tuple[int, ...] | None = None) -> bytes:
    """`code` (extended) with the Arena's pad: the block placed, its three sites sent to it, and the table of the
    button above each weapon set (`up`, default the curated `up_buttons`) written."""
    layout = layout or load_layout()
    up = up_buttons() if up is None else up
    if not supports_arena_pad(code):
        raise CodeSpaceError("arena pad: the select scene's calls are not the update's (another executable, or "
                             "already patched)")
    out = bytearray(code)
    layout.place(out, BLOCK)
    layout.place(out, TABLE, bytes(up).ljust(len(layout.block(TABLE).data), b"\0"))
    layout.hook(out, TOUCH_HOOK, layout.symbol(BLOCK, "arena_touch"), calls=TOUCH_CALLEE)
    layout.hook(out, PAD_HOOK, layout.symbol(BLOCK, "arena_pad"), calls=PAD_CALLEE)
    layout.hook(out, FRAME_HOOK, layout.symbol(BLOCK, "arena_frame_hook"), original=FRAME_ORIGINAL)
    return bytes(out)
