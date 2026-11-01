"""The recorder: exact snapshots of the game's GUI, read only, from the
running emulator (between the recording probe's frame counters) or from save states. `reader` is the GUI reader in use,
on the GUI's structures (`interface/game_gui/structs.py`)."""

from core.interface.game_gui.recorder import structs_reader as reader

__all__ = ["reader"]
