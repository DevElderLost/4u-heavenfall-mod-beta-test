"""The NCCH (CXI) of the installed title: ExeFS image, retitled exheader, the container and a reader of the pieces
the player's game gives (formats: 3dbrew NCCH, ExeFS, NCCH/Extended_Header).

Not encrypted (NoCrypto flag) and not signed (the signature is zeros; Luma3DS' signature patches accept it). The
RomFS comes from another module and is any object with `size`, `hash_region_size`, `header_region()` and
`chunks(progress)` (see `RomFsImage`).
"""

import hashlib
import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from core.game.executable.containers import MEDIA_UNIT, NO_EXECUTABLE, ExtractError, open_container
from core.game.executable.extract import read_exactly, read_ncch

EXEFS_HEADER = 0x200
EXEFS_ENTRIES = 10
EXHEADER_SIZE = 0x800
EXHEADER_HASHED = 0x400            # the part of the exheader the NCCH header hashes
NCCH_HEADER = 0x200
# Exheader fields (system control info at 0, ARM11 local capabilities at 0x200, the access descriptor at 0x600).
DEPENDENCIES, DEPENDENCIES_SIZE = 0x40, 0x180
SAVE_DATA_SIZE, JUMP_ID = 0x1C0, 0x1C8
LOCAL_PROGRAM_ID, CORE_VERSION = 0x200, 0x208
ACCESS_DESC_PROGRAM_ID = 0x600
ACCESS_DESC_SIGNED = (0x400, 0x600)  # the access descriptor's signature and the NCCH header's public key
SCI_FLAGS, REMASTER_VERSION = 0xD, 0xE
FLAG_SD_APPLICATION = 0x02
PRODUCT_KIND = 0x154               # the letter after "CTR-" in the product code: P a game, U an update
# An update title as the system takes it: what the official update (0004000E00126100) has and its base lacks. With
# remaster version 0 and title version 0 the console launched the base without it.
UPDATE_HIGH = "0004000e"
UPDATE_REMASTER_VERSION = 1
# An add-on content title (the game data): a CFA, data only, as makerom makes one
# (form "SimpleContent", content type Application) and as the system keeps DLC: product kind M, the RomFS at 0x1000.
ADDON_HIGH = "0004008c"
CFA_ROMFS_ALIGNMENT = 0x1000
CONTENT_TYPE_DATA = 0x01           # the NCCH header's 0x18D: data, no executable; application content
PRODUCT_KIND_ADDON = "M"
# NCCH header fields.
SIGNATURE, MAGIC = 0x000, 0x100
FLAG_NO_CRYPTO, FLAG_FIXED_KEY, FLAG_SEED = 0x04, 0x01, 0x20
ROMFS_ALIGNMENT_CAP = 0x10000
GAME_FILES = (".code", "icon", "banner", "logo")   # the ExeFS files the title takes from the game


class RomFsImage(Protocol):
    """What the NCCH builder needs of the RomFS (core/install/title/romfs_writer.py)."""

    size: int                  # bytes of the whole image
    hash_region_size: int      # bytes (a multiple of 0x200) the NCCH's RomFS superblock hash covers

    def header_region(self) -> bytes: ...

    def chunks(self, progress=None) -> Iterator[bytes]: ...


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def title_id_bytes(title_id: str) -> bytes:
    """The 8 little-endian bytes of a 16-digit hexadecimal title id."""
    if len(title_id) != 16:
        raise ValueError(f"a title id has 16 hexadecimal digits, not {title_id!r}")
    return int(title_id, 16).to_bytes(8, "little")


# ---- ExeFS -------------------------------------------------------------------------------------------------------

def exefs(files: list[tuple[str, bytes]]) -> bytes:
    """The ExeFS image of `files` (name, contents): a 0x200 header of file entries and the files' SHA-256 in reverse
    order, then each file at a multiple of 0x200."""
    if not 0 < len(files) <= EXEFS_ENTRIES:
        raise ValueError(f"an ExeFS holds 1 to {EXEFS_ENTRIES} files, not {len(files)}")
    header = bytearray(EXEFS_HEADER)
    body = bytearray()
    for n, (name, data) in enumerate(files):
        raw = name.encode("ascii")
        if not 0 < len(raw) <= 8:
            raise ValueError(f"an ExeFS file name has 1 to 8 characters, not {name!r}")
        struct.pack_into("<8sII", header, n * 16, raw, len(body), len(data))
        header[0xC0 + (EXEFS_ENTRIES - 1 - n) * 0x20:0xC0 + (EXEFS_ENTRIES - n) * 0x20] = sha256(data)
        body += data + bytes(align(len(data), MEDIA_UNIT) - len(data))
    return bytes(header) + bytes(body)


