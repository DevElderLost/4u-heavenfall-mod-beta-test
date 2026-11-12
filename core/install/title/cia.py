"""The CIA writer: certificate chain, ticket, TMD, the NCCH as content 0 and the meta section, nothing encrypted
(formats: 3dbrew CIA, Title_metadata, Ticket, Certificates). The ticket and TMD have zeroed
signatures, which Luma3DS' signature patches accept; the certificates are Nintendo's public ones (`certs.bin`), as
every CIA carries them, because the console's AM checks their signatures on any system.

Layout, each section at a multiple of 64: header (0x2020), certificate chain, ticket, TMD, content 0, meta.
"""

import hashlib
import struct
from functools import cache
from pathlib import Path
from typing import BinaryIO

from core.game.executable.containers import CIA_ALIGNMENT, CIA_HEADER_SIZE
from core.install.title.ncch import (
    CORE_VERSION,
    DEPENDENCIES,
    DEPENDENCIES_SIZE,
    Ncch,
    align,
    is_addon,
    is_update,
    save_data_size,
    sha256,
)

SMDH_SIZE = 0x36C0
META_SIZE = 0x3AC0                  # 0x400 of dependency list and core version, then the SMDH
CONTENT_INDEX_SIZE = 0x2000

# Signature types (big endian) and the bytes each takes with its padding to 0x40.
RSA4096_SHA256, RSA2048_SHA256 = 0x010003, 0x010004
SIGNATURE_BYTES = {RSA4096_SHA256: 0x240, RSA2048_SHA256: 0x140}
ISSUER_SIZE = 0x40
TICKET_ISSUER = "Root-CA00000003-XS0000000c"
TMD_ISSUER = "Root-CA00000003-CP0000000b"
TICKET_SIZE = 0x350
TMD_HEADER = 0xC4
TMD_INFO_RECORDS = 0x900
TMD_CHUNK = 0x30
TITLE_TYPE_CTR = 0x40
UPDATE_TITLE_VERSION = 1 << 10       # 1.0.0 (major 1: the exheader's remaster version, ncch.py)
TICKET_ID_BASE = 0x0004000000000000
# The ticket's content index section (a constant block as makerom writes it; one bit per content, content 0 only).
CONTENT_INDEX_HEADER = struct.pack(">10I", 0x00010014, 0xAC, 0x14, 0x00010014, 0, 0x28, 1, 0x84, 0x84, 0x00030000)


CERTS_FILE = Path(__file__).with_name("certs.bin")
CERT_CHAIN_SIZE = 0xA00


@cache
def certificate_chain() -> bytes:
    """The chain a CIA carries: CA00000003, then the ticket's signer (XS0000000c) and the TMD's (CP0000000b)."""
    chain = CERTS_FILE.read_bytes()
    if len(chain) != CERT_CHAIN_SIZE:
        raise ValueError(f"{CERTS_FILE} holds {len(chain):#x} bytes, not a certificate chain")
    return chain


def _text(value: str, size: int) -> bytes:
    return value.encode().ljust(size, b"\0")


def ticket_id(title_id: str) -> int:
    """The ticket's id: TICKET_ID_BASE and the title's low word; an add-on content title's is its title id, so the game
    data's ticket never shares its application's id."""
    value = int(title_id, 16)
    return value if is_addon(title_id) else TICKET_ID_BASE | value & 0xFFFFFFFF


def build_ticket(title_id: str) -> bytes:
    """A permanent ticket for every console, signature zeros, title key zeros (the content is not encrypted)."""
    out = bytearray(TICKET_SIZE)
    struct.pack_into(">I", out, 0, RSA2048_SHA256)
    out[0x140:0x180] = _text(TICKET_ISSUER, ISSUER_SIZE)
    out[0x1BC] = 1                                                    # format version
    struct.pack_into(">Q", out, 0x1D0, ticket_id(title_id))
    struct.pack_into(">Q", out, 0x1DC, int(title_id, 16))
    out[0x1F0] = 0                                                    # licence type: permanent
    out[0x1F1] = 0                                                    # common key index
    out[0x2A4:0x2A4 + len(CONTENT_INDEX_HEADER)] = CONTENT_INDEX_HEADER
    # content 0, after the segment's 4-byte level: bit `1 << (index & 7)` (makerom tik.c), unlike the CIA header's
    out[0x2A4 + len(CONTENT_INDEX_HEADER) + 4] = 0x01
    return bytes(out)


