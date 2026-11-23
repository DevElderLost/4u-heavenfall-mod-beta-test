"""The item wheel in a quest: hold L, push the C-stick, the item of that direction is used
(blocks `radial_stub`, `radial_wheel`, `radial_data`,
`radial_pad_stub`, and the Radial Menu's screens in Mod Settings, `radial_editor` and `radial_editor_data`).

Two places of the update's executable change. FUN_00b1cdf0, the local hunter's input update, calls FUN_00b3d160 (the
actions of the item mode: with L held, A / Y / X pick or scroll the bar) once per frame; that `bl` (HOOK) goes to the
stub, which calls radial_wheel.c with the hunter and then FUN_00b3d160 with the registers it was entered with. While
the item mode is on (the actions word has bit 0x800) the wheel reads the C-stick from the pad object, keeps the
camera from seeing it, and a direction held in one sector uses that slot's item through the game's own route; with
the weapon drawn the wheel raises the game's sheathe and the item waits until the weapon is away. And FUN_005b8284,
the pad update's read, calls FUN_005b8460 (the raw words) once per frame; that `bl` (PAD_HOOK) goes to the pad's stub,
which makes the call and then lets the wheel take ZR out of the raw words while the trigger ZR claims it (L held).

The choices live in Mod Settings' save zone (curated mod_settings.json `save_zone`, 48 bytes the game does not use):
the wheel's bytes 6-7 and 37-47 (`wheel_zone` for the layout). The numbers (thresholds, dwell, which slot a sector uses,
the default items) are curated and written into the block `radial_data` here (`wheel_data`); the C holds none.
Written for the update's executable (canonical); the hook's call is checked first. The Radial Menu's row of Mod
Settings is `patch_mod_options(..., wheel=True)`'s (interface/mod_settings/mod_options.py).
"""

import json
import struct
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.executable.blocks import RADIAL_DATA_SIZE
from core.game.executable.code_space import Layout, bl_target, load_layout
from core.interface.mod_settings.mod_settings import load_zone, supports_mod_settings
from core.interface.quest_layouts.quest_layouts import QuestLayout, add_quest_layout, supports_quest_layouts
from core.interface.radial_menu.radial_draw import INDEX, LAYOUT_PATH, draw_data, load_draw_settings
from core.interface.radial_menu.radial_editor import editor_data

SETTINGS_FILE = CURATED_DIR / "radial_menu.json"
STUB, WHEEL, DATA, DRAW_DATA = "radial_stub", "radial_wheel", "radial_data", "radial_draw_data"
EDITOR, EDITOR_DATA = "radial_editor", "radial_editor_data"
VARIABLES = ("radial_state", "radial_debug", "radial_draw_state", "radial_menu_state", "radial_editor_state",
             "radial_stick_hold", "radial_zr")
HOOK = 0xB1D0A4                 # FUN_00b1cdf0: bl FUN_00b3d160 (r0 = the hunter)
HOOK_CALLEE = 0xB3D160
PAD_STUB = "radial_pad_stub"
PAD_HOOK = 0x5B8308             # FUN_005b8284: bl FUN_005b8460 (r0 the pad object, r1 pad + 0x2C, r2 the 3DS's status)
PAD_HOOK_CALLEE = 0x5B8460
CALLS = ((HOOK, HOOK_CALLEE), (PAD_HOOK, PAD_HOOK_CALLEE))     # the calls the wheel takes over, and their callees

