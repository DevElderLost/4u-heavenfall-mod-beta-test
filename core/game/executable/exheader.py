"""The exheader of the player's executable (any MH4U version of SECTIONS), and its version for an extended code.bin.

The exheader gives the sizes of the executable's segments, and the system calls the process may make.
An extended code.bin (code_space.extend_code) needs a new one: .data then covers the old .bss (as zeros
in the file) and the extension, .bss is empty, the code is not compressed, and the bootstrap's system
calls are allowed. The emulator or Luma3DS loads it as `exheader.bin` next to `exefs/`.
"""

import struct
from pathlib import Path

from core.game.executable.containers import TRUNCATED, ExtractError, open_container
from core.game.executable.extract import read_ncch

SIZE = 0x800  # system control info, ARM11/ARM9 capabilities and the access descriptor's copy of them
PAGE = 0x1000
FLAGS, COMPRESSED = 0x0D, 0x01       # system control info flags: bit 0, ExeFS .code is compressed
TEXT_INFO, RODATA_INFO = 0x10, 0x20  # code set info of .text, .rodata: address, size in pages, size in bytes
DATA_INFO = 0x30                     # .data: address, size in pages, size in bytes
BSS_SIZE = 0x3C
KERNEL_CAPS = (0x370, 0x770)         # ARM11 kernel capabilities, and the access descriptor's copy
CAPS = 28                            # descriptors per copy; 0xFFFFFFFF is an empty one
# ARM11 local system capabilities' filesystem access info (7 bytes: storage info + 0x18), and the access descriptor's
# copy, which the console checks it against. Bits: 3dbrew "NCCH/Extended Header", "Filesystem Access Info".
FS_ACCESS = (0x248, 0x648)
FS_ACCESS_SIZE = 7
FS_CATEGORY_SYSTEM_APPLICATION = 0x1
EMPTY = 0xFFFFFFFF
SVC_PREFIX, SVC_PREFIX_MASK = 0xF0000000, 0xF8000000  # 0b11110: SVCs 24 * index + bit (bits 0-23)
# Each MH4U version's (game/executable/versions.py keys) .text, .rodata and .data sizes and .bss, as their exheaders
# give them: in all of them .data starts at DATA_ADDRESS and .bss ends at
# code_space.BSS_END, so every version extends the same way.
SECTIONS = {
    "eur_update": (0xCEC784, 0xD2D90, 0x1C1B84, 0x9B5A4),
    "usa_update": (0xCEC734, 0xD2D90, 0x1C1B84, 0x9B5A4),
    "eur_base": (0xCEC0EC, 0xD2D60, 0x1C1B7C, 0x9B5AC),
    "usa_base": (0xCEC0C4, 0xD2D60, 0x1C1B7C, 0x9B5AC),
}
DATA_ADDRESS = 0xEC0000
# The update's .data and .bss.
ORIGINAL_DATA = (DATA_ADDRESS, 0x1C2, SECTIONS["eur_update"][2])
ORIGINAL_BSS = SECTIONS["eur_update"][3]
# System calls of the extension's bootstrap (core/game/executable/ext_bootstrap.s).
SVC_CLOSE_HANDLE, SVC_DUPLICATE_HANDLE = 0x23, 0x27
SVC_FLUSH_PROCESS_DATA_CACHE, SVC_CONTROL_PROCESS_MEMORY = 0x54, 0x70
BOOTSTRAP_SVCS = (SVC_CLOSE_HANDLE, SVC_DUPLICATE_HANDLE, SVC_FLUSH_PROCESS_DATA_CACHE, SVC_CONTROL_PROCESS_MEMORY)


class ExheaderError(ValueError):
    pass


def extract_exheader(path: Path) -> bytes:
    """The exheader (0x800 bytes) of a decrypted game file in any accepted format (containers.py)."""
    with open_container(path) as f:
        read_ncch(f, decrypted=False)
        exheader = f.read(SIZE)
    if len(exheader) != SIZE:
        raise ExtractError.of(TRUNCATED, "inside the exheader")
    return exheader


def allowed_svcs(exheader: bytes, at: int = KERNEL_CAPS[0]) -> set[int]:
    """The system calls the kernel capabilities at `at` allow."""
    svcs = set()
    for cap in struct.unpack_from(f"<{CAPS}I", exheader, at):
        if cap & SVC_PREFIX_MASK == SVC_PREFIX:
            index = cap >> 24 & 7
            svcs |= {24 * index + bit for bit in range(24) if cap >> bit & 1}
    return svcs


