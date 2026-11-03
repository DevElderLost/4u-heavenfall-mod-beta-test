"""Open any decrypted 3DS game container as one seekable file whose offset 0 is the NCSD or NCCH.

    .3ds / .cci     cartridge image (NCSD), first partition      returned as it is
    .cxi / .app     one NCCH, e.g. an installed update's 00000000.app   returned as it is
    .cia            decrypted CIA: header, certificate chain, ticket, TMD and contents, each section aligned to
                    64 bytes; content 0 is the NCCH (game or update)     a window onto content 0
    .zcci .zcxi .zcia   Azahar's Z3DS compression of the three above (src/common/zstd_compression.cpp and
                    file_derived.* in azahar-emu/azahar, PR #1208): a 0x20-byte header, a metadata block and seekable
                    zstd (facebook/zstd contrib/seekable_format)     decompressed one frame at a time

The format is told by the file's content, never by its extension. Every reader of the game files (`ncch_identity`,
`extract_code`, `RomFS`, `extract_exheader`) opens its file with `open_container`, so a new format needs no code of its
own anywhere else. Refusals are `ExtractError`s with a `kind`, which the GUI translates (gui/strings.py).
"""

import bisect
import io
import os
import struct
import threading
from collections import OrderedDict
from pathlib import Path

try:
    import zstandard
except ImportError:    # a build without the package (the Android app may lack its wheel): only .zcci/.zcia need it
    zstandard = None

# Every extension a player's game file may have: the file pickers and tools/build/setup_local.py list them.
EXTENSIONS = (".3ds", ".cci", ".cxi", ".app", ".cia", ".zcci", ".zcxi", ".zcia")

ENCRYPTED, NOT_A_GAME_FILE, TRUNCATED = "encrypted", "not_a_game_file", "truncated"
UNSUPPORTED_COMPRESSION, DAMAGED = "unsupported_compression", "damaged"
NO_EXECUTABLE, NO_ROMFS, INVALID_ROMFS = "no_executable", "no_romfs", "invalid_romfs"
OTHER = "other"   # a refusal with its own text (not in MESSAGES)

# The English text of each kind; gui/strings.py has the same kinds in the GUI's languages.
MESSAGES = {
    ENCRYPTED: "the file is encrypted; decrypt it first (e.g. with GodMode9)",
    NOT_A_GAME_FILE: "not a decrypted 3DS game file (" + ", ".join(EXTENSIONS[:-1]) + " or " + EXTENSIONS[-1] + ")",
    TRUNCATED: "the file is incomplete (the download or copy was interrupted)",
    UNSUPPORTED_COMPRESSION: "this compressed file uses a format version that this program cannot read",
    DAMAGED: "the file is damaged (its compressed data cannot be read)",
    NO_EXECUTABLE: "this file has no executable (ExeFS)",
    NO_ROMFS: "this file has no RomFS",
    INVALID_ROMFS: "invalid RomFS (no IVFC header)",
}


class ExtractError(ValueError):
    """A game file this program cannot use. `kind` says why (MESSAGES; OTHER for a free text), `detail` is for a
    developer (what exactly was wrong), `title_id` the title the file names when it could be read (an encrypted CIA's
    TMD). `str(error)` is the standard English text of the kind, which the GUI replaces by its translation."""

    def __init__(self, message: str, kind: str = OTHER, title_id: str | None = None, detail: str = ""):
        super().__init__(message)
        self.kind = kind
        self.title_id = title_id
        self.detail = detail

    @classmethod
    def of(cls, kind: str, detail: str = "", title_id: str | None = None) -> "ExtractError":
        """The refusal of `kind`, with its standard text."""
        return cls(MESSAGES[kind], kind, title_id, detail)


MEDIA_UNIT = 0x200
NCCH_MAGICS = (b"NCSD", b"NCCH")
HEAD = 0x200                     # what is read to tell the formats apart

# ---- CIA ---------------------------------------------------------------------------------------------------------

CIA_HEADER_SIZE = 0x2020
CIA_ALIGNMENT = 64
# Bytes a TMD spends on its signature type, the signature and the padding to 0x40, by signature type (big endian).
TMD_SIGNATURE_SECTION = {0x010000: 0x240, 0x010001: 0x140, 0x010002: 0x80,
                         0x010003: 0x240, 0x010004: 0x140, 0x010005: 0x80}
