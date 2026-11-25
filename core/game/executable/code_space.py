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
from core.game.executable.blocks import GAME_SYMBOLS, PACK_SLOTS

BASE_ADDRESS = 0x100000  # virtual address of code.bin's first byte
LAYOUT_PATH = Path(__file__).with_name("generated") / "code_space.json"
# The update's executable: code.bin's size (up to the page after .data), and where .bss ends.
CLEAN_SIZE = 0xF82000
BSS_END = 0x111D128
# The extension: new pages after the last .bss page. EXT_SIZE is the
# most it may take; a build takes only the pages up to its last block in it (Layout.extend), but one that uses the
# extension's variables (ext_vars, right after EXT_SIZE) takes every page before them, so each page of EXT_SIZE costs
# the Old 3DS heaps a page.
EXT_START = 0x111E000
# The pages the layout's blocks take (the resident ones, a probe's diagnostics packed last; the ported monsters', the
# port machinery's, the town's and the screens' blocks are in packs) and tuning.json memory.ext_margin_pages for new
# code. When the blocks outgrow it,
# tools/build/build_code_space.py names the size to write and what to rebuild (the version maps' identity runs end
# at the extension's variables' end). Its history:
EXT_SIZE = 0x86000
PAGE = 0x1000                   # the extension grows by whole pages (the exheader counts .data in pages)
# The extension's variables: pages after the extension, in
# the file as zeros (zero at boot) and left read-write, since the bootstrap's range stops before them. A build that
# uses one takes the whole extension before it (zeros where it has no block). Two pages: the new monster ids' kill
# records, em data slots and save records; a third for Damage Numbers'
# state. 26 more for the diagnostics ring (105 KB, only a diagnostics
# file reaches it: the product's variables are packed first and the file ends at the last page a build uses). One more
# for the jukebox's saved block, its engine and its menu. 162 more for the online
# sync log's ring (640 KB; a diagnostics file's only). 32 more for the rocket's
# sound latch (132 KB; a diagnostics file's only).
# 64 more for the RAM manager's probe log (256 KB; a diagnostics run's
# only).
# Eleven more for Heavenfall Beta's sidecars, their state and two card images, in the tail stage before the
# diagnostics.
EXT_VARS_SIZE = 299 * PAGE
EXTENDED_SIZE = EXT_START + EXT_SIZE + EXT_VARS_SIZE - BASE_ADDRESS     # the most an extended code.bin takes
# The executable's entry starts with `bl clear_bss`; the extension's bootstrap takes its place.
ENTRY_HOOK = 0x100000
# The packs: blocks kept out of the executable, each pack a file
# the loader reads at a quest load into its own fixed range of the heap region, above the root heap and below the
# main thread's stack ("P2 study (S2)", 1). A pack's range is its slot's (blocks.PACK_SLOTS): PACK_ROOM bytes from
# PACKS_START + slot * PACK_ROOM, so no pack moves when another one changes, and a pack may grow to PACK_ROOM.
PACKS_START, PACKS_END = 0x0C000000, 0x0E000000
PACK_ROOM = 0x80000
PACK_SLOT_COUNT = (PACKS_END - PACKS_START) // PACK_ROOM     # 64


@dataclass(frozen=True)
class Region:
    """Free space: `kind` "code" is executable and stored in code.bin (zeros in the update's file);
    "bss" is read-write memory the game never uses (zero at start, not in the file): variables only;
    "pack" is one pack's range (`pack` its name): code and data kept out of the executable, in the run's pack image
    (Layout.place, session.Session.packs) and loaded at run time.
    `original_sha256`: a "code" region reclaimed from dead game code holds the game's bytes, not zeros;
    this is their hash, and Layout.place zeroes the region when it still holds exactly them.
    `extension`: the region is not in the update's code.bin; placing a block there, or reserving a variable there,
    grows the executable (Layout.extend, Layout.reserve)."""
    name: str
    start: int
    end: int
    kind: str
    original_sha256: str | None = None
    extension: bool = False
    pack: str | None = None

    @property
    def size(self) -> int:
        return self.end - self.start


