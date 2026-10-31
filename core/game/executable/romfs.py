"""Read single files from the RomFS of a decrypted game file (.3ds, .cci, .cxi, .app, .cia, .zcci, .zcxi, .zcia;
containers.py), without extracting it.

RomFS = IVFC hash tree whose level 3 holds a directory/file metadata table
and the file data. Only level 3 is used (hashes are not checked).
"""

import struct
from pathlib import Path

from core.game.executable.containers import INVALID_ROMFS, MEDIA_UNIT, NO_ROMFS, ExtractError, open_container
from core.game.executable.extract import read_exactly, read_ncch

NONE = 0xFFFFFFFF


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


class RomFS:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._index: dict[str, int] | None = None
        with open_container(self.path) as f:
            ncch_offset, ncch = read_ncch(f)
            self.title_id = ncch[0x108:0x110][::-1].hex()
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
            self.level3 = start + _align(0x60 + master_hash_size, level3_block)
            f.seek(self.level3)
            header = read_exactly(f, 0x28, "the RomFS")
            (_, _, _, dir_meta_offset, dir_meta_size, _, _, file_meta_offset, file_meta_size,
             self.data_offset) = struct.unpack("<10I", header)
            f.seek(self.level3 + dir_meta_offset)
            self.dirs = read_exactly(f, dir_meta_size, "the RomFS")
            f.seek(self.level3 + file_meta_offset)
            self.files = read_exactly(f, file_meta_size, "the RomFS")

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
        if self._index is None:
            self._index = {}
            for name, offset in self._walk_entries(0, ""):
                self._index.setdefault(name, offset)
        return self._index.get("/".join(p for p in path.replace("\\", "/").split("/") if p))

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

    def walk(self, dir_offset: int = 0, prefix: str = ""):
        """Every file path of the RomFS."""
        for name, _ in self._walk_entries(dir_offset, prefix):
            yield name
