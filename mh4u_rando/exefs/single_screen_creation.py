"""Single-screen mode, the new game's character creation (emulator
only): the hunter and Felyne menus (`ui800`, `ui415`) on the top screen, at the right, and the 3D model in the strip
left of them.

* Screen: the two layouts' loader bytes and the kind bytes of their binders' tables (`SCREEN_PATCHES`, merged into
  exefs/single_screen.py's; the curated `top_screen` names them).
* Panel size: the code's own group positions (a table of Vec2 written from float literals) scaled by the curated
  factor of `ui415` / `ui800` (`patch_creation_panel`), so a smaller panel keeps its buttons, pager and swatch sign
  together; the cursors the code steps are wrapped by the layout side (hud/single_screen.py, `wrap`).
* Camera: `FUN_00B74748(scene, mode)` sets the scene's goal eye, target and fov for each of the creation's six modes.
  Block `single_screen_creation` hooks its target x load (0xB74850) and, for the modes 0 to 5, stores the eye z and
  the target x of the data block `single_screen_creation_camera` (six {target x, eye z} float pairs) instead. A target
  to the screen's right of the model puts the model on the left; an eye farther back makes it smaller. Python writes
  the table from the curated `creation_camera` (single_screen.json): per mode the pixels the model moves left and the
  factor of its camera distance.

On the canonical executable like every patcher.
"""

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

from ..data.paths import CURATED_DIR
from .blocks import CREATION_CAMERA_SIZE
from .code_space import BASE_ADDRESS, CodeSpaceError, Layout, branch_word, load_layout

SETTINGS_FILE = CURATED_DIR / "single_screen.json"

# The binders' tables (FUN_005A16CC / FUN_005976A8): 12-byte entries {name hash, kind, ...}; kind 1 or 2 is the bottom
# screen, any other the top (FUN_00584c08)
UI800_TABLE = 0xE03D68
UI800_GROUPS = 7
UI415_TABLE = 0xDFF050
UI415_GROUPS = 10
TABLE_ENTRY = 12
KIND_AT = 4
TITLE_BYTES = {"ui800": 0xEFE150, "ui415": 0xEFE159}     # the title list's screen bytes (from 0xEFE150)


def _screen(loader: int, table: int, groups: int) -> tuple[tuple[int, bytes, bytes], ...]:
    return ((loader, b"\x01", b"\x00"),
            *((table + TABLE_ENTRY * n + KIND_AT, b"\x01", b"\x00") for n in range(groups)))


SCREEN_PATCHES: dict[str, tuple[tuple[int, bytes, bytes], ...]] = {
    "ui800": _screen(TITLE_BYTES["ui800"], UI800_TABLE, UI800_GROUPS),
    "ui415": _screen(TITLE_BYTES["ui415"], UI415_TABLE, UI415_GROUPS),
}

MODES = 6                            # FUN_00B74748's modes the creation uses (0 to 5)
CAMERA_HOOK = 0xB74850               # FUN_00B74748: ldr r3, [r2] (the goal target x); the eye was stored just before
CAMERA_HOOK_ORIGINAL = struct.pack("<I", 0xE5923000)
# the goal eye z of each mode (a float literal each; modes 1 and 2 share one) and the fov table (degrees, one per mode)
EYE_Z_LITERALS = (0xB74920, 0xB74928, 0xB74928, 0xB74930, 0xB74938, 0xB74940)
EYE_Z_ORIGINAL = (220.0, 90.0, 90.0, 300.0, 150.0, 305.0)
FOV_TABLE = 0xDEE34C
FOV_ORIGINAL = (50.0, 25.0, 40.0, 25.0, 25.0, 42.0)
HALF_HEIGHT = 120                    # the screen's half height in pixels: the fov is vertical
CAMERA_CHECKS = ((CAMERA_HOOK, CAMERA_HOOK_ORIGINAL),
                 *((address, struct.pack("<f", z)) for address, z in zip(EYE_Z_LITERALS, EYE_Z_ORIGINAL)),
                 (FOV_TABLE, struct.pack(f"<{MODES}f", *FOV_ORIGINAL)))
LEFT_LIMIT = 300                     # pixels, the most the curated file may ask of a mode
DISTANCE_RANGE = (0.5, 4.0)          # the factor of the camera's distance


