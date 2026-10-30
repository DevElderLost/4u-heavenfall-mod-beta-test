"""Single-screen mode, the Arena's select scene (emulator).

The quest board `ui413`, the Arena's counter `ui495` and its ranking `ui496`, the team and weapon choice `ui497` and
its sign `ui498` are placed by the game GUI engine (their
loader bytes stay the game's). What stays here is a behaviour the engine's places cannot make: the places the select
scene's own code writes.

`patch_arena_choice` gives the scene the places its own code writes into the info panels' groups and the choice's
frame, from rodata tables and literals: `FUN_006526b8` rebuilds the scene for each mode (0 the choice, the pad's only
view; 1-4 by the four big buttons of `ui497`). The choice takes the top screen's left column (the engine's `ui497`
block, its buttons in one row by fixes.json's `nudge`), so the modes that put a panel there get the curated places of
single_screen.json's "arena_choice" (pixels right and down from where the layout file has the panel): the equipment
panel `ui034` of mode 2 (`FUN_00653774`'s table), the skills `ui031_hatudo00` and `ui031_skill_syosai` of mode 3
(`FUN_006526b8`'s table) and the status `ui031_status01` of mode 3 (FUN_00651ff8's two float literals; the antivirus
group ui031_antivirus shares its x). The panels are shared layouts of core_common.arc and only mode 0 of the scene is
recorded, so they stay a table patch. The frame of the mode's button (FUN_006531f4's
table) follows the buttons' nudges, and mode 3 no longer shows the item grid (`ui498_b_waku00`: `FUN_006526b8`'s call
that shows it becomes a nop), whose place the status takes. The pad's cursor over the choice is
exefs/single_screen_arena.py.
"""

import json
import struct
from pathlib import Path

from ..data.paths import CURATED_DIR
from .code_space import BASE_ADDRESS, CodeSpaceError

SETTINGS_FILE = CURATED_DIR / "single_screen.json"

# The arena's select scene. The info panels' places are the negated pixels their groups hold at +0x28 / +0x2C.
# FUN_00653774's table of the equipment panel's places (ui034, its 30 groups): two pairs of shorts (x, y), entry 0 (mode
# 0, the choice) (-200, 0): 200 pixels to the right; entry 1 (mode 2, the equipment) (0, -24): at the left, 24 down.
WEAPON_TABLE = 0xEC7CF0
WEAPON_ORIGINAL = struct.pack("<4h", -200, 0, 0, -24)
# FUN_006526b8's table of the skills' places (ui031_hatudo00, and ui031_skill_syosai in mode 3), indexed by mode != 0:
# entry 0 (-198, -71), 198 right and 71 down; entry 1 (0, 0), the file's own place (the left of the top screen)
SKILLS_TABLE = 0xEC7CE0
SKILLS_ORIGINAL = struct.pack("<4h", -198, -71, 0, 0)
# FUN_00651ff8 (mode 3) loads ui031_status01's place from two float literals (vldr s16 / s0 at 0x652028 / 0x65202C):
# (-196.0, 72.0), 196 right and 72 up; ui031_antivirus takes the same x (s16) and its own y (the literal at 0x6526A4)
STATUS_LITERALS = 0x652404
STATUS_ORIGINAL = struct.pack("<2f", -196.0, 72.0)
# FUN_006531f4's table of the frame `ui497_sel_flame_00` around the button of modes 1-4 (mode - 1): the buttons' own
# places in ui497's file units, (x, y) shorts, written into the frame's null (under the engine's wrapper, which scales
# the code's units with the block)
FRAME_TABLE = 0xEC7DB4
FRAME_ORIGINAL = ((-68, 66), (-130, 66), (-68, 4), (-130, 4))
BUTTONS = ("ui497_button1", "ui497_button2", "ui497_button3", "ui497_button4")
# FUN_006526b8, mode 3: `mov r1, #1; cpy r0, r7; bl FUN_00651d98` shows ui498's group 1, the item grid b_waku00
GRID_SHOW = 0x652878
GRID_SHOW_ORIGINAL = bytes.fromhex("46fdffeb")      # bl 0x00651d98
NOP = bytes.fromhex("00f020e3")                     # nop {0}
ARENA_PLACES = ("weapon_detail", "skills_overview", "status_overview")
ARENA_OTHER = ("up",)                  # the other keys of "arena_choice": single_screen_arena.up_buttons'
SHIFT_LIMIT = 400                      # pixels: the curated shift is within the screen's size
WHOLE = 1e-6                           # a frame's place in file units must be a whole number to this


