"""Packs: code and data kept out of the executable and loaded only for the scene that needs them.

A pack is a set of blocks (blocks.BlockSpec.pack) with a fixed range of its own in the heap region
(code_space.PACK_REGIONS: blocks.PACK_SLOTS gives the slot, code_space.PACK_ROOM bytes a slot). A run builds each
pack's image as it builds the executable: `Layout.place` of a pack's block writes into the run's
`session.Session.packs`, and the rebase carries the images to the player's game version as it carries the executable
(`rebase.rebase`, `Rebased.packs`).

The game and the resident blocks reach a pack only through declared entries:

* an entry stub (`entry_stub`) per call or branch the game makes into a pack: it reads the pack's state byte (the
  variable STATE, a byte a slot, 1 once the loader has the pack in) and goes on into the pack, or does what the game
  did there (the call's old target, or the replaced instruction and a branch back);
* resident words whose value is a fixed address in a pack and which only code of a scene with that pack loaded reads
  (the port records, the new ids' tables): the caller names them (`EntryWords`);
* the loader's table (TABLE, `pack_table`, laid out as pack_table.h): each pack's range, file size, the pack it needs,
  the pack loaded with it, its file, and the pack each new monster id needs.

`check` is the build's check of that rule (a resident word into a pack outside the entries, a pack into another it
does not declare); `memory` gives a run's memory as the game has it with chosen packs loaded, for the tests' emulation.
"""

from __future__ import annotations

import bisect
import struct
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from core.game.executable.blocks import (
    PACK_ENTRY_SIZE, PACK_FILE_SIZE, PACK_SLOTS, PACK_STATE_BYTES, PACK_STUB_SIZE, PACK_TABLE_COUNT, PACK_VARS_SIZE,
    RESIDENT, VARIABLES, pack_covers, pack_side, pack_table_size,
)
from core.game.executable.canonical import arm_branch_target
from core.game.executable.rebase import changed_words
from core.game.executable.code_space import (
    BASE_ADDRESS, PACK_REGIONS, CodeSpaceError, Layout, encode_branch, is_game_address, load_layout,
    note_game_pointer, pack_of,
)

STATE = "pack_state"        # the variable of the state bytes: a byte a slot, 1 while its pack is loaded (pack_table.h)
TABLE = "pack_table"        # the loader's table (pack_table.h)
SIDES = {"quest": 0, "town": 1, "screen": 2}    # pack_table.h PACK_SIDE_QUEST, PACK_SIDE_TOWN, PACK_SIDE_SCREEN


def table_side(pack: str) -> int:
    """The side the table gives pack `pack` (pack_table.h PACK_SIDE_*): a quest's (blocks.pack_side "quest"), the
    town's, or a screen's (the town's side too, loaded as its screen opens: blocks.SCREEN)."""
    from core.game.executable.blocks import SCREEN
    return SIDES["screen"] if pack.startswith(SCREEN) else SIDES[pack_side(pack)]

# ---- the entry stub ----
# Reached by the game's `bl` (a call: the fallback is the call's old target) or `b` (a branch: the fallback is the
# replaced instruction, then a branch back after it). It changes no register and no flag: the state byte (0 or 1) picks
# one of two words, which `ldr pc, [sp], #4` jumps to; the stack below sp holds the scratch.
_STUB_CODE = (
    0xE24DD004,     # sub sp, sp, #4            room for the target
    0xE92D0003,     # push {r0, r1}
    0xE59F0018,     # ldr r0, [pc, #0x18]       the state byte's address (+0x28)
    0xE5D00000,     # ldrb r0, [r0]
    0xE2000001,     # and r0, r0, #1
    0xE28F1010,     # add r1, pc, #0x10         the two targets (+0x2C)
    0xE7910100,     # ldr r0, [r1, r0, lsl #2]
    0xE58D0008,     # str r0, [sp, #8]
    0xE8BD0003,     # pop {r0, r1}
    0xE49DF004,     # ldr pc, [sp], #4          (pop {pc})
)
STUB_STATE, STUB_FALLBACK, STUB_TARGET = 0x28, 0x2C, 0x30
STUB_TRAMPOLINE = 0x34      # a branch's entry: the replaced instruction, then `b` back after the site
STUB_SIZE = STUB_TRAMPOLINE + 8     # every entry takes the same room, a call's leaving its trampoline zero
if STUB_SIZE != PACK_STUB_SIZE:
    raise ImportError(f"blocks.PACK_STUB_SIZE is {PACK_STUB_SIZE:#x}, the entry stub {STUB_SIZE:#x}")


