"""The running game's memory, read in the emulator's own process (Windows).
Read only: the process is opened without the right to write, so nothing here can change the game.

Citra and Azahar keep the emulated game's memory in their process and, for the game, a page table
(`Memory::PageTable`, src/core/memory.h: its first member `raw`, one host pointer per 4 KB guest page, 2^20 of them,
null where the game maps nothing), made by `std::make_shared` (src/core/hle/kernel/vm_manager.cpp), so in an allocation
of its own a little after the allocation's start. It is found by its shape: nothing mapped under the code (0x00100000),
the code's first pages one after another (the kernel loads the code segment into one block, process.cpp `LoadModule`).
Several may match (another process's, a chance pattern): the caller keeps the one whose anchor table is a local
executable's (memory.py, `attach`). A guest address is read at `raw[address >> 12] + (address & 0xFFF)`. A new boot
(a restart, or another game) frees the table and the memory: reading through them then fails (LinkError) and the table
is found again.

Taken from the archived live editor, where it was used
on two PCs (Citra nightly 2104), through restarts, loaded states and the tool opened before or after the game; its
writing was removed.
"""

import ctypes
import struct
import sys
from ctypes import wintypes

PAGE = 0x1000
ENTRIES = 1 << 20               # the page table's host pointers (PAGE_TABLE_NUM_ENTRIES)
CODE = 0x00100000               # the game's code starts here; nothing is mapped below
SEARCH = 0x10000                # the table starts in its allocation's first 64 KB (the heap's header, make_shared's)
_LOW = CODE // PAGE             # null entries before the code's

_COMMIT, _PRIVATE, _READ_WRITE = 0x1000, 0x20000, 0x04
RIGHTS = 0x0400 | 0x0010        # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ: never PROCESS_VM_WRITE


class LinkError(RuntimeError):
    """The game's memory cannot be reached: no emulator, no game in it, or the emulator gave it back (a restart)."""


class LinkRefused(LinkError):
    """An address the game does not map (the GUI's lists not made yet at boot): the link itself still serves."""


class LinkDenied(LinkError):
    """Windows does not let this program open the emulator's process (the emulator runs as administrator)."""


class _Region(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD), ("Protect", wintypes.DWORD),
                ("Type", wintypes.DWORD)]


def _kernel32():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_Region), ctypes.c_size_t]
    k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                      ctypes.POINTER(ctypes.c_size_t)]
    return k32


