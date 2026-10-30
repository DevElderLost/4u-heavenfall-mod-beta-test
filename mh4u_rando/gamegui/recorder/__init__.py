"""The recorder: exact snapshots of the game's GUI, read only, from the running
emulator (between the recording probe's frame marks) or from save states. `reader` is the GUI reader in use, on the
GUI's structures (`gamegui/structs.py`)."""

from . import structs_reader as reader

__all__ = ["reader"]