SLOTS = 8
SECTORS = 8
# The wheel's bytes in Mod Settings' save zone (radial_wheel.c): 0 is no choice yet (the default), else the value + 1
ZONE_SIZE = 48
ZONE_MAGIC, ZONE_VERSION = 0x00, 0x04       # u32, u16: Mod Settings'
# The wheel's bytes are in the zone's header (bytes 6-8, unused by Mod Settings) and after the options' room (half a
# byte each in bytes 10-35, mod_options.option_half), never among the options: bytes 37-47 end with the zone. They
# count only in a zone with the magic and the mod's version (radial_wheel.c zone_has_wheel)
ZONE_POSITION, ZONE_ENABLED = 6, 7          # u8 each: 1 centre, 2 right, 3 bottom left (and the size + 1 in the
                                            # high half); bits 0-1 on (1) / off (2), bits 2-3 Auto-Combine (1 on,
                                            # 2 off), bits 4-6 the trigger + 1 (1 Tilt, 2 Flick, 3 Release, 4 ZR)
ZONE_TEXT = 8                               # the text size + 1 in its low half (its high half unused)
TRIGGERS, POSITIONS = 4, 3                  # how many triggers and positions the Radial Menu screen cycles
ZONE_SLOTS = 37                             # 8 slots of 11 bits, from the low bits up, to the zone's end
SLOT_BITS, SLOT_EMPTY = 11, 0x7FF           # a slot: 0 no choice yet (the default item), emptied, or the item
WHEEL_VERSION = 2                           # the zone's first version with the wheel's bytes (the curated one or later)
# The game's items that are no item: nothing, and the two placeholders the gates refuse
NO_ITEMS = (0, 0x790, 0x791)


class RadialMenuError(ValueError):
    """The curated radial_menu.json is not what the wheel can use."""


def _value(raw: dict, key: str):
    entry = raw.get(key)
    if not isinstance(entry, dict) or "value" not in entry or not isinstance(entry.get("description"), str):
        raise RadialMenuError(f"radial_menu.json: {key} must be {{\"value\": ..., \"description\": ...}}")
    return entry["value"]


