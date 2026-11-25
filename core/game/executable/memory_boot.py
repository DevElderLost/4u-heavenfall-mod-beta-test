"""The heap sizes at boot, made for each executable the build writes.

FUN_001047c0, which the executable's entry calls once, splits the application's memory (min(APPMEMALLOC, cap): 80 MB on
an Old 3DS, 124 MB on a New 3DS) into the device memory (the literal at `DEVICE_LITERAL`, 0xA00000 more on a New 3DS)
and the root heap (what is left after the executable, the main thread's stack and the device memory). FUN_0010612c then
cuts the heap table (`HEAP_TABLE`) into fixed heaps: those of flags 9 from the device memory (their sizes add up to the
literal exactly), those of flags 8 from the root heap; 0x500000 more for Resource on a New 3DS.

The blocks `memory_boot_hook`, `memory_boot` and `memory_boot_rows` (memory_boot.c) take the split's numbers from a row
per memory size: the heap sizes of the row (Global, Resource, CommandCache, Unit/Area and Develop; the New 3DS's adders
inside them), the device memory as the device heaps' exact sum, and a packs' budget kept out of the root heap,
uncommitted. A memory size without a row keeps every number of the game.

The build fills the rows from the executable's real end (`process_end`, the extension's variables included), the
curated floors (tuning.json, memory.boot_heaps: the small heaps' sizes, the root heap's margin above what the game
takes from it at boot, `root_boot_demand`) and the run's packs: on an Old 3DS the packs' window (pack_loader.run_need:
the most its loader commits at once, from the run's own table and quests), on a New 3DS every pack (resident_need: no
packs' manager there, every pack read at boot and kept). Resource gets everything left after the root heap's margin, up
to the curated maximum, and the build stops
(MemoryPlanError, naming what sets the packs and the bytes missing) when that falls under the curated minimum. Every
MH4U version has the hook's instruction, the literal and the table at the same addresses (the version maps carry them).
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.game.data.tuning import TUNING_PATH, load_tuning
from core.game.executable.blocks import MEMORY_BOOT_HEAPS, MEMORY_BOOT_ROWS, MEMORY_BOOT_ROWS_SIZE
from core.game.executable.code_space import BASE_ADDRESS, EXT_START, PAGE, CodeSpaceError, Layout, load_layout

if TYPE_CHECKING:
    from core.game.executable.pack_loader import PacksNeed
    from core.game.files.mib import Quest

KB, MB = 0x400, 0x100000
HOOK_BLOCK, CODE_BLOCK, ROWS_BLOCK = "memory_boot_hook", "memory_boot", "memory_boot_rows"
# FUN_001047c0's `sub r0, r4, r5`: the root heap's size, from the memory left and the device memory
HOOK, HOOK_ORIGINAL = 0x104804, struct.pack("<I", 0xE0440005)
DEVICE_LITERAL, DEVICE_ORIGINAL = 0x104828, 0x3063000     # its `ldr r5`: the device memory's size
HEAP_TABLE, HEAP_ENTRY = 0xF2BB44, 0x18     # FUN_0010612c's table: name, index, flags (u16), size, two more words
DEVICE_FLAGS, ROOT_FLAGS = 9, 8
# The update's table (every version's): each heap's name, flags and size; the order is the table's
GAME_HEAPS = (("Global", ROOT_FLAGS, 0xC0000), ("Temp", DEVICE_FLAGS, 0x8A000), ("Resource", DEVICE_FLAGS, 0x2F00000),
              ("CommandCache", DEVICE_FLAGS, 0xC0000), ("System", ROOT_FLAGS, 0x33F000),
              ("Unit/Area", ROOT_FLAGS, 0x700000), ("Array/String", ROOT_FLAGS, 0x12000),
              ("Collision", ROOT_FLAGS, 0x1C0000), ("Develop", DEVICE_FLAGS, 0x19000))
NAMES = tuple(name for name, _, _ in GAME_HEAPS)
GAME_SIZES = {name: size for name, _, size in GAME_HEAPS}
DEVICE_HEAPS = tuple(name for name, flags, _ in GAME_HEAPS if flags == DEVICE_FLAGS)
ROOT_HEAPS = tuple(name for name, flags, _ in GAME_HEAPS if flags == ROOT_FLAGS)
# The heaps a row sizes, with their tuning keys (memory.boot_heaps); Resource is what is left
SIZED = {"Global": "global_kb", "CommandCache": "command_cache_kb", "Unit/Area": "unit_area_kb",
         "Develop": "develop_kb"}
RESOURCE = "Resource"
SMALLEST = PAGE             # FUN_0010612c skips a heap of size 0; svcControlMemory takes whole pages
OLD3DS, NEW3DS = 0x5000000, 0x7C00000       # min(APPMEMALLOC, cap): the two memory sizes with a row (80, 124 MB)
APP_SIZES = {"80": OLD3DS, "124": NEW3DS}  # memory.boot_heaps' keys
MAIN_STACK = 0x40000        # the main thread's stack (every version's exheader), taken before FUN_001047c0 runs
# What the game takes from the root heap at boot with its own sizes (ten save states: its one free block started at
# 0x8E68C28): the flags 8 heaps (13.44 MB with Physical's 0.63, which no row changes) and the objects made at boot
GAME_ROOT_BOOT_DEMAND = 15_109_160
ROW_FORMAT = f"<2I{MEMORY_BOOT_HEAPS}I"     # memory_boot.c struct memory_row: app, packs, the sizes (0: the game's)
ROW_SIZE = struct.calcsize(ROW_FORMAT)
assert len(NAMES) == MEMORY_BOOT_HEAPS and ROW_SIZE * MEMORY_BOOT_ROWS == MEMORY_BOOT_ROWS_SIZE


class MemoryPlanError(CodeSpaceError):
    """An executable too large for the curated Resource heap's minimum on a memory size."""