# ---- Exheader ----------------------------------------------------------------------------------------------------

def retitle_exheader(exheader: bytes, title_id: str, program_id: str | None = None) -> bytes:
    """`exheader` with `title_id` as the system info's jump id and `program_id` (default `title_id`) as the ARM11
    local capabilities' program id and the access descriptor's copy of it. An update title passes its base's
    program id, as the official update's exheader does (0004000E00126100 runs as 0004000000126100). The save data
    size and the extdata id stay (event quests are shared with the game). An update title (`is_update`) also gets
    the official update's remaster version and SD application flag. First `common_exheader`: the copy of the game
    does not matter."""
    if len(exheader) != EXHEADER_SIZE:
        raise ValueError(f"an exheader has {EXHEADER_SIZE:#x} bytes, not {len(exheader):#x}")
    out = bytearray(common_exheader(exheader))
    out[JUMP_ID:JUMP_ID + 8] = title_id_bytes(title_id)
    program = title_id_bytes(program_id or title_id)
    for at in (LOCAL_PROGRAM_ID, ACCESS_DESC_PROGRAM_ID):
        out[at:at + 8] = program
    if is_update(title_id):
        struct.pack_into("<H", out, REMASTER_VERSION, UPDATE_REMASTER_VERSION)
        out[SCI_FLAGS] |= FLAG_SD_APPLICATION
    return bytes(out)


def common_exheader(exheader: bytes) -> bytes:
    """`exheader` without what the cartridge and the eShop copies of one game differ in, so either gives the same title
    and the same patch-set source: the SD application flag (set only in the eShop copy; cleared, as the cartridge has
    it) and the access descriptor's signature and NCCH header key (each copy has its own; zeros, as the header's
    signature, which Luma3DS' signature patches accept)."""
    out = bytearray(exheader)
    out[SCI_FLAGS] &= ~FLAG_SD_APPLICATION & 0xFF
    start, end = ACCESS_DESC_SIGNED
    out[start:end] = bytes(end - start)
    return bytes(out)


def is_update(title_id: str) -> bool:
    return title_id.lower().startswith(UPDATE_HIGH)


def is_addon(title_id: str) -> bool:
    return title_id.lower().startswith(ADDON_HIGH)


def save_data_size(exheader: bytes) -> int:
    return struct.unpack_from("<Q", exheader, SAVE_DATA_SIZE)[0]


# ---- The container -----------------------------------------------------------------------------------------------

def _mu(size: int) -> int:
    return align(size, MEDIA_UNIT) // MEDIA_UNIT


