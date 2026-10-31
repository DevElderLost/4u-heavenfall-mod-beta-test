"""MT Framework ARC archives.

Layout (version 17/19):
    0x00  magic "ARC\\0"
    0x04  u16 version
    0x06  u16 file count
    0x08  u32 unknown (0)
    0x0C  file table, 0x50 bytes per entry:
            name[64]   path without extension, backslash separated, NUL padded
            u32        type hash (e.g. 0x1BBFD18E for quest files)
            u32        compressed size
            u32        uncompressed size (low 24 bits) | flags (high 8 bits)
            u32        data offset
    data   zlib streams

Entry order matters to the game (quests are looked up by position), so the
writer keeps entries exactly in the order they were read. The data area starts
0x14 bytes after the file table, as in the archives produced by the legacy
tool, which are known to work in-game.
"""

import hashlib
import struct
import zlib
from collections import OrderedDict
from dataclasses import dataclass, field

MAGIC = b"ARC\x00"
SUPPORTED_VERSIONS = (17, 19)
HEADER_SIZE = 0x0C
ENTRY_SIZE = 0x50
NAME_SIZE = 64
DATA_GAP = 0x14
MIB_TYPE_HASH = 0x1BBFD18E
DEFAULT_FLAGS = 0x20


class ArcFormatError(ValueError):
    pass


class ArcEntry:
    """One file of an archive: `name` (e.g. "loc\\quest\\m10101"), `type_hash`, `data` (uncompressed) and `flags`.

    An entry read by `parse_arc` keeps the zlib stream the archive stored and decompresses it the first time `data` is
    read: a run edits a few entries of each archive it reads and writes the rest as they were. While `data` is not
    replaced, `write_arc` finds the entry's stream by the stored one (StreamCache.entry_stream), so an entry nobody
    changed is not decompressed, hashed or compressed again, and is written as ever: zlib's own stream of its data."""

    def __init__(self, name: str, type_hash: int, data: bytes, flags: int = DEFAULT_FLAGS):
        self.name = name
        self.type_hash = type_hash
        self.flags = flags
        self._data: bytes | None = data
        self._size = len(data)
        self._stored: bytes | None = None      # the archive's stream, while `data` is what it holds

    @classmethod
    def stored(cls, name: str, type_hash: int, stream: bytes, size: int, flags: int) -> "ArcEntry":
        """An entry as an archive holds it: its zlib `stream`, of `size` bytes when decompressed."""
        entry = cls(name, type_hash, b"", flags)
        entry._data, entry._size, entry._stored = None, size, stream
        return entry

    @property
    def data(self) -> bytes:
        if self._data is None:
            data = zlib.decompress(self._stored)
            if len(data) != self._size:
                raise ArcFormatError(f"entry {self.name} has an unexpected size after decompression")
            self._data = data
        return self._data

    @data.setter
    def data(self, value: bytes) -> None:
        self._data, self._size, self._stored = value, len(value), None

    @property
    def size(self) -> int:
        """len(data), without decompressing an entry that was not read."""
        return self._size

    def __eq__(self, other) -> bool:
        if other.__class__ is not self.__class__:
            return NotImplemented
        return (self.name, self.type_hash, self.data, self.flags) == (other.name, other.type_hash, other.data,
                                                                      other.flags)

    __hash__ = None

    def __repr__(self) -> str:
        return f"ArcEntry(name={self.name!r}, type_hash={self.type_hash!r}, data={self.data!r}, flags={self.flags!r})"

    @property
    def file_name(self) -> str:
        """Name as extracted on disk by the legacy tools, e.g. "m10101.1BBFD18E"."""
        return f"{self.name.split(chr(92))[-1]}.{self.type_hash:08X}"


@dataclass
class Arc:
    version: int = 19
    entries: list[ArcEntry] = field(default_factory=list)

    def quest_entries(self) -> list[ArcEntry]:
        return [e for e in self.entries if e.type_hash == MIB_TYPE_HASH]