TMD_HEADER = 0xC4                # after the signature; its content count and title id
TMD_INFO_RECORDS = 0x900         # 64 content info records
TMD_CHUNK_RECORD = 0x30
TMD_MAX = 0x100000
CONTENT_ENCRYPTED = 0x0001       # content type flag


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


class _View(io.RawIOBase):
    """A read-only seekable file over `size` bytes that a subclass supplies by position."""

    def __init__(self, size: int):
        super().__init__()
        self.size = size
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence not in (io.SEEK_SET, io.SEEK_CUR, io.SEEK_END):
            raise ValueError(f"invalid whence ({whence})")
        position = (0, self._pos, self.size)[whence] + offset
        if position < 0:
            raise ValueError("negative seek position")
        self._pos = position
        return position

    def read(self, size: int | None = -1) -> bytes:
        if self.closed:
            raise ValueError("read of a closed file")
        left = max(self.size - self._pos, 0)
        if size is None or size < 0 or size > left:
            size = left
        if not size:
            return b""
        data = self._read_at(self._pos, size)
        self._pos += len(data)
        return data

    def readinto(self, buffer) -> int:
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def _read_at(self, position: int, size: int) -> bytes:
        raise NotImplementedError


class _Window(_View):
    """Bytes [start, start + size) of `parent`, which it closes with itself."""

    def __init__(self, parent, start: int, size: int):
        super().__init__(size)
        self._parent = parent
        self._start = start

    def _read_at(self, position: int, size: int) -> bytes:
        self._parent.seek(self._start + position)
        return self._parent.read(size)

    def close(self) -> None:
        if not self.closed:
            self._parent.close()
        super().close()


def _looks_like_cia(head: bytes) -> bool:
    return len(head) >= 8 and struct.unpack_from("<IH", head, 0) == (CIA_HEADER_SIZE, 0)


def _cia_content(f) -> _Window:
    """A window onto content 0 of the CIA `f`, which must be plain (not encrypted)."""
    f.seek(0)
    head = f.read(0x20)
    if len(head) < 0x20:
        raise ExtractError.of(NOT_A_GAME_FILE, "a CIA header cut short")
    header_size, _, _, cert_size, ticket_size, tmd_size, _, _ = struct.unpack("<IHHIIIIQ", head)
    f.seek(0, io.SEEK_END)
    total = f.tell()
    tmd_at = _align(header_size, CIA_ALIGNMENT) + _align(cert_size, CIA_ALIGNMENT) + _align(ticket_size, CIA_ALIGNMENT)
    content_at = tmd_at + _align(tmd_size, CIA_ALIGNMENT)
    if not TMD_CHUNK_RECORD < tmd_size <= TMD_MAX:
        raise ExtractError.of(NOT_A_GAME_FILE, "a CIA without a TMD")
    if total < tmd_at + tmd_size:
        raise ExtractError.of(TRUNCATED, "inside the CIA's TMD")
    f.seek(tmd_at)
    tmd = f.read(tmd_size)
    section = TMD_SIGNATURE_SECTION.get(struct.unpack_from(">I", tmd, 0)[0])
    record_at = None if section is None else section + TMD_HEADER + TMD_INFO_RECORDS
    if record_at is None or len(tmd) < record_at + TMD_CHUNK_RECORD:
        raise ExtractError.of(NOT_A_GAME_FILE, "a CIA with an unreadable TMD")
    if not struct.unpack_from(">H", tmd, section + 0x9E)[0]:
        raise ExtractError.of(NOT_A_GAME_FILE, "a CIA with no content")
    title_id = tmd[section + 0x4C:section + 0x54].hex()
    _, _, content_type, content_size = struct.unpack_from(">IHHQ", tmd, record_at)
    if content_type & CONTENT_ENCRYPTED:
        raise ExtractError.of(ENCRYPTED, "the CIA's content is encrypted", title_id)
    if content_size < HEAD:
        raise ExtractError.of(NOT_A_GAME_FILE, "a CIA whose first content is not an NCCH")
    if total < content_at + content_size:
        raise ExtractError.of(TRUNCATED, "inside the CIA's content")
    content = _Window(f, content_at, content_size)
    if content.read(HEAD)[0x100:0x104] != b"NCCH":
        raise ExtractError.of(NOT_A_GAME_FILE, "a CIA whose first content is not an NCCH")
    content.seek(0)
    return content


