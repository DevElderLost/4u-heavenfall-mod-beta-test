"""Extract the decompressed executable (ExeFS ".code") from 3DS containers.

Supported inputs (decrypted only, NCCH "NoCrypto" flag): .3ds / .cci (the first partition), .app / .cxi (a single
NCCH, e.g. an installed update's 00000000.app), .cia, and Azahar's .zcci / .zcxi / .zcia; `containers.open_container`
opens them all.
"""

import struct
from functools import lru_cache
from pathlib import Path

from .containers import (
    ENCRYPTED, MEDIA_UNIT, NCCH_MAGICS, NO_EXECUTABLE, NOT_A_GAME_FILE, TRUNCATED, ExtractError, open_container,
)

NO_CRYPTO = 0x04


@lru_cache(maxsize=4)
def blz_decompress(data: bytes) -> bytes:
    """Nintendo bottom-up LZ77 used for compressed ExeFS code. Kept for the last few inputs: a run reads the same
    executable twice and decompressing it takes over a second."""
    buffer_top_and_bottom, extra_size = struct.unpack_from("<II", data, len(data) - 8)
    header_len = buffer_top_and_bottom >> 24
    compressed_len = buffer_top_and_bottom & 0xFFFFFF
    out = bytearray(data) + bytes(extra_size)
    src = len(data) - header_len
    dst = len(out)
    end = len(data) - compressed_len
    while src > end:
        src -= 1
        flags = data[src]
        for _ in range(8):
            if src <= end:
                break
            if flags & 0x80:
                src -= 2
                pair = data[src] | data[src + 1] << 8
                length = (pair >> 12) + 3
                distance = (pair & 0x0FFF) + 3
                if distance >= length:      # the copy does not overlap itself: one slice
                    dst -= length
                    out[dst:dst + length] = out[dst + distance:dst + distance + length]
                else:
                    for _ in range(length):
                        dst -= 1
                        out[dst] = out[dst + distance]
            else:
                src -= 1
                dst -= 1
                out[dst] = data[src]
            flags <<= 1
    return bytes(out)


def _ncch_offset(f) -> int:
    """Where the NCCH starts in `f`, a file from `open_container` (its offset 0 is an NCSD or an NCCH)."""
    f.seek(0)
    header = f.read(0x200)
    if header[0x100:0x104] == b"NCSD":
        return struct.unpack_from("<I", header, 0x120)[0] * MEDIA_UNIT
    if header[0x100:0x104] in NCCH_MAGICS:
        return 0
    raise ExtractError.of(NOT_A_GAME_FILE)


def read_ncch(f, decrypted: bool = True) -> tuple[int, bytes]:
    """(offset, 0x200-byte header) of the NCCH in `f`, a file from `open_container`. `decrypted`: refuse an
    encrypted one."""
    offset = _ncch_offset(f)
    f.seek(offset)
    header = f.read(0x200)
    if len(header) < 0x200 or header[0x100:0x104] != b"NCCH":
        raise ExtractError.of(NOT_A_GAME_FILE, "no NCCH partition")
    if decrypted and not header[0x18F] & NO_CRYPTO:
        raise ExtractError.of(ENCRYPTED)
    return offset, header


def read_exactly(f, size: int, what: str) -> bytes:
    """`size` bytes of `f`, or a refusal that the file is cut short inside `what`."""
    data = f.read(size)
    if len(data) != size:
        raise ExtractError.of(TRUNCATED, f"inside {what}")
    return data


def ncch_identity(path: Path) -> tuple[str, bool]:
    """(title id as lowercase hex, whether it is decrypted) of a game file in any accepted format (containers.py;
    an encrypted CIA is told apart by its TMD)."""
    try:
        f = open_container(path)
    except ExtractError as error:
        if error.kind == ENCRYPTED and error.title_id:
            return error.title_id, False
        raise
    with f:
        _, ncch = read_ncch(f, decrypted=False)
    return ncch[0x108:0x110][::-1].hex(), bool(ncch[0x18F] & NO_CRYPTO)


def extract_code(path: Path) -> tuple[bytes, str]:
    """Return (decompressed code.bin, title id as hex string)."""
    with open_container(path) as f:
        ncch_offset, ncch = read_ncch(f)
        title_id = ncch[0x108:0x110][::-1].hex()
        exefs_offset, exefs_size = struct.unpack_from("<II", ncch, 0x1A0)
        if not exefs_size:
            raise ExtractError.of(NO_EXECUTABLE)
        compressed = read_exactly(f, 0x400, "the exheader")[0x0D] & 1
        exefs_start = ncch_offset + exefs_offset * MEDIA_UNIT
        f.seek(exefs_start)
        exefs_header = read_exactly(f, 0x200, "the ExeFS header")
        for i in range(10):
            name, offset, size = struct.unpack_from("<8sII", exefs_header, i * 16)
            if name.rstrip(b"\x00") == b".code":
                f.seek(exefs_start + 0x200 + offset)
                code = read_exactly(f, size, "the executable")
                return (blz_decompress(code) if compressed else code), title_id
    raise ExtractError.of(NO_EXECUTABLE)
