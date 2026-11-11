"""A title's build data: what a release's
patch set carries in its title-build slot (`patchset.set_build_data`) so the console hashes nothing before it writes:
the content's size and SHA-256 (the TMD goes before the content), the level-2 hashes of the bytes the console makes
(its RomFS's hash tree without reading them first), and what they were made from (the dump's revision, the executable,
the exheader, the SMDH and every mod file's size and SHA-256). The console checks the mod's bytes against those level-2
hashes as they stream; a console whose inputs differ computes everything itself. The sizes also give the title's layout
before the patch set's ARC files are made. Read by the C `digest.c`.

Two formats, both read:
* **2**, the single title's (`build_title.base_title_digest`): the level-2 hashes of the seam and the mod's files
  (`KeptRomfsImage.tail_hashes`).
* **3**, the split title's (`build_title.mod_title_digest`): the edition's title with the mod's files only, its level-2
  hashes those of its whole level 3 (`RomfsImage.level2_hashes`); and the game data title's id and, per dump the PC
  knew (keyed by its RomFS superblock hash), that title's content size and SHA-256 (`build_title.game_digest`).

Little endian:

    0x00 "HFTD", u32 format (2 or 3), u64 title id
    0x10 u64 content size, the content's SHA-256 (32 bytes)
    0x38 the dump's RomFS superblock hash (its NCCH header at 0x1E0: the game's revision)
    0x58 SHA-256 of the executable (.code as the title holds it), 0x78 of the mod's exheader (before retitling),
         0x98 of the title's SMDH
    0xB8 u32 file count, u32 count of the level-2 hashes
    0xC0 format 3 only: u64 the game data title's id, u32 game entry count, u32 0; then each entry (0x48 bytes): the
         dump's RomFS superblock hash (32), u64 the game data's content size, its SHA-256 (32)
    then the mod's RomFS files sorted by path (UTF-8 bytes): u64 size, SHA-256, u32 path length, the path padded to 4
    then the level-2 hashes, 32 bytes each, in the image's order
"""

import struct
from dataclasses import dataclass, field

MAGIC = b"HFTD"
FORMAT = 2                  # the single title's
FORMAT_SPLIT = 3            # the split title's: the mod's title and the game data's hashes
FORMATS = (FORMAT, FORMAT_SPLIT)
HEADER = 0xC0
HASH = 32
_HEAD = struct.Struct("<4sIQQ32s32s32s32s32sII")
_GAMES = struct.Struct("<QII")
_GAME = struct.Struct("<32sQ32s")


class DigestError(ValueError):
    pass


@dataclass(frozen=True)
class DigestFile:
    path: str
    size: int
    sha256: bytes


@dataclass(frozen=True)
class GameDigest:
    """The game data title made from a dump whose RomFS superblock hash is `romfs_hash`: its content's size and
    SHA-256."""
    romfs_hash: bytes
    content_size: int
    content_sha256: bytes


@dataclass(frozen=True)
class TitleDigest:
    title_id: int
    content_size: int
    content_sha256: bytes
    game_romfs_hash: bytes
    code_sha256: bytes
    exheader_sha256: bytes
    smdh_sha256: bytes
    files: tuple[DigestFile, ...] = field(default=())
    tail_hashes: bytes = b""          # KeptRomfsImage.tail_hashes (format 2), RomfsImage.level2_hashes (format 3)
    format: int = FORMAT
    game_title_id: int = 0            # format 3: the game data title's
    games: tuple[GameDigest, ...] = field(default=())

    def to_bytes(self) -> bytes:
        if len(self.tail_hashes) % HASH:
            raise DigestError("the level-2 hashes are not whole")
        if self.format not in FORMATS or (self.format == FORMAT and (self.games or self.game_title_id)):
            raise DigestError(f"format {self.format} cannot carry this build data")
        files = sorted(self.files, key=lambda f: f.path.encode())
        out = bytearray(_HEAD.pack(MAGIC, self.format, self.title_id, self.content_size, self.content_sha256,
                                   self.game_romfs_hash, self.code_sha256, self.exheader_sha256, self.smdh_sha256,
                                   len(files), len(self.tail_hashes) // HASH))
        if self.format == FORMAT_SPLIT:
            out += _GAMES.pack(self.game_title_id, len(self.games), 0)
            for game in self.games:
                out += _GAME.pack(game.romfs_hash, game.content_size, game.content_sha256)
        for f in files:
            raw = f.path.encode()
            out += struct.pack("<Q32sI", f.size, f.sha256, len(raw)) + raw + bytes(-len(raw) % 4)
        return bytes(out + self.tail_hashes)

    @classmethod
    def from_bytes(cls, data: bytes) -> "TitleDigest":
        if len(data) < HEADER:
            raise DigestError("the title's build data is cut short")
        (magic, fmt, title_id, size, content, game, code, exheader, smdh, count, hashes) = _HEAD.unpack_from(data)
        if magic != MAGIC or fmt not in FORMATS:
            raise DigestError("not the title's build data of this format")
        at, game_title_id, games = HEADER, 0, []
        if fmt == FORMAT_SPLIT:
            if at + _GAMES.size > len(data):
                raise DigestError("the title's build data is cut short")
            game_title_id, entries, _ = _GAMES.unpack_from(data, at)
            at += _GAMES.size
            if at + entries * _GAME.size > len(data):
                raise DigestError("the title's build data is cut short")
            for _ in range(entries):
                games.append(GameDigest(*_GAME.unpack_from(data, at)))
                at += _GAME.size
        files = []
        for _ in range(count):
            if at + 44 > len(data):
                raise DigestError("the title's build data is cut short")
            fsize, digest, n = struct.unpack_from("<Q32sI", data, at)
            at += 44
            raw = data[at:at + n]
            if len(raw) != n:
                raise DigestError("the title's build data is cut short")
            files.append(DigestFile(raw.decode(), fsize, digest))
            at += n + (-n % 4)
        if at + hashes * HASH != len(data):
            raise DigestError("the title's build data does not end with its level-2 hashes")
        return cls(title_id, size, content, game, code, exheader, smdh, tuple(files), bytes(data[at:]), fmt,
                   game_title_id, tuple(games))
