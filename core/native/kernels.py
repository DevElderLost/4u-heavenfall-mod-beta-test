"""Typed calls of the native kernels. Each returns its twin's result, or None when the
library is absent, turned off or refuses the input: the caller then runs its Python twin, which gives the same
result or raises its own error. Buffers go by address, with their lengths; nothing here holds a tuning value.
ctypes is imported only once the library is there (a browser's Python has none to load)."""

from array import array
from functools import cache
from itertools import chain

from core import native

# The kernels' parameters: p a buffer's address, q an int64, u a uint32, d a double (src/*.c).
SIGNATURES = {
    "hf_blz_decompress": "pqpq",
    "hf_to_canonical": "pqpqupppqppppqpqppq",
    "hf_coplanar_counts": "pqpqpqdddpqqpq",
    "hf_sink_meshes": "pqppqddpqq",
}


@cache
def _bound(lib, name: str):
    import ctypes
    types = {"p": ctypes.c_void_p, "q": ctypes.c_int64, "u": ctypes.c_uint32, "d": ctypes.c_double}
    function = getattr(lib, name)
    function.restype, function.argtypes = ctypes.c_int, [types[kind] for kind in SIGNATURES[name]]
    return function


def _call(name: str, *args) -> bool:
    """Run a kernel (the library is loaded): whether it did the job rather than refuse."""
    return _bound(native.library(), name)(*args) == 0


def _address(buffer) -> int:
    """The address of a bytes, bytearray or array's first byte (0 when empty); the caller keeps the buffer alive and
    its size unchanged during the call."""
    import ctypes
    if not len(buffer):
        return 0
    if isinstance(buffer, bytes):
        return ctypes.cast(ctypes.c_char_p(buffer), ctypes.c_void_p).value
    if isinstance(buffer, array):
        return buffer.buffer_info()[0]
    return ctypes.addressof((ctypes.c_char * len(buffer)).from_buffer(buffer))


def _int64s(values) -> array | None:
    try:
        return array("q", values)
    except (OverflowError, TypeError):
        return None


def blz_decompress(data: bytes) -> bytes | None:
    """extract._blz_decompress."""
    if native.library() is None or len(data) < 8:
        return None
    data = bytes(data)
    out = bytearray(data) + bytes(int.from_bytes(data[-4:], "little"))
    return bytes(out) if _call("hf_blz_decompress", _address(data), len(data), _address(out), len(out)) else None


def to_canonical(code: bytes, version, base: int, trap: int) -> bytes | None:
    """canonical._to_canonical of a version that is not canonical (`base`, `trap`: canonical.BASE and TRAP)."""
    if native.library() is None or not 0 <= trap < 2**32 or not -2**62 < base < 2**62:
        return None
    code = bytes(code)
    by_version = sorted(version.runs, key=lambda run: run.start + run.delta)     # as VersionMap sorts them
    columns = [_int64s(values) for values in (
        [run.start for run in version.runs], [run.end for run in version.runs], [run.delta for run in version.runs],
        [run.start + run.delta for run in by_version], [run.end + run.delta for run in by_version],
        [run.delta for run in by_version], version.branch_slots, version.pointer_slots,
        [start for start, _ in version.holes], [stop for _, stop in version.holes])]
    if any(column is None for column in columns):
        return None
    starts, ends, deltas, v_starts, v_ends, v_deltas, branches, pointers, hole_starts, hole_stops = columns
    out = bytearray(len(code))
    done = _call("hf_to_canonical", _address(code), len(code), _address(out), base, trap,
                 _address(starts), _address(ends), _address(deltas), len(starts),
                 _address(v_starts), _address(v_ends), _address(v_deltas),
                 _address(branches), len(branches), _address(pointers), len(pointers),
                 _address(hole_starts), _address(hole_stops), len(hole_starts))
    return bytes(out) if done else None


def coplanar_counts(mod: bytes, samples, margin: float, cell: float, parallel: float, formats, bone_size: int,
                    only=None) -> list[int] | None:
    """felyne_face's count per mesh of `mod` (0 for one not in `only`), before it drops the zeros. `samples`: the
    float 6-tuples (point, unit normal) face_samples makes."""
    if native.library() is None or len(mod) < 10:
        return None
    mod = bytes(mod)
    mesh_count = int.from_bytes(mod[8:10], "little")
    try:
        flat = array("d", chain.from_iterable(samples))
    except (TypeError, OverflowError):
        return None
    if len(flat) != 6 * len(samples):         # a sample of another length: the twin decides what it means
        return None
    mask = None if only is None else bytes(mesh in only for mesh in range(mesh_count))
    counts = array("q", bytes(8 * mesh_count))
    formats = array("I", sorted(formats))
    done = _call("hf_coplanar_counts", _address(mod), len(mod), 0 if mask is None else _address(mask),
                 0 if mask is None else len(mask), _address(flat), len(flat) // 6, margin, cell, parallel,
                 _address(formats), len(formats), bone_size, _address(counts), mesh_count)
    return counts.tolist() if done else None


def sink_meshes(mod: bytes, meshes, depth: float, weld: float, formats, bone_size: int) -> bytes | None:
    """felyne_face.sink_meshes (`weld`: its WELD)."""
    if native.library() is None:
        return None
    mod = bytes(mod)
    order = _int64s(sorted(meshes))
    if order is None:
        return None
    out = bytearray(mod)
    formats = array("I", sorted(formats))
    done = _call("hf_sink_meshes", _address(mod), len(mod), _address(out), _address(order), len(order), depth, weld,
                 _address(formats), len(formats), bone_size)
    return bytes(out) if done else None
