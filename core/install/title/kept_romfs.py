"""The base title's RomFS built around the game's own: the dump's level 3
stays byte for byte, moved by a multiple of 512 KB behind the new tables, so its level-1 and level-2 hashes are copied
from the dump. The mod's files (the ones replacing the game's and the new ones) go after it; a replaced file's old
bytes stay, unused. Only the tables, the seam and the mod's files are hashed, then the master hash. The game is read
once, while the image streams. Byte-identical to the C `kept.c`.

Level 3: the header and tables, zero padded to `shift` (the smallest multiple of 512 KB that holds them); the dump's
level 3 as it is; zeros up to 0x10; the mod's files in the tables' order, each padded to 0x10. The header's data
offset is `shift` plus the game's, so every game file keeps its entry's data offset.

Hashes: a level-2 hash covers 4 KB of level 3 and a level-1 hash 512 KB, so with the game moved by `shift` every
4 KB block of the game is the dump's (its level-2 hash is copied) and every whole 512 KB of it too (its level-1 hash is
copied). Hashed: the blocks of the tables, the seam (the game's last part block, then the mod's files) and the level-1
hashes of the level-2 blocks around them.
"""

import hashlib
import struct
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from core.game.executable.containers import MEDIA_UNIT, open_container
from core.game.executable.extract import read_exactly, read_ncch
from core.game.executable.romfs import RomFS
from core.install.title.romfs_writer import (
    BLOCK,
    FILE_ALIGN,
    HASH_SIZE,
    MASTER_HASH_OFFSET,
    READ_CHUNK,
    HashTree,
    Source,
    _align,
    _hash_level,
    level3_tables,
)

SHIFT_UNIT = 0x80000            # the level 3 one level-1 hash covers: 128 level-2 hashes of 4 KB each
L2_PER_L1 = BLOCK // HASH_SIZE  # 128
LEVEL3_HEADER = 0x28
SUPERBLOCK_HASH = 0x1E0         # the NCCH header's SHA-256 of the RomFS hash region


class LayoutError(ValueError):
    """The dump's RomFS is not in the form this builder keeps, or its own hashes do not match."""


@dataclass(frozen=True)
class GameRomfs:
    """The dump's RomFS, checked: where it starts in the file `open_container` gives, its hash tree's layout, the
    level-3 header's data offset and the NCCH header's hash of its first `hash_region_size` bytes."""
    path: Path
    start: int
    tree: HashTree
    data_offset: int
    superblock_hash: bytes

    def opener(self):
        return open_container(self.path)


def read_game_romfs(rom: Path) -> GameRomfs:
    """The dump's RomFS when it has our writer's form, which is the game's: the IVFC header,
    the master hash, level 3 at the next 4 KB, then levels 1 and 2, all with 4 KB blocks; and the NCCH header's hash
    of its hash region right. Anything else is refused (LayoutError)."""
    rom = Path(rom)
    with open_container(rom) as f:
        base, header = read_ncch(f)
        offset, size = struct.unpack_from("<II", header, 0x1B0)
        region_size = struct.unpack_from("<I", header, 0x1B8)[0] * MEDIA_UNIT
        start = base + offset * MEDIA_UNIT
        if not size or not MASTER_HASH_OFFSET <= region_size <= BLOCK:
            raise LayoutError("the game has no RomFS of the usual form")
        f.seek(start)
        region = read_exactly(f, region_size, "the RomFS header")
        if hashlib.sha256(region).digest() != header[SUPERBLOCK_HASH:SUPERBLOCK_HASH + 0x20]:
            raise LayoutError("the RomFS header does not match the game's NCCH header (a damaged dump)")
        level3_size = struct.unpack_from("<Q", region, 0xC + 2 * 24 + 8)[0]
        tree = HashTree(level3_size)
        if region[:MASTER_HASH_OFFSET] != tree.header() or region_size != tree.hash_region_size:
            raise LayoutError("the RomFS's hash levels are not laid out as the game's")
        if size * MEDIA_UNIT < tree.size:
            raise LayoutError("the RomFS is shorter than its levels")
        f.seek(start + tree.l3_start)
        head = struct.unpack("<10I", read_exactly(f, LEVEL3_HEADER, "the level-3 header"))
    if head[0] != LEVEL3_HEADER or not head[8] + head[7] <= head[9] <= level3_size:
        raise LayoutError("the RomFS's level-3 header is not the usual one")
    return GameRomfs(rom, start, tree, head[9], header[SUPERBLOCK_HASH:SUPERBLOCK_HASH + 0x20])


