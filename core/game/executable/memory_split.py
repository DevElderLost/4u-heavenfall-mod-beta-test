"""The game's memory split at boot: part of the Resource heap's room goes to the root heap, so a full mod boots on an
Old 3DS (Azahar or Citra with New 3DS mode off, and real Old 3DS and 2DS consoles).

FUN_001047c0 reserves the device memory (the literal at `DEVICE_LITERAL`; 10 MB more on a New 3DS) and gives the root
heap what is left of the application's memory after the executable and the main thread's stack. The executable's
extension comes out of the root heap one for one, and the base game leaves only 0.84 MB of it free on an Old 3DS: a
full mod's extension took it all and the boot failed (a thread's stack allocated at 0). FUN_0010612c then
carves the device memory into the Temp, Resource, CommandCache and Develop heaps from the heap table (`HEAP_TABLE`,
entries of 0x18 bytes: name, index, flags, size, ...); their sizes add up to the literal exactly.

The patch lowers both the literal and the Resource heap's size by the curated `memory.resource_to_root_mb`
(tuning.json): the device heaps still fill the device memory, and the root heap grows by that much (in both modes; on a
New 3DS the Resource heap is 5 MB larger and its root heap was never short). Both values are data the version maps
carry at the same address in every MH4U version.
"""

import struct
from pathlib import Path

from core.game.data.tuning import TUNING_PATH, load_tuning
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError

MB = 0x100000
DEVICE_LITERAL, DEVICE_ORIGINAL = 0x104828, 0x3063000   # FUN_001047c0's `ldr r5`: the device memory's size
HEAP_TABLE, HEAP_ENTRY = 0xF2BB44, 0x18                 # FUN_0010612c's table of nine heaps
RESOURCE_ENTRY = HEAP_TABLE + 2 * HEAP_ENTRY            # the third: "Resource" (index 11, flags 9: device memory)
RESOURCE_SIZE, RESOURCE_ORIGINAL = RESOURCE_ENTRY + 0xC, 0x2F00000
RESOURCE_NAME = 0xEB57BB                                # its name, in .data
# What the Resource heap can give: 47 MB on an Old 3DS, its peak in the save states measured 39.5 MB
RESOURCE_MB_MAX = 6

# The Old 3DS root heap (FUN_001047c0): the application's memory (system mode 3, and the function's own cap) less the
# executable from BASE_ADDRESS to its end, the main thread's stack (every version's exheader) and the device memory
OLD3DS_APP_MEMORY, MAIN_STACK = 0x5000000, 0x40000
# What the game took from the root heap at boot in ten save states (its one free block
# started at 0x8E68C28): the sub-heaps (13.44 MB) and the objects made at boot
ROOT_BOOT_DEMAND = 15_109_160


def resource_to_root_mb(path: Path = TUNING_PATH) -> int:
    """The megabytes moved from the Resource heap to the root heap (tuning.json, memory.resource_to_root_mb)."""
    value = load_tuning(path)["memory"]["resource_to_root_mb"]
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= RESOURCE_MB_MAX:
        raise ValueError(f"tuning memory.resource_to_root_mb: a whole number of megabytes from 0 to {RESOURCE_MB_MAX}")
    return value


def old3ds_min_margin(path: Path = TUNING_PATH) -> int:
    """The bytes the Old 3DS root heap must keep free after the boot (tuning.json, memory.old3ds_root_margin_kb)."""
    return int(load_tuning(path)["memory"]["old3ds_root_margin_kb"]) * 1024


def old3ds_root_margin(code_end: int, moved_mb: int) -> int:
    """The bytes left in the Old 3DS root heap after the boot, for an executable ending at `code_end` (its extension's
    last page) with `moved_mb` moved from the Resource heap; negative when the boot cannot fit."""
    root = OLD3DS_APP_MEMORY - (code_end - BASE_ADDRESS + MAIN_STACK) - (DEVICE_ORIGINAL - moved_mb * MB)
    return root - ROOT_BOOT_DEMAND


def _word(code: bytes, address: int) -> int:
    return struct.unpack_from("<I", code, address - BASE_ADDRESS)[0]


def supports_memory_split(code: bytes) -> bool:
    """True if the literal and the Resource heap's entry are the game's own (the canonical executable, not yet
    patched)."""
    name = RESOURCE_NAME - BASE_ADDRESS
    return (len(code) >= RESOURCE_SIZE + 4 - BASE_ADDRESS and _word(code, DEVICE_LITERAL) == DEVICE_ORIGINAL
            and _word(code, RESOURCE_ENTRY) == RESOURCE_NAME and _word(code, RESOURCE_SIZE) == RESOURCE_ORIGINAL
            and code[name:name + 9] == b"Resource\0")


def patch_memory_split(code: bytes, moved_mb: int) -> bytes:
    """`code` where `moved_mb` megabytes of the Resource heap's go to the root heap (nothing for 0)."""
    if not supports_memory_split(code):
        raise CodeSpaceError(f"memory split: the device memory literal at {DEVICE_LITERAL:#x} or the Resource heap at "
                             f"{RESOURCE_ENTRY:#x} is not the update's (another executable, or already patched)")
    if not moved_mb:
        return code
    out = bytearray(code)
    struct.pack_into("<I", out, DEVICE_LITERAL - BASE_ADDRESS, DEVICE_ORIGINAL - moved_mb * MB)
    struct.pack_into("<I", out, RESOURCE_SIZE - BASE_ADDRESS, RESOURCE_ORIGINAL - moved_mb * MB)
    return bytes(out)
