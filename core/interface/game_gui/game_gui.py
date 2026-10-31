"""The game GUI engine's executable side (interface/game_gui/game_gui_engine.c): the build side and the patch are in
interface/game_gui/engine.py, which imports
nothing of the code space (R2); this module gives it the committed layout and checks that
blocks.py and the engine agree.

Applied on the canonical executable like every patcher: the run carries it to the player's
base game with the layout."""

from core.interface.game_gui import engine
from core.game.executable.blocks import GAME_GUI_TABLE_SIZE
from core.game.executable.code_space import Layout, load_layout


def patch_game_gui(code: bytes, table: bytes, layout: Layout | None = None, pad_hook: int | None = None) -> bytes:
    """`code` with the engine's block, `table` (engine.engine_table) and its two hooks (each checks its instruction);
    with `pad_hook`, the pad update's call the guild card's block holds, the photo mode's entry chained after that
    block (the call is checked to be the card's)."""
    layout = layout or load_layout()
    block = layout.block(engine.TABLE)
    assert block.end - block.address == GAME_GUI_TABLE_SIZE, (
        "game/executable/blocks.py and the layout disagree: rebuild it"
    )
    return engine.patch_engine(code, table, layout, pad_hook)
