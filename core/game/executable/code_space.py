"""Free space of the update's executable: where added code, data and variables go.

The executable's segments have fixed sizes, so new code can only go in the free regions listed in
REGIONS. Nothing in the mod's build writes a free-space address by hand: every block and variable is
declared in `blocks.py`, placed by `tools/build/build_code_space.py` (which also links the machine code at
its address) and recorded in `generated/code_space.json`. At run time a patcher asks the `Layout`
for a block's address or bytes, writes it with `Layout.place` and redirects the game to it with
`Layout.hook`; both check the bytes they replace first, so another executable is rejected instead
of being corrupted.
"""

import hashlib
import json
import struct
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from core.game.executable import session
from core.game.executable.blocks import GAME_SYMBOLS

BASE_ADDRESS = 0x100000  # virtual address of code.bin's first byte
LAYOUT_PATH = Path(__file__).with_name("generated") / "code_space.json"
# The update's executable: code.bin's size (up to the page after .data), and where .bss ends.
CLEAN_SIZE = 0xF82000
BSS_END = 0x111D128
# The extension: new pages after the last .bss page. EXT_SIZE is the
# most it may take; a build takes only the pages up to its last block in it (Layout.extend). 284 KB since
# Alatreon (204 KB with his effect player and shell files) joined layered equipment and MHGen's models (80 KB) in
# one layout, 320 KB for his shells' code, 384 KB with Mizutsune's class for his probes, and pages more for the ported
# monsters' items (the item table's copy, 41,300 bytes), hunter gear
# and Felyne gear.
EXT_START = 0x111E000
# 0x84000 + the ported monsters' items, weapons, armor and recipes, Felyne gear, break lists, + Bubbleblight (a page),
# + Glavenus' class and data (41 pages), + single-screen menus (4 pages)
# + the game GUI engine and its table (11 pages)
# + the frames table grown to 16 scenes, 16 sets and 160 names (a page) + the ported monsters' severed tail fall (a
# page: gameplay/tail_fall/tail_fall.py, joined with the game GUI
# engine) + hold A (a page: gameplay/hold_a/hold_a.py)
EXT_SIZE = 0xDC000
EXTENDED_SIZE = EXT_START + EXT_SIZE - BASE_ADDRESS     # the most an extended code.bin takes
PAGE = 0x1000                   # the extension grows by whole pages (the exheader counts .data in pages)
# The executable's entry starts with `bl clear_bss`; the extension's bootstrap takes its place.
ENTRY_HOOK = 0x100000


@dataclass(frozen=True)
class Region:
    """Free space: `kind` "code" is executable and stored in code.bin (zeros in the update's file);
    "bss" is read-write memory the game never uses (zero at start, not in the file): variables only.
    `original_sha256`: a "code" region reclaimed from dead game code holds the game's bytes, not zeros;
    this is their hash, and Layout.place zeroes the region when it still holds exactly them.
    `extension`: the region is not in the update's code.bin; placing a block there grows the executable
    (Layout.extend)."""
    name: str
    start: int
    end: int
    kind: str
    original_sha256: str | None = None
    extension: bool = False

    @property
    def size(self) -> int:
        return self.end - self.start


REGIONS = {region.name: region for region in (
    # Zeros between the end of .text (0xDEC784) and .rodata, which starts at the next page.
    Region("text_tail", 0xDEC784, 0xDED000, "code"),
    # Pages added after .bss, made executable by the bootstrap (blocks.py: ext_bootstrap).
    Region("ext", EXT_START, EXT_START + EXT_SIZE, "code", extension=True),
    # The rest of the last .bss page: bss ends at 0x111D128, the page at 0x111E000.
    Region("bss_tail", BSS_END, EXT_START, "bss"),
)}


class CodeSpaceError(ValueError):
    pass


# The game's own code and data in the update's executable: .text up to text_tail, then .rodata, .data and .bss up to
# BSS_END. Their addresses move in another version; the free regions do not.
GAME_RANGES = ((BASE_ADDRESS, REGIONS["text_tail"].start), (REGIONS["text_tail"].end, BSS_END))


def is_game_address(address: int) -> bool:
    return any(start <= address < end for start, end in GAME_RANGES)


def note_game_pointer(at: int, value: int) -> None:
    """Note in the run's session that the word at `at` holds `value`, if that is an address of the game's code or data
    (a Thumb address keeps its bit 0); our own blocks' and variables' addresses never move and need no note."""
    if is_game_address(value & ~1):
        session.note_pointer(at)


def note_game_pointers(at: int, data: bytes) -> None:
    """`note_game_pointer` for each word of `data` (an array of pointers, written at address `at`, 4-aligned)."""
    for k in range(0, len(data) - 3, 4):
        note_game_pointer(at + k, struct.unpack_from("<I", data, k)[0])


COND_EQ, COND_HI, COND_ALWAYS = 0x0, 0x8, 0xE


