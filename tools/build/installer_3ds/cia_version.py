"""Writes a release's version into the launcher CIA's TMD and ticket: the title version is major (6 bits), minor (6),
micro (4), as launcher.h's hf_tmd_version. makerom 0.19 drops the minor (its -minor, -ver and the RSF's
RemasterVersion alike), and AM does not import the app's own update over an installed launcher of the same or a
higher version, so a release going from 0.1.x to 0.2.0 would never install itself.

Usage: python cia_version.py <file.cia> <major.minor.micro>. Refuses (exit 1, the file untouched) a version that does
not fit and a file not laid out as makerom's CIA."""

import struct
import sys
from pathlib import Path

SIGNATURES = {0x10000: 0x200, 0x10001: 0x100, 0x10002: 0x3C, 0x10003: 0x200, 0x10004: 0x100, 0x10005: 0x3C}
TICKET_ID, TICKET_VERSION = 0x9C, 0xA6      # in the ticket's body, after its signature
TMD_ID, TMD_VERSION = 0x4C, 0x9C            # in the TMD's header, after its signature


def align(n: int) -> int:
    return (n + 63) // 64 * 64


def title_version(text: str) -> int:
    parts = text.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"{text!r} is not major.minor.micro")
    major, minor, micro = (int(p) for p in parts)
    if major > 63 or minor > 63 or micro > 15:
        raise ValueError(f"{text} does not fit a title version (major and minor up to 63, micro up to 15)")
    return major << 10 | minor << 4 | micro


def body(data: bytes, at: int) -> int:
    """Where a signed block's body starts: its signature type, the signature, padding to 64 bytes."""
    if at + 4 > len(data):
        raise ValueError("the file is cut")
    kind = struct.unpack_from(">I", data, at)[0]
    if kind not in SIGNATURES:
        raise ValueError(f"unknown signature type 0x{kind:X} at 0x{at:X}")
    return at + align(4 + SIGNATURES[kind])


def set_version(data: bytearray, version: int) -> None:
    if len(data) < 0x20:
        raise ValueError("the file is cut")
    header, _, _, certs, ticket, tmd = struct.unpack_from("<IHHIII", data, 0)
    ticket_at = align(header) + align(certs)
    tmd_at = ticket_at + align(ticket)
    ticket_body, tmd_body = body(data, ticket_at), body(data, tmd_at)
    if tmd_at + tmd > len(data) or ticket_body + TICKET_VERSION + 2 > tmd_at:
        raise ValueError("the file is cut")
    ticket_id = struct.unpack_from(">Q", data, ticket_body + TICKET_ID)[0]
    tmd_id = struct.unpack_from(">Q", data, tmd_body + TMD_ID)[0]
    if ticket_id != tmd_id:
        raise ValueError(f"the ticket names {ticket_id:016X} and the TMD {tmd_id:016X}")
    struct.pack_into(">H", data, ticket_body + TICKET_VERSION, version)
    struct.pack_into(">H", data, tmd_body + TMD_VERSION, version)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    path = Path(argv[0])
    data = bytearray(path.read_bytes())
    try:
        set_version(data, title_version(argv[1]))
    except ValueError as error:
        print(f"cia_version: {path.name}: {error}", file=sys.stderr)
        return 1
    path.write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