def _whole(raw: dict, key: str, low: int, high: int) -> int:
    value = _value(raw, key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RadialMenuError(f"radial_menu.json: {key} must be a whole number from {low} to {high}")
    return value


def load_settings(path: Path = SETTINGS_FILE) -> dict:
    """The curated values, checked: fire / rearm magnitudes (rearm below fire), dwell frames, the sector -> slot
    table (a permutation of 0..7), the 8 default items, the default position, size (an index of the drawing's
    draw_sizes, whose number is `sizes`) and on / off, the default trigger (0 Tilt, 1 Flick, 2 Release, 3 ZR), the
    flick's window and the default Auto-Combine, the magnitude from which ZR uses a slot (the picture's
    draw_mark_magnitude: ZR uses the slot shown in gold), the default text size (an index of draw_text_sizes, whose
    number is `texts`), the magnitude from which a stick points in Edit Slots, Mod Settings' save zone
    (its offset, magic as bytes and version, which must have the wheel's bytes) and the limit of a queued item in the
    game's time (60 per second)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    fire, rearm = _whole(raw, "fire_magnitude", 1, 127), _whole(raw, "rearm_magnitude", 0, 126)
    if rearm >= fire:
        raise RadialMenuError("radial_menu.json: rearm_magnitude must be below fire_magnitude")
    table, items = _value(raw, "sector_to_slot"), _value(raw, "default_items")
    if not isinstance(table, list) or sorted(table) != list(range(SLOTS)) or \
            not all(isinstance(slot, int) and not isinstance(slot, bool) for slot in table):
        raise RadialMenuError(f"radial_menu.json: sector_to_slot must list each slot 0 to {SLOTS - 1} once, one per "
                              f"sector ({SECTORS})")
    if not isinstance(items, list) or len(items) != SLOTS or \
            not all(isinstance(item, int) and not isinstance(item, bool) and 0 < item < SLOT_EMPTY
                    and item not in NO_ITEMS for item in items):
        raise RadialMenuError(f"radial_menu.json: default_items must be {SLOTS} item ids of the game's table")
    draw = load_draw_settings(path)
    sizes, texts = len(draw["sizes"]), len(draw["text_sizes"])
    size = _whole(raw, "default_size", 0, sizes - 1)
    zone = load_zone()
    if not WHEEL_VERSION <= zone["version"] <= 0xFF:
        raise RadialMenuError(f"mod_settings.json: save_zone's version must be {WHEEL_VERSION} or more (the zone with "
                              "the wheel's bytes) and fit a byte")
    return {"fire": fire, "rearm": rearm, "dwell": _whole(raw, "dwell_frames", 1, 255), "sector_to_slot": table,
            "items": items, "position": _whole(raw, "default_position", 0, POSITIONS - 1), "size": size, "sizes": sizes,
            "enabled": _whole(raw, "default_enabled", 0, 1), "offset": zone["offset"],
            "magic": zone["magic"], "version": zone["version"],
            "queue_frames": _whole(raw, "queue_frames", 1, 3600),
            "trigger": _whole(raw, "default_trigger", 0, TRIGGERS - 1),
            "flick_window": _whole(raw, "flick_window", 1, 3600), "autocraft": _whole(raw, "default_autocraft", 0, 1),
            "editor_point": _whole(raw, "editor_point_magnitude", 1, 127),
            "text": _whole(raw, "default_text_size", 0, texts - 1), "texts": texts,
            "zr_magnitude": draw["mark_magnitude"], "zr_reads": _whole(raw, "zr_trigger_reads", 1, 255),
            "release": _whole(raw, "release_frames", 1, 255)}


def wheel_data(settings: dict | None = None) -> bytes:
    """The block `radial_data` (struct radial_data in radial_wheel.c): fire, rearm, dwell, the zone's offset and its
    magic (u32 each), the version, the default position, on / off and size (u8 each), the sector -> slot table (u8 x
    8), the default items (u16 x 8), the queue's limit (a float: FUN_00b0709c counts it down), the number of sizes, the
    default trigger, Auto-Combine and the frames a let-go stick rests before Flick and Release use the item (u8
    each), the flick's window (a float, counted down the
    same way), the default text size, the number of text sizes, the magnitude from which ZR uses a slot and the pad
    updates the trigger ZR's hold with L held lasts (u8 each)."""
    settings = settings or load_settings()
    data = struct.pack("<4I4s4B", settings["fire"], settings["rearm"], settings["dwell"], settings["offset"],
                       settings["magic"], settings["version"], settings["position"], settings["enabled"],
                       settings["size"])
    data += bytes(settings["sector_to_slot"]) + struct.pack(f"<{SLOTS}H", *settings["items"])
    data += struct.pack("<fBBBBfBBBB", settings["queue_frames"], settings["sizes"], settings["trigger"],
                        settings["autocraft"], settings["release"], settings["flick_window"], settings["text"],
                        settings["texts"], settings["zr_magnitude"], settings["zr_reads"])
    if len(data) != RADIAL_DATA_SIZE:
        raise RadialMenuError(f"radial_data holds {RADIAL_DATA_SIZE} bytes, the settings make {len(data)}")
    return data


def wheel_zone(head: bytes = b"", position: int | None = None, enabled: bool | None = None,
               slots: "list[int | None] | None" = None, size: int | None = None, *,
               autocraft: bool | None = None, trigger: int | None = None, text: int | None = None) -> bytes:
    """The zone's 48 bytes as radial_wheel.c writes the wheel's: `head` (the magic, version, ... up to byte 5, zero
    padded) and the wheel's bytes, zeros elsewhere. Byte 6 has `position` 0 centre, 1 right or 2 bottom left in its low
    half and `size` (an index of draw_sizes) in its high half; byte 7 has `enabled` (bits 0-1), `autocraft` (bits 2-3)
    and `trigger` (0 Tilt, 1 Flick, 2 Release, 3 ZR; bits 4-6); byte 8 has `text` (an index of draw_text_sizes) in its
    low half; bytes 37-47 hold each slot's item (0 emptied) in 11 bits, slot
    k at bit 11 k; None is no choice yet."""
    zone = bytearray(head.ljust(ZONE_SIZE, b"\0"))
    codes = [0 if item is None else item or SLOT_EMPTY for item in (slots or [None] * SLOTS)]
    packed = sum(code << (SLOT_BITS * slot) for slot, code in enumerate(codes))
    zone[ZONE_POSITION] = (0 if position is None else position + 1) | (0 if size is None else size + 1) << 4
    zone[ZONE_ENABLED] = ((0 if enabled is None else 2 - bool(enabled)) |
                          (0 if autocraft is None else 2 - bool(autocraft)) << 2 |
                          (0 if trigger is None else trigger + 1) << 4)
    zone[ZONE_TEXT] = 0 if text is None else text + 1
    zone[ZONE_SLOTS:] = packed.to_bytes(ZONE_SIZE - ZONE_SLOTS, "little")
    return bytes(zone)