# ---- Z3DS --------------------------------------------------------------------------------------------------------

Z3DS_MAGIC = b"Z3DS"
Z3DS_HEADER = struct.Struct("<4s4sBBHIQQ")     # magic, underlying magic, version, reserved, header size,
Z3DS_VERSION = 1                                # metadata size, compressed size, uncompressed size
SKIPPABLE_MAGIC, SEEKABLE_MAGIC = 0x184D2A5E, 0x8F92EAB1
SEEK_FOOTER = struct.Struct("<IBI")            # frames, descriptor, seekable magic
CHECKSUM_FLAG, RESERVED_BITS = 0x80, 0x7C
# Decompressed frames kept for the next read (a RomFS reads many small files of the same frame; a CIA's frames hold
# 32 MB), and parsed seek tables.
FRAME_CACHE_BYTES = 128 * 1024 * 1024
INDEX_CACHE = 4

_lock = threading.Lock()
_frames: OrderedDict[tuple, bytes] = OrderedDict()
_frames_size = 0
_indexes: OrderedDict[tuple, "_Index"] = OrderedDict()


def clear_caches() -> None:
    """Forget the decompressed frames and the seek tables kept between reads."""
    global _frames_size
    with _lock:
        _frames.clear()
        _indexes.clear()
        _frames_size = 0


class _Index:
    """Where each frame of a Z3DS file is, compressed (in the file) and decompressed (in the plain container)."""

    def __init__(self, key: tuple, compressed_at: list[int], compressed_size: list[int], plain_at: list[int]):
        self.key = key
        self.compressed_at = compressed_at
        self.compressed_size = compressed_size
        self.plain_at = plain_at          # one more than the frames: the last is the plain size

    @property
    def size(self) -> int:
        return self.plain_at[-1]


def _read_index(raw, key: tuple, file_size: int) -> _Index:
    raw.seek(0)
    head = raw.read(Z3DS_HEADER.size)
    if len(head) < Z3DS_HEADER.size:
        raise ExtractError.of(TRUNCATED, "inside the Z3DS header")
    _, _, version, _, header_size, metadata_size, compressed_size, _ = Z3DS_HEADER.unpack(head)
    if version != Z3DS_VERSION or header_size < Z3DS_HEADER.size:
        raise ExtractError.of(UNSUPPORTED_COMPRESSION, f"Z3DS version {version}")
    start = header_size + metadata_size
    end = start + compressed_size
    # Azahar writes the header last: a compression that was stopped leaves the sizes at zero.
    if not compressed_size or file_size < end:
        raise ExtractError.of(TRUNCATED, "the compressed data ends early")
    if compressed_size < SEEK_FOOTER.size + 8:
        raise ExtractError.of(UNSUPPORTED_COMPRESSION, "no seek table")
    raw.seek(end - SEEK_FOOTER.size)
    frames, descriptor, magic = SEEK_FOOTER.unpack(raw.read(SEEK_FOOTER.size))
    entry = 12 if descriptor & CHECKSUM_FLAG else 8
    table_at = end - SEEK_FOOTER.size - frames * entry
    if magic != SEEKABLE_MAGIC or descriptor & RESERVED_BITS or table_at - 8 < start:
        raise ExtractError.of(UNSUPPORTED_COMPRESSION, "no seek table")
    raw.seek(table_at - 8)
    skippable, skippable_size = struct.unpack("<II", raw.read(8))
    if skippable != SKIPPABLE_MAGIC or skippable_size != frames * entry + SEEK_FOOTER.size:
        raise ExtractError.of(UNSUPPORTED_COMPRESSION, "the seek table is not a skippable frame")
    table = raw.read(frames * entry)
    compressed_at, compressed_size_of, plain_at = [], [], [0]
    position = start
    for offset in range(0, len(table), entry):
        size, plain = struct.unpack_from("<II", table, offset)
        compressed_at.append(position)
        compressed_size_of.append(size)
        position += size
        plain_at.append(plain_at[-1] + plain)
    if position != table_at - 8:
        raise ExtractError.of(UNSUPPORTED_COMPRESSION, "the frames do not fill the compressed data")
    return _Index(key, compressed_at, compressed_size_of, plain_at)