def _uses_pc(word: int) -> bool:
    """`word`, an ARM instruction that is no branch, reads or writes the pc (run elsewhere it would mean something
    else) or is of a kind this check does not know (refused too)."""
    kind = word >> 25 & 7
    if kind in (0b000, 0b001, 0b010, 0b011):        # data processing, loads and stores
        registers = [word >> 16 & 0xF, word >> 12 & 0xF] + ([word & 0xF] if kind in (0b000, 0b011) else [])
        return 15 in registers
    if kind == 0b100:                                # block transfer: by the pc, or loading it (a return)
        return word >> 16 & 0xF == 15 or bool(word & 0x8000 and word >> 20 & 1)
    return kind not in (0b110, 0b111)               # coprocessor transfers and svc are fine


_RETURN_ZERO = struct.pack("<2I", 0xE3A00000, 0xE12FFF1E)     # mov r0, #0; bx lr


def entry_stub(at: int, state: int, target: int, fallback: int | None = None, *, site: int | None = None,
               original: int | None = None, returns_zero: bool = False) -> bytes:
    """The entry stub placed at `at` (STUB_SIZE bytes): with the byte at `state` set it goes to `target` (in a pack),
    else to `fallback` (a call's old target: a game function, or another resident entry), or, for a branch that
    replaced the instruction `original` at `site`, runs that instruction and branches back to `site + 4`, or, with
    `returns_zero` (a declared entry of a pack's that the game never called: BlockSpec.entries' "label"), returns 0.
    A game address it holds and every branch it builds are noted in the run's session (the rebase moves them)."""
    if returns_zero:
        if fallback is not None or original is not None:
            raise CodeSpaceError(f"entry stub at {at:#x}: a stub that returns 0 has no other fallback")
        return struct.pack(f"<{len(_STUB_CODE)}I3I", *_STUB_CODE, state, at + STUB_TRAMPOLINE, target) + _RETURN_ZERO
    if (fallback is None) == (original is None):
        raise CodeSpaceError(f"entry stub at {at:#x}: give the call's old target or the replaced instruction")
    if original is not None:
        if site is None:
            raise CodeSpaceError(f"entry stub at {at:#x}: a replaced instruction needs its site")
        fallback = at + STUB_TRAMPOLINE
        branch = arm_branch_target(original, site)
        if branch is not None:          # a branch moved into the trampoline keeps its target, condition and link
            if original >> 28 == 0xF:
                raise CodeSpaceError(f"entry stub at {at:#x}: the blx at {site:#x} cannot move")
            first = encode_branch(at + STUB_TRAMPOLINE, branch, link=bool(original >> 24 & 1), cond=original >> 28)
        elif _uses_pc(original):
            raise CodeSpaceError(f"entry stub at {at:#x}: the instruction {original:#010x} at {site:#x} uses the pc")
        else:
            first = struct.pack("<I", original)
        trampoline = first + encode_branch(at + STUB_TRAMPOLINE + 4, site + 4)
    else:
        trampoline = bytes(8)
        note_game_pointer(at + STUB_FALLBACK, fallback)
    return struct.pack(f"<{len(_STUB_CODE)}I3I", *_STUB_CODE, state, fallback, target) + trampoline


# ---- the opening stub (a screen's pack) ----
# An entry stub after four words that load the pack first when it is out: `push {r12, lr}`, `mov r12, #slot`,
# `bl pack_opening` (pack_guard.s: every register and the flags kept, pack_loader.c pack_open), `pop {r12, lr}`. It
# takes two stubs' room (OPEN_SLOTS), the entry stub at OPEN_SIZE.
OPEN_SIZE = 0x10
OPEN_SLOTS = 2
if OPEN_SIZE + STUB_SIZE > OPEN_SLOTS * PACK_STUB_SIZE:
    raise ImportError("the opening stub does not fit two entry stubs' room")