def table_starts(head: bytes) -> list[int]:
    """The offsets in `head` (an allocation's first bytes) where a page table of the game could start: its entries
    for the pages under the code all null, the code's first two consecutive host pages."""
    words = struct.unpack(f"<{len(head) // 8}Q", head[:len(head) // 8 * 8])
    out = []
    for i in range(_LOW, min(len(words) - 1, SEARCH // 8 + _LOW)):
        first = words[i]
        if first and words[i + 1] == first + PAGE and not any(words[i - _LOW:i]):
            out.append(8 * (i - _LOW))
    return out


class ProcessMemory:
    """The game's memory in the emulator process `pid`, through its page table at `table` (`page_tables` lists the
    candidates): `read` and `word` take the game's own addresses."""

    def __init__(self, pid: int, table: int = 0):
        if sys.platform != "win32":
            raise LinkError("the emulator's memory is read on Windows only")
        self.k32 = _kernel32()
        self.pid, self.table = pid, table
        self.scanned = 0                        # allocations the last `page_tables` looked into
        self.handle = self.k32.OpenProcess(RIGHTS, False, pid)
        if not self.handle:
            code = ctypes.get_last_error()
            if code == 5:                       # ERROR_ACCESS_DENIED
                raise LinkDenied(f"the emulator's process {pid} cannot be opened (access denied: is it run as "
                                 "administrator?)")
            raise LinkError(f"the emulator's process {pid} cannot be opened (Windows error {code}: it closed?)")

    @property
    def connected(self) -> bool:
        return bool(self.handle)

    def close(self) -> None:
        if self.handle:
            self.k32.CloseHandle(self.handle)
            self.handle = None

    def _regions(self):
        """(base, size) of every committed private read-write region that could hold a page table. Not only those
        that start an allocation: once (Citra nightly 2104) the table was 0x50 bytes into a
        52 MB region in the middle of its allocation (a heap segment's)."""
        region, address = _Region(), 0
        while self.k32.VirtualQueryEx(self.handle, address, ctypes.byref(region), ctypes.sizeof(region)):
            base, size = region.BaseAddress or 0, region.RegionSize
            if (region.State == _COMMIT and region.Type == _PRIVATE and region.Protect == _READ_WRITE
                    and size >= ENTRIES * 8):
                yield base, size
            address = base + size
            if address >= 1 << 47:
                break

    def page_tables(self) -> list[int]:
        """The addresses where a page table of the game could start, in the emulator's memory."""
        if not self.handle:
            raise LinkError("not connected")
        out, self.scanned = [], 0
        for base, size in self._regions():
            self.scanned += 1
            head = self._host_read(base, min(size, SEARCH + 8 * _LOW + 16), quiet=True)
            if head is not None:
                out += [base + at for at in table_starts(head)]
        return out

    def _host_read(self, host: int, size: int, quiet: bool = False) -> bytes | None:
        buffer, done = ctypes.create_string_buffer(size), ctypes.c_size_t()
        if self.handle and self.k32.ReadProcessMemory(self.handle, host, buffer, size, ctypes.byref(done)) \
                and done.value == size:
            return buffer.raw
        if quiet:
            return None
        raise LinkError(f"the emulator's memory at {host:#x} cannot be read (Windows error {ctypes.get_last_error()}):"
                        " the game stopped or booted again")

    def _pieces(self, address: int, size: int) -> list[tuple[int, int, int]]:
        """(host address, offset in the data, length) of each guest page `address .. address + size` touches."""
        if not self.table:
            raise LinkError("no page table")
        first, last = address // PAGE, (address + size - 1) // PAGE
        if address < 0 or last >= ENTRIES:
            raise LinkRefused(f"{address:#x} is outside the game's address space")
        count = last - first + 1
        entries = struct.unpack(f"<{count}Q", self._host_read(self.table + 8 * first, 8 * count))
        out = []
        for index, host in enumerate(entries):
            page = (first + index) * PAGE
            start, end = max(address, page), min(address + size, page + PAGE)
            if not host:
                if not self._code_mapped():
                    raise LinkError("the page table no longer maps the game: it booted again or a state was loaded")
                raise LinkRefused(f"the game maps nothing at {page:#x}")
            out.append((host + start - page, start - address, end - start))
        return out

    def _code_mapped(self) -> bool:
        """Whether the table still maps the code's first page, as it always does while its game runs. A table the
        emulator let go (a new boot, a loaded state: 577 refreshes kept on one) stays readable but maps
        nothing: the link is lost, not refused, and the next refresh finds the new table."""
        entry = self._host_read(self.table + 8 * _LOW, 8, quiet=True)
        return entry is not None and struct.unpack("<Q", entry)[0] != 0

    def runs(self, address: int, size: int) -> list[tuple[int, int]]:
        """(host address, length) of `address .. address + size` as the fewest reads: guest pages whose host pages
        follow one another are one run, so a large region (a GUI pool) costs a few reads."""
        runs: list[list[int]] = []
        for host, _at, length in self._pieces(address, size):
            if runs and runs[-1][0] + runs[-1][1] == host:
                runs[-1][1] += length
            else:
                runs.append([host, length])
        return [(host, length) for host, length in runs]

    def read(self, address: int, size: int) -> bytes:
        """`size` bytes of the game's memory at `address`, in as few reads as its host pages allow."""
        if size <= 0:
            return b""
        return b"".join(self._host_read(host, length) for host, length in self.runs(address, size))

    def plan(self, regions) -> "ReadPlan":
        """The reads of `regions` ((address, size) of the game's memory) resolved now, to be done later in one go."""
        return ReadPlan(self, regions)

    def word(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]


class ReadPlan:
    """Regions of the game's memory resolved to host runs ahead of time, with their buffers made: `read` then costs
    only the reads (no page-table walk, no allocation), which is what a copy taken inside a frame's short quiet window
    needs. The reads fill the same buffers every time; `result` makes the regions' bytes. `current` says whether the
    page table still gives the same runs (it does not after a new boot or a loaded state), to be asked after a copy
    that must be kept."""

    def __init__(self, client: ProcessMemory, regions):
        self.client = client
        self.regions = [(address, size) for address, size in regions if size > 0]
        self.runs = [client.runs(address, size) for address, size in self.regions]
        self.buffers = [ctypes.create_string_buffer(size) for _, size in self.regions]
        self.done = ctypes.c_size_t()
        # (host, length, buffer address) of every read, in order
        self.steps: list[tuple[int, int, int]] = []
        for runs, buffer in zip(self.runs, self.buffers):
            at = ctypes.addressof(buffer)
            for host, length in runs:
                self.steps.append((host, length, at))
                at += length

    def read(self) -> None:
        """Fill the buffers from the game now. LinkError when a read fails (the game was given back)."""
        handle, read, done = self.client.handle, self.client.k32.ReadProcessMemory, self.done
        if not handle:
            raise LinkError("not connected")
        for host, length, at in self.steps:
            if not read(handle, host, at, length, done) or done.value != length:
                raise LinkError(f"the emulator's memory at {host:#x} cannot be read (Windows error "
                                f"{ctypes.get_last_error()}): the game stopped or booted again")

    def result(self) -> dict[int, bytes]:
        """The bytes of the last `read`, by region address."""
        return {address: buffer.raw for (address, _), buffer in zip(self.regions, self.buffers)}

    def current(self) -> bool:
        """Whether the page table still resolves every region to the runs planned (no remap since)."""
        try:
            return all(self.client.runs(address, size) == runs
                       for (address, size), runs in zip(self.regions, self.runs))
        except LinkError:
            return False
