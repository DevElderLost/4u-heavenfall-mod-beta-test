"""Single-screen mode, the "[X] World Map" hint (emulator
only), executable side.

The hint is a group of the lobby's ui430 layout (interface/single_screen/layout/single_screen_hint.py, curated
single_screen.json, "world_map_hint").
Block `single_screen_map_hint` is chained in front of the world map block in the pad update's call: it runs it, then
shows the group when X would open the map and hides it in every other case, finding the group by the hash of its
curated name in the GUI manager's list every frame, and fills its text pane with the game's own name of the World Map
(a lobby message, curated) each time it is shown (interface/single_screen/executable/single_screen_map_hint.s).

Applied by `patch_single_screen` (interface/single_screen/executable/single_screen.py) on the canonical executable like
every patcher: the block's code and variables are placed by the code space.
"""

import struct

from core.game.files.gui.lyt import name_hash
from core.interface.single_screen.layout.single_screen_hint import MapHint, map_hint_settings
from core.game.executable.code_space import CodeSpaceError, Layout, load_layout

BLOCK = "single_screen_map_hint"
ENTRY = "map_hint_pad"
WORLD_MAP_BLOCK, WORLD_MAP_ENTRY = "single_screen_world_map", "world_map_pad"


def patch_map_hint(code: bytes, hook: int, layout: Layout | None = None, hint: MapHint | None = None) -> bytes:
    """`code` (extended, the world map block already hooked at `hook`, the pad update's call) with the hint's block
    placed with the hashes of the curated group's and text pane's names and the curated lobby message of the word,
    and called first by the pad update (it calls the world map block itself)."""
    layout = layout or load_layout()
    hint = hint or map_hint_settings()
    block = layout.block(BLOCK)
    data = bytearray(block.data)
    for symbol, value in (("hint_hash", name_hash(hint.group)), ("hint_text_hash", name_hash(hint.text_pane)),
                          ("hint_message_file", hint.message_file), ("hint_message_id", hint.message_id)):
        struct.pack_into("<I", data, layout.symbol(BLOCK, symbol) - block.address, value)
    out = bytearray(code)
    try:
        layout.place(out, BLOCK, bytes(data))
        layout.hook(out, hook, layout.symbol(BLOCK, ENTRY), calls=layout.symbol(WORLD_MAP_BLOCK, WORLD_MAP_ENTRY))
    except CodeSpaceError as error:
        raise CodeSpaceError(f"map hint: {error}") from None
    return bytes(out)