def branch_word(at: int, target: int, link: bool = False, cond: int = COND_ALWAYS) -> bytes:
    """The bytes of ARM `b`/`bl` (with a condition) at address `at`, not noted: to compare with what the executable
    holds. A patcher that writes a branch uses `encode_branch`."""
    delta = (target - (at + 8)) >> 2
    if not -(1 << 23) <= delta < (1 << 23):
        raise CodeSpaceError(f"branch from {at:#x} cannot reach {target:#x}")
    return struct.pack("<I", cond << 28 | (0xB if link else 0xA) << 24 | (delta & 0xFFFFFF))


def encode_branch(at: int, target: int, link: bool = False, cond: int = COND_ALWAYS) -> bytes:
    """ARM `b`/`bl` (with a condition) placed at address `at`: the one place Python builds a branch it writes, so it
    is noted in the run's session."""
    word = branch_word(at, target, link, cond)
    session.note_branch(at, target)
    return word


def encode_bl(at: int, target: int) -> bytes:
    """ARM `bl target` placed at address `at`."""
    return encode_branch(at, target, link=True)


def bl_target(code: bytes, at: int) -> int | None:
    """Target of the ARM `bl` (always) at `at`, or None if there is none."""
    word = struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]
    if word >> 24 != 0xEB:
        return None
    delta = word & 0xFFFFFF
    if delta & 0x800000:
        delta -= 1 << 24
    return at + 8 + delta * 4


CALL, ABS32 = "call", "abs32"


@dataclass(frozen=True)
class Reloc:
    """A word of a linked block that holds a position in the game:
    `offset` in the block; `kind` CALL (an ARM or Thumb B/BL/BLX to the game's code) or ABS32 (a word holding a game
    address); `symbol`, the name it was linked against (a GAME_SYMBOLS name, or the linker's for an absolute one)."""
    offset: int
    kind: str
    symbol: str


@dataclass(frozen=True)
class Block:
    """Code or data placed in a "code" region; `symbols` are its labels, as offsets from `address`; `relocs`, the
    words that point into the game (tools/build/build_code_space.py keeps them from the link)."""
    name: str
    region: str
    address: int
    data: bytes
    symbols: dict[str, int]
    relocs: tuple[Reloc, ...] = ()

    @property
    def end(self) -> int:
        return self.address + len(self.data)


@dataclass(frozen=True)
class Variable:
    """Memory in a "bss" region. Debug variables (diagnostic builds only) may share space with each other."""
    name: str
    region: str
    address: int
    size: int
    debug: bool


