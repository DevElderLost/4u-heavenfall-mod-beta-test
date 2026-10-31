"""The views a GUI reader reads through (`read_gui(view)`): each has `shift` (canonical -> running address), `u32` (a
canonical .data / .bss word), `word` and `read_raw` (the heap's own addresses), like interface/game_gui/memory.py's
GameMemory.

* `MemoryImage`: the regions of one exact copy (exact.py). A read outside them is `OutsideImage`, never a read of the
  live game: everything a snapshot holds comes from the one copy.
* `TracingView`: reads the live game (or a state) page by page, keeping each page it read once, and lists the pages a
  reader touched as a few large regions (`runs`): how a reader's `regions(memory)` finds what to copy."""

import struct

PAGE = 0x1000


class OutsideImage(LookupError):
    """A read of an address the copy does not hold: the GUI's objects moved since the regions were found."""

    def __init__(self, address: int, size: int):
        super().__init__(f"{address:#x} (+{size:#x}) is outside the copied regions")
        self.address, self.size = address, size


class MemoryImage:
    def __init__(self, regions: dict[int, bytes], shift=None):
        self.regions = sorted(regions.items())
        self._shift = shift

    def shift(self, address: int) -> int:
        return address if self._shift is None else self._shift(address)

    def read_raw(self, address: int, size: int) -> bytes:
        for start, data in self.regions:
            if start <= address and address + size <= start + len(data):
                return data[address - start:address - start + size]
        raise OutsideImage(address, size)

    def word(self, address: int) -> int:
        return struct.unpack("<I", self.read_raw(address, 4))[0]

    def u32(self, address: int) -> int:
        return self.word(self.shift(address))

    def read(self, address: int, size: int) -> bytes:
        return self.read_raw(self.shift(address), size)


def merge_runs(pages, gap: int) -> list[tuple[int, int]]:
    """(address, size) runs covering the page numbers `pages`, joined when less than `gap` bytes lie between them."""
    runs: list[list[int]] = []
    for page in sorted(set(pages)):
        start = page * PAGE
        if runs and start - (runs[-1][0] + runs[-1][1]) < gap:
            runs[-1][1] = start + PAGE - runs[-1][0]
        else:
            runs.append([start, PAGE])
    return [(start, size) for start, size in runs]


class TracingView:
    """`memory` read a page at a time, the pages kept; `touched` holds the running addresses' pages read."""

    def __init__(self, memory):
        self.memory = memory
        self.pages: dict[int, bytes] = {}

    def shift(self, address: int) -> int:
        return self.memory.shift(address)

    def _page(self, number: int) -> bytes:
        if number not in self.pages:
            self.pages[number] = self.memory.read_raw(number * PAGE, PAGE)
        return self.pages[number]

    def read_raw(self, address: int, size: int) -> bytes:
        out = bytearray()
        while size > 0:
            page, at = divmod(address, PAGE)
            part = min(size, PAGE - at)
            out += self._page(page)[at:at + part]
            address, size = address + part, size - part
        return bytes(out)

    def word(self, address: int) -> int:
        return struct.unpack("<I", self.read_raw(address, 4))[0]

    def u32(self, address: int) -> int:
        return self.word(self.shift(address))

    def read(self, address: int, size: int) -> bytes:
        return self.read_raw(self.shift(address), size)

    def runs(self, gap: int) -> list[tuple[int, int]]:
        return merge_runs(self.pages, gap)