@dataclass(frozen=True)
class BootConfig:
    """One memory size's curated numbers, in bytes (tuning.json, memory.boot_heaps)."""
    sizes: dict[str, int]       # the heaps of SIZED
    root_margin: int            # the root heap's free bytes after the boot, at least
    resource_min: int
    resource_max: int


@dataclass(frozen=True)
class Row:
    """The heap sizes of memory size `app` (every heap of NAMES, as it is made) and the packs' budget kept out of the
    root heap, uncommitted (the run's packs' window on an Old 3DS, every pack on a New 3DS)."""
    app: int
    packs: int
    sizes: dict[str, int]

    @property
    def device(self) -> int:
        """The device memory: the device heaps' exact sum."""
        return sum(self.sizes[name] for name in DEVICE_HEAPS)


def boot_config(path: Path = TUNING_PATH) -> dict[int, BootConfig]:
    """memory.boot_heaps, checked: each memory size's numbers in whole pages, no heap under a page, the minimum under
    the maximum."""
    table = load_tuning(path)["memory"]["boot_heaps"]
    if set(table) != set(APP_SIZES):
        raise ValueError(f"tuning memory.boot_heaps: the memory sizes {sorted(APP_SIZES)}, not {sorted(table)}")
    out = {}
    for key, values in table.items():
        keys = (*SIZED.values(), "root_margin_kb", "resource_min_kb", "resource_max_kb")
        if set(values) != set(keys):
            raise ValueError(f"tuning memory.boot_heaps.{key}: the keys {sorted(keys)}")
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value * KB % PAGE:
                raise ValueError(f"tuning memory.boot_heaps.{key}.{name}: whole 4 KB pages, in KB")
        sizes = {heap: values[name] * KB for heap, name in SIZED.items()}
        low, high = values["resource_min_kb"] * KB, values["resource_max_kb"] * KB     # one unit: bytes
        if min(sizes.values()) < SMALLEST or not SMALLEST <= low <= high:
            raise ValueError(f"tuning memory.boot_heaps.{key}: a heap under 4 KB, or Resource's minimum over its "
                             "maximum")
        out[APP_SIZES[key]] = BootConfig(sizes, values["root_margin_kb"] * KB, values["resource_min_kb"] * KB,
                                         values["resource_max_kb"] * KB)
    return out


