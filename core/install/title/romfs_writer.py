"""Streaming RomFS image builder: level-3 tables and file data, then the IVFC hash tree (SHA-256 of every 0x1000
block: level 3 -> level 2 -> level 1 -> master hash). Format: 3dbrew RomFS, checked against the game's own RomFS
(tests/install/title/test_romfs_writer.py). File data is never held in memory: `prepare` reads every file once to hash
it, `chunks` reads it again. Only the level-2 hashes (32 bytes per 4 KB of data) stay in memory.

Image order: IVFC header (0x5C) and master hash, zero padding to 0x1000, level 3, level 1, level 2, each padded to
0x1000. The NCCH's RomFS superblock hash covers the first `hash_region_size` bytes.
"""

import hashlib
import io
import struct
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from core.game.executable.containers import open_container
from core.game.executable.romfs import RomFS

NONE = 0xFFFFFFFF
BLOCK_LOG2 = 12
BLOCK = 1 << BLOCK_LOG2
HASH_SIZE = 32
IVFC_HEADER = 0x5C
MASTER_HASH_OFFSET = 0x60  # the header, aligned to 4
HASH_REGION_ALIGN = 0x200
FILE_ALIGN = 0x10
HEADER_SIZE = 0x28
READ_CHUNK = 1 << 20
DATA_OFFSET_FIELD = 0x24         # the level-3 header's file data offset
_PRIME_FACTORS = (2, 3, 5, 7, 11, 13, 17)


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def bucket_count(entries: int) -> int:
    """Size of a hash table for that many entries (Nintendo's rule: 3 below 3, odd below 19, else the next number
    with no small prime factor)."""
    if entries < 3:
        return 3
    if entries < 19:
        return entries | 1
    n = entries
    while any(n % p == 0 for p in _PRIME_FACTORS):
        n += 1
    return n


def name_hash(parent: int, name: str, buckets: int) -> int:
    """The bucket of an entry: its parent directory's metadata offset and its UTF-16 name."""
    h = parent ^ 123456789
    for (c,) in struct.iter_unpack("<H", name.encode("utf-16-le")):
        h = ((h >> 5) | (h << 27)) & 0xFFFFFFFF
        h ^= c
    return h % buckets


@dataclass(frozen=True)
class Source:
    """Bytes [offset, offset+size) of the binary file `open()` returns (a new one each call)."""
    open: Callable[[], BinaryIO]
    offset: int
    size: int

    @classmethod
    def from_bytes(cls, data: bytes) -> "Source":
        data = bytes(data)
        return cls(lambda: io.BytesIO(data), 0, len(data))

    @classmethod
    def from_file(cls, path: Path) -> "Source":
        path = Path(path)
        return cls(lambda: path.open("rb"), 0, path.stat().st_size)


def game_sources(rom: Path) -> dict[str, Source]:
    """Every file of a decrypted game's RomFS (any format open_container accepts) as a Source."""
    rom = Path(rom)

    def opener() -> BinaryIO:
        return open_container(rom)

    return {path: Source(opener, offset, size) for path, offset, size in RomFS(rom).entries()}


class _Dir:
    def __init__(self, name: str, parent: "_Dir | None"):
        self.name = name
        self.parent = parent
        self.dirs: dict[str, _Dir] = {}
        self.files: dict[str, str] = {}      # name -> the path as the caller gave it
        self.offset = 0
        self.file_offsets: dict[str, int] = {}


def _tree(paths: Iterable[str]) -> _Dir:
    root = _Dir("", None)
    for path in paths:
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        if not parts:
            raise ValueError(f"empty RomFS path {path!r}")
        node = root
        for part in parts[:-1]:
            if part in node.files:
                raise ValueError(f"{path!r}: {part!r} is both a file and a folder")
            node = node.dirs.setdefault(part, _Dir(part, node))
        if parts[-1] in node.dirs:
            raise ValueError(f"{path!r} is both a file and a folder")
        node.files[parts[-1]] = path
    return root


