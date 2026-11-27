"""The console release's shared file (.hfpack) and the console sets' source stamp.

The shared file holds the files every patch set of a release has the same bytes of, by RomFS path, each named by its
catalogue number. Each set copies them from it (source kind 4, format 3) instead of carrying them as literal bytes, and
the 3DS app downloads it once and keeps it on the SD card. One file for both regions, with and without MH XX and the
cheats. It is made from the checkout's own files, the same bytes on the PC (tools/release/build_console_patches.py) and
in the release workflow (tools/release/console_sets.py), so it is never kept in git.

Little-endian:

    Header, 0x20 bytes: "HFSH", u32 format (1), u32 entries, u32 index length, u64 total length, u64 0.
    Index at 0x20, one record per entry in name order (UTF-8 bytes): u64 offset, u64 size, 32-byte SHA-256,
        u32 name length, u32 0, the name (padded to 4).
    The entries' bytes, in the index's order, the first right after the index.

The source stamp is what a set was made from: the SHA-256 digest of the edition's exported `core/` files
(`tree_digest`). The export refuses a set of another stamp and the workflow checks it against its checkout.

Standard library only: the release workflow runs it with the runner's own Python.
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"HFSH"
FORMAT = 1
HEADER = 0x20
RECORD = 0x38                     # an index record before its name
SUFFIX = "-shared.hfpack"         # the release file: the app's CIA name without ".cia", then this
CATALOGUE = "core/game/data/curated/jukebox.json"
SHARED_FOLDER = "sound/bgm/jukebox"    # core/music/jukebox/queue.py, SHIPPED_FOLDER
SHARED_SOURCE = "extra"                # the catalogue's entries the mod ships from the checkout and every set shares
STAMP_FOLDER = "core/"                 # the exported files the source stamp covers


class SharedFileError(ValueError):
    pass


@dataclass(frozen=True)
class SharedEntry:
    name: str
    offset: int
    size: int
    sha256: bytes


def write_shared(files: dict[str, bytes]) -> bytes:
    """The shared file holding `files` ({RomFS path: bytes}), always the same bytes for the same files."""
    names = sorted(files, key=lambda name: name.encode("utf-8"))
    if not names or any(not name or name.startswith("/") or "\\" in name for name in names):
        raise SharedFileError("a shared file holds at least one file, each by a RomFS path")
    index_len = sum(RECORD + _padded(len(name.encode("utf-8"))) for name in names)
    at = HEADER + index_len
    index, body = bytearray(), bytearray()
    for name in names:
        data, raw = files[name], name.encode("utf-8")
        index += struct.pack("<QQ32sII", at, len(data), hashlib.sha256(data).digest(), len(raw), 0)
        index += raw + bytes(_padded(len(raw)) - len(raw))
        body += data
        at += len(data)
    head = struct.pack("<4sIIIQQ", MAGIC, FORMAT, len(names), index_len, at, 0)
    return head + bytes(index) + bytes(body)


def parse_shared(blob: bytes, check: bool = True) -> dict[str, SharedEntry]:
    """The entries of a shared file by name; with `check`, every entry's SHA-256 checked. SharedFileError for a file
    that is not one, is cut or damaged."""
    if len(blob) < HEADER:
        raise SharedFileError("not a shared file")
    magic, form, count, index_len, total, zero = struct.unpack_from("<4sIIIQQ", blob, 0)
    if magic != MAGIC or form != FORMAT or zero:
        raise SharedFileError("not a shared file of a format this program reads")
    if total != len(blob) or HEADER + index_len > total:
        raise SharedFileError("the shared file is cut or its header is wrong")
    entries, at, end, data_at = {}, HEADER, HEADER + index_len, HEADER + index_len
    for _ in range(count):
        if at + RECORD > end:
            raise SharedFileError("the shared file's index is cut")
        offset, size, sha, name_len, reserved = struct.unpack_from("<QQ32sII", blob, at)
        name = blob[at + RECORD:at + RECORD + name_len].decode("utf-8")
        at += RECORD + _padded(name_len)
        if reserved or at > end or offset != data_at or offset + size > total or name in entries or not name:
            raise SharedFileError(f"the shared file's index is wrong at {name!r}")
        if check and hashlib.sha256(blob[offset:offset + size]).digest() != sha:
            raise SharedFileError(f"the shared file's {name} is damaged")
        entries[name] = SharedEntry(name, offset, size, sha)
        data_at = offset + size
    if at != end or data_at != total:
        raise SharedFileError("the shared file does not end where its index says")
    return entries


def read_entry(blob: bytes, entry: SharedEntry) -> bytes:
    return blob[entry.offset:entry.offset + entry.size]


def shared_name(app_cia: str) -> str:
    """The shared file's release name: "<app>-3ds.cia" -> "<app>-3ds-shared.hfpack" (core/app/edition.py,
    ConsoleRelease.shared_file; hf_editions.h's asset_shared)."""
    if not app_cia.endswith(".cia"):
        raise SharedFileError(f"{app_cia} is not a CIA's name")
    return app_cia.removesuffix(".cia") + SUFFIX


def entry_name(number: int) -> str:
    """The RomFS path the mod ships the catalogue's entry `number` at (core/music/jukebox/build.py, shipped_file, which
    a test keeps equal)."""
    return f"{SHARED_FOLDER}/t{number}.mca"


def shared_entries(read) -> list[tuple[int, str]]:
    """(number, checkout path) of the catalogue's entries every set shares: source SHARED_SOURCE, not retired.
    `read(rel)`: a checkout file's bytes."""
    catalogue = json.loads(read(CATALOGUE).decode("utf-8"))
    return [(t["id"], t["path"]) for t in catalogue["tracks"]
            if t.get("source") == SHARED_SOURCE and not t.get("retired")]


def shared_files(root: Path | None = None, read=None) -> dict[str, bytes]:
    """{RomFS path: bytes} of the shared file made from the checkout `root`, or from `read(rel)` (a checkout file's
    bytes: the export gives the bytes it writes)."""
    read = read or (lambda rel: (Path(root) / rel).read_bytes())
    files = {}
    for number, path in shared_entries(read):
        name = entry_name(number)
        if name in files:
            raise SharedFileError(f"two entries of the catalogue are both {name}")
        files[name] = read(path)
    return files


def tree_digest(files) -> bytes:
    """The source stamp of `files` ((path, bytes) pairs): SHA-256 over the sorted paths, each its UTF-8 path, a NUL and
    the SHA-256 of its bytes with CRLF read as LF (a checkout on Windows may hold either), one line each."""
    digest = hashlib.sha256()
    for path, data in sorted(files, key=lambda item: item[0].encode("utf-8")):
        digest.update(path.encode("utf-8") + b"\0" + hashlib.sha256(data.replace(b"\r\n", b"\n")).digest() + b"\n")
    return digest.digest()


def checkout_tree_digest(root: Path) -> bytes:
    """The source stamp of a checkout of an exported edition: its `core/` files as git lists them."""
    done = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", STAMP_FOLDER], capture_output=True,
                          check=True)
    paths = [p for p in done.stdout.decode("utf-8").split("\0") if p]
    if not paths:
        raise SharedFileError(f"git lists no {STAMP_FOLDER} files in {root}")
    return tree_digest((path, (Path(root) / path).read_bytes()) for path in paths)


def _padded(n: int) -> int:
    return (n + 3) // 4 * 4