def _packs(need: PacksNeed | int) -> tuple[int, str]:
    """The packs' window in whole pages, and what asks for it."""
    size, what = (need, "the packs") if isinstance(need, int) else (need.size, need.what)
    if isinstance(size, bool) or size < 0:
        raise ValueError(f"heap sizes at boot: a packs' window of {size!r} bytes")
    return -(-size // PAGE) * PAGE, what


def process_end(code: bytes) -> int:
    """Where the executable's memory ends at boot: the last page of the file, or of the game's .bss when the file has
    no extension."""
    end = max(BASE_ADDRESS + len(code), EXT_START)
    return -(-end // PAGE) * PAGE


def boot_room(app: int, code_end: int) -> int:
    """The application memory FUN_001047c0 splits for an executable ending at `code_end`: `app` less the executable and
    the main thread's stack (what svcGetResourceLimitCurrentValues gives it)."""
    return app - (code_end - BASE_ADDRESS + MAIN_STACK)


def root_boot_demand(sizes: dict[str, int]) -> int:
    """What the game takes from the root heap at boot with the heap sizes `sizes`: its own demand, less what the root
    heaps (flags 8) of `sizes` give back against the game's."""
    return GAME_ROOT_BOOT_DEMAND + sum(sizes[name] - GAME_SIZES[name] for name in ROOT_HEAPS)


def root_free(row: Row, code_end: int) -> int:
    """The root heap's free bytes after the boot of an executable ending at `code_end` with `row` (negative: it does not
    boot)."""
    return boot_room(row.app, code_end) - row.device - row.packs - root_boot_demand(row.sizes)


def _resource_room(app: int, code_end: int, config: BootConfig, packs: int) -> tuple[dict[str, int], int]:
    """The heap sizes of `config` and the room left for Resource (whole pages, maybe under the minimum) with `packs`
    bytes of packs' window."""
    sizes = dict(GAME_SIZES) | config.sizes
    others = sum(sizes[name] for name in DEVICE_HEAPS if name != RESOURCE)
    room = boot_room(app, code_end) - packs - root_boot_demand(sizes) - config.root_margin - others
    return sizes, room // PAGE * PAGE


def plan_row(app: int, code_end: int, config: BootConfig, need: PacksNeed | int = 0) -> Row:
    """The row of memory size `app` for an executable ending at `code_end` whose run's packs are `need` (bytes, rounded
    up to pages: on an Old 3DS the packs' window, pack_loader.run_need; on a New 3DS every pack, resident_need): the
    curated heaps, the packs, the root heap's curated margin, and Resource whatever is left, up to the curated maximum.
    MemoryPlanError when that is under the curated minimum (the root heap would keep less than its margin otherwise),
    naming what sets the packs and how many bytes are missing."""
    packs, what = _packs(need)
    sizes, room = _resource_room(app, code_end, config, packs)
    if room < config.resource_min:
        raise MemoryPlanError(
            f"heap sizes at boot: with the executable ending at {code_end:#x} and {packs} bytes of packs kept out of "
            f"the root heap ({what}), the Resource heap of the {app // MB} MB console gets {room} bytes, "
            f"{config.resource_min - room} bytes under the curated {config.resource_min} (tuning.json "
            "memory.boot_heaps)")
    sizes[RESOURCE] = min(room, config.resource_max)
    return Row(app, packs, sizes)


def plan(code_end: int, path: Path = TUNING_PATH, need: PacksNeed | int = 0,
         resident: PacksNeed | int = 0) -> tuple[Row, ...]:
    """Every memory size's row for an executable ending at `code_end` with a packs' window of `need` on an Old 3DS and
    `resident` bytes of packs on a New 3DS (every pack), smallest memory first."""
    return tuple(plan_row(app, code_end, config, resident if app == NEW3DS else need)
                 for app, config in sorted(boot_config(path).items()))


def spare_room(code_end: int, app: int = OLD3DS, path: Path = TUNING_PATH, need: PacksNeed | int = 0) -> int:
    """What Resource has over its curated minimum plus what the root heap has over its curated margin, for an executable
    ending at `code_end` on memory size `app` with packs of `need` (the window on an Old 3DS, every pack on a New 3DS;
    the room later code may take; negative: it does not fit)."""
    config = boot_config(path)[app]
    packs, _ = _packs(need)
    sizes, room = _resource_room(app, code_end, config, packs)
    row = Row(app, packs, sizes | {RESOURCE: min(room, config.resource_max)})
    return min(room, config.resource_max) - config.resource_min + root_free(row, code_end) - config.root_margin


def rows_data(rows: tuple[Row, ...]) -> bytes:
    """memory_boot_rows' bytes: each row, then empty ones (memory size 0, which no console has)."""
    if len(rows) > MEMORY_BOOT_ROWS:
        raise ValueError(f"heap sizes at boot: {len(rows)} rows, room for {MEMORY_BOOT_ROWS}")
    out = b"".join(struct.pack(ROW_FORMAT, row.app, row.packs, *(row.sizes[name] for name in NAMES)) for row in rows)
    return out + bytes(MEMORY_BOOT_ROWS_SIZE - len(out))


def written_rows(code: bytes, layout: Layout | None = None) -> tuple[Row, ...]:
    """The rows an executable patched by patch_memory_boot holds (none when it has no block)."""
    layout = layout or load_layout()
    at = layout.address(ROWS_BLOCK) - BASE_ADDRESS
    if len(code) < at + MEMORY_BOOT_ROWS_SIZE:
        return ()
    rows = []
    for k in range(MEMORY_BOOT_ROWS):
        app, packs, *sizes = struct.unpack_from(ROW_FORMAT, code, at + k * ROW_SIZE)
        if app:
            rows.append(Row(app, packs, {name: size or GAME_SIZES[name] for name, size in zip(NAMES, sizes)}))
    return tuple(rows)


def _word(code: bytes, address: int) -> int:
    return struct.unpack_from("<I", code, address - BASE_ADDRESS)[0]


def heap_table(code: bytes) -> tuple[tuple[str, int, int], ...]:
    """(name, flags, size) of each entry of the executable's heap table."""
    out = []
    for k in range(MEMORY_BOOT_HEAPS):
        name_at, _, flags, size = struct.unpack_from("<IIHxxI", code, HEAP_TABLE + k * HEAP_ENTRY - BASE_ADDRESS)
        at = name_at - BASE_ADDRESS
        name = code[at:code.index(b"\0", at)] if 0 <= at < len(code) and b"\0" in code[at:at + 32] else b""
        out.append((name.decode("ascii", "replace"), flags, size))
    return tuple(out)


def supports_memory_boot(code: bytes) -> bool:
    """True if FUN_001047c0's instruction, the device memory's literal and the heap table are the game's own (the
    canonical executable, not yet patched)."""
    try:
        return (code[HOOK - BASE_ADDRESS:HOOK - BASE_ADDRESS + 4] == HOOK_ORIGINAL
                and _word(code, DEVICE_LITERAL) == DEVICE_ORIGINAL and heap_table(code) == GAME_HEAPS)
    except (struct.error, ValueError):
        return False


def run_needs(code: bytes, quests: Iterable[Quest] = (), layout: Layout | None = None) -> tuple[PacksNeed, PacksNeed]:
    """The packs' window of the run (`code`, `quests`: pack_loader.run_need) and every pack of it (resident_need)."""
    from core.game.executable import pack_loader
    return pack_loader.run_need(code, quests, layout), pack_loader.resident_need(code, layout)


def check_rows_current(code: bytes, layout: Layout | None = None, path: Path = TUNING_PATH, *,
                       extensible: bool = True, quests: Iterable[Quest] = ()) -> None:
    """Raises MemoryPlanError unless the rows `code` holds are the ones `plan` gives for its end, its run's packs'
    window (`quests`: the run's) and its packs now (a patch placed after patch_memory_boot that grew the file or changed
    the packs' table would otherwise take the root heap's margin with no error). Nothing to check in a loose code.bin
    (`extensible` False: no rows were made)."""
    if not extensible:
        return
    if written_rows(code, layout) != plan(process_end(code), path, *run_needs(code, quests, layout)):
        raise MemoryPlanError(
            f"heap sizes at boot: the executable ends at {process_end(code):#x} but its rows were made for another "
            "end or packs' window (a patch grew the file or the packs' table after patch_memory_boot; it must be the "
            "last patch of the product)")


def patch_memory_boot(code: bytes, layout: Layout | None = None, path: Path = TUNING_PATH, *,
                      extensible: bool = True, quests: Iterable[Quest] = ()) -> bytes:
    """`code` (the canonical executable, after every other patch of the product, the packs' loader and its table
    included: its end and its packs set the rows) with the heap sizes at boot: the blocks placed, FUN_001047c0's
    hook, the rows made for the file's end and the run's packs (`run_needs` over `quests`, the run's).
    MemoryPlanError when the executable and the packs leave Resource or a New 3DS's root heap under a curated minimum.
    Not `extensible` (a loose code.bin, with no exheader to load an extension): `code` as it is, with the game's
    numbers, since nothing of such a build reaches the extension."""
    if not extensible:
        return code
    if not supports_memory_boot(code):
        raise CodeSpaceError(f"heap sizes at boot: FUN_001047c0 at {HOOK:#x}, the device memory literal at "
                             f"{DEVICE_LITERAL:#x} or the heap table at {HEAP_TABLE:#x} is not the update's (another "
                             "executable, or already patched)")
    layout = layout or load_layout()
    needs = run_needs(code, quests, layout)
    out = bytearray(code)
    layout.place(out, CODE_BLOCK)
    layout.place(out, HOOK_BLOCK)
    layout.hook(out, HOOK, HOOK_BLOCK, original=HOOK_ORIGINAL)
    layout.extend(out, layout.block(ROWS_BLOCK).end)    # the file as it boots, the rows' page included
    layout.place(out, ROWS_BLOCK, rows_data(plan(process_end(out), path, *needs)))
    return bytes(out)
