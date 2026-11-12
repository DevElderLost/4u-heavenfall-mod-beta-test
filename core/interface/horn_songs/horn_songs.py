"""The Hunting Horn's songs on the top screen. The executable's side: the code
(horn_songs.c), its data and its state, and its entry in the quest's layouts (interface/quest_layouts/, the hooks it
shares with Damage Numbers); the game files' side is layout.py. The option is the START menu's (Mod Settings >
Gameplay > Hunting Horn Songs, the page's only, on by default; core/interface/mod_settings), so every mod with that
page carries it and a character's choice acts at once.

This feature changes no instruction of its own; through the quest's shared hooks (quest_layouts.py), FUN_00af52a0
(sMhMain::frame) runs horn_frame, FUN_00c1017c loads our layout at INDEX and FUN_00c0f110 frees it. Update's executable
only; the version maps carry it to the base games.
"""

import struct

from core.game.executable.blocks import HORN_SONGS_DATA_SIZE
from core.game.executable.code_space import Layout, load_layout
from core.game.files.gui.lyt import name_hash
from core.interface.horn_songs.layout import GROUP, LAYOUT_PATH, NOTE_CELL, HornSongsError, load_tuning
from core.interface.quest_layouts.quest_layouts import QuestLayout, add_quest_layout, supports_quest_layouts

CODE, DATA, STATE = "horn_songs_code", "horn_songs_data", "horn_songs_state"
OPTION = "horn_songs"
INDEX = 0x5D1           # the group's slot in the GUI manager (quest_layouts.FREE_INDICES), after Damage Numbers'
STATES = ("idle", "partial", "full")    # horn_songs.c IDLE, PARTIAL, FULL
MESSAGE_FILE = 3        # the common file of the songs' names: Menu (FUN_00277938's)
# The HUD's note pictures (FUN_00b8f58c): a note's cell is 16 texels of qst00 (512 x 512) in the row v = 160; the
# special horn's are 256 texels to the right, in the row v = 202
NORMAL_V, SPECIAL_U, SPECIAL_V = 160 / 512, 256 / 512, 202 / 512
SPECIAL_HORN = 0xA9     # the weapon id (status +0x1C2) whose notes are the special ones


def _rgba(colour) -> int:
    return struct.unpack("<I", bytes(colour))[0]


def data_block(tuning: dict | None = None) -> bytes:
    """The block horn_songs_data (horn_songs.c struct horn_data)."""
    from core.interface.mod_settings.mod_options import OPTION_IDS
    tuning = tuning or load_tuning()
    colours, group = tuning["colours"], tuning["group"]
    data = struct.pack("<6I", name_hash(GROUP), INDEX, group["layer"], group["priority"], OPTION_IDS[OPTION],
                       MESSAGE_FILE)
    data += struct.pack("<3I", *(_rgba(colours["text"][state]) for state in STATES))
    data += struct.pack("<3I", *(_rgba(colours["bar"][state]) for state in STATES))
    data += struct.pack("<2I", _rgba(colours["notes"]["waiting"]), _rgba(colours["notes"]["lit"]))
    data += struct.pack("<4fI", NOTE_CELL, NORMAL_V, SPECIAL_U, SPECIAL_V, SPECIAL_HORN)
    if len(data) != HORN_SONGS_DATA_SIZE:
        raise HornSongsError(f"horn_songs_data holds {HORN_SONGS_DATA_SIZE} bytes, made {len(data)}")
    return data


def supports_horn_songs(code: bytes) -> bool:
    """`code` (the update's executable, canonical, not patched yet) has the instructions the quest's shared hooks
    replace."""
    return supports_quest_layouts(code)


def patch_horn_songs(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (the update's executable) with the songs' code, data and state and their entry in the quest's layouts
    (the shared hooks, placed by the first feature). Refuses an executable where a site is not the game's instruction,
    or one patched already."""
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, CODE)
    layout.place(out, DATA, data_block())
    layout.reserve(out, STATE)
    add_quest_layout(out, QuestLayout(layout.symbol(CODE, "horn_frame"), INDEX, LAYOUT_PATH), layout)
    return bytes(out)


__all__ = ["CODE", "DATA", "INDEX", "MESSAGE_FILE", "OPTION", "STATE", "STATES", "data_block", "patch_horn_songs",
           "supports_horn_songs"]