def _name_size(name: str) -> int:
    return _align(len(name.encode("utf-16-le")), 4)


def _blocks(size: int) -> int:
    return (size + BLOCK - 1) // BLOCK


def _hash_level(data: bytes) -> bytes:
    """SHA-256 of each 0x1000 block of `data` (the last one zero padded)."""
    out = bytearray()
    for i in range(0, len(data), BLOCK):
        out += hashlib.sha256(data[i:i + BLOCK].ljust(BLOCK, b"\0")).digest()
    return bytes(out)


@dataclass
class Level3Tables:
    """The level-3 header and four tables (`tables`, the header's data offset still 0) and where each file's data
    goes."""
    tables: bytes
    order: list[str]            # the paths whose data is appended, in data order (the tables' order)
    offsets: dict[str, int]     # every path's data offset (from the header's data offset)
    data_end: int               # where the appended data ends, its last file padded to 0x10

    def with_data_offset(self, data_off: int, size: int | None = None) -> bytes:
        """The tables with the header's data offset set, zero padded to `size` (default: up to the data offset)."""
        size = data_off if size is None else size
        if data_off < len(self.tables) or size < len(self.tables):
            raise ValueError("the file data would start inside the tables")
        out = bytearray(self.tables.ljust(size, b"\0"))
        struct.pack_into("<I", out, DATA_OFFSET_FIELD, data_off)
        return bytes(out)


def level3_tables(sizes: Mapping[str, int], fixed: Mapping[str, int] | None = None,
                  append_at: int = 0) -> Level3Tables:
    """The tables of the files `sizes` (path -> size). A path in `fixed` keeps that data offset; the others are
    appended from `append_at` on, in the tables' order (folders in pre-order, names sorted), each at 0x10.
    Byte-identical to the C `romfs_tables` (core/install/title/c/romfs.c)."""
    fixed = fixed or {}
    root = _tree(sizes)
    dirs: list[_Dir] = []
    stack = [root]
    while stack:  # pre-order, siblings sorted by name
        d = stack.pop()
        dirs.append(d)
        stack.extend(d.dirs[n] for n in sorted(d.dirs, reverse=True))
    offset = 0
    for d in dirs:
        d.offset = offset
        offset += 0x18 + _name_size(d.name)
    dir_meta_size = offset

    file_list: list[tuple[_Dir, str, int, int, str | None]] = []
    order: list[str] = []
    offsets: dict[str, int] = {}
    offset, data_at = 0, append_at
    for d in dirs:
        names = sorted(d.files)
        for i, name in enumerate(names):
            path = d.files[name]
            size = sizes[path]
            d.file_offsets[name] = offset
            if path in fixed:
                at = fixed[path]
            else:
                at = data_at
                order.append(path)
                data_at += _align(size, FILE_ALIGN)
            offsets[path] = at
            file_list.append((d, name, size, at, names[i + 1] if i + 1 < len(names) else None))
            offset += 0x20 + _name_size(name)
    file_meta_size = offset

    next_dir: dict[int, _Dir] = {}                 # a folder's next sibling, by id
    for d in dirs:
        names = sorted(d.dirs)
        for a, b in zip(names, names[1:]):
            next_dir[id(d.dirs[a])] = d.dirs[b]
    dir_buckets = bucket_count(len(dirs))
    file_buckets = bucket_count(len(file_list))
    dir_table = [NONE] * dir_buckets
    file_table = [NONE] * file_buckets
    dir_meta = bytearray(dir_meta_size)
    for d in dirs:
        parent = d.parent.offset if d.parent else 0
        sibling = next_dir[id(d)].offset if id(d) in next_dir else NONE
        child = d.dirs[min(d.dirs)].offset if d.dirs else NONE
        child_file = d.file_offsets[min(d.files)] if d.files else NONE
        bucket = name_hash(parent, d.name, dir_buckets)
        chained, dir_table[bucket] = dir_table[bucket], d.offset
        raw = d.name.encode("utf-16-le")
        struct.pack_into("<6I", dir_meta, d.offset, parent, sibling, child, child_file, chained, len(raw))
        dir_meta[d.offset + 0x18:d.offset + 0x18 + len(raw)] = raw
    file_meta = bytearray(file_meta_size)
    for d, name, size, data_offset, next_name in file_list:
        sibling = d.file_offsets[next_name] if next_name is not None else NONE
        at = d.file_offsets[name]
        bucket = name_hash(d.offset, name, file_buckets)
        chained, file_table[bucket] = file_table[bucket], at
        raw = name.encode("utf-16-le")
        struct.pack_into("<IIQQII", file_meta, at, d.offset, sibling, data_offset, size, chained, len(raw))
        file_meta[at + 0x20:at + 0x20 + len(raw)] = raw

    dir_hash_off = HEADER_SIZE
    dir_meta_off = dir_hash_off + 4 * dir_buckets
    file_hash_off = dir_meta_off + dir_meta_size
    file_meta_off = file_hash_off + 4 * file_buckets
    head = struct.pack("<10I", HEADER_SIZE, dir_hash_off, 4 * dir_buckets, dir_meta_off, dir_meta_size,
                       file_hash_off, 4 * file_buckets, file_meta_off, file_meta_size, 0)
    tables = (head + struct.pack(f"<{dir_buckets}I", *dir_table) + bytes(dir_meta)
              + struct.pack(f"<{file_buckets}I", *file_table) + bytes(file_meta))
    return Level3Tables(tables, order, offsets, data_at)