def opening_stub(at: int, opening: int, slot: int, state: int, target: int, fallback: int | None = None, *,
                 site: int | None = None, original: int | None = None, returns_zero: bool = False) -> bytes:
    """The opening stub placed at `at` (OPEN_SLOTS * PACK_STUB_SIZE bytes, its tail zero): pack_opening (`opening`, its
    address) with the pack's `slot`, then `entry_stub` at `at + OPEN_SIZE` with the other arguments."""
    if not 0 <= slot < 0x100:
        raise CodeSpaceError(f"opening stub at {at:#x}: slot {slot} does not fit its mov")
    head = struct.pack("<2I", 0xE92D5000, 0xE3A0C000 | slot) + encode_branch(at + 8, opening, link=True) + \
        struct.pack("<I", 0xE8BD5000)
    stub = entry_stub(at + OPEN_SIZE, state, target, fallback, site=site, original=original, returns_zero=returns_zero)
    return (head + stub).ljust(OPEN_SLOTS * PACK_STUB_SIZE, b"\0")


def stub_target(code: bytes, address: int | None) -> int | None:
    """The pack's address the entry stub (or opening stub) at `address` of the executable `code` goes to while the pack
    is in, or None when no stub is there: what a patcher that checks an earlier hook reads behind it."""
    if address is None or not 0 <= address - BASE_ADDRESS <= len(code) - OPEN_SIZE - STUB_SIZE:
        return None
    first = struct.unpack_from("<I", code, address - BASE_ADDRESS)[0]
    start = address + (OPEN_SIZE if first == 0xE92D5000 else 0)
    if struct.unpack_from("<I", code, start - BASE_ADDRESS)[0] != _STUB_CODE[0]:
        return None
    return struct.unpack_from("<I", code, start + STUB_TARGET - BASE_ADDRESS)[0]


# ---- the guarded entry (risk 3: a call the network callback can make, from a thread that may not be the main one) ----
# A call's stub that counts the calls inside the pack (pack_guard.s, `pack_guarded`, resident): `add r12, pc, #0` then
# `b pack_guarded` with r12 at its four words: the pack's function, the game's (the call's old target), the state
# byte's address and the busy word's (PACK_BUSY + 4 * slot). pack_guarded raises the busy word (ldrex / strex), reads
# the state byte after it, calls one of the two with r0-r3 as the game left them and lowers the word; the scene gate
# clears the state byte first and frees only once the word is 0. It takes PACK_STUB_SIZE bytes like the plain stub.
GUARD_SIZE = 0x18
GUARD_TARGET, GUARD_FALLBACK, GUARD_STATE, GUARD_BUSY = 0x8, 0xC, 0x10, 0x14
if GUARD_SIZE > PACK_STUB_SIZE:
    raise ImportError("the guarded stub does not fit an entry stub's room")


def guarded_stub(at: int, guard: int, state: int, busy: int, target: int, fallback: int) -> bytes:
    """The guarded call stub placed at `at` (PACK_STUB_SIZE bytes, its tail zero): `guard` is pack_guarded's address,
    `state` the pack's state byte, `busy` its busy word, `target` the pack's function, `fallback` the call's old
    target (a game function: noted, the rebase moves it)."""
    note_game_pointer(at + GUARD_FALLBACK, fallback)
    stub = struct.pack("<I", 0xE28FC000) + encode_branch(at + 4, guard) + struct.pack("<4I", target, fallback, state,
                                                                                      busy)
    return stub.ljust(PACK_STUB_SIZE, b"\0")


# ---- the loader's table (pack_table.h) ----
PACK_NONE = 0xFF            # no pack: an id without one, a pack that needs none
TABLE_HEAD = 4              # u16 count (entries), u16 first id
PACK_FOLDER = "packs"       # the packs' folder in the RomFS