def pack_region_name(pack: str) -> str:
    """The region of pack `pack` (a name of blocks.PACK_SLOTS; a screen's "screen:<name>" gives pack_screen_<name>)."""
    return f"pack_{pack.replace(':', '_')}"


def _pack_regions() -> tuple[Region, ...]:
    slots = sorted(PACK_SLOTS.items(), key=lambda item: item[1])
    if len({slot for _, slot in slots}) != len(slots) or any(not 0 <= slot < PACK_SLOT_COUNT for _, slot in slots):
        raise ValueError(f"blocks.PACK_SLOTS: each pack needs a slot of its own, 0 to {PACK_SLOT_COUNT - 1}")
    return tuple(Region(pack_region_name(name), PACKS_START + slot * PACK_ROOM, PACKS_START + (slot + 1) * PACK_ROOM,
                        "pack", pack=name) for name, slot in slots)


REGIONS = {region.name: region for region in (
    # Zeros between the end of .text (0xDEC784) and .rodata, which starts at the next page.
    Region("text_tail", 0xDEC784, 0xDED000, "code"),
    # Pages added after .bss, made executable by the bootstrap (blocks.py: ext_bootstrap).
    Region("ext", EXT_START, EXT_START + EXT_SIZE, "code", extension=True),
    # The rest of the last .bss page: bss ends at 0x111D128, the page at 0x111E000.
    Region("bss_tail", BSS_END, EXT_START, "bss"),
    # Pages after the extension, read-write: variables only (a patcher that uses one calls Layout.reserve).
    Region("ext_vars", EXT_START + EXT_SIZE, EXT_START + EXT_SIZE + EXT_VARS_SIZE, "bss", extension=True),
    # One range per pack, in the heap region, never in the executable's file.
    *_pack_regions(),
)}
EXT_VARS_START = REGIONS["ext_vars"].start
PACK_REGIONS = {region.pack: region for region in REGIONS.values() if region.kind == "pack"}


def pack_of(address: int) -> str | None:
    """The pack whose range holds `address`, or None."""
    if not PACKS_START <= address < PACKS_END:
        return None
    region = next((r for r in PACK_REGIONS.values() if r.start <= address < r.end), None)
    return region.pack if region else None


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