class Layout:
    """Where every block and variable is (built by tools/build/build_code_space.py)."""

    def __init__(self, blocks: dict[str, Block], variables: dict[str, Variable]):
        self.blocks = blocks
        self.variables = variables

    def block(self, name: str) -> Block:
        if name not in self.blocks:
            raise CodeSpaceError(f"no block {name!r} in the layout (declare it in game/executable/blocks.py and run "
                                 "tools/build/build_code_space.py)")
        return self.blocks[name]

    def address(self, name: str) -> int:
        """Address of a block, or of a variable."""
        if name in self.variables:
            return self.variables[name].address
        return self.block(name).address

    def symbol(self, block: str, symbol: str) -> int:
        """Address of the label `symbol` of `block` (e.g. a constant the patcher fills in)."""
        found = self.block(block)
        if symbol not in found.symbols:
            raise CodeSpaceError(f"block {block!r} has no symbol {symbol!r}")
        return found.address + found.symbols[symbol]

    def symbol_in(self, blocks: tuple[str, ...], symbol: str) -> int:
        """Address of the label `symbol` of the first of `blocks` that has it (code blocks that call each other)."""
        for name in blocks:
            if symbol in self.block(name).symbols:
                return self.symbol(name, symbol)
        raise CodeSpaceError(f"no block of {', '.join(blocks)} has a symbol {symbol!r}")

    def place(self, code: bytearray, name: str, data: bytes | None = None, *, pointers: bool = False) -> None:
        """Write block `name` into `code` (the whole executable), or `data` instead of its bytes (the
        values of a data block, or a variant of the same size). The block's range must still be free.
        A reclaimed region (dead game code) is zeroed first if it still holds the game's bytes.
        `pointers`: `data` is an array of pointers (a vtable, a pointer table copied from the game), and each word
        holding a game address is noted (note_game_pointers)."""
        block = self.block(name)
        data = block.data if data is None else data
        if len(data) != len(block.data):
            raise CodeSpaceError(f"{name}: {len(data)} bytes for a block of {len(block.data)}")
        region = REGIONS[block.region]
        start, end = block.address - BASE_ADDRESS, block.end - BASE_ADDRESS
        if region.extension:
            self.extend(code, block.end)
        if len(code) < (end if region.extension else region.end - BASE_ADDRESS):
            raise CodeSpaceError(f"no free space for {name} at {block.address:#x}: not the update's executable")
        reclaim(code, region)
        if any(code[start:end]):
            raise CodeSpaceError(f"no free space for {name} at {block.address:#x}: already patched, or not "
                                 "the update's executable")
        code[start:end] = data
        session.note_place(name, block.address)
        if pointers:
            note_game_pointers(block.address, data)

    def extend(self, code: bytearray, end: int | None = None) -> None:
        """Grow `code`, the update's executable, so that the extension holds everything up to address `end`
        (default: the end of this layout's last block in the extension), in whole pages and no more: the first
        time, its old .bss becomes zeros in the file and the bootstrap that makes the extension executable is
        installed; each time, the bootstrap's range is set to the pages the file holds. Nothing to do if
        `code` already holds them."""
        if end is None:
            end = max((b.end for b in self.blocks.values() if REGIONS[b.region].extension), default=EXT_START)
        size = -(-max(end, EXT_START) // PAGE) * PAGE - BASE_ADDRESS
        if size > EXTENDED_SIZE:
            raise CodeSpaceError(f"{end:#x} is past the extension's end ({EXT_START + EXT_SIZE:#x})")
        if len(code) == CLEAN_SIZE:
            code.extend(bytes(size - CLEAN_SIZE))
            self.place(code, "ext_bootstrap")
            self.hook(code, ENTRY_HOOK, "ext_bootstrap", calls=GAME_SYMBOLS["clear_bss"])
            self._set_range_end(code, EXT_START + EXT_SIZE)     # as ext_bootstrap.s is linked
            return
        if not (EXT_START - BASE_ADDRESS <= len(code) <= EXTENDED_SIZE and len(code) % PAGE == 0):
            raise CodeSpaceError(f"cannot extend an executable of {len(code):#x} bytes: not the update's executable")
        if len(code) < size:
            old = BASE_ADDRESS + len(code)
            code.extend(bytes(size - len(code)))
            self._set_range_end(code, old)

    def _set_range_end(self, code: bytearray, old: int) -> None:
        """Point the placed bootstrap's range at the extension's pages in `code`; it must still name `old`."""
        at = self.symbol("ext_bootstrap", "range_end") - BASE_ADDRESS
        if struct.unpack_from("<I", code, at)[0] != old:
            raise CodeSpaceError(f"the bootstrap's range does not end at {old:#x}: not an executable this layout "
                                 "extended")
        struct.pack_into("<I", code, at, BASE_ADDRESS + len(code))

    def hook(self, code: bytearray, at: int, target: str | int, *, original: bytes | None = None,
             calls: int | None = None, link: bool = True, cond: int = COND_ALWAYS) -> None:
        """Replace the instruction at `at` with `b`/`bl` to block `target` (or an address). The current
        instruction must be `original`, or a `bl` to `calls`."""
        offset = at - BASE_ADDRESS
        if original is not None and bytes(code[offset:offset + 4]) != original or \
                calls is not None and bl_target(code, at) != calls:
            raise CodeSpaceError(f"unexpected instruction at {at:#x}: already patched, or not the update's "
                                 "executable")
        address = target if isinstance(target, int) else self.address(target)
        code[offset:offset + 4] = encode_branch(at, address, link=link, cond=cond)

    def used(self, region: str) -> int:
        """Bytes of `region` taken by blocks or variables (debug variables included)."""
        ends = [b.end for b in self.blocks.values() if b.region == region] + \
            [v.address + v.size for v in self.variables.values() if v.region == region]
        return max(ends, default=REGIONS[region].start) - REGIONS[region].start

    def to_json(self) -> dict:
        return {
            "note": "Generated by tools/build/build_code_space.py; do not edit.",
            "regions": {r.name: {"start": f"{r.start:#x}", "end": f"{r.end:#x}", "kind": r.kind,
                                 "used": self.used(r.name), "free": r.size - self.used(r.name)}
                        for r in REGIONS.values()},
            "blocks": {b.name: {"region": b.region, "address": f"{b.address:#x}", "size": len(b.data),
                                "code": b.data.hex(), "symbols": b.symbols,
                                "relocs": [[r.offset, r.kind, r.symbol] for r in b.relocs]}
                       for b in sorted(self.blocks.values(), key=lambda b: b.address)},
            "variables": {v.name: {"region": v.region, "address": f"{v.address:#x}", "size": v.size,
                                   "debug": v.debug}
                          for v in sorted(self.variables.values(), key=lambda v: (v.address, v.name))},
        }

    @classmethod
    def from_json(cls, data: dict) -> "Layout":
        blocks = {name: Block(name, b["region"], int(b["address"], 16), bytes.fromhex(b["code"]),
                              dict(b["symbols"]), tuple(Reloc(*r) for r in b.get("relocs", ())))
                  for name, b in data["blocks"].items()}
        variables = {name: Variable(name, v["region"], int(v["address"], 16), v["size"], v["debug"])
                     for name, v in data["variables"].items()}
        return cls(blocks, variables)


def reclaim(code: bytearray, region: Region) -> None:
    """Zero a region of dead game code while it holds exactly the game's bytes (the first block placed
    in it); afterwards, or in another executable, its bytes are left as they are."""
    start, end = region.start - BASE_ADDRESS, region.end - BASE_ADDRESS
    if region.original_sha256 and hashlib.sha256(code[start:end]).hexdigest() == region.original_sha256:
        code[start:end] = bytes(end - start)


@cache
def load_layout(path: Path = LAYOUT_PATH) -> Layout:
    """The layout the mod's build uses (generated/code_space.json)."""
    return Layout.from_json(json.loads(path.read_text(encoding="utf-8")))