def supports_radial_wheel(code: bytes) -> bool:
    """`code` has the calls the wheel takes over (the update's executable, canonical)."""
    return all(bl_target(code, site) == callee for site, callee in CALLS)


def patch_radial_wheel(code: bytes, layout: Layout | None = None, settings: dict | None = None) -> bytes:
    """`code` where the hunter's input update calls the wheel before FUN_00b3d160: its `bl` at HOOK goes to the stub
    (block radial_stub), which calls radial_wheel.c and then the game's function; and where the pad update's raw read
    is followed by the wheel's look at ZR: the `bl` at PAD_HOOK goes to the pad's stub (block radial_pad_stub), which
    calls FUN_005b8460 and then radial_wheel.c's radial_pad. The data block gets the curated numbers. Refuses an
    executable that does not call FUN_00b3d160 and FUN_005b8460 there."""
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, STUB)
    layout.place(out, WHEEL)
    layout.place(out, PAD_STUB)
    layout.place(out, DATA, wheel_data(settings))
    layout.place(out, DRAW_DATA, draw_data((settings or load_settings())["sector_to_slot"]))
    layout.hook(out, HOOK, STUB, calls=HOOK_CALLEE)
    layout.hook(out, PAD_HOOK, PAD_STUB, calls=PAD_HOOK_CALLEE)
    layout.reserve(out, *VARIABLES)                     # in the extension's variables
    return bytes(out)


def patch_radial_draw(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` where the quest's shared frame hook draws the wheel (radial_draw.c radial_frame, after every system's
    move) and the quest loads its layout (radial_draw.py LAYOUT_PATH at INDEX): an entry of the quest's layouts
    (interface/quest_layouts/), whose blocks and hooks the first feature to need them places. Refuses an executable
    whose quest sites are neither the game's words nor the hooks, a taken index and a full table."""
    layout = layout or load_layout()
    out = bytearray(code)
    add_quest_layout(out, QuestLayout(layout.symbol(WHEEL, "radial_frame"), INDEX, LAYOUT_PATH), layout)
    return bytes(out)


def supports_radial_menu(code: bytes) -> bool:
    """`code` has what the option `radial_menu` changes: the wheel's call, the quest's sites its picture is drawn from
    and the START menu's sites (its screens are a row of Mod Settings)."""
    return supports_radial_wheel(code) and supports_quest_layouts(code) and supports_mod_settings(code)


def patch_radial_menu(code: bytes, layout: Layout | None = None, settings: dict | None = None) -> bytes:
    """The option `radial_menu`: the wheel (`settings`: radial_menu.json's), its picture's entry in the quest's layouts
    and its screens' blocks, which the Radial Menu row of Mod Settings opens (`patch_mod_options(..., wheel=True)` puts
    the row in the page). The picture's layout file is radial_draw.py wheel_files' (the pipelines add it)."""
    layout = layout or load_layout()
    out = bytearray(patch_radial_draw(patch_radial_wheel(code, layout, settings), layout))
    layout.place(out, EDITOR)
    layout.place(out, EDITOR_DATA, editor_data(settings=settings))
    return bytes(out)