@dataclass(frozen=True)
class HashTree:
    """Where the parts of a RomFS image with `level3_size` bytes of level 3 go, in our writer's order, which is the
    game's own: the IVFC header and master hash, level 3, level 1, level 2, each from a 0x1000 boundary."""
    level3_size: int

    @property
    def l2_size(self) -> int:
        return _blocks(self.level3_size) * HASH_SIZE

    @property
    def l1_size(self) -> int:
        return _blocks(self.l2_size) * HASH_SIZE

    @property
    def master_size(self) -> int:
        return _blocks(self.l1_size) * HASH_SIZE

    @property
    def hash_region_size(self) -> int:
        """Bytes the NCCH's RomFS superblock hash covers."""
        return _align(MASTER_HASH_OFFSET + self.master_size, HASH_REGION_ALIGN)

    @property
    def l3_start(self) -> int:
        return _align(MASTER_HASH_OFFSET + self.master_size, BLOCK)

    @property
    def l1_start(self) -> int:
        return self.l3_start + _align(self.level3_size, BLOCK)

    @property
    def l2_start(self) -> int:
        return self.l1_start + _align(self.l1_size, BLOCK)

    @property
    def size(self) -> int:
        return self.l2_start + _align(self.l2_size, BLOCK)

    def header(self) -> bytes:
        """The IVFC header, padded to the master hash at 0x60."""
        l1, l2, l3 = self.l1_size, self.l2_size, self.level3_size
        l2_logical = _align(l1, BLOCK)
        l3_logical = _align(l2_logical + l2, BLOCK)
        head = struct.pack("<4sII", b"IVFC", 0x10000, self.master_size)
        for off, size in ((0, l1), (l2_logical, l2), (l3_logical, l3)):
            head += struct.pack("<QQII", off, size, BLOCK_LOG2, 0)
        head += struct.pack("<I", IVFC_HEADER)
        return head.ljust(MASTER_HASH_OFFSET, b"\0")


