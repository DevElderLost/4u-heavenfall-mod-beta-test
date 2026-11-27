"""Encrypted 3DS game files read as decrypted ones: the readers of the game files (containers.open_container) get a
file whose bytes are the decrypted ones and whose NCCH header says "decrypted", so nothing after it knows the
difference. Nothing is written: each read decrypts the bytes it asks for.

    NCCH   (.3ds, .cci, .cxi, .app, and the content of a CIA)  the exheader, the ExeFS and the RomFS: AES-CTR with the
           keys of the player's key file (crypto.py): the exheader, the ExeFS header, `icon` and `banner` with keyslot
           0x2C, the rest of the ExeFS and the RomFS with the slot that the NCCH names (0x2C, 0x25, 0x18, 0x1B), whose
           Y is changed by the game's seed when the NCCH uses seed encryption (seeddb.bin)
    CIA    a content encrypted by the title key (AES-CBC), which the ticket holds encrypted by a common key

A game that needs a key the file does not have is refused with the names of the missing keys. A NCCH with a fixed key
(system and demo titles) is not read: no game of the mod has one.
"""

import hashlib
import io
import struct

from core.game.executable import crypto
from core.game.executable.containers import (
    ENCRYPTED, MEDIA_UNIT, MESSAGES, MISSING_KEYS, NOT_A_GAME_FILE, ExtractError, _View,
)

NO_CRYPTO, FIXED_KEY, SEED_CRYPTO = 0x04, 0x01, 0x20
# The keyslot of the second key by the NCCH's crypto method (header byte 0x18B)
METHOD_SLOT = {0x00: 0x2C, 0x01: 0x25, 0x0A: 0x18, 0x0B: 0x1B}
PRIMARY_SLOT = 0x2C
PLAIN_NAMES = (b"icon", b"banner")      # the ExeFS files that keep the first key
EXHEADER_AT, EXHEADER_SIZE = 0x200, 0x800
EXEFS, ROMFS, EXHEADER = 2, 3, 1       # the counter's section type


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def missing_keys(names, title_id: str | None = None) -> ExtractError:
    """The refusal for a file whose key file lacks `names`."""
    return ExtractError(f"{MESSAGES[MISSING_KEYS]} ({', '.join(names)})", MISSING_KEYS, title_id, ", ".join(names))


class _Wrap(_View):
    """A read-only view over `parent` (a file), whose close closes it too."""

    def __init__(self, parent, size: int):
        super().__init__(size)
        self._parent = parent

    def _raw(self, position: int, size: int) -> bytes:
        self._parent.seek(position)
        return self._parent.read(size)

    def close(self) -> None:
        if not self.closed:
            self._parent.close()
        super().close()


def ncch_start(f) -> int | None:
    """Where the NCCH starts in `f` (offset 0 is an NCSD or an NCCH); None for anything else."""
    f.seek(0)
    head = f.read(0x200)
    if head[0x100:0x104] == b"NCSD":
        return struct.unpack_from("<I", head, 0x120)[0] * MEDIA_UNIT
    return 0 if head[0x100:0x104] == b"NCCH" else None


