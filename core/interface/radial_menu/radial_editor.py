"""The data of the Radial Menu's screen, its menu level and Edit Slots (radial_editor.c): the block
`radial_editor_data`, each text as its message index in the menu's file (Mod Settings'
texts, interface/mod_settings/mod_texts.py), then the Size row's texts, how many sizes there are, the magnitude from
which a stick points at a slot and the sector table of the wheel's use (curated radial_menu.json), then the Text Size
row's description and texts and how many text sizes there are."""

import struct
from collections.abc import Mapping, Sequence

from core.game.executable.blocks import RADIAL_EDITOR_DATA_SIZE
from core.interface.mod_settings.mod_texts import message_index
from core.interface.radial_menu.radial_draw import MAX_SIZES, MAX_TEXTS, load_draw_settings

# The wheel's slots by the place each has on it: slot 0 is at the top, then clockwise
DIRECTIONS = ("up", "up_right", "right", "down_right", "down", "down_left", "left", "up_left")
TEXTS = (
    *(f"direction_{direction}" for direction in DIRECTIONS),
    "slot_help", "position_help", "wheel_help", "pouch_help",
    "position_center", "position_right", "position_bottom_left",
    "wheel_off", "wheel_on",
    "size_help",
    "autocraft_help", "trigger_help",
    "autocraft_off", "autocraft_on",
    "trigger_tilt", "trigger_flick", "trigger_release",
    "edit_slots", "edit_slots_help",
)


def size_key(size: float) -> str:
    """The menu text of the Radial Menu's Size row at `size` (a curated draw_sizes value): wheel_size_<percent>."""
    return f"wheel_size_{round(size * 100)}"


def text_key(size: float) -> str:
    """The menu text of the Radial Menu's Text Size row at `size` (a curated draw_text_sizes value):
    text_size_<percent>."""
    return f"text_size_{round(size * 100)}"


def editor_data(sizes: Sequence[float] | None = None, settings: Mapping | None = None,
                texts: Sequence[float] | None = None) -> bytes:
    """The block: struct radial_editor_data in radial_editor.c, the texts of TEXTS in its order, the Size row's text
    of each curated size (draw_sizes, the rest 0 to MAX_SIZES; u16 each), the number of sizes (u8), the magnitude from
    which a stick points at a slot (`settings` is radial_menu.load_settings') and the sector table (u8 x 8), then the
    Text Size row's description and its text at each text size (draw_text_sizes, the rest 0 to MAX_TEXTS; u16 each)
    and the number of text sizes (u8)."""
    from core.interface.radial_menu.radial_menu import load_settings    # radial_menu.py imports this module
    draw = load_draw_settings() if sizes is None or texts is None else None
    sizes = draw["sizes"] if sizes is None else sizes
    texts = draw["text_sizes"] if texts is None else texts
    settings = load_settings() if settings is None else settings
    if not 1 <= len(sizes) <= MAX_SIZES:
        raise ValueError(f"the Size row takes 1 to {MAX_SIZES} sizes")
    if not 1 <= len(texts) <= MAX_TEXTS:
        raise ValueError(f"the Text Size row takes 1 to {MAX_TEXTS} sizes")
    values = [message_index(size_key(size)) for size in sizes]
    text_values = [message_index(text_key(text)) for text in texts]
    data = struct.pack(f"<{len(TEXTS)}H{MAX_SIZES}HBB8BH{MAX_TEXTS}HB", *(message_index(key) for key in TEXTS),
                       *values, *[0] * (MAX_SIZES - len(values)), len(values), settings["editor_point"],
                       *settings["sector_to_slot"], message_index("text_size_help"),
                       *text_values, *[0] * (MAX_TEXTS - len(text_values)), len(text_values))
    if len(data) > RADIAL_EDITOR_DATA_SIZE:
        raise ValueError(f"radial_editor_data holds {RADIAL_EDITOR_DATA_SIZE} bytes, the texts make {len(data)}")
    return data.ljust(RADIAL_EDITOR_DATA_SIZE, b"\0")