class RomfsImage:
    def __init__(self, files: Mapping[str, Source]):
        """Computes the layout; reads nothing."""
        t = level3_tables({path: src.size for path, src in files.items()})
        self._data_order: list[Source] = [files[path] for path in t.order]
        #: The level 3 header and tables, padded to where the file data starts.
        self.metadata = t.with_data_offset(_align(len(t.tables), FILE_ALIGN))
        self.level3_size = len(self.metadata) + t.data_end
        tree = self._tree = HashTree(self.level3_size)
        self._master_size = tree.master_size
        self._level_sizes = (tree.l1_size, tree.l2_size, self.level3_size)
        #: bytes that the NCCH's RomFS superblock hash covers (valid after prepare, known now)
        self.hash_region_size = tree.hash_region_size
        self._l3_start = tree.l3_start
        self._l1_start = tree.l1_start
        self._l2_start = tree.l2_start
        #: bytes of the whole image
        self.size = tree.size
        self._l1 = b""
        self._l2 = b""
        self._master = b""
        self._prepared = False

    def _level3(self, progress=None, total: int = 0) -> Iterator[bytes]:
        """The level 3 bytes in order, files read in chunks. One handle is shared by consecutive files that come
        from the same `open` callable."""
        yield self.metadata
        done = len(self.metadata)
        handle = opener = None
        try:
            for src in self._data_order:
                if src.size:
                    if handle is None or opener is not src.open:
                        if handle is not None:
                            handle.close()
                        handle, opener = src.open(), src.open
                    handle.seek(src.offset)
                    left = src.size
                    while left:
                        data = handle.read(min(READ_CHUNK, left))
                        if not data:
                            raise ValueError(f"a source file is {left} bytes shorter than its size")
                        left -= len(data)
                        done += len(data)
                        yield data
                        if progress:
                            progress(done, total)
                pad = -src.size % FILE_ALIGN
                if pad:
                    yield bytes(pad)
                    done += pad
        finally:
            if handle is not None:
                handle.close()

    def prepare(self, progress=None) -> None:
        """Read every file once and build the hash tree. Idempotent."""
        if self._prepared:
            return
        l2 = bytearray()
        buf = bytearray()
        for data in self._level3(progress, self.level3_size):
            buf += data
            n = len(buf) // BLOCK * BLOCK
            if n:
                view = memoryview(buf)
                for i in range(0, n, BLOCK):
                    l2 += hashlib.sha256(view[i:i + BLOCK]).digest()
                view.release()
                del buf[:n]
        if buf:
            l2 += hashlib.sha256(bytes(buf).ljust(BLOCK, b"\0")).digest()
        if len(l2) != self._level_sizes[1]:
            raise ValueError("the sources changed size while hashing")
        self._l2 = bytes(l2)
        self._l1 = _hash_level(self._l2)
        self._master = _hash_level(self._l1)
        self._prepared = True

    def _header(self) -> bytes:
        return self._tree.header()

    def _need_prepare(self) -> None:
        if not self._prepared:
            raise RuntimeError("call prepare() first")

    def header_region(self) -> bytes:
        """The first `hash_region_size` bytes of the image (IVFC header, master hash, zeros)."""
        self._need_prepare()
        return (self._header() + self._master).ljust(self.hash_region_size, b"\0")

    @property
    def level2_hashes(self) -> bytes:
        """Level 2: the SHA-256 of each 4 KB of level 3 (the last block zero padded), after prepare."""
        self._need_prepare()
        return self._l2

    def chunks(self, progress=None) -> Iterator[bytes]:
        """The whole image in order, `size` bytes in all, files read again from the sources."""
        self._need_prepare()
        yield (self._header() + self._master).ljust(self._l3_start, b"\0")
        sent = self._l3_start
        for data in self._level3():
            yield data
            sent += len(data)
            if progress:
                progress(sent, self.size)
        yield bytes(self._l1_start - self._l3_start - self.level3_size)
        yield self._l1.ljust(self._l2_start - self._l1_start, b"\0")
        yield self._l2.ljust(self.size - self._l2_start, b"\0")
        if progress:
            progress(self.size, self.size)