def build_tmd(title_id: str, save_size: int, content_size: int = 0, content_hash: bytes = bytes(32),
              title_version: int | None = None) -> bytes:
    """The TMD of one content (id 0, index 0, type 0: not encrypted) of `content_size` bytes and SHA-256.
    `title_version` (major << 10 | minor << 4 | micro): by default 1.0.0 for an update title, 0 for a base title."""
    if title_version is None:
        title_version = UPDATE_TITLE_VERSION if is_update(title_id) else 0
    section = SIGNATURE_BYTES[RSA2048_SHA256]
    chunk = struct.pack(">IHHQ", 0, 0, 0, content_size) + content_hash
    info = struct.pack(">HH", 0, 1) + sha256(chunk)                   # index offset, command count, hash of chunks
    infos = info + bytes(0x24 * 63)
    out = bytearray(section + TMD_HEADER)
    struct.pack_into(">I", out, 0, RSA2048_SHA256)
    out[section:section + ISSUER_SIZE] = _text(TMD_ISSUER, ISSUER_SIZE)
    out[section + 0x40] = 1                                           # format version
    struct.pack_into(">Q", out, section + 0x4C, int(title_id, 16))
    struct.pack_into(">I", out, section + 0x54, TITLE_TYPE_CTR)
    struct.pack_into("<I", out, section + 0x5A, save_size)            # save data size: little endian, as makerom
    struct.pack_into(">H", out, section + 0x9C, title_version)
    struct.pack_into(">H", out, section + 0x9E, 1)                    # content count
    out[section + 0xA4:section + 0xC4] = sha256(infos)
    return bytes(out) + infos + chunk


def build_header(cert_size: int, ticket_size: int, tmd_size: int, meta_size: int, content_size: int) -> bytes:
    out = bytearray(CIA_HEADER_SIZE)
    struct.pack_into("<IHHIIIIQ", out, 0, CIA_HEADER_SIZE, 0, 0, cert_size, ticket_size, tmd_size, meta_size,
                     content_size)
    out[0x20] = 0x80                                                  # content index: content 0
    return bytes(out)


def build_meta(exheader: bytes, smdh: bytes) -> bytes:
    if len(smdh) != SMDH_SIZE:
        raise ValueError(f"an SMDH has {SMDH_SIZE:#x} bytes, not {len(smdh):#x}")
    out = bytearray(META_SIZE)
    out[:DEPENDENCIES_SIZE] = exheader[DEPENDENCIES:DEPENDENCIES + DEPENDENCIES_SIZE]
    out[0x300:0x304] = exheader[CORE_VERSION:CORE_VERSION + 4]
    out[0x400:] = smdh
    return bytes(out)


def write_cia(out: BinaryIO, title_id: str, ncch: Ncch, meta_smdh: bytes | None, progress=None,
              certificates: bytes | None = None, save_size: int | None = None,
              title_version: int | None = None) -> None:
    """Write the CIA of `ncch` into `out`, a seekable file. The content is streamed once, hashed on the way, and
    the TMD (written first as a placeholder) is filled afterwards. `save_size`: the TMD's, by default the
    exheader's; an update title's is 0, as the official update's TMD has it. `title_version`: build_tmd's. `ncch` may
    be a `Cfa` (no exheader): no save data, no meta section."""
    if ncch.title_id.lower() != title_id.lower():
        raise ValueError(f"the NCCH is for {ncch.title_id}, not {title_id}")
    certs = certificate_chain() if certificates is None else certificates
    ticket = build_ticket(title_id)
    if save_size is None:
        save_size = save_data_size(ncch.exheader) if ncch.exheader is not None else 0
    tmd = build_tmd(title_id, save_size, ncch.size, title_version=title_version)
    meta = build_meta(ncch.exheader, meta_smdh) if meta_smdh is not None and ncch.exheader is not None else b""
    start = out.tell()
    header = build_header(len(certs), len(ticket), len(tmd), len(meta), ncch.size)
    sections = [header, certs, ticket]
    tmd_at = sum(align(len(s), CIA_ALIGNMENT) for s in sections)
    for section in (*sections, tmd):
        out.write(section)
        out.write(bytes(align(len(section), CIA_ALIGNMENT) - len(section)))
    digest = hashlib.sha256()
    written = 0
    for chunk in ncch.chunks(progress):
        digest.update(chunk)
        written += len(chunk)
        out.write(chunk)
    if written != ncch.size:
        raise ValueError(f"the NCCH gave {written} bytes, not the {ncch.size} it announced")
    out.write(bytes(align(written, CIA_ALIGNMENT) - written))
    if meta:
        out.write(meta)
        out.write(bytes(align(len(meta), CIA_ALIGNMENT) - len(meta)))
    end = out.tell()
    out.seek(start + tmd_at)
    out.write(build_tmd(title_id, save_size, ncch.size, digest.digest(), title_version))
    out.seek(end)