def _read(f, offset: int, size: int) -> Iterator[bytes]:
    f.seek(offset)
    while size:
        data = f.read(min(READ_CHUNK, size))
        if not data:
            raise ValueError(f"a source file is {size} bytes shorter than its size")
        size -= len(data)
        yield data


def _sources(sources: list[Source]) -> Iterator[bytes]:
    """The files in order, each padded to 0x10; consecutive files of one `open` share a handle."""
    handle = opener = None
    try:
        for src in sources:
            if src.size:
                if handle is None or opener is not src.open:
                    if handle is not None:
                        handle.close()
                    handle, opener = src.open(), src.open
                yield from _read(handle, src.offset, src.size)
            if src.size % FILE_ALIGN:
                yield bytes(-src.size % FILE_ALIGN)
    finally:
        if handle is not None:
            handle.close()


class _BlockHasher:
    def __init__(self):
        self.out = bytearray()
        self._buf = bytearray()

    def update(self, data: bytes) -> None:
        self._buf += data
        n = len(self._buf) // BLOCK * BLOCK
        if n:
            view = memoryview(self._buf)
            for i in range(0, n, BLOCK):
                self.out += hashlib.sha256(view[i:i + BLOCK]).digest()
            view.release()
            del self._buf[:n]

    def finish(self) -> bytes:
        if self._buf:
            self.out += hashlib.sha256(bytes(self._buf).ljust(BLOCK, b"\0")).digest()
            self._buf.clear()
        return bytes(self.out)


