"""The World-style sharpness gauge, adapted from Jamo's mod "MH4U MH4G World Style
Sharpness Indicator" v1.1, used with Jamo's permission: in a quest with a blade, the HUD's sharpness bar shrinks with
what is left of its colour, has World's colours, and the gauge's frames are darker. The option is the START menu's
(Mod Settings > Interface > World Sharpness, the page's only, on by default; core/interface/mod_settings), so every mod
with that page carries it and a character's choice acts at once. No game file changes: the code (world_sharpness.c)
writes the game's own panes.

This feature changes no instruction of its own: through the quest's shared frame hook (interface/quest_layouts/, a
frame-only entry), FUN_00af52a0 (sMhMain::frame) runs world_sharpness_frame after every system's move and before the
render. Update's executable only; the version maps carry it to the base games.
"""

import json
import struct
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.executable.blocks import WORLD_SHARPNESS_DATA_SIZE
from core.game.executable.code_space import CodeSpaceError, Layout, load_layout
from core.game.files.gui.lyt import name_hash
from core.interface.quest_layouts.quest_layouts import add_quest_layout, frame_only, supports_quest_layouts

CODE, DATA = "world_sharpness_code", "world_sharpness_data"
FRAME = "world_sharpness_frame"
OPTION = "world_sharpness"
TUNING_FILE = CURATED_DIR / "world_sharpness.json"
# The gauge in ui202 (every language's core_quest.arc): its group, its three frames and its bar
GROUP = "ui202_kireaji"
FRAMES = ("ui202_kire00", "ui202_kire01", "ui202_kire02")
BAR = "ui202_color00"
FRAME_COLOUR = (255, 255, 255, 255)     # the frames' four corners in the layout
LEVELS = 7                              # the sharpness colours, red to purple


class WorldSharpnessError(ValueError):
    pass


def _byte(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255


def _rgb(value) -> bool:
    return isinstance(value, list) and len(value) == 3 and all(_byte(v) for v in value)


def load_tuning(path: Path = TUNING_FILE) -> dict:
    """The curated numbers, checked: seven RGB colours, an alpha byte, an RGB tint and a slide in (0, 1]."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    tuning = {}
    for key in ("colours", "alpha", "frame_tint", "slide"):
        entry = raw.get(key)
        if not isinstance(entry, dict) or "value" not in entry or not isinstance(entry.get("description"), str):
            raise WorldSharpnessError(f"world_sharpness.json: {key} must be {{\"value\": ..., \"description\": ...}}")
        tuning[key] = entry["value"]
    colours = tuning["colours"]
    if not isinstance(colours, list) or len(colours) != LEVELS or not all(_rgb(colour) for colour in colours):
        raise WorldSharpnessError(f"world_sharpness.json: colours must be {LEVELS} RGB colours, red to purple")
    if not _byte(tuning["alpha"]) or not _rgb(tuning["frame_tint"]):
        raise WorldSharpnessError("world_sharpness.json: alpha is a byte and frame_tint an RGB colour")
    slide = tuning["slide"]
    if not isinstance(slide, (int, float)) or isinstance(slide, bool) or not 0 < slide <= 1:
        raise WorldSharpnessError("world_sharpness.json: slide is a number in (0, 1]")
    return tuning


def _rgba(colour) -> int:
    return struct.unpack("<I", bytes(colour))[0]


def data_block(tuning: dict | None = None) -> bytes:
    """The block world_sharpness_data (world_sharpness.c struct world_data)."""
    from core.interface.mod_settings.mod_options import OPTION_IDS
    tuning = tuning or load_tuning()
    data = struct.pack("<2I", OPTION_IDS[OPTION], name_hash(GROUP))
    data += struct.pack(f"<{len(FRAMES)}I", *(name_hash(name) for name in FRAMES)) + struct.pack("<I", name_hash(BAR))
    data += struct.pack(f"<{LEVELS}I", *(_rgba([*colour, tuning["alpha"]]) for colour in tuning["colours"]))
    data += struct.pack("<2If", _rgba([*tuning["frame_tint"], 255]), _rgba(FRAME_COLOUR), float(tuning["slide"]))
    if len(data) != WORLD_SHARPNESS_DATA_SIZE:
        raise WorldSharpnessError(f"world_sharpness_data holds {WORLD_SHARPNESS_DATA_SIZE} bytes, made {len(data)}")
    return data


def supports_world_sharpness(code: bytes) -> bool:
    """`code` (the update's executable, canonical, not patched yet) has the instructions the quest's shared hooks
    replace."""
    return supports_quest_layouts(code)


def patch_world_sharpness(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (the update's executable) with the gauge's code and data and its frame-only entry in the quest's layouts
    (the shared hooks, placed by the first feature). Refuses an executable where a site is not the game's instruction,
    or one patched already."""
    layout = layout or load_layout()
    out = bytearray(code)
    try:
        layout.place(out, CODE)
        layout.place(out, DATA, data_block())
    except CodeSpaceError as error:
        raise CodeSpaceError(f"world sharpness: {error}") from error
    add_quest_layout(out, frame_only(layout.symbol(CODE, FRAME)), layout)
    return bytes(out)


__all__ = ["BAR", "CODE", "DATA", "FRAME", "FRAMES", "FRAME_COLOUR", "GROUP", "LEVELS", "OPTION", "TUNING_FILE",
           "WorldSharpnessError", "data_block", "load_tuning", "patch_world_sharpness", "supports_world_sharpness"]
