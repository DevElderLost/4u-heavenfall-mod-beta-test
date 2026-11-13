"""The Hunting Horn's songs on the top screen. The executable's side: the code
(horn_songs.c), its data and its state, and its entry in the quest's layouts (interface/quest_layouts/, the hooks it
shares with Damage Numbers); the game files' side is layout.py. The option is the START menu's (Mod Settings >
Interface > Hunting Horn Songs, the page's only, on by default; core/interface/mod_settings), so every mod with that
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
MODE_OPTION = "horn_songs_colour"       # Mod Settings' Highlight: what an effect colours
MODES = ("background", "text")          # its values' settings, in order: horn_songs.c BACKGROUND, TEXT
EFFECT_KINDS = ("normal", "encore")     # horn_songs.c NORMAL, ENCORE (the colours' order)
INDEX = 0x5D1           # the group's slot in the GUI manager (quest_layouts.FREE_INDICES), after Damage Numbers'
STATES = ("idle", "partial", "full")    # horn_songs.c IDLE, PARTIAL, FULL
MESSAGE_FILE = 3        # the common file of the songs' names: Menu (FUN_00277938's)
# The HUD's note pictures (FUN_00b8f58c): a note's cell is 16 texels of qst00 (512 x 512) in the row v = 160; the
# special horn's are 256 texels to the right, in the row v = 202
NORMAL_V, SPECIAL_U, SPECIAL_V = 160 / 512, 256 / 512, 202 / 512
SPECIAL_HORN = 0xA9     # the weapon id (status +0x1C2) whose notes are the special ones

# The songs' effects. A song's effect is the game's table
# (GAME_SYMBOLS horn_song_effects); FUN_00b29140 gives each effect to one or two of the hunter's SLOTS slots (work
# +0x800: a level byte at +0x804 + slot, the time left at +0x824 + 4 x slot, in TICKS_PER_SECOND), at a level: 1 for a
# plain one (2 once extended), 1, 3 or 5 for an effect's weaker, middle or stronger song (FUN_0035716c: 2, 4 or 6 once
# extended), the health it gives for a health boost (FUN_00b40140). EFFECT_NEEDS copies that switch: per effect, its
# (slot, least level) pairs; none for the instant ones (heals 0x0E-0x13, Sonic Waves 0x29). The song is green while
# each of its slots has time left at its level or more.
SLOTS = 29
TICKS_PER_SECOND = 60   # the effects' time falls by the frame's delta (uPlayer +0x14), in 1/60 s (the frame limiter's)
NO_SLOT = 0xFF


def _plain(slot):
    return ((slot, 1),)


def _levels(slot):
    return ((slot, 1),), ((slot, 5),)


EFFECT_NEEDS = (
    _plain(0), *_levels(1), *_levels(2),                        # 0x00-0x04
    ((3, 30),), ((3, 40),), ((3, 50),),                         # 0x05-0x07: the health boosts
    ((4, 1),), ((4, 3),), ((4, 5),),                            # 0x08-0x0A: three levels
    *_levels(5), _plain(6),                                     # 0x0B-0x0D
    (), (), (), (), (), (),                                     # 0x0E-0x13: heals
    *_levels(7), _plain(8), _plain(9), _plain(10), *_levels(11),    # 0x14-0x1A
    _plain(12), _plain(13), _plain(14), _plain(15),             # 0x1B-0x1E
    *_levels(16), *_levels(17), *_levels(18), *_levels(19), *_levels(20),   # 0x1F-0x28
    (), _plain(26), _plain(21),                                 # 0x29 Sonic Waves, 0x2A extends every effect, 0x2B
    ((1, 1), (2, 1)),                                           # 0x2C: effects 0x01 and 0x03 together
    _plain(22), _plain(23), _plain(27), _plain(24), _plain(25),     # 0x2D-0x31
    ((11, 1), (4, 3)),                                          # 0x32: effects 0x19 and 0x09 together
    _plain(28),                                                 # 0x33
)


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
    effect = tuning["effect"]
    data += struct.pack("<5I", *(_rgba(effect[part][kind]) for part in ("bar", "text") for kind in EFFECT_KINDS),
                        OPTION_IDS[MODE_OPTION])
    data += struct.pack("<2f", effect["blink_seconds"] * TICKS_PER_SECOND,
                        2 / (effect["blink_period"] * TICKS_PER_SECOND))
    for pairs in EFFECT_NEEDS:
        data += bytes(x for pair in pairs for x in pair) + bytes((NO_SLOT, 0)) * (2 - len(pairs))
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


__all__ = ["CODE", "DATA", "EFFECT_KINDS", "EFFECT_NEEDS", "INDEX", "MESSAGE_FILE", "MODES", "MODE_OPTION", "NO_SLOT",
           "OPTION", "SLOTS", "STATE", "STATES", "TICKS_PER_SECOND", "data_block", "patch_horn_songs",
           "supports_horn_songs"]
