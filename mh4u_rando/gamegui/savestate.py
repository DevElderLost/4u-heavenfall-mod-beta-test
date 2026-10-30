"""The game's memory in a Citra / Azahar save state (`.cst`), read like the running game's (gamegui/memory.py): `u32` /
`read` take canonical .data / .bss addresses, `word` / `read_raw` the main heap's own. A save state is frozen, so a
copy of it is exact by nature.

How the state is read is tools/citra_state.py's (`DataView`): a 0x100-byte
header and a zstd stream holding the emulated memory; the live .data is found by the anchor table (where the pad's .bss
pointer is set), the main heap (0x08000000) as the block where the .bss pointers to heap objects all reach a vtable,
the linear heap (0x30000000: the GUI's fonts, the layouts' resources) where the GUI's first font starts with
rLayoutFont's vtable and its data with "lfd"."""

import struct
from collections.abc import Iterable
from pathlib import Path

from .memory import ANCHOR, ANCHOR_SIZE, BASE_ADDRESS
from .process import LinkError, LinkRefused

HEADER = 0x100
RODATA, DATA = 0xDED000, 0xEC0000
DATA_SIZE = 0x300000
PAD_POINTER = 0x10572E0
HEAP, HEAP_END = 0x08000000, 0x10000000
HEAP_ANCHORS = (0x1057534, 0x10572E0, 0x108260C, 0xFB6B7C, 0x105729C, 0xFCF7EC)  # GUI, pad, HUD, settings, quest, save
HEAP_MIN_ANCHORS = 3
PAGE = 0x1000
LINEAR, LINEAR_END = 0x30000000, 0x38000000
GUI_POINTER, GUI_FONT, FONT_VTABLE, FONT_DATA, FONT_MAGIC = 0x1057534, 0xDC, 0xE5D100, 0x64, b"lfd\0"


class NotAState(LinkError):
    """A file that is no save state, or a state whose game is none of the executables tried."""


def load_state(path: Path) -> bytes:
    """The emulated memory of the save state `path`, decompressed."""
    import zstandard
    raw = Path(path).read_bytes()
    if raw[:3] != b"CST":
        raise NotAState(f"{path}: not a Citra save state")
    return zstandard.ZstdDecompressor().stream_reader(raw[HEADER:]).read()


class StateMemory:
    def __init__(self, state: bytes, code: bytes, version=None):
        self.state, self.version = state, version
        self.data = self.shift(DATA)
        self.rodata = (self.shift(RODATA), self.data)
        anchor_at = self.shift(ANCHOR)
        anchor = code[anchor_at - BASE_ADDRESS:anchor_at - BASE_ADDRESS + ANCHOR_SIZE]
        if len(anchor) < ANCHOR_SIZE or not any(anchor):
            raise NotAState("the executable has no anchor table where its version map says")
        self.base = None
        at = state.find(anchor)
        while at != -1:
            base = at - (anchor_at - self.data)
            if base >= 0 and self._at(base + self.shift(PAD_POINTER) - self.data):
                self.base = base
                break
            at = state.find(anchor, at + 1)
        if self.base is None:
            raise NotAState("live .data not found: another executable, or the game was not running")
        self.linear = None
        self.heap = self._find_heap()
        self.linear = self._find_linear()

    @classmethod
    def detect(cls, state: bytes, candidates: Iterable[tuple[bytes, object]]) -> "StateMemory":
        """The memory of the first (code.bin, VersionMap or None) whose anchor table is in the state's live .data."""
        for code, version in candidates:
            try:
                return cls(state, code, version)
            except NotAState:
                continue
        raise NotAState("the game in this state is none of the local executables, or it was not running")

    def _at(self, offset: int) -> int:
        if not 0 <= offset <= len(self.state) - 4:
            raise LinkRefused(f"offset {offset:#x} is outside the state")
        return struct.unpack_from("<I", self.state, offset)[0]

    def shift(self, address: int) -> int:
        moved = None if self.version is None else self.version.to_version(address)
        return address if moved is None else moved

    def _offset(self, address: int, size: int) -> int:
        """The state's offset of the running address `address` (the version's .data / .bss, the main heap or the
        linear heap)."""
        if self.data <= address and address + size <= self.data + DATA_SIZE:
            offset = self.base + address - self.data
        elif HEAP <= address and address + size <= HEAP_END:
            offset = self.heap + address - HEAP
        elif LINEAR <= address and address + size <= LINEAR_END and self.linear is not None:
            offset = self.linear + address - LINEAR
        else:
            raise LinkRefused(f"{address:#x} is in neither .data / .bss nor a heap of the state")
        if offset < 0 or offset + size > len(self.state):
            raise LinkRefused(f"{address:#x} is not in the state")
        return offset

    def _find_heap(self) -> int:
        pointers = [p for p in (self._at(self._offset(self.shift(a), 4)) for a in HEAP_ANCHORS) if HEAP <= p < HEAP_END]
        if len(pointers) < HEAP_MIN_ANCHORS:
            raise NotAState("too few heap objects in .bss: the game was not running")
        low, high = self.rodata
        first = self.base % PAGE - ((min(pointers) - HEAP) // PAGE + 1) * PAGE
        for at in range(first, len(self.state), PAGE):
            heads = [at + p - HEAP for p in pointers]
            if all(0 <= h <= len(self.state) - 4 and low <= self._at(h) < high and not self._at(h) % 4
                   for h in heads):
                return at
        raise NotAState("the main heap was not found in this state")

    def _find_linear(self) -> int | None:
        """Where the linear heap starts in the state; None without a GUI font (the game not in its GUI yet)."""
        gui = self._at(self._offset(self.shift(GUI_POINTER), 4))
        if not HEAP <= gui < HEAP_END:
            return None
        font = self._at(self._offset(gui + GUI_FONT, 4))
        if not LINEAR <= font < LINEAR_END:
            return None
        vtable = struct.pack("<I", self.shift(FONT_VTABLE))
        at = self.state.find(vtable)
        while at != -1:         # any byte: the state's memory blocks need not be word-aligned
            start = at - (font - LINEAR)
            data = struct.unpack_from("<I", self.state, at + FONT_DATA)[0] if at + FONT_DATA + 4 <= len(self.state) \
                else 0
            where = start + data - LINEAR
            if LINEAR <= data < LINEAR_END and 0 <= where <= len(self.state) - 4 \
                    and self.state[where:where + 4] == FONT_MAGIC:
                return start
            at = self.state.find(vtable, at + 1)
        return None

    def read_raw(self, address: int, size: int) -> bytes:
        offset = self._offset(address, size)
        return self.state[offset:offset + size]

    def word(self, address: int) -> int:
        return struct.unpack("<I", self.read_raw(address, 4))[0]

    def read(self, address: int, size: int) -> bytes:
        return self.read_raw(self.shift(address), size)

    def u32(self, address: int) -> int:
        return self.word(self.shift(address))

    def close(self) -> None:
        pass