class Ncch:
    """A CXI laid out as header, exheader, plain and logo regions (in the template's order), ExeFS and RomFS, all at
    media units. Nothing is read from the RomFS until `chunks`."""

    def __init__(self, template: bytes, title_id: str, exheader: bytes, exefs_image: bytes, romfs: RomFsImage,
                 plain: bytes = b"", logo: bytes = b""):
        if len(template) != NCCH_HEADER or template[MAGIC:MAGIC + 4] != b"NCCH":
            raise ValueError("the template is not an NCCH header")
        if len(exheader) != EXHEADER_SIZE:
            raise ValueError(f"an exheader has {EXHEADER_SIZE:#x} bytes, not {len(exheader):#x}")
        if romfs.hash_region_size % MEDIA_UNIT or not 0 < romfs.hash_region_size <= romfs.size:
            raise ValueError("the RomFS hash region must be a multiple of 0x200 inside the image")
        self.title_id = title_id
        self.exheader = exheader
        self.exefs = exefs_image
        self.romfs = romfs
        self.plain, self.logo = plain, logo
        template_order = sorted(
            (struct.unpack_from("<I", template, at)[0], kind, data)
            for at, kind, data in ((0x190, "plain", plain), (0x198, "logo", logo)) if data)
        self._regions = [(kind, data) for _, kind, data in template_order]
        # Where each part starts, in bytes from the NCCH's start.
        at = NCCH_HEADER + EXHEADER_SIZE
        self._at: dict[str, int] = {}
        for kind, data in self._regions:
            self._at[kind] = at
            at += align(len(data), MEDIA_UNIT)
        self._at["exefs"] = at
        at += align(len(exefs_image), MEDIA_UNIT)
        template_romfs = struct.unpack_from("<I", template, 0x1B0)[0] * MEDIA_UNIT
        step = min(template_romfs & -template_romfs, ROMFS_ALIGNMENT_CAP) if template_romfs else MEDIA_UNIT
        self._at["romfs"] = align(at, max(step, MEDIA_UNIT))
        self.size = align(self._at["romfs"] + romfs.size, MEDIA_UNIT)
        self._header = self._build_header(template)

    def _build_header(self, template: bytes) -> bytes:
        h = bytearray(template)
        h[SIGNATURE:SIGNATURE + 0x100] = bytes(0x100)
        new = title_id_bytes(self.title_id)
        h[0x104:0x108] = struct.pack("<I", self.size // MEDIA_UNIT)
        h[0x108:0x110] = new                       # partition id
        h[0x114:0x118] = bytes(4)                  # content lock seed hash: no seed crypto
        h[0x118:0x120] = new                       # program id
        if is_update(self.title_id):
            h[PRODUCT_KIND] = ord("U")
        h[0x130:0x150] = sha256(self.logo) if self.logo else bytes(0x20)
        h[0x160:0x180] = sha256(self.exheader[:EXHEADER_HASHED])
        h[0x180:0x184] = struct.pack("<I", EXHEADER_HASHED)
        h[0x18F] = (h[0x18F] | FLAG_NO_CRYPTO) & ~(FLAG_FIXED_KEY | FLAG_SEED) & 0xFF
        for field_at, kind, data in ((0x190, "plain", self.plain), (0x198, "logo", self.logo)):
            h[field_at:field_at + 8] = (struct.pack("<II", self._at[kind] // MEDIA_UNIT, _mu(len(data)))
                                        if data else bytes(8))
        h[0x1A0:0x1A8] = struct.pack("<II", self._at["exefs"] // MEDIA_UNIT, _mu(len(self.exefs)))
        h[0x1A8:0x1AC] = struct.pack("<I", 1)      # the ExeFS hash region: its header
        h[0x1B0:0x1B8] = struct.pack("<II", self._at["romfs"] // MEDIA_UNIT, _mu(self.romfs.size))
        h[0x1B8:0x1BC] = struct.pack("<I", self.romfs.hash_region_size // MEDIA_UNIT)
        h[0x1C0:0x1E0] = sha256(self.exefs[:EXEFS_HEADER])
        h[0x1E0:0x200] = sha256(self.romfs.header_region()[:self.romfs.hash_region_size])
        return bytes(h)

    def header(self) -> bytes:
        return self._header

    def chunks(self, progress=None) -> Iterator[bytes]:
        """The whole NCCH in order; the RomFS is streamed."""
        yield self._header
        yield self.exheader
        at = NCCH_HEADER + EXHEADER_SIZE
        for kind, data in self._regions:
            yield from self._pad(at, self._at[kind])
            yield data
            at = self._at[kind] + len(data)
        yield from self._pad(at, self._at["exefs"])
        yield self.exefs
        yield from self._pad(self._at["exefs"] + len(self.exefs), self._at["romfs"])
        sent = 0
        for chunk in self.romfs.chunks(progress):
            sent += len(chunk)
            yield chunk
        if sent != self.romfs.size:
            raise ValueError(f"the RomFS gave {sent} bytes, not the {self.romfs.size} it announced")
        yield from self._pad(self._at["romfs"] + sent, self.size)

    @staticmethod
    def _pad(at: int, to: int) -> Iterator[bytes]:
        if to > at:
            yield bytes(to - at)


class Cfa:
    """A CFA (an add-on content title's content): the header and the RomFS at 0x1000, nothing else (no exheader, no
    ExeFS, no regions). The header is made from the game's only for its maker code, NCCH version, product code (kind M)
    and platform, so either copy of a game (cartridge, eShop) gives the same bytes. `exheader` is None for the CIA
    writer: no save data, no meta section."""

    exheader = None

    def __init__(self, template: bytes, title_id: str, romfs: RomFsImage):
        if len(template) != NCCH_HEADER or template[MAGIC:MAGIC + 4] != b"NCCH":
            raise ValueError("the template is not an NCCH header")
        if romfs.hash_region_size % MEDIA_UNIT or not 0 < romfs.hash_region_size <= romfs.size:
            raise ValueError("the RomFS hash region must be a multiple of 0x200 inside the image")
        self.title_id = title_id
        self.romfs = romfs
        self._romfs_at = align(NCCH_HEADER, CFA_ROMFS_ALIGNMENT)
        self.size = align(self._romfs_at + romfs.size, MEDIA_UNIT)
        h = bytearray(NCCH_HEADER)
        h[MAGIC:MAGIC + 4] = b"NCCH"
        h[0x104:0x108] = struct.pack("<I", self.size // MEDIA_UNIT)
        h[0x108:0x110] = h[0x118:0x120] = title_id_bytes(title_id)     # partition id, program id
        h[0x110:0x114] = template[0x110:0x114]                            # maker code, NCCH version
        h[0x150:0x160] = template[0x150:0x160]                            # product code
        h[PRODUCT_KIND] = ord(PRODUCT_KIND_ADDON)
        h[0x18C] = template[0x18C]                                        # platform
        h[0x18D] = CONTENT_TYPE_DATA
        h[0x18E] = template[0x18E]                                        # content unit size
        h[0x18F] = FLAG_NO_CRYPTO
        h[0x1B0:0x1BC] = struct.pack("<III", self._romfs_at // MEDIA_UNIT, _mu(romfs.size),
                                     romfs.hash_region_size // MEDIA_UNIT)
        h[0x1E0:0x200] = sha256(romfs.header_region()[:romfs.hash_region_size])
        self._header = bytes(h)

    def header(self) -> bytes:
        return self._header

    def chunks(self, progress=None) -> Iterator[bytes]:
        yield self._header
        yield bytes(self._romfs_at - NCCH_HEADER)
        sent = 0
        for chunk in self.romfs.chunks(progress):
            sent += len(chunk)
            yield chunk
        if sent != self.romfs.size:
            raise ValueError(f"the RomFS gave {sent} bytes, not the {self.romfs.size} it announced")
        if self.size > self._romfs_at + sent:
            yield bytes(self.size - self._romfs_at - sent)


# ---- The player's game -------------------------------------------------------------------------------------------

@dataclass
class GameParts:
    """The pieces of a game file's NCCH a title is built from."""
    header: bytes                       # the NCCH header (0x200, decrypted)
    exheader: bytes                     # 0x800
    exefs_files: dict[str, bytes] = field(default_factory=dict)   # GAME_FILES the game has
    plain: bytes = b""
    logo: bytes = b""                   # the logo region


def read_game_parts(path: Path) -> GameParts:
    """The header, exheader, ExeFS files (GAME_FILES) and plain and logo regions of a decrypted game file in any
    accepted format (containers.py). The RomFS is not read."""
    with open_container(path) as f:
        base, header = read_ncch(f)
        f.seek(base + NCCH_HEADER)
        exheader = read_exactly(f, EXHEADER_SIZE, "the exheader")

        def region(at: int) -> bytes:
            offset, size = struct.unpack_from("<II", header, at)
            if not size:
                return b""
            f.seek(base + offset * MEDIA_UNIT)
            return read_exactly(f, size * MEDIA_UNIT, "a region")

        plain, logo = region(0x190), region(0x198)
        offset, size = struct.unpack_from("<II", header, 0x1A0)
        if not size:
            raise ExtractError.of(NO_EXECUTABLE)
        start = base + offset * MEDIA_UNIT
        f.seek(start)
        table = read_exactly(f, EXEFS_HEADER, "the ExeFS header")
        files = {}
        for n in range(EXEFS_ENTRIES):
            name, at, length = struct.unpack_from("<8sII", table, n * 16)
            name = name.rstrip(b"\0").decode("ascii", "replace")
            if name in GAME_FILES:
                f.seek(start + EXEFS_HEADER + at)
                files[name] = read_exactly(f, length, f"the ExeFS file {name}")
    return GameParts(header, exheader, files, plain, logo)