def arena_places(path: Path = SETTINGS_FILE) -> dict[str, tuple[int, int]]:
    """The curated places of the info panels whose places the select scene's code writes (single_screen.json,
    "arena_choice": each of `ARENA_PLACES` as [dx, dy], whole pixels right and down from where the layout file has the
    panel): `weapon_detail` the equipment panel ui034 in mode 2 (the game's [0, 24]), `skills_overview` the skills and
    the skill's detail in mode 3 (the game's [0, 0]), `status_overview` the status in mode 3 (the game's [196, -72]).
    The record also holds the pad's `up` (exefs/single_screen_arena.py)."""
    where = "single_screen.json, arena_choice"
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("arena_choice")
    if not isinstance(record, dict) or set(record) != {*ARENA_PLACES, *ARENA_OTHER}:
        raise ValueError(f"{where}: must give exactly {', '.join((*ARENA_PLACES, *ARENA_OTHER))}")
    places = {}
    for name in ARENA_PLACES:
        shift = record[name]
        if (not isinstance(shift, list) or len(shift) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) and abs(v) <= SHIFT_LIMIT for v in shift)):
            raise ValueError(f"{where}, {name}: [dx, dy], two whole numbers of pixels, at most {SHIFT_LIMIT} each")
        places[name] = (shift[0], shift[1])
    return places


def button_frames(setting=None) -> tuple[tuple[int, int], ...]:
    """The places, in ui497's file units, of the frame around each of its four buttons (`FRAME_TABLE`'s entries): the
    game's own moved by the button's `nudge` (the game GUI arrangement's fixes.json: the file's units, right and down;
    the file's x grows to the left, its y up), divided by the setting's factor (1 for a fix: the engine's wrapper
    scales the code's units with the block). `setting`: ui497's LayoutSetting (default: its curated fixes). Raises
    ValueError when a nudge is not a whole number of file units at the factor."""
    if setting is None:
        from ..gamegui.fixes import load_fixes
        setting = load_fixes()["ui497"]
    frames = []
    for name, (x, y) in zip(BUTTONS, FRAME_ORIGINAL):
        dx, dy = setting.nudge.get(name, (0.0, 0.0))
        frame_x, frame_y = x - dx / setting.factor, y - dy / setting.factor
        if abs(frame_x - round(frame_x)) > WHOLE or abs(frame_y - round(frame_y)) > WHOLE:
            raise ValueError(f"fixes.json, ui497, nudge, {name}: [{dx}, {dy}] is not a whole number of the "
                             f"file's units at the factor {setting.factor} (the frame's table holds whole numbers)")
        frames.append((round(frame_x), round(frame_y)))
    return tuple(frames)


def _shorts(pairs) -> bytes:
    return struct.pack(f"<{2 * len(pairs)}h", *(v for pair in pairs for v in pair))


# (address, the game's bytes) of every site of the arena's select scene, in `arena_edits`' order
ARENA_SITES = ((WEAPON_TABLE, WEAPON_ORIGINAL), (SKILLS_TABLE, SKILLS_ORIGINAL), (STATUS_LITERALS, STATUS_ORIGINAL),
               (FRAME_TABLE, _shorts(FRAME_ORIGINAL)), (GRID_SHOW, GRID_SHOW_ORIGINAL))


def arena_edits(places: dict[str, tuple[int, int]] | None = None,
                frames: tuple[tuple[int, int], ...] | None = None) -> tuple[tuple[int, bytes, bytes], ...]:
    """(address, the game's bytes, the mod's) of each site of the arena's select scene: the places of mode 2's
    equipment panel and of mode 3's skills and status (`places`, default the curated `arena_places`; the tables' entries
    for mode 0 are kept), the frames of the four buttons (`frames`, default `button_frames`) and the nop in place of
    mode 3's call that shows the item grid."""
    places = arena_places() if places is None else places
    frames = button_frames() if frames is None else frames
    negated = {name: (-dx, -dy) for name, (dx, dy) in places.items()}
    return ((WEAPON_TABLE, WEAPON_ORIGINAL, WEAPON_ORIGINAL[:4] + _shorts([negated["weapon_detail"]])),
            (SKILLS_TABLE, SKILLS_ORIGINAL, SKILLS_ORIGINAL[:4] + _shorts([negated["skills_overview"]])),
            (STATUS_LITERALS, STATUS_ORIGINAL, struct.pack("<2f", *(float(v) for v in negated["status_overview"]))),
            (FRAME_TABLE, _shorts(FRAME_ORIGINAL), _shorts(frames)),
            (GRID_SHOW, GRID_SHOW_ORIGINAL, NOP))


def supports_arena_choice(code: bytes) -> bool:
    """True if every site of the arena's select scene holds the game's own bytes (the canonical executable, not yet
    patched)."""
    return all(code[address - BASE_ADDRESS:address - BASE_ADDRESS + len(old)] == old for address, old in ARENA_SITES)


def patch_arena_choice(code: bytes, places: dict[str, tuple[int, int]] | None = None,
                       frames: tuple[tuple[int, int], ...] | None = None) -> bytes:
    """`code` with the arena's select scene laid out for the top screen's left column (`arena_edits`)."""
    if not supports_arena_choice(code):
        raise CodeSpaceError("arena choice: the select scene's tables are not the update's (another executable, or "
                             "already patched)")
    out = bytearray(code)
    for address, _old, new in arena_edits(places, frames):
        out[address - BASE_ADDRESS:address - BASE_ADDRESS + len(new)] = new
    return bytes(out)