def parse_arc(buf: bytes) -> Arc:
    if buf[:4] != MAGIC:
        raise ArcFormatError("not an ARC archive")
    version, count = struct.unpack_from("<HH", buf, 4)
    if version not in SUPPORTED_VERSIONS:
        raise ArcFormatError(f"unsupported ARC version {version}")
    arc = Arc(version=version)
    for i in range(count):
        base = HEADER_SIZE + i * ENTRY_SIZE
        raw_name = buf[base:base + NAME_SIZE].split(b"\x00", 1)[0]
        type_hash, comp_size, size_and_flags, offset = struct.unpack_from("<IIII", buf, base + NAME_SIZE)
        if offset + comp_size > len(buf):
            raise ArcFormatError(f"entry {i} points outside the archive")
        arc.entries.append(ArcEntry.stored(raw_name.decode("ascii"), type_hash, bytes(buf[offset:offset + comp_size]),
                                           size_and_flags & 0xFFFFFF, size_and_flags >> 24))
    return arc


class StreamCache:
    """zlib streams of the entries written lately, by their data's digest. Nine in ten entries a run writes were
    written before (the same textures in many archives, the same files run after run), and compressing them was half
    of a run. The oldest streams leave once the cache holds more than `budget` bytes of them."""

    STORED_KEYS = 100_000      # how many stored streams are remembered by the digest of their data (entry_stream)

    def __init__(self, budget: int):
        self.budget = budget
        self.size = 0
        self.hits = 0
        self.streams: OrderedDict[bytes, bytes] = OrderedDict()
        self.by_stored: OrderedDict[bytes, bytes] = OrderedDict()      # digest of a stored stream -> its data's digest

    def compress(self, data: bytes) -> bytes:
        return self._stream(data)[1]

    def _stream(self, data: bytes) -> tuple[bytes, bytes]:
        """(the data's digest, zlib's stream of the data)."""
        key = hashlib.blake2b(data, digest_size=16).digest()
        stream = self.streams.get(key)
        if stream is not None:
            self.streams.move_to_end(key)
            self.hits += 1
            return key, stream
        stream = zlib.compress(data)
        self.streams[key] = stream
        self.size += len(stream)
        while self.size > self.budget and self.streams:
            self.size -= len(self.streams.popitem(last=False)[1])
        return key, stream

    def entry_stream(self, entry: ArcEntry) -> bytes:
        """zlib's stream of the entry's data. An entry whose data is still what its archive stored is found by that
        stored stream (a third of the data's size to digest), without decompressing it once its stream is known."""
        stored = entry._stored
        if stored is None:
            return self.compress(entry.data)
        stored_key = hashlib.blake2b(stored, digest_size=16).digest()
        key = self.by_stored.get(stored_key)
        stream = self.streams.get(key) if key is not None else None
        if stream is not None:
            self.streams.move_to_end(key)
            self.hits += 1
            return stream
        key, stream = self._stream(entry.data)
        self.by_stored[stored_key] = key
        if len(self.by_stored) > self.STORED_KEYS:
            self.by_stored.popitem(last=False)
        return stream


STREAMS = StreamCache(budget=64 << 20)      # a whole run's distinct streams are about 37 MB


def write_arc(arc: Arc) -> bytes:
    table_end = HEADER_SIZE + ENTRY_SIZE * len(arc.entries)
    out = bytearray(table_end + DATA_GAP)
    out[0:HEADER_SIZE] = MAGIC + struct.pack("<HHI", arc.version, len(arc.entries), 0)
    for i, entry in enumerate(arc.entries):
        name = entry.name.encode("ascii")
        if len(name) >= NAME_SIZE:
            raise ArcFormatError(f"name too long: {entry.name}")
        compressed = STREAMS.entry_stream(entry)
        offset = len(out)
        out += compressed
        base = HEADER_SIZE + i * ENTRY_SIZE
        out[base:base + NAME_SIZE] = name.ljust(NAME_SIZE, b"\x00")
        struct.pack_into("<IIII", out, base + NAME_SIZE, entry.type_hash, len(compressed),
                         (entry.flags << 24) | entry.size, offset)
    return bytes(out)
