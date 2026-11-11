"""Heavenfall's native kernels: a C library (src/, built by tools/build/build_native.py into lib/<platform>/) that does
the numeric work of a few hot functions, each the exact twin of a Python function.

The library is optional: without it, or when it is refused, every caller runs its Python twin and gets the same
bytes. It is loaded with ctypes (no tie to a Python version), only if its file exists, and refused when its ABI is not
ABI or, in a checkout that has the sources, when it was built from other sources than these (rebuild it). Setting
HEAVENFALL_NATIVE=0 turns it off. `kernels` holds the typed calls.
"""

import hashlib
import os
import platform
import sys
from functools import cache
from pathlib import Path

ABI = 1                                    # src/heavenfall_native.h, HF_ABI
HERE = Path(__file__).resolve().parent
SOURCES = HERE / "src"
LIBRARIES = HERE / "lib"
OFF_ENV = "HEAVENFALL_NATIVE"
# The library's file per platform tag (the tags build_native.py builds).
FILES = {"win_amd64": "heavenfall_native.dll"}
# How the library is compiled and linked (zig cc): part of the source hash, so a change of flags asks for a rebuild.
FLAGS = ("-shared", "-s", "-std=c11", "-O2", "-ffp-contract=off", "-fno-fast-math", "-fno-math-errno",
         "-fno-strict-aliasing", "-Wall", "-Wextra", "-Werror")
TARGETS = {"win_amd64": ("x86_64-windows-gnu", "baseline")}     # tag -> (zig target, cpu)
HASH_MARK = b"HFNATIVE-SRC:"               # the library's file holds its source hash after this (src/abi.c)


def platform_tag() -> str | None:
    """This interpreter's tag among FILES (None for a platform with no library)."""
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64") and sys.maxsize > 2**32:
        return "win_amd64"
    return None


def library_path(tag: str | None = None) -> Path | None:
    tag = tag or platform_tag()
    return LIBRARIES / tag / FILES[tag] if tag in FILES else None


def source_files() -> list[Path]:
    return sorted(SOURCES.glob("*.[ch]")) if SOURCES.is_dir() else []


def source_hash() -> str | None:
    """sha256 of the sources (line ends made LF), the flags, the targets and the ABI; None without sources (an
    installed program, an edition)."""
    files = source_files()
    if not files:
        return None
    digest = hashlib.sha256(f"abi {ABI}\nflags {' '.join(FLAGS)}\ntargets {sorted(TARGETS.items())}\n".encode())
    for path in files:
        digest.update(path.name.encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def embedded_hash(path: Path) -> str | None:
    """The source hash a library's file holds (HASH_MARK), read without loading it; None for none."""
    data = path.read_bytes() if path.is_file() else b""
    at = data.find(HASH_MARK)
    return data[at + len(HASH_MARK):at + len(HASH_MARK) + 64].decode("ascii", "replace") if at >= 0 else None


@cache
def _load():
    """(library, why): the loaded library, or None and the reason."""
    path = library_path()
    if path is None:
        return None, f"no library for this platform ({sys.platform}, {platform.machine()})"
    if not path.is_file():
        return None, f"{path.name} is absent"
    import ctypes
    try:
        lib = ctypes.CDLL(str(path))
    except OSError as error:
        return None, f"{path.name} does not load: {error}"
    lib.hf_abi.restype, lib.hf_abi.argtypes = ctypes.c_int, []
    lib.hf_source.restype, lib.hf_source.argtypes = ctypes.c_char_p, []
    if lib.hf_abi() != ABI:
        return None, f"{path.name} has ABI {lib.hf_abi()}, not {ABI}: rebuild it (tools/build/build_native.py)"
    expected = source_hash()
    if expected is not None and lib.hf_source().decode("ascii") != expected:
        return None, f"{path.name} was built from other sources: rebuild it (tools/build/build_native.py)"
    return lib, f"{path.name} loaded"


def library():
    """The loaded library, or None (absent, refused, or turned off with HEAVENFALL_NATIVE=0)."""
    if os.environ.get(OFF_ENV) == "0":
        return None
    return _load()[0]


def available() -> bool:
    return library() is not None


def status() -> str:
    """Why the kernels run natively or not, in a line."""
    if os.environ.get(OFF_ENV) == "0":
        return f"turned off ({OFF_ENV}=0)"
    return _load()[1]