# The ui415 menu's root groups are placed by the code at a table of 16 Vec2 (0xF266A0, written at start by the
# initializer at 0xD5D8E0 from 18 float literals): the table is the groups' positions in the layout's own units, so a
# layout scaled by a factor needs the literals scaled by it (the layout's wrapped panes and children scale themselves).
PANEL_POOL = 0xD5DAF4                # the first non-zero literal (0xD5DAF0 is 0.0); 18 words follow
PANEL_VALUES = (6.0, -54.0, 28.0, 2.0, -62.0, -100.0, -25.0, 13.0, 122.0, -46.0, 182.0, -23.0, -124.0, -48.0, -72.0,
                62.0, -20.0, -38.0)
# ui800's skin group (FUN_005A2208 case 4) is put at one more Vec2, (-30, 22) at 0xF2BADC, written at start by the
# initializer at 0xD5F254 from the two literals after its code
HADAIRO_POOL = 0xD5F358
HADAIRO_VALUES = (-30.0, 22.0)
PANEL_LITERALS = (tuple((PANEL_POOL + 4 * n, value) for n, value in enumerate(PANEL_VALUES))
                  + tuple((HADAIRO_POOL + 4 * n, value) for n, value in enumerate(HADAIRO_VALUES)))
PANEL_CHECKS = tuple((address, struct.pack("<f", value)) for address, value in PANEL_LITERALS)
PANEL_LAYOUTS = ("ui415", "ui800")   # the layouts that make one panel (curated: one factor)


def panel_factor(path: Path = SETTINGS_FILE) -> float:
    """The factor of the creation's panel: ui415's (single_screen.json, "layouts"); ui800 must have the same."""
    layouts = json.loads(Path(path).read_text(encoding="utf-8"))["layouts"]
    factors = {name: float(layouts.get(name, {}).get("factor", 1.0)) for name in PANEL_LAYOUTS}
    if len(set(factors.values())) != 1:
        raise ValueError(f"single_screen.json: ui415 and ui800 are one panel, they need the same factor ({factors})")
    return factors["ui415"]


MENU_GROUPS = 8                      # the most root groups the curated "creation_prompt" may name
SHIFT_LIMIT = 400                    # pixels, the most the curated file may ask of a ui006 group


@dataclass(frozen=True)
class CreationPrompt:
    """ui006 (the creation's help text and OK / Back buttons) goes up while one of `groups` is shown and none of
    `unless` is (the Palico board's base: the rooms' copy of ui415, the Palico's clothes, shows the creation's groups),
    each of its own groups moved by `shift` (name -> pixels right and down,
    from the layout's own place)."""
    groups: tuple[str, ...] = ()
    shift: tuple[tuple[str, float, float], ...] = ()
    unless: tuple[str, ...] = ()


def creation_prompt(path: Path = SETTINGS_FILE) -> CreationPrompt:
    """The curated `creation_prompt` of single_screen.json (none: ui006 stays down in the creation)."""
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("creation_prompt")
    if record is None:
        return CreationPrompt()
    where = "single_screen.json, creation_prompt"
    if not isinstance(record, dict) or not {"groups", "shift"} <= set(record) <= {"groups", "shift", "unless"}:
        raise ValueError(f"{where}: needs groups and shift (and may have unless), nothing else")
    groups, shift, unless = record["groups"], record["shift"], record.get("unless", [])
    for name, value in (("groups", groups), ("unless", unless)):
        if (not isinstance(value, list) or not (0 if name == "unless" else 1) <= len(value) <= MENU_GROUPS
                or not all(isinstance(g, str) and g for g in value)):
            raise ValueError(f"{where}, {name}: up to {MENU_GROUPS} root group names")
    if not isinstance(shift, dict) or any(
            not isinstance(v, list) or len(v) != 2
            or any(isinstance(n, bool) or not isinstance(n, int | float) or abs(n) > SHIFT_LIMIT for n in v)
            for v in shift.values()):
        raise ValueError(f"{where}, shift: ui006 group name -> [dx, dy] pixels (at most {SHIFT_LIMIT})")
    return CreationPrompt(tuple(groups), tuple((name, float(v[0]), float(v[1])) for name, v in shift.items()),
                          tuple(unless))


