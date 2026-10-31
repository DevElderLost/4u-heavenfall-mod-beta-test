"""Single-screen mode, the guild card's groups on the top screen and its hint (emulator only), executable side.

The card is the lobby's ui502 (placed on the top screen by the game GUI engine), with a hint in ui430
(interface/single_screen/layout/single_screen_card.py, curated single_screen.json, "card_info"). Y on the card is the
photo mode's (the game GUI engine: settings.json `photo`, screen 78), not this
block's. Block `single_screen_card_info` is chained in front of the Palico menus' frames block (which runs the
minimap's) in the pad update's call: it runs it, then keeps the card's groups on the top screen and shows its hint while
the card is up alone (where Y is the photo mode's), filling the hint's word with the game's own lobby message
(interface/single_screen/executable/single_screen_card_info.s). It reads no button; the patch touches the pad update's
call only.

Applied by `patch_single_screen` (interface/single_screen/executable/single_screen.py) on the canonical executable like
every patcher: the block's code and variables are placed by the code space.
"""

import struct

from core.game.files.gui.lyt import name_hash
from core.interface.single_screen.layout.single_screen_card import MAX_GROUPS, MAX_UNLESS, CardInfo, card_info_settings
from core.game.executable.code_space import CodeSpaceError, Layout, load_layout

BLOCK = "single_screen_card_info"
ENTRY = "card_info_pad"
FRAMES_BLOCK, FRAMES_ENTRY = "single_screen_frames", "frames_pad"


def patch_card_info(code: bytes, hook: int, layout: Layout | None = None, card: CardInfo | None = None) -> bytes:
    """`code` (extended, the frames' block already hooked at `hook`, the pad update's call) with the card's block
    placed with the hashes of the curated groups' names and the hint's word, called first by the pad update (it calls
    the frames' block itself). The hook checks the call it replaces."""
    layout = layout or load_layout()
    card = card or card_info_settings()
    hashes = [name_hash(card.hint.group), name_hash(card.when)]
    hashes += [name_hash(name) for name in card.unless] + [0] * (MAX_UNLESS - len(card.unless))
    hashes += [name_hash(name) for name in card.groups] + [0] * (MAX_GROUPS - len(card.groups))
    block = layout.block(BLOCK)
    data = bytearray(block.data)
    for symbol, values in (("card_hashes", hashes), ("card_text_hash", [name_hash(card.hint.text_pane)]),
                           ("card_message_file", [card.hint.message_file]),
                           ("card_message_id", [card.hint.message_id])):
        struct.pack_into(f"<{len(values)}I", data, layout.symbol(BLOCK, symbol) - block.address, *values)
    out = bytearray(code)
    try:
        layout.place(out, BLOCK, bytes(data))
        layout.hook(out, hook, layout.symbol(BLOCK, ENTRY), calls=layout.symbol(FRAMES_BLOCK, FRAMES_ENTRY))
    except CodeSpaceError as error:
        raise CodeSpaceError(f"card info: {error}") from None
    return bytes(out)