COND_EQ, COND_NE, COND_HI, COND_ALWAYS = 0x0, 0x1, 0x8, 0xE


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
        if region.kind == "pack":
            self._place_in_pack(region, block, data, pointers)
            return
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

    def _place_in_pack(self, region: Region, block: Block, data: bytes, pointers: bool) -> None:
        """A block of a pack into the run's image of that pack (`session.Session.packs`): the pack is no part of the
        executable, so outside a recording it has nowhere to go."""
        notes = session.current()
        if notes is None:
            raise CodeSpaceError(f"{block.name} is in pack {region.pack}: place it inside session.recording(), which "
                                 "holds the run's pack images")
        image = notes.packs.setdefault(region.pack, bytearray(self.pack_size(region.pack)))
        start, end = block.address - region.start, block.end - region.start
        if end > len(image):
            raise CodeSpaceError(f"{block.name} ends past pack {region.pack}'s image: not this layout's pack")
        if any(image[start:end]):
            raise CodeSpaceError(f"no free space for {block.name} at {block.address:#x}: already placed")
        image[start:end] = data
        session.note_place(block.name, block.address)
        if pointers:
            note_game_pointers(block.address, data)

    def pack_blocks(self, pack: str) -> list[Block]:
        """The blocks of pack `pack`, by address."""
        region = pack_region_name(pack)
        return sorted((b for b in self.blocks.values() if b.region == region), key=lambda b: b.address)

    def pack_size(self, pack: str) -> int:
        """Bytes of pack `pack`'s image (and file): its range up to its last block, in whole pages; 0 for a pack with
        no block in this layout."""
        return -(-self.used(pack_region_name(pack)) // PAGE) * PAGE

    def packs(self) -> list[str]:
        """The packs with blocks in this layout, by slot."""
        return [pack for pack in PACK_REGIONS if self.used(pack_region_name(pack))]

    def reserve(self, code: bytearray, *names: str) -> None:
        """The variables `names` are used: grow `code` so that the file holds those in the extension's variables
        (ext_vars; a variable of the game's .bss needs nothing)."""
        ends = [self.variables[n].address + self.variables[n].size for n in names
                if REGIONS[self.variables[n].region].extension]
        if ends:
            self.extend(code, max(ends))

    def extend(self, code: bytearray, end: int | None = None) -> None:
        """Grow `code`, the update's executable, so that the extension holds everything up to address `end`
        (default: the end of this layout's last block or variable in the extension), in whole pages and no more:
        the first time, its old .bss becomes zeros in the file and the bootstrap that makes the extension executable
        is installed; each time, the bootstrap's range is set to the pages the file holds, up to the extension's
        variables at most. Nothing to do if `code` already holds them."""
        if end is None:
            end = max([b.end for b in self.blocks.values() if REGIONS[b.region].extension] +
                      [v.address + v.size for v in self.variables.values() if REGIONS[v.region].extension],
                      default=EXT_START)
        size = -(-max(end, EXT_START) // PAGE) * PAGE - BASE_ADDRESS
        if size > EXTENDED_SIZE:
            raise CodeSpaceError(f"{end:#x} is past the extension's end ({BASE_ADDRESS + EXTENDED_SIZE:#x})")
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
        """Point the placed bootstrap's range at the extension's pages in `code`, never into its variables (they stay
        read-write); it must still name `old` (a file end, cut the same way)."""
        at = self.symbol("ext_bootstrap", "range_end") - BASE_ADDRESS
        if struct.unpack_from("<I", code, at)[0] != min(old, EXT_VARS_START):
            raise CodeSpaceError(f"the bootstrap's range does not end at {old:#x}: not an executable this layout "
                                 "extended")
        struct.pack_into("<I", code, at, min(BASE_ADDRESS + len(code), EXT_VARS_START))

    def hook(self, code: bytearray, at: int, target: str | int, *, original: bytes | None = None,
             calls: int | None = None, link: bool = True, cond: int = COND_ALWAYS, guard: bool = False,
             opens: bool = False) -> None:
        """Replace the instruction at `at` with `b`/`bl` to block `target` (or an address). The current
        instruction must be `original`, or a `bl` to `calls`. A target in a pack goes through a resident entry stub
        (hook_stub): the hook branches there, and the stub into the pack while it is in, else to what the game did.
        `guard`: the site is one the network callback can reach, maybe off the main thread (docs/develop/
        memory_manager.md, "As built: code manager step 2", risk 3): its stub counts the call (packs.guarded_stub).
        `opens`: the hook opens a screen whose pack it enters (blocks.SCREEN): its stub loads the pack first when it is
        out (packs.opening_stub; "As built: code manager step 3")."""
        offset = at - BASE_ADDRESS
        if original is not None and bytes(code[offset:offset + 4]) != original or \
                calls is not None and bl_target(code, at) != calls:
            raise CodeSpaceError(f"unexpected instruction at {at:#x}: already patched, or not the update's "
                                 "executable")
        address = target if isinstance(target, int) else self.address(target)
        if pack_of(address & ~1) is not None:
            address = self.hook_stub(code, at, address, original=original, calls=calls, guard=guard, link=link,
                                     opens=opens)
        elif opens:
            raise CodeSpaceError(f"the hook at {at:#x} opens a screen, and its target {address:#x} is in no pack")
        code[offset:offset + 4] = encode_branch(at, address, link=link, cond=cond)

    def hook_stub(self, code: bytearray, at: int, target: int, *, original: bytes | None = None,
                  calls: int | None = None, guard: bool = False, link: bool = True, opens: bool = False) -> int:
        """The resident stub of a hook at `at` into a pack's `target`, written in the first free slot of the pack's
        stubs' block (blocks.HOOK_STUBS; two slots for an opening stub, `opens`): its fallback is the call's old target
        (`calls`, or the `bl` the site holds) or the replaced instruction (`original`, or the one the site holds) and a
        branch back. A call the hook turns into a branch (`calls` with `link` False: the target returns past the site
        itself) falls back to the call moved into the stub and a branch back (B139). Refused for a pack without a
        stubs' block, for a site in the save's functions (blocks.SAVE_FUNCTIONS), for a guarded site that is no call
        and for an opening stub outside a screen's pack. Returns the stub's address."""
        from core.game.executable import packs      # (it imports this module)
        from core.game.executable.blocks import (
            HOOK_STUBS, PACK_BUSY, PACK_SLOTS, PACK_STUB_SIZE, SAVE_FUNCTIONS, SCREEN,
        )
        pack = pack_of(target & ~1)
        if any(start <= at < start + size for start, size in SAVE_FUNCTIONS):
            raise CodeSpaceError(f"a hook at {at:#x} into pack {pack}: the site is in the save's functions "
                                 "(blocks.SAVE_FUNCTIONS), which run in the title, the town and a quest while the pack "
                                 "may be out. Hook a resident block there instead (scene=RESIDENT)")
        if pack not in HOOK_STUBS:
            raise CodeSpaceError(f"a hook at {at:#x} into pack {pack}, which has no stubs' block: declare one in "
                                 "game/executable/blocks.py HOOK_STUBS")
        if opens and (guard or not pack.startswith(SCREEN)):
            raise CodeSpaceError(f"the hook at {at:#x} opens pack {pack}: only a screen's pack opens with its screen "
                                 "(blocks.SCREEN), on the main thread (no guard)")
        name, room = HOOK_STUBS[pack]
        block = self.block(name)
        if REGIONS[block.region].extension:
            self.extend(code, block.end)
        start = block.address - BASE_ADDRESS
        need = packs.OPEN_SLOTS if opens else 1
        slot = next((k for k in range(room - need + 1) if not any(code[start + k * PACK_STUB_SIZE:
                                                                       start + (k + need) * PACK_STUB_SIZE])), None)
        if slot is None:
            raise CodeSpaceError(f"{name}: no free stub for the hook at {at:#x} (raise its room in blocks.HOOK_STUBS)")
        stub = block.address + slot * PACK_STUB_SIZE
        state = self.address(packs.STATE) + PACK_SLOTS[pack]
        offset = at - BASE_ADDRESS
        old_call = calls if calls is not None else (bl_target(code, at) if original is None else None)
        if old_call is not None and not link and not guard:     # B139: the call moves into the stub's trampoline
            original, old_call = bytes(code[offset:offset + 4]), None
        if guard:
            if old_call is None:
                raise CodeSpaceError(f"the guarded hook at {at:#x} is no call: only a call's stub counts its calls")
            data = packs.guarded_stub(stub, self.symbol("pack_loader", "pack_guarded"), state,
                                      self.address(PACK_BUSY) + 4 * PACK_SLOTS[pack], target, old_call)
        else:
            if old_call is not None:
                kind = {"fallback": old_call}
            else:
                word = original if original is not None else bytes(code[offset:offset + 4])
                kind = {"site": at, "original": struct.unpack("<I", word)[0]}
            if opens:
                data = packs.opening_stub(stub, self.symbol("pack_loader", "pack_opening"), PACK_SLOTS[pack], state,
                                          target, **kind)
            else:
                data = packs.entry_stub(stub, state, target, **kind)
        code[start + slot * PACK_STUB_SIZE:start + slot * PACK_STUB_SIZE + len(data)] = data
        return stub

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