# The name boards (ui802_l_player / _otomo): FUN_0022cd40, the menu owner's command queue, changes page with
# `bl FUN_0022cec4(owner, kind)`; the game shows the model's board on every page (FUN_005a27a0) and hides it only when
# the menu closes, so the block `single_screen_board` takes that call and hides the boards on the other pages.
BOARD_HOOK = 0x22CDB4                # the call to FUN_0022cec4
BOARD_CALLEE = 0x22CEC4
BOARD_PAGES = 0x19                   # the kinds (pages) FUN_0022cec4 handles, 0 to 0x18


@dataclass(frozen=True)
class CreationBoards:
    """The pages (kinds, 0 to 0x18: 0 the hunter's main menu, 0xF the Felyne's) on which the name board is shown; the
    game's other pages show none."""
    kinds: tuple[int, ...]


def creation_boards(path: Path = SETTINGS_FILE) -> CreationBoards | None:
    """The curated `creation_boards` of single_screen.json (none: the game shows the board on every page)."""
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("creation_boards")
    if record is None:
        return None
    where = "single_screen.json, creation_boards"
    if not isinstance(record, dict) or set(record) != {"kinds"}:
        raise ValueError(f"{where}: needs kinds, nothing else")
    kinds = record["kinds"]
    if (not isinstance(kinds, list) or len(set(kinds)) != len(kinds)
            or any(isinstance(k, bool) or not isinstance(k, int) or not 0 <= k < BOARD_PAGES for k in kinds)):
        raise ValueError(f"{where}, kinds: a list of different pages, 0 to {BOARD_PAGES - 1}")
    return CreationBoards(tuple(sorted(kinds)))


def supports_creation_boards(code: bytes) -> bool:
    """True if the page change's call is the game's own."""
    try:
        return code[BOARD_HOOK - BASE_ADDRESS:BOARD_HOOK - BASE_ADDRESS + 4] == branch_word(
            BOARD_HOOK, BOARD_CALLEE, link=True)
    except IndexError:
        return False


def patch_creation_boards(code: bytes, boards: CreationBoards | None = None, layout: Layout | None = None) -> bytes:
    """`code` (extended) where the creation menu's page change hides the name boards on every page but those of
    `boards` (the curated ones by default)."""
    layout = layout or load_layout()
    boards = creation_boards() if boards is None else boards
    if boards is None:
        return bytes(code)
    block = layout.block("single_screen_board")
    data = bytearray(block.data)
    struct.pack_into("<I", data, layout.symbol("single_screen_board", "board_kinds") - block.address,
                     sum(1 << kind for kind in boards.kinds))
    out = bytearray(code)
    layout.place(out, "single_screen_board", bytes(data))
    layout.hook(out, BOARD_HOOK, layout.symbol("single_screen_board", "creation_page"), calls=BOARD_CALLEE)
    return bytes(out)


# The Aceptar / Atrás buttons of the main pages (block `single_screen_creation_pad`): the menu owner's pad reader
# FUN_0022a0f4 steps the cursor with
# `bl FUN_0022b96c(owner, mode, pad, cells, columns)`; the two calls of mode 1 (page 0, the hunter's 9 cells; page 0xF,
# the Felyne's 7) take the pad's left and right as down and up while the cursor is on a button.
PAD_HOOKS = (0x22A19C, 0x22A3C0)
PAD_CALLEE = 0x22B96C


def supports_creation_pad(code: bytes) -> bool:
    """True if both calls of the menu cursor on the main pages are the game's own."""
    try:
        return all(code[hook - BASE_ADDRESS:hook - BASE_ADDRESS + 4] == branch_word(hook, PAD_CALLEE, link=True)
                   for hook in PAD_HOOKS)
    except IndexError:
        return False