def _allow_svc(exheader: bytearray, at: int, svc: int) -> None:
    index, bit = divmod(svc, 24)
    caps = list(struct.unpack_from(f"<{CAPS}I", exheader, at))
    for n, cap in enumerate(caps):
        if cap & SVC_PREFIX_MASK == SVC_PREFIX and cap >> 24 & 7 == index:
            caps[n] = cap | 1 << bit
            break
    else:
        if EMPTY not in caps:
            raise ExheaderError(f"no free kernel capability for SVC {svc:#x}")
        caps[caps.index(EMPTY)] = SVC_PREFIX | index << 24 | 1 << bit
    struct.pack_into(f"<{CAPS}I", exheader, at, *caps)


def allow_fs_access(exheader: bytes, bits: int) -> bytes:
    """`exheader` whose filesystem access info asks for `bits` too, in the access info and in the access descriptor's
    copy (Luma3DS' signature patches accept the descriptor, as they accept the bootstrap's system calls)."""
    if len(exheader) != SIZE:
        raise ExheaderError(f"an exheader has {SIZE:#x} bytes, not {len(exheader):#x}")
    if bits >> 8 * FS_ACCESS_SIZE:
        raise ExheaderError(f"the filesystem access info has {8 * FS_ACCESS_SIZE} bits, not {bits:#x}")
    out = bytearray(exheader)
    for at in FS_ACCESS:
        have = int.from_bytes(out[at:at + FS_ACCESS_SIZE], "little")
        out[at:at + FS_ACCESS_SIZE] = (have | bits).to_bytes(FS_ACCESS_SIZE, "little")
    return bytes(out)


def exheader_version(exheader: bytes) -> str:
    """The MH4U version (a SECTIONS key) whose sections `exheader` gives; ExheaderError for any other (another game,
    or an exheader already extended)."""
    if len(exheader) != SIZE:
        raise ExheaderError(f"an exheader has {SIZE:#x} bytes, not {len(exheader):#x}")
    sizes = (*(struct.unpack_from("<I", exheader, at + 8)[0] for at in (TEXT_INFO, RODATA_INFO, DATA_INFO)),
             struct.unpack_from("<I", exheader, BSS_SIZE)[0])
    data = struct.unpack_from("<3I", exheader, DATA_INFO)
    for version, known in SECTIONS.items():
        if sizes == known and data == (DATA_ADDRESS, -(-known[2] // PAGE), known[2]):
            return version
    raise ExheaderError("not the exheader of an MH4U version the mod knows (its sections differ)")


def built_version(exheader: bytes) -> str | None:
    """The MH4U version (a SECTIONS key) a mod's exheader.bin was made from, extended or not: its .text and .rodata
    sizes, which no extension changes, are each version's own. None for any other exheader."""
    if len(exheader) != SIZE:
        return None
    sizes = tuple(struct.unpack_from("<I", exheader, at + 8)[0] for at in (TEXT_INFO, RODATA_INFO))
    return next((version for version, known in SECTIONS.items() if sizes == known[:2]), None)


def without_compression(exheader: bytes) -> bytes:
    """`exheader` (a known version's) for a code.bin written raw: its code is not compressed."""
    exheader_version(exheader)
    out = bytearray(exheader)
    out[FLAGS] &= ~COMPRESSED
    return bytes(out)


def extend_exheader(exheader: bytes, data_end: int, version: str | None = None) -> bytes:
    """A known version's exheader (`version`, checked, or whichever it is) for a code.bin whose .data runs, in the
    file, up to `data_end` (page aligned): no .bss, not compressed, the bootstrap's system calls allowed. Any other
    exheader is refused."""
    found = exheader_version(exheader)
    if version is not None and found != version:
        raise ExheaderError(f"the exheader is {found}'s, not {version}'s")
    _, _, data_size, bss = SECTIONS[found]
    address = DATA_ADDRESS
    if data_end % PAGE or data_end < address + data_size + bss:
        raise ExheaderError(f"the extended .data cannot end at {data_end:#x}")
    out = bytearray(without_compression(exheader))
    size = data_end - address
    struct.pack_into("<3I", out, DATA_INFO, address, size // PAGE, size)
    struct.pack_into("<I", out, BSS_SIZE, 0)
    for at in KERNEL_CAPS:
        for svc in BOOTSTRAP_SVCS:
            _allow_svc(out, at, svc)
    return bytes(out)
