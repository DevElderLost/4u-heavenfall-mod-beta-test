"""Single-screen mode, the World Map (emulator only).

The map (layout ui430, opened by the touch menu's World Map button) is made for the touch screen. In this mode:

* it is loaded on the top screen: its loader byte (the lobby list's index 30) and the kind byte of the 13 entries of its
  binder table, which would put its groups back on the bottom screen at every open (`SCREEN_PATCHES`, merged into
  exefs/single_screen.py's);
* it is opened and driven with the pad: block `single_screen_world_map`, chained into the pad update's call to the
  prompt block (`patch_world_map`), opens it on a fresh press of the curated open button while the hunter walks freely
  in the hub, closes it on the close button (a press of B), opens the Solo / Local Play / Online window on the online
  button and makes the circle pad the D-pad while it is open. The curated buttons: single_screen.json ("world_map");
* its cursor ("you are here" and the place cursor) is moved by the code from a table of offsets in layout units
  (`CURSOR_TABLE`): they are scaled by the layout's curated `factor` (single_screen.json, `layouts.ui430`).

Applied by `patch_single_screen` (exefs/single_screen.py) on the canonical executable like every patcher.
"""

import json
import struct
from dataclasses import dataclass
from pathlib import Path

from ..data.paths import CURATED_DIR
from .code_space import BASE_ADDRESS, CodeSpaceError, Layout, load_layout

SETTINGS_FILE = CURATED_DIR / "single_screen.json"
BLOCK = "single_screen_world_map"
PROMPT_BLOCK, PROMPT_ENTRY = "single_screen_prompt", "prompt_screen"

LOADER_BYTE = 0xEFE01E                 # the lobby list's byte of ui430 (FUN_00c0ff8c, index 30): 1 bottom, 0 top
BINDER_TABLE = 0xE004C8                # FUN_0059e03c's table: 13 entries {name hash, kind and flags, float}, kind at +4
BINDER_GROUPS = 13
CURSOR_TABLE = 0xDF2E44                # 10 float pairs (x, y): the cursor's offset from its resting place, by place
CURSOR_ORIGINAL = ((1.0, -1.0), (-57.0, 15.0), (-56.0, -40.0), (-121.0, 46.0), (-155.0, -31.0), (86.0, -37.0),
                   (-4.0, 48.0), (46.0, 36.0), (-104.0, -8.0), (88.0, 62.0))

SCREEN_PATCHES: dict[str, tuple[tuple[int, bytes, bytes], ...]] = {
    "ui430": ((LOADER_BYTE, b"\x01", b"\x00"),
              *((BINDER_TABLE + 12 * n + 4, b"\x01", b"\x00") for n in range(BINDER_GROUPS))),
}

BUTTONS = {"X": 0x1000, "Y": 0x8000}  # the game's raw button bits (pad + 0x8C) the curated names stand for
BUTTON_B = 0x4000                      # what the close button presses for one frame
MARKS = {"X": 0x2000000, "Y": 0x4000000}   # the unused held-word bits that remember a hidden button (the block's)
ALLOWED = {"open", "close", "online", "circle_pad"}


@dataclass(frozen=True)
class WorldMap:
    """The curated "world_map" section: the button that opens the map while the hunter walks freely (`open`), the one
    that closes it (a press of B, `close`) and the one that opens the Solo / Local Play / Online window from the place
    choice (`online`), each "X" or "Y"; and whether the circle pad also moves the cursor (`circle_pad`)."""
    open: str
    close: str
    online: str
    circle_pad: bool


def world_map_settings(path: Path = SETTINGS_FILE) -> WorldMap:
    """The world_map section of single_screen.json, validated."""
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("world_map")
    where = "single_screen.json, world_map"
    if not isinstance(record, dict) or set(record) != ALLOWED:
        raise ValueError(f"{where}: a record with open, close, online and circle_pad, nothing else")
    for key in ("open", "close", "online"):
        if record[key] not in BUTTONS:
            raise ValueError(f"{where}, {key}: one of {', '.join(BUTTONS)}")
    if record["close"] == record["online"]:
        raise ValueError(f"{where}: close and online are both used while the map is open: two different buttons")
    if not isinstance(record["circle_pad"], bool):
        raise ValueError(f"{where}, circle_pad: true or false")
    return WorldMap(record["open"], record["close"], record["online"], record["circle_pad"])


def cursor_factor(path: Path = SETTINGS_FILE) -> float:
    """The factor the layout side scales ui430 by (`layouts.ui430.factor`, hud/single_screen.py; 1.0 when absent)."""
    from ..hud.single_screen import load_layout_settings
    setting = load_layout_settings(path).get("ui430")
    return 1.0 if setting is None else setting.factor


def cursor_table(factor: float) -> bytes:
    """The cursor table's 80 bytes with every offset times `factor`: the layout is scaled around its origin, and the
    table is the cursor group's offset from the resting place of a layout pane that was scaled with it."""
    return b"".join(struct.pack("<2f", x * factor, y * factor) for x, y in CURSOR_ORIGINAL)


def supports_world_map(code: bytes) -> bool:
    """True if the cursor table is the game's own (the canonical executable, not yet patched). The screen bytes are
    checked with the other layouts' (`SCREEN_PATCHES`)."""
    at = CURSOR_TABLE - BASE_ADDRESS
    return code[at:at + 80] == cursor_table(1.0)


def patch_world_map(code: bytes, hook: int, layout: Layout | None = None, settings: WorldMap | None = None,
                    factor: float | None = None) -> bytes:
    """`code` (extended, the prompt block already hooked at `hook`, the pad update's call) with the world map's block
    placed with the curated buttons and called first by the pad update (it calls the prompt block itself), and the
    cursor table scaled by `factor` (default: the layout's, `cursor_factor`)."""
    layout = layout or load_layout()
    settings = settings or world_map_settings()
    factor = cursor_factor() if factor is None else factor
    if not supports_world_map(code):
        raise CodeSpaceError("world map: the cursor table is not the update's (another executable, or already patched)")
    block = layout.block(BLOCK)
    data = bytearray(block.data)
    for label, value in (("open_mask", BUTTONS[settings.open]), ("close_mask", BUTTONS[settings.close]),
                         ("online_mask", BUTTONS[settings.online]), ("circle_on", int(settings.circle_pad))):
        at = layout.symbol(BLOCK, label) - block.address
        struct.pack_into("<I", data, at, value)
    out = bytearray(code)
    layout.place(out, BLOCK, bytes(data))
    layout.hook(out, hook, layout.symbol(BLOCK, "world_map_pad"), calls=layout.symbol(PROMPT_BLOCK, PROMPT_ENTRY))
    if factor != 1.0:
        at = CURSOR_TABLE - BASE_ADDRESS
        out[at:at + 80] = cursor_table(factor)
    return bytes(out)