class KeptRomfsImage:
    """The base title's RomFS (the RomFsImage protocol of ncch.py): the game `rom` with `mod` (RomFS path -> Source)
    over it. Computes the layout and reads the dump's headers only; `prepare` reads a few hashes of the dump and the
    mod's files; `chunks` streams the whole image, reading the game once."""

    def __init__(self, rom: Path, mod: Mapping[str, Source]):
        self.game = game = read_game_romfs(rom)
        data_start = game.start + game.tree.l3_start + game.data_offset
        sizes: dict[str, int] = {}
        fixed: dict[str, int] = {}
        for path, at, size in RomFS(rom).entries():
            if path not in mod:
                sizes[path] = size
                fixed[path] = at - data_start
        sizes.update((path, src.size) for path, src in mod.items())
        game_l3 = game.tree.level3_size
        tables = level3_tables(sizes, fixed, _align(game_l3, FILE_ALIGN) - game.data_offset)
        #: how far the game's level 3 moves: the smallest multiple of 512 KB that holds the new tables
        self.shift = _align(len(tables.tables), SHIFT_UNIT)
        data_off = self.shift + game.data_offset
        self.metadata = tables.with_data_offset(data_off, self.shift)
        self._tail = [mod[path] for path in tables.order]
        self.level3_size = data_off + tables.data_end
        tree = self.tree = HashTree(self.level3_size)
        self.hash_region_size = tree.hash_region_size
        self.size = tree.size
        #: the dump's whole 4 KB blocks of level 3, and its whole 512 KB stretches: their hashes are copied
        self.copied_l2 = game_l3 // BLOCK
        self.copied_l1 = game_l3 // SHIFT_UNIT
        self._l2_head = self._l2_tail = self._l1 = self._master = b""
        self._prepared = False

    # ---- the hashes ------------------------------------------------------------------------------------------------

    def _seam(self) -> Iterator[bytes]:
        """Level 3 from the first block that is not a whole game block to the end."""
        game = self.game
        game_l3 = game.tree.level3_size
        at = self.copied_l2 * BLOCK
        with game.opener() as f:
            yield from _read(f, game.start + game.tree.l3_start + at, game_l3 - at)
        if game_l3 % FILE_ALIGN:
            yield bytes(-game_l3 % FILE_ALIGN)
        yield from _sources(self._tail)

    def prepare(self, progress=None) -> None:
        """Copies the dump's level-1 hashes (checked against its master hash) and hashes the tables, the seam and the
        mod's files. Idempotent."""
        if self._prepared:
            return
        game, tree = self.game, self.tree
        with game.opener() as f:
            f.seek(game.start + MASTER_HASH_OFFSET)
            master = read_exactly(f, game.tree.master_size, "the master hash")
            f.seek(game.start + game.tree.l1_start)
            game_l1 = read_exactly(f, game.tree.l1_size, "level 1")
            first = self.copied_l1 * L2_PER_L1        # the game's level-2 hashes the seam's level-1 hash also covers
            f.seek(game.start + game.tree.l2_start + first * HASH_SIZE)
            seam_l2 = read_exactly(f, (self.copied_l2 - first) * HASH_SIZE, "level 2")
        if _hash_level(game_l1) != master:
            raise LayoutError("the dump's level-1 hashes do not match its master hash (a damaged dump)")
        self._l2_head = _hash_level(self.metadata)
        hasher = _BlockHasher()
        done = 0
        for data in self._seam():
            hasher.update(data)
            done += len(data)
            if progress:
                progress(done, self.level3_size - self.shift - self.copied_l2 * BLOCK)
        self._l2_tail = hasher.finish()
        k0 = self.shift // BLOCK
        if k0 + self.copied_l2 + len(self._l2_tail) // HASH_SIZE != tree.l2_size // HASH_SIZE:
            raise ValueError("the sources changed size while hashing")
        j0 = self.shift // SHIFT_UNIT
        l1 = bytearray(_hash_level(self._l2_head))
        l1 += game_l1[:self.copied_l1 * HASH_SIZE]
        l1 += _hash_level(seam_l2 + self._l2_tail)
        if len(l1) != tree.l1_size or len(self._l2_head) != j0 * BLOCK:
            raise ValueError("the level-1 hashes do not add up")
        self._l1 = bytes(l1)
        self._master = _hash_level(self._l1)
        self._prepared = True

    def _need_prepare(self) -> None:
        if not self._prepared:
            raise RuntimeError("call prepare() first")

    @property
    def master(self) -> bytes:
        self._need_prepare()
        return self._master

    @property
    def tail_hashes(self) -> bytes:
        """The level-2 hashes `prepare` computes: the seam's block (the game's last part block with the first mod
        bytes) and every block of the mod's files. The build data carries them so the console hashes nothing first."""
        self._need_prepare()
        return self._l2_tail

    def header_region(self) -> bytes:
        """The first `hash_region_size` bytes of the image (IVFC header, master hash, zeros)."""
        self._need_prepare()
        return (self.tree.header() + self._master).ljust(self.hash_region_size, b"\0")

    # ---- the image -------------------------------------------------------------------------------------------------

    def chunks(self, progress=None) -> Iterator[bytes]:
        """The whole image in order, `size` bytes in all: the game's level 3 and level 2 read from the dump once."""
        self._need_prepare()
        game, tree = self.game, self.tree
        sent = 0

        def track(data: bytes) -> bytes:
            nonlocal sent
            sent += len(data)
            if progress:
                progress(sent, self.size)
            return data

        yield track((tree.header() + self._master).ljust(tree.l3_start, b"\0"))
        yield track(self.metadata)
        with game.opener() as f:
            for data in _read(f, game.start + game.tree.l3_start, game.tree.level3_size):
                yield track(data)
        game_l3 = game.tree.level3_size
        if game_l3 % FILE_ALIGN:
            yield track(bytes(-game_l3 % FILE_ALIGN))
        for data in _sources(self._tail):
            yield track(data)
        yield track(bytes(tree.l1_start - tree.l3_start - self.level3_size))
        yield track(self._l1.ljust(tree.l2_start - tree.l1_start, b"\0"))
        yield track(self._l2_head)
        with game.opener() as f:
            for data in _read(f, game.start + game.tree.l2_start, self.copied_l2 * HASH_SIZE):
                yield track(data)
        yield track(self._l2_tail)
        yield track(bytes(tree.size - tree.l2_start - tree.l2_size))