def pack_file(pack: str) -> str:
    """The RomFS path of pack `pack`'s file (pack_files, write_files); a screen's "screen:<name>" is screen_<name>."""
    return f"{PACK_FOLDER}/{pack.replace(':', '_')}.bin"


@dataclass(frozen=True)
class PackPlan:
    """What the table says of one pack of the run: its file's bytes, the pack its code needs loaded first (a Deviant's
    base) and the pack loaded with it (the small monsters his monster calls)."""
    size: int
    needs: str | None = None
    with_pack: str | None = None


def pack_table(layout: Layout, plans: Mapping[str, PackPlan], id_packs: Mapping[int, str], first_id: int,
               ids: int, *, gate_frames: int | None = None) -> bytes:
    """The table (TABLE, pack_table.h): an entry per slot up to the last of PACK_SLOTS, with its range, and for the
    run's packs (`plans`) their size, needs and file (0 and PACK_NONE for the others); before them the pack of each
    new monster id (`id_packs`, id -> pack; PACK_NONE for an id without one) from `first_id`, `ids` of them; after
    them each pack's variables (pack_variables) and the scene gate's wait (`gate_frames`, default
    scene_gate_frames)."""
    out = bytearray(pack_table_size(ids))
    struct.pack_into("<HH", out, 0, PACK_TABLE_COUNT, first_id)
    out[TABLE_HEAD:TABLE_HEAD + ids] = bytes([PACK_NONE]) * ids
    for monster_id, pack in id_packs.items():
        if not first_id <= monster_id < first_id + ids:
            raise CodeSpaceError(f"monster id {monster_id} has no place in the packs' table")
        out[TABLE_HEAD + monster_id - first_id] = PACK_SLOTS[pack]
    heads = TABLE_HEAD + -(-ids // 4) * 4
    for pack, plan in plans.items():
        if plan.size != layout.pack_size(pack):
            raise CodeSpaceError(f"pack {pack}: {plan.size} bytes, the layout's is {layout.pack_size(pack)}")
    variables = pack_variables(layout)
    for pack, slot in PACK_SLOTS.items():
        region, plan = PACK_REGIONS[pack], plans.get(pack)
        needs = PACK_SLOTS[plan.needs] if plan and plan.needs else PACK_NONE
        with_pack = PACK_SLOTS[plan.with_pack] if plan and plan.with_pack else PACK_NONE
        name = pack_file(pack).encode("ascii") if plan else b""
        if len(name) >= PACK_FILE_SIZE:
            raise CodeSpaceError(f"pack {pack}: its file name {name!r} is too long for the table")
        struct.pack_into(f"<3I4B{PACK_FILE_SIZE}s", out, heads + PACK_ENTRY_SIZE * slot, region.start, region.size,
                         plan.size if plan else 0, slot, needs, with_pack, table_side(pack), name)
        if plan and pack in variables:
            struct.pack_into("<2I", out, heads + PACK_ENTRY_SIZE * PACK_TABLE_COUNT + PACK_VARS_SIZE * slot,
                             *variables[pack])
    struct.pack_into("<I", out, heads + (PACK_ENTRY_SIZE + PACK_VARS_SIZE) * PACK_TABLE_COUNT,
                     scene_gate_frames() if gate_frames is None else gate_frames)
    return bytes(out)


def scene_gate_frames() -> int:
    """The frames the scene gate waits at most for the quest's last units and calls (tuning.json,
    memory.scene_gate_frames)."""
    from core.game.data.tuning import tuning
    value = tuning("memory", "scene_gate_frames")
    if not isinstance(value, int) or not 1 <= value < 1 << 32:
        raise ValueError(f"tuning memory.scene_gate_frames: a whole number of frames, not {value!r}")
    return value


def pack_variables(layout: Layout) -> dict[str, tuple[int, int]]:
    """Each pack's variables (VariableSpec.scene a pack's) as one range, (start, bytes), which the loader zeroes each
    time it loads the pack. Refused when another variable lies inside a pack's range: a pack's variables are laid out
    together (tools/build/build_code_space.py pack_variables)."""
    ranges: dict[str, tuple[int, int]] = {}
    for spec in VARIABLES:
        if spec.scene == RESIDENT or spec.name not in layout.variables:
            continue
        if spec.scene not in PACK_SLOTS:
            raise CodeSpaceError(f"variable {spec.name}: scene {spec.scene!r} is no pack's")
        found = layout.variables[spec.name]
        start, end = ranges.get(spec.scene, (found.address, found.address))
        ranges[spec.scene] = (min(start, found.address), max(end, found.address + found.size))
    for pack, (start, end) in ranges.items():
        inside = [v.name for v in layout.variables.values() if start < v.address + v.size and v.address < end and
                  next((s.scene for s in VARIABLES if s.name == v.name), RESIDENT) != pack]
        if inside:
            raise CodeSpaceError(f"pack {pack}'s variables are not together: {', '.join(inside)} lie among them")
    return {pack: (start, end - start) for pack, (start, end) in ranges.items()}


@dataclass(frozen=True)
class TableEntry:
    start: int
    room: int
    size: int
    slot: int
    needs: int
    with_pack: int
    file: str
    variables: tuple[int, int] = (0, 0)     # (start, bytes): the pack's variables, zeroed at each load
    side: int = 0                           # SIDES: the quest's or the town's (pack_table.h PACK_SIDE_*)


def read_table(data: bytes, ids: int) -> tuple[int, tuple[int, ...], tuple[TableEntry, ...]]:
    """The table `pack_table` made, read back as the loader reads it: (first id, each new id's slot, the entries)."""
    count, first_id = struct.unpack_from("<HH", data, 0)
    heads = TABLE_HEAD + -(-ids // 4) * 4
    entries = []
    for k in range(count):
        start, room, size, slot, needs, with_pack, side, name = struct.unpack_from(
            f"<3I4B{PACK_FILE_SIZE}s", data, heads + PACK_ENTRY_SIZE * k)
        variables = struct.unpack_from("<2I", data, heads + PACK_ENTRY_SIZE * count + PACK_VARS_SIZE * k)
        entries.append(TableEntry(start, room, size, slot, needs, with_pack, name.rstrip(b"\0").decode("ascii"),
                                  variables, side))
    return first_id, tuple(data[TABLE_HEAD:TABLE_HEAD + ids]), tuple(entries)


# ---- the run's memory with packs loaded (the tests' emulation) ----
def memory(code: bytes, packs: Mapping[str, bytes], loaded: Iterable[str] | None = None,
           layout: Layout | None = None) -> tuple[bytes, tuple[tuple[int, bytes], ...]]:
    """The run's memory as the game has it with the packs `loaded` in (default every pack of `packs`, the run's
    images), as the loader leaves it: the executable `code` with those packs' state bytes set (grown with zeros up to
    them when its file ends before), and each of those packs' image at its address, as (address, bytes)."""
    names = list(packs) if loaded is None else list(loaded)
    missing = [name for name in names if name not in packs]
    if missing:
        raise CodeSpaceError(f"no image of pack {', '.join(missing)} in this run")
    out = bytearray(code)
    state = (layout or load_layout()).address(STATE) - BASE_ADDRESS
    if len(out) < state + PACK_STATE_BYTES:         # (with no pack in, the stubs still read the bytes: 0)
        out.extend(bytes(state + PACK_STATE_BYTES - len(out)))
    for name in names:
        out[state + PACK_SLOTS[name]] = 1
    return bytes(out), tuple((PACK_REGIONS[name].start, bytes(packs[name])) for name in names)


def pack_files(packs: Mapping[str, bytes]) -> dict[str, bytes]:
    """The RomFS files of a run's packs (its `Rebased.packs`, the player's version's): path -> bytes, where the loader
    reads them (pack_table.h's file names)."""
    return {pack_file(name): bytes(image) for name, image in packs.items()}


class PackedCode(bytes):
    """An executable and the pack images of its run (`packs`: pack -> image), for a tool that reads a built mod's
    ported monsters' code (research/probes' `box["canonical"]`, `port_probe.check`)."""
    packs: dict[str, bytes]

    def __new__(cls, code: bytes, images: Mapping[str, bytes]) -> PackedCode:
        out = super().__new__(cls, code)
        out.packs = {name: bytes(image) for name, image in images.items()}
        return out


def _image(code: bytes, address: int, *, writing: bool = False) -> tuple[bytearray | bytes, int] | None:
    """The image of the pack whose range holds `address` and the address's offset in it: `code`'s own (a PackedCode),
    else the run's (session.Session.packs, the images its patchers build); None outside every pack."""
    from core.game.executable import session
    pack = pack_of(address)
    if pack is None:
        return None
    notes = session.current()
    images = notes.packs if notes is not None and not isinstance(code, PackedCode) else getattr(code, "packs", {})
    if pack not in images:
        if writing:
            raise CodeSpaceError(f"{address:#x} is in pack {pack}, which the run has no image of: place its block "
                                 "first, inside session.recording()")
        return b"", 0
    return images[pack], address - PACK_REGIONS[pack].start


def read_at(code: bytes, offset: int, size: int) -> bytes:
    """`size` bytes at file offset `offset` (address - BASE_ADDRESS) of a run's executable `code`, or, for an address
    in a pack's range, of that pack's image (`_image`; empty for a pack the run has none of): what a reader of the
    patched executable follows a pointer with."""
    found = _image(code, offset + BASE_ADDRESS) if offset >= len(code) else None
    if found is None:
        return bytes(code[offset:offset + size])
    image, at = found
    return bytes(image[at:at + size])


def write_at(out: bytearray, offset: int, data: bytes) -> None:
    """`data` at file offset `offset` of the run's executable `out`, or into the run's image of the pack whose range
    holds the address (refused for a pack the run has no image of, and past an image's end)."""
    found = _image(out, offset + BASE_ADDRESS, writing=True) if offset >= len(out) else None
    if found is None:
        if offset + len(data) > len(out):
            raise CodeSpaceError(f"{offset + BASE_ADDRESS:#x}: {len(data)} bytes past the executable's end")
        out[offset:offset + len(data)] = data
        return
    image, at = found
    if at + len(data) > len(image):
        raise CodeSpaceError(f"{offset + BASE_ADDRESS:#x}: {len(data)} bytes past its pack image's end")
    image[at:at + len(data)] = data


def carried(patched: bytes, carry_args: tuple) -> PackedCode:
    """What `PlayerCode.carry(patched, notes, ...)` is given, with its packs: `carry_args` are its arguments after
    `patched` (a probe's hook of `carry` passes its `*args`)."""
    notes = carry_args[0] if carry_args else None
    return PackedCode(patched, getattr(notes, "packs", None) or {})


def romfs_paths() -> list[str]:
    """Every RomFS path a run may write a pack at (one per slot), for the files of an earlier run to remove."""
    return [pack_file(name) for name in PACK_SLOTS]


def remove_files(mod: Path) -> None:
    """The packs' files of an earlier run in the mod folder `mod` (a pack the run no longer builds, a monster turned
    off, a fix, a run with no executable): they would still be loaded. Any `*.bin` of the packs' folder goes."""
    folder = Path(mod) / "romfs" / PACK_FOLDER
    for path in [*(Path(mod) / "romfs" / name for name in romfs_paths()), *folder.glob("*.bin")]:
        path.unlink(missing_ok=True)
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()


def write_files(mod: Path, packs: Mapping[str, bytes]) -> list[Path]:
    """The run's pack files written into the mod folder `mod` (its RomFS), those of an earlier run removed first."""
    remove_files(mod)
    out = []
    for path, data in pack_files(packs).items():
        target = Path(mod) / "romfs" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        out.append(target)
    return out


def read_files(mod: Path) -> dict[str, bytes]:
    """The packs a written mod folder holds (`write_files`'s files): pack -> image; empty when it has none."""
    folder = Path(mod) / "romfs" / PACK_FOLDER
    names = {Path(pack_file(name)).name: name for name in PACK_SLOTS}
    return {names.get(path.name, path.stem): path.read_bytes() for path in sorted(folder.glob("*.bin"))} \
        if folder.is_dir() else {}


# ---- the build's check ----
@dataclass(frozen=True)
class EntryWords:
    """Resident words that may hold an address in a pack, all read only in a scene whose packs are loaded: whole blocks
    (`blocks`), parts of blocks (`ranges`: block -> [start, end) bytes of it) and single words (`words`, addresses)."""
    blocks: frozenset[str] = frozenset()
    ranges: Mapping[str, tuple[int, int]] = field(default_factory=dict)
    words: frozenset[int] = frozenset()


class PackLeak(CodeSpaceError):
    """Words that reach a pack outside the declared entries."""


@dataclass
class CheckReport:
    """What `check` found: the leaks (errors) and the coincidences it told apart, counted by kind."""
    leaks: list[str] = field(default_factory=list)
    coincidences: dict[str, int] = field(default_factory=dict)

    def count(self, kind: str) -> None:
        self.coincidences[kind] = self.coincidences.get(kind, 0) + 1


def _words(data: bytes) -> tuple[int, ...]:
    return struct.unpack(f"<{len(data) // 4}I", bytes(data[:len(data) // 4 * 4]))


def _read_in(block, pack: str) -> bool:
    """Whether the game's words may name `block` (a block of pack `pack`): its spec declares read_in, scenes its pack
    covers (blocks.BlockSpec.read_in, pack_covers)."""
    from core.game.executable.blocks import BLOCKS
    spec = next((one for one in BLOCKS if block is not None and one.name == block.name), None)
    return bool(spec and spec.read_in) and set(spec.read_in) <= pack_covers(pack)


class _Blocks:
    def __init__(self, layout: Layout):
        self._blocks = sorted(layout.blocks.values(), key=lambda b: b.address)
        self._starts = [b.address for b in self._blocks]

    def holder(self, address: int):
        i = bisect.bisect_right(self._starts, address) - 1
        return self._blocks[i] if i >= 0 and address < self._blocks[i].end else None


def check(patched: bytes, canonical: bytes, packs: Mapping[str, bytes], layout: Layout, entries: EntryWords,
          reaches: Mapping[str, Iterable[str]], *, values: Iterable[str] | Mapping[str, Iterable[str]] = (),
          code: Iterable[str] = ()) -> CheckReport:
    """The check of a run's product: `patched` (the canonical executable after the patchers; `canonical` before them)
    and its pack images `packs` (pack -> image at its range's start). A leak is
    * a word of the executable that the patch changed (a resident block's, or a game word it wrote) that points at a
      block of a pack, outside `entries`;
    * a word of a pack that points or branches at a block of another pack that `reaches[pack]` does not name.
    A word points at a block when its value is the block's start or one of its labels (with bit 0, a Thumb one, only
    in a block of `code`): what the patchers write (a block's address, a symbol) and what a link makes of a name. Told
    apart as coincidences, as the study did ("P2 study (S2)", 5): a value inside a block at no start or label (a
    number of a table, an image's float), a word of a block of `values` (tables of numbers: hashes, floats, ids; or,
    as a mapping, pack -> the blocks read as numbers for the words into that pack), and a branch pattern outside code
    (`code`: the code blocks) or to no label. No branch of the executable reaches a pack (too far for an ARM branch),
    so only a pack's are branches. The link checks the code's names apart (build_code_space: a resident block names no
    pack's label). Returns the report."""
    report = CheckReport()
    spans = {name: (PACK_REGIONS[name].start, PACK_REGIONS[name].start + len(image)) for name, image in packs.items()}
    blocks = _Blocks(layout)
    code_blocks = set(code)
    if isinstance(values, Mapping):
        by_pack = {pack: frozenset(names) for pack, names in values.items()}
    else:
        flat = frozenset(values)
        by_pack = {pack: flat for pack in PACK_SLOTS}

    def numbers(holder, found: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
        """`found` without the hits that `holder`, a block of values for their pack, holds as numbers (counted)."""
        kept = [hit for hit in found if holder is None or holder.name not in by_pack.get(hit[2], ())]
        if len(kept) < len(found):
            report.count("a number in a table of values")
        return kept
    allowed = {name: (0, len(layout.block(name).data)) for name in entries.blocks} | dict(entries.ranges)
    labels = {block.address + offset for name in packs for block in layout.pack_blocks(name)
              for offset in (0, *block.symbols.values())}

    def into(value: int | None) -> str | None:
        pack = pack_of(value) if value is not None else None
        return pack if pack in spans and spans[pack][0] <= value < spans[pack][1] else None

    def hits(at: int, w: int) -> list[tuple[int, str, str]]:
        """(value, how, pack) of the word `w` at `at` that reach a pack, coincidences counted."""
        found = []
        pack = into(w)
        if pack:
            if w & 2 or w & ~1 not in labels or w & 1 and blocks.holder(w & ~1).name not in code_blocks:
                report.count("a value inside a block, at no start or label")
            else:
                found.append((w, "points", pack))
        target = arm_branch_target(w, at)
        pack = into(target)
        if pack:
            holder = blocks.holder(at)
            if holder is None or holder.name not in code_blocks or target not in labels:
                report.count("a branch pattern outside code or to no label")
            else:
                found.append((target, "branches", pack))
        return found

    def where(at: int) -> str:
        holder = blocks.holder(at)
        if holder:
            return f"{holder.name}+{at - holder.address:#x}"
        return ("the game's" if is_game_address(at) else "the executable's") + f" {at:#x}"

    for at in changed_words(canonical, patched):
        w = struct.unpack_from("<I", patched, at - BASE_ADDRESS)[0]
        found = hits(at, w)
        if not found:
            continue
        holder = blocks.holder(at)
        found = numbers(holder, found)
        if not found:
            continue
        if holder is None and is_game_address(at):   # a game word the game never read as a pointer (B135)
            was = struct.unpack_from("<I", canonical, at - BASE_ADDRESS)[0]
            if was and not is_game_address(was & ~1):
                report.count("a number of the game's, no pointer slot")
                continue
        span = allowed.get(holder.name) if holder else None
        if at in entries.words or span is not None and span[0] <= at - holder.address < span[1]:
            continue
        if holder is None and is_game_address(at):    # a game word: its block declares where the game reads it
            unread = [hit for hit in found if not _read_in(blocks.holder(hit[0] & ~1), hit[2])]
            if not unread:
                report.count("a game word into a pack its readers' scenes cover (read_in)")
                continue
            for value, how, pack in unread:
                target = blocks.holder(value & ~1)
                report.leaks.append(f"{where(at)} {how} into pack {pack} ({value:#x}, block {target.name}): a game "
                                    f"word the game may read while the pack is out. Declare read_in=(<the readers' "
                                    f"scenes>,) on block {target.name} if every reader runs while its pack is in, or "
                                    "keep the block resident")
            continue
        for value, how, pack in found:
            report.leaks.append(f"{where(at)} {how} into pack {pack} ({value:#x}) outside the declared entries")
    for pack, image in packs.items():
        start = PACK_REGIONS[pack].start
        free = {pack, *reaches.get(pack, ())}
        for k, w in enumerate(_words(image)):
            if not w:
                continue
            at = start + 4 * k
            found = [hit for hit in hits(at, w) if hit[2] not in free]
            if not found:
                continue
            found = numbers(blocks.holder(at), found)
            for value, how, other in found:
                report.leaks.append(f"{where(at)} {how} into pack {other} ({value:#x}), which pack {pack} does not "
                                    "declare")
    return report


def check_or_raise(*args, **kwargs) -> CheckReport:
    """`check`, raising PackLeak with its first leaks."""
    report = check(*args, **kwargs)
    if report.leaks:
        shown = "; ".join(report.leaks[:8])
        more = f" (and {len(report.leaks) - 8} more)" if len(report.leaks) > 8 else ""
        raise PackLeak(f"{len(report.leaks)} words reach a pack outside its declared entries: {shown}{more}")
    return report
