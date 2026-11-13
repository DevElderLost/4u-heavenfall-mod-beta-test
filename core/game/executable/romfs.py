"""Read single files from the RomFS of a decrypted game file (.3ds, .cci, .cxi, .app, .cia, .zcci, .zcxi, .zcia;
containers.py), without extracting it.

RomFS = IVFC hash tree whose level 3 holds a directory/file metadata table
and the file data. Only level 3 is used (hashes are not checked).
"""

import os
import struct
import threading
from collections import OrderedDict
from pathlib import Path

from core.game.executable.containers import INVALID_ROMFS, MEDIA_UNIT, NO_ROMFS, ExtractError, open_container
from core.game.executable.extract import read_exactly, read_ncch

NONE = 0xFFFFFFFF

# The parsed header and tables of the RomFS of each game file already opened (the build opens the same game several
# times). Of an encrypted file every open decrypts them again, and the tables are megabytes: without this each
# `RomFS(game)` of a build costs as much as the first one. Kept by path, size and modification time.
_TABLES: OrderedDict = OrderedDict()
_TABLES_LOCK = threading.Lock()
TABLES_KEPT = 4


def clear_caches() -> None:
    """Forget the tables kept between `RomFS(...)` of the same file."""
    with _TABLES_LOCK:
        _TABLES.clear()


def _tables_key(path: Path):
    try:
        status = os.stat(path)
    except OSError:
        return None
    return os.path.abspath(path), status.st_size, status.st_mtime_ns


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


class RomFS:
    def __init__(self, path: Path):
        self.path = Path(path)
        key = _tables_key(self.path)
        with _TABLES_LOCK:
            state = _TABLES.get(key) if key else None
            if state is not None:
                _TABLES.move_to_end(key)
        if state is None:
            state = self._read_tables()
            if key:
                with _TABLES_LOCK:
                    _TABLES[key] = state
                    while len(_TABLES) > TABLES_KEPT:
                        _TABLES.popitem(last=False)
        self._state = state
        self.title_id, self.level3, self.data_offset = state["title_id"], state["level3"], state["data_offset"]
        self.dirs, self.files = state["dirs"], state["files"]

    def _read_tables(self) -> dict:
        with open_container(self.path) as f:
            ncch_offset, ncch = read_ncch(f)
            title_id = ncch[0x108:0x110][::-1].hex()
            romfs_offset, romfs_size = struct.unpack_from("<II", ncch, 0x1B0)
            if not romfs_size:
                raise ExtractError.of(NO_ROMFS)
            start = ncch_offset + romfs_offset * MEDIA_UNIT
            f.seek(start)
            ivfc = read_exactly(f, 0x60, "the RomFS header")
            if ivfc[:4] != b"IVFC":
                raise ExtractError.of(INVALID_ROMFS)
            master_hash_size = struct.unpack_from("<I", ivfc, 0x08)[0]
            level3_block = 1 << struct.unpack_from("<I", ivfc, 0x4C)[0]
            level3 = start + _align(0x60 + master_hash_size, level3_block)
            f.seek(level3)
            header = read_exactly(f, 0x28, "the RomFS")
            (_, _, _, dir_meta_offset, dir_meta_size, _, _, file_meta_offset, file_meta_size,
             data_offset) = struct.unpack("<10I", header)
            f.seek(level3 + dir_meta_offset)
            dirs = read_exactly(f, dir_meta_size, "the RomFS")
            f.seek(level3 + file_meta_offset)
            files = read_exactly(f, file_meta_size, "the RomFS")
        return {"title_id": title_id, "level3": level3, "data_offset": data_offset, "dirs": dirs, "files": files,
                "index": None}

    @staticmethod
    def _name(table: bytes, at: int, length: int) -> str:
        return table[at:at + length].decode("utf-16-le")

    def _children(self, dir_offset: int):
        """(name, is_dir, offset) of the entries of a directory."""
        _, _, child, file_offset, _, _ = struct.unpack_from("<6I", self.dirs, dir_offset)
        while child != NONE:
            name_length = struct.unpack_from("<I", self.dirs, child + 0x14)[0]
            yield self._name(self.dirs, child + 0x18, name_length), True, child
            child = struct.unpack_from("<I", self.dirs, child + 0x04)[0]
        while file_offset != NONE:
            name_length = struct.unpack_from("<I", self.files, file_offset + 0x1C)[0]
            yield self._name(self.files, file_offset + 0x20, name_length), False, file_offset
            file_offset = struct.unpack_from("<I", self.files, file_offset + 0x04)[0]

    def _find(self, path: str) -> int | None:
        """The metadata offset of a file. The index of every file is built on the first lookup: scanning a folder
        per lookup made reading the thousands of files of a big folder take a quarter of a minute."""
        index = self._state["index"]
        if index is None:
            index = {}
            for name, offset in self._walk_entries(0, ""):
                index.setdefault(name, offset)
            self._state["index"] = index          # shared with the other RomFS of this file
        return index.get("/".join(p for p in path.replace("\\", "/").split("/") if p))

    def _walk_entries(self, dir_offset: int, prefix: str):
        for name, is_dir, offset in self._children(dir_offset):
            if is_dir:
                yield from self._walk_entries(offset, f"{prefix}{name}/")
            else:
                yield prefix + name, offset

    def exists(self, path: str) -> bool:
        return self._find(path) is not None

    def read(self, path: str) -> bytes:
        entry = self._find(path)
        if entry is None:
            raise FileNotFoundError(f"{path} is not in the RomFS of {self.path.name}")
        data_offset, data_size = struct.unpack_from("<QQ", self.files, entry + 0x08)
        with open_container(self.path) as f:
            f.seek(self.level3 + self.data_offset + data_offset)
            return read_exactly(f, data_size, f"{path} in the RomFS")

    def entries(self):
        """(path, absolute offset in the file open_container returns, size) of every file."""
        for name, entry in self._walk_entries(0, ""):
            data_offset, data_size = struct.unpack_from("<QQ", self.files, entry + 0x08)
            yield name, self.level3 + self.data_offset + data_offset, data_size

    def walk(self, dir_offset: int = 0, prefix: str = ""):
        """Every file path of the RomFS."""
        for name, _ in self._walk_entries(dir_offset, prefix):
            yield name