def _decompress_frame(data: bytes, size: int) -> bytes:
    """One frame of `size` decompressed bytes. The frame may not state its size (Azahar's writer streams them), so the
    size from the seek table bounds the output; `decompressobj` takes a second for a 32 MB frame, this takes 10 ms."""
    if not size:
        return b""
    try:
        plain = zstandard.ZstdDecompressor().decompress(data, max_output_size=size)
    except zstandard.ZstdError as error:
        raise ExtractError.of(DAMAGED, str(error)) from error
    if len(plain) != size:
        raise ExtractError.of(DAMAGED, "a frame is shorter than the seek table says")
    return plain


class _ZstdFile(_View):
    """The plain container inside a Z3DS file, decompressed a frame at a time."""

    def __init__(self, raw, index: _Index):
        super().__init__(index.size)
        self._raw = raw
        self._index = index

    def _frame(self, number: int) -> bytes:
        global _frames_size
        index = self._index
        key = (index.key, number)
        with _lock:
            plain = _frames.get(key)
            if plain is not None:
                _frames.move_to_end(key)
                return plain
        self._raw.seek(index.compressed_at[number])
        data = self._raw.read(index.compressed_size[number])
        if len(data) != index.compressed_size[number]:
            raise ExtractError.of(TRUNCATED, "inside a compressed frame")
        plain = _decompress_frame(data, index.plain_at[number + 1] - index.plain_at[number])
        if len(plain) <= FRAME_CACHE_BYTES:
            with _lock:
                if key not in _frames:
                    _frames[key] = plain
                    _frames_size += len(plain)
                while _frames_size > FRAME_CACHE_BYTES:
                    _, dropped = _frames.popitem(last=False)
                    _frames_size -= len(dropped)
        return plain

    def _read_at(self, position: int, size: int) -> bytes:
        plain_at = self._index.plain_at
        pieces = []
        while size > 0:
            number = bisect.bisect_right(plain_at, position) - 1
            frame = self._frame(number)
            piece = frame[position - plain_at[number]:position - plain_at[number] + size]
            pieces.append(piece)
            position += len(piece)
            size -= len(piece)
        return b"".join(pieces)

    def close(self) -> None:
        if not self.closed:
            self._raw.close()
        super().close()


def _open_z3ds(raw, path: Path) -> _ZstdFile:
    if zstandard is None:
        raise ExtractError("compressed game files (.zcci, .zcxi, .zcia) need the zstandard package, which this build "
                           "does not include; use the .3ds or .cia file instead")
    status = os.fstat(raw.fileno())
    key = (os.path.abspath(path), status.st_size, status.st_mtime_ns)
    with _lock:
        index = _indexes.get(key)
    if index is None:
        index = _read_index(raw, key, status.st_size)
        with _lock:
            _indexes[key] = index
            while len(_indexes) > INDEX_CACHE:
                _indexes.popitem(last=False)
    return _ZstdFile(raw, index)


# ---- the entry points --------------------------------------------------------------------------------------------

def looks_like_container(path: Path) -> bool:
    """True for a file in one of the accepted formats (even one that will be refused, e.g. encrypted), as opposed to a
    loose game file such as a code.bin or a quest01.arc."""
    with Path(path).open("rb") as f:
        head = f.read(HEAD)
    return head[:4] == Z3DS_MAGIC or head[0x100:0x104] in NCCH_MAGICS or _looks_like_cia(head)


def open_container(path: Path):
    """The game file as a seekable binary file whose offset 0 is the NCSD or NCCH, whatever the format (see the module
    text). Close it, or use `with`. Raises ExtractError for a file that is none of the formats, is encrypted, cut
    short or damaged; OSError when it cannot be opened."""
    path = Path(path)
    raw = path.open("rb")
    try:
        f = raw
        head = raw.read(HEAD)
        if head[:4] == Z3DS_MAGIC:
            f = _open_z3ds(raw, path)
            head = f.read(HEAD)
        if head[0x100:0x104] in NCCH_MAGICS:
            f.seek(0)
            return f
        if _looks_like_cia(head):
            return _cia_content(f)
        raise ExtractError.of(NOT_A_GAME_FILE)
    except BaseException:
        raw.close()
        raise