def patch_creation_pad(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (extended) where the creation menu's cursor on its main pages also steps between Aceptar and Atrás with
    the pad's left and right (and no longer with up and down): the two calls go through the block."""
    layout = layout or load_layout()
    if not supports_creation_pad(code):
        sites = ", ".join(f"{hook:#x}" for hook in PAD_HOOKS)
        raise CodeSpaceError(f"creation menu cursor: a call at {sites} is not the update's (another executable, or "
                             "already patched)")
    out = bytearray(code)
    layout.place(out, "single_screen_creation_pad")
    for hook in PAD_HOOKS:
        layout.hook(out, hook, layout.symbol("single_screen_creation_pad", "creation_pad"), calls=PAD_CALLEE)
    return bytes(out)


def supports_creation_panel(code: bytes) -> bool:
    """True if the 20 literals the panel patch scales are the game's own."""
    try:
        return all(code[a - BASE_ADDRESS:a - BASE_ADDRESS + 4] == old for a, old in PANEL_CHECKS)
    except IndexError:
        return False


def patch_creation_panel(code: bytes, factor: float | None = None) -> bytes:
    """`code` where the menu groups' position literals are scaled by `factor` (the curated panel factor by default)."""
    factor = panel_factor() if factor is None else factor
    if not 0 < factor <= 1:
        raise ValueError(f"the panel factor must be above 0 and at most 1, not {factor}")
    for address, old in PANEL_CHECKS:
        at = address - BASE_ADDRESS
        if code[at:at + 4] != old:
            raise CodeSpaceError(f"character creation panel at {address:#x}: {code[at:at + 4].hex()} is not the "
                                 f"update's {old.hex()} (another executable, or already patched)")
    out = bytearray(code)
    for address, value in PANEL_LITERALS:
        struct.pack_into("<f", out, address - BASE_ADDRESS, value * factor)
    return bytes(out)


@dataclass(frozen=True)
class CreationCamera:
    model_left: tuple[float, ...]    # per mode: pixels the model moves to the left of the screen's centre
    distance: tuple[float, ...]      # per mode: factor of the camera's distance (above 1: the model is smaller)


def _numbers(value: object, where: str, low: float, high: float) -> tuple[float, ...]:
    if (not isinstance(value, list) or len(value) != MODES
            or any(isinstance(v, bool) or not isinstance(v, int | float) or not low <= v <= high for v in value)):
        raise ValueError(f"single_screen.json, creation_camera, {where}: {MODES} numbers (one per camera mode) of "
                         f"{low} to {high}")
    return tuple(float(v) for v in value)


def creation_camera(path: Path = SETTINGS_FILE) -> CreationCamera:
    """The curated camera of the creation (single_screen.json, "creation_camera"); a file without it leaves the game's
    camera as it is."""
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("creation_camera")
    if record is None:
        return CreationCamera((0.0,) * MODES, (1.0,) * MODES)
    if not isinstance(record, dict) or set(record) != {"model_left", "distance"}:
        raise ValueError("single_screen.json, creation_camera: needs model_left and distance, nothing else")
    return CreationCamera(_numbers(record["model_left"], "model_left", 0, LEFT_LIMIT),
                          _numbers(record["distance"], "distance", *DISTANCE_RANGE))


def camera_table(camera: CreationCamera) -> bytes:
    """Block `single_screen_creation_camera`: per mode the goal target x and eye z (floats). The eye z is the game's
    times the mode's distance factor; the target x is `distance * left * tan(fov / 2) / 120`, so the model (at the
    origin, the camera on the z axis) lands `left` pixels left of the screen's centre."""
    out = bytearray()
    for mode in range(MODES):
        eye_z = EYE_Z_ORIGINAL[mode] * camera.distance[mode]
        target_x = eye_z * camera.model_left[mode] * math.tan(math.radians(FOV_ORIGINAL[mode]) / 2) / HALF_HEIGHT
        out += struct.pack("<2f", target_x, eye_z)
    assert len(out) == CREATION_CAMERA_SIZE
    return bytes(out)


def supports_creation_camera(code: bytes) -> bool:
    """True if every byte the camera patch reads or replaces is the game's own."""
    try:
        return all(code[a - BASE_ADDRESS:a - BASE_ADDRESS + len(old)] == old for a, old in CAMERA_CHECKS)
    except IndexError:
        return False


def patch_creation_camera(code: bytes, camera: CreationCamera | None = None, layout: Layout | None = None) -> bytes:
    """`code` (extended) where the creation's camera modes 0 to 5 get the eye z and target x of `camera` (the curated
    one by default)."""
    layout = layout or load_layout()
    camera = camera or creation_camera()
    for address, old in CAMERA_CHECKS:
        at = address - BASE_ADDRESS
        if code[at:at + len(old)] != old:
            raise CodeSpaceError(f"character creation camera at {address:#x}: {code[at:at + len(old)].hex()} is not "
                                 f"the update's {old.hex()} (another executable, or already patched)")
    out = bytearray(code)
    layout.place(out, "single_screen_creation")
    layout.place(out, "single_screen_creation_camera", camera_table(camera))
    layout.hook(out, CAMERA_HOOK, layout.symbol("single_screen_creation", "creation_hook"),
                original=CAMERA_HOOK_ORIGINAL, link=False)
    return bytes(out)
