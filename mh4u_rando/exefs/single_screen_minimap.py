"""Single-screen mode, the town minimap on the top screen (emulator only),
executable side.

The map is the lobby's ui422 (placed for the top screen by the layout side, with a state group and, in ui430, a hint:
hud/single_screen_minimap.py, curated single_screen.json, "minimap"). Block `single_screen_minimap` is chained in front
of the "[X] Map" hint's block in the pad update's call: it runs it, then turns the minimap on or off at a fresh press of
the curated button while the hunter walks freely and the game shows the map, or in a Gathering Hall's hub states
where the game hides it (the state is the state group's shown bit), keeps the map's groups on the top screen while it
is on and on the touch screen while it is off, and shows its hint while the button can act, filling the hint's word
with the game's own lobby message (exefs/asm/single_screen_minimap.s). In those hall states block
`single_screen_minimap_hall` shows and hides the map with the game's own functions (exefs/asm/
single_screen_minimap_hall.c). The button is L, which the raw pad read FUN_005b8460 gives as raw 0x100 (SELECT opened
the pause menu like START in game, so the mod no longer reads it); the patch touches the pad update's call only.

Applied by `patch_single_screen` (exefs/single_screen.py) on the canonical executable like every patcher: the block's
code and variables are placed by the code space.
"""

import struct

from ..hud.lyt import name_hash
from ..hud.single_screen_minimap import MAX_GROUPS, Minimap, minimap_settings
from .code_space import CodeSpaceError, Layout, load_layout

BLOCK = "single_screen_minimap"
ENTRY = "minimap_pad"
# Its unit for a Gathering Hall, where the game hides the map (exefs/asm/single_screen_minimap_hall.c): called by it
HALL_BLOCK = "single_screen_minimap_hall"
MAP_HINT_BLOCK, MAP_HINT_ENTRY = "single_screen_map_hint", "map_hint_pad"
# The raw bits (pad + 0x8C) of the buttons the block can read: the game's own (FUN_005b8460 turns the 3DS's L, HID
# 0x200, into raw 0x100, as X, HID 0x400, into the world map's 0x1000)
BUTTONS = {"L": 0x100}


def patch_minimap(code: bytes, hook: int, layout: Layout | None = None, minimap: Minimap | None = None) -> bytes:
    """`code` (extended, the "[X] Map" hint's block already hooked at `hook`, the pad update's call) with the minimap's
    block placed with the hashes of the curated groups' names (the map's, then the place name's: `Minimap.follow`), the
    button's raw bit and the hint's word, called first by the pad update (it calls the hint's block itself). The hook
    checks the call it replaces."""
    layout = layout or load_layout()
    minimap = minimap or minimap_settings()
    hashes = [name_hash(minimap.state_group), name_hash(minimap.hint.group), *map(name_hash, minimap.follow)]
    hashes += [0] * (2 + MAX_GROUPS - len(hashes))
    block = layout.block(BLOCK)
    data = bytearray(block.data)
    for symbol, values in (("minimap_hashes", hashes), ("minimap_button", [BUTTONS[minimap.button]]),
                           ("minimap_text_hash", [name_hash(minimap.hint.text_pane)]),
                           ("minimap_message_file", [minimap.hint.message_file]),
                           ("minimap_message_id", [minimap.hint.message_id])):
        struct.pack_into(f"<{len(values)}I", data, layout.symbol(BLOCK, symbol) - block.address, *values)
    out = bytearray(code)
    try:
        layout.place(out, BLOCK, bytes(data))
        layout.place(out, HALL_BLOCK)
        layout.hook(out, hook, layout.symbol(BLOCK, ENTRY), calls=layout.symbol(MAP_HINT_BLOCK, MAP_HINT_ENTRY))
    except CodeSpaceError as error:
        raise CodeSpaceError(f"minimap: {error}") from None
    return bytes(out)