class NcchView(_Wrap):
    """`parent` as it would be with its NCCH (at `start`) decrypted. `header`: the NCCH's 0x200 bytes."""

    def __init__(self, parent, start: int, header: bytes, keys: "crypto.KeySet"):
        parent.seek(0, io.SEEK_END)
        super().__init__(parent, parent.tell())
        self.start = start
        self._keys = keys
        self._title_id = header[0x108:0x110][::-1].hex()
        flags, method = header[0x18F], header[0x18B]
        if flags & FIXED_KEY or method not in METHOD_SLOT:
            raise ExtractError(f"{ENCRYPTED_TEXT} (fixed key or unknown crypto method)", ENCRYPTED,
                               self._title_id, f"flags {flags:#x}, method {method:#x}")
        self._version = struct.unpack_from("<H", header, 0x112)[0]
        self._partition = header[0x108:0x110]
        self._header = bytearray(header)
        self._header[0x18B] = 0
        self._header[0x18F] = (flags & ~(FIXED_KEY | SEED_CRYPTO)) | NO_CRYPTO
        self.exefs_at, self.exefs_size = (value * MEDIA_UNIT for value in struct.unpack_from("<II", header, 0x1A0))
        self.romfs_at, self.romfs_size = (value * MEDIA_UNIT for value in struct.unpack_from("<II", header, 0x1B0))
        key_y = header[0:16]
        try:
            self._primary = keys.ncch_key(PRIMARY_SLOT, key_y)
            slot = METHOD_SLOT[method]
            if flags & SEED_CRYPTO:
                key_y = hashlib.sha256(key_y + self._seed(header)).digest()[:16]
            self._secondary = keys.ncch_key(slot, key_y)
        except crypto.MissingKey as error:
            raise missing_keys(error.names, self._title_id) from None
        self._regions_list = None

    def _seed(self, header: bytes) -> bytes:
        """The game's seed from seeddb.bin, checked by the hash the NCCH header holds."""
        program_id = header[0x118:0x120]
        seed = self._keys.seed(program_id)
        if seed is None or hashlib.sha256(seed + program_id).digest()[:4] != header[0x114:0x118]:
            raise missing_keys([f"seeddb.bin (seed of {self._title_id})"], self._title_id)
        return seed

    def _counter(self, kind: int, section_at: int) -> int:
        """The AES-CTR counter of the section of type `kind` that starts `section_at` bytes into the NCCH."""
        if self._version in (0, 2):
            block = self._partition[::-1] + bytes([kind]) + bytes(7)
        elif self._version == 1:
            block = self._partition + bytes(4) + struct.pack(">I", section_at)
        else:
            raise ExtractError(f"{ENCRYPTED_TEXT} (NCCH version {self._version})", ENCRYPTED, self._title_id)
        return int.from_bytes(block, "big")

    def _regions(self) -> list[tuple[int, int, bytes, int]]:
        """(start, end, key, counter at start) of every encrypted piece of the file, by position."""
        if self._regions_list is not None:
            return self._regions_list
        regions = [(self.start + EXHEADER_AT, self.start + EXHEADER_AT + EXHEADER_SIZE, self._primary,
                    self._counter(EXHEADER, EXHEADER_AT))]
        if self.exefs_size:
            at = self.start + self.exefs_at
            counter = self._counter(EXEFS, self.exefs_at)
            header = crypto.ctr_xor(self._primary, counter, self._raw(at, 0x200))
            regions.append((at, at + 0x200, self._primary, counter))
            for i in range(10):
                name, offset, size = struct.unpack_from("<8sII", header, i * 16)
                if not size or not name.rstrip(b"\x00"):
                    continue
                key = self._primary if name.rstrip(b"\x00") in PLAIN_NAMES else self._secondary
                first = at + 0x200 + offset
                regions.append((first, first + _align(size, MEDIA_UNIT), key, counter + (0x200 + offset) // 16))
        if self.romfs_size:
            at = self.start + self.romfs_at
            regions.append((at, at + self.romfs_size, self._secondary, self._counter(ROMFS, self.romfs_at)))
        self._regions_list = sorted(regions)
        return self._regions_list

    def _read_at(self, position: int, size: int) -> bytes:
        data = bytearray(self._raw(position, size))
        end = position + len(data)
        head_end = self.start + len(self._header)
        if position < head_end and end > self.start:       # the NCCH header: only its flags change
            low = max(position, self.start)
            high = min(end, head_end)
            data[low - position:high - position] = self._header[low - self.start:high - self.start]
        for start, stop, key, counter in self._regions():
            low, high = max(position, start), min(end, stop)
            if low >= high:
                continue
            block, skip = divmod(low - start, 16)
            plain = crypto.ctr_xor(key, counter + block, bytes(skip) + bytes(data[low - position:high - position]))
            data[low - position:high - position] = plain[skip:]
        return bytes(data)


ENCRYPTED_TEXT = "the file is encrypted"


class CbcView(_Wrap):
    """A CIA's content decrypted with its title key (AES-CBC, the IV of the first block is `iv`)."""

    def __init__(self, parent, key: bytes, iv: bytes):
        parent.seek(0, io.SEEK_END)
        super().__init__(parent, parent.tell())
        self._key, self._iv = key, iv

    def _read_at(self, position: int, size: int) -> bytes:
        start = position & ~15
        end = min(_align(position + size, 16), self.size)
        raw = self._raw(max(start - 16, 0), end - max(start - 16, 0))
        iv, cipher = (self._iv, raw) if start == 0 else (raw[:16], raw[16:])
        whole = len(cipher) - len(cipher) % 16
        plain = crypto.cbc_decrypt(self._key, iv, cipher[:whole]) + cipher[whole:]
        return plain[position - start:position - start + size]


def title_key(keys: "crypto.KeySet", ticket: bytes, signature_section: int) -> bytes:
    """The title key of a CIA's ticket: its encrypted key (at 0x7F of the ticket data), AES-CBC with the common key
    the ticket names (0xB1), IV the title id (0x9C) and zeros."""
    data = ticket[signature_section:]
    if len(data) < 0xB2:
        raise ExtractError.of(NOT_A_GAME_FILE, "a CIA with an unreadable ticket")
    try:
        common = keys.common_key(data[0xB1])
    except crypto.MissingKey as error:
        raise missing_keys(error.names, data[0x9C:0xA4].hex()) from None
    return crypto.cbc_decrypt(common, data[0x9C:0xA4] + bytes(8), data[0x7F:0x8F])


def decrypt_cia_content(window, keys, ticket: bytes, signature_section: int, index: int):
    """`window` (a CIA's encrypted content 0) decrypted with the title key of `ticket`."""
    key = title_key(keys, ticket, signature_section)
    return CbcView(window, key, struct.pack(">H", index) + bytes(14))


def open_decrypted(f, keys):
    """`f` (offset 0 is an NCSD or an NCCH) as it is when its NCCH is plain; the NCCH decrypted by `keys` when it is
    encrypted. `f` is returned as it is for a plain NCCH and for a file that is not one."""
    start = ncch_start(f)
    if start is None:
        return f
    f.seek(start)
    header = f.read(0x200)
    if len(header) < 0x200 or header[0x100:0x104] != b"NCCH" or header[0x18F] & NO_CRYPTO:
        return f
    f.seek(0)
    return NcchView(f, start, header, keys)
