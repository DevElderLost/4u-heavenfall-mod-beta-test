"""MH Generations' message files (GMD, version 0x00010302).

Header (0x28 bytes): "GMD\\0", u32 version, u32 language (0 jpn, 1 eng, 2 fre, 3 spa, 4 ger, 5 ita), 8 unknown
bytes, u32 label count, u32 string count, u32 label blob size, u32 string blob size, u32 name length. Then the
file's name and a NUL; with labels, 20 bytes per label, 256 u32 buckets and the label blob; then the strings,
each ending in a NUL. Message i is the i-th string. The equipment tables have no labels.
"""

import struct

MAGIC = b"GMD\x00"
HEADER = struct.Struct("<4sIIQIIIII")
LABEL = 20
BUCKETS = 0x400


class GmdError(ValueError):
    pass


def gmd_strings(data: bytes) -> list[str]:
    """Every message of a GMD file, in order."""
    if data[:4] != MAGIC:
        raise GmdError("not a GMD")
    _, _, _, _, labels, count, label_size, string_size, name_size = HEADER.unpack_from(data)
    at = HEADER.size + name_size + 1
    if labels:
        at += LABEL * labels + BUCKETS + label_size
    if at + string_size != len(data):
        raise GmdError(f"the strings end at {at + string_size:#x}, the file's size is {len(data):#x}")
    parts = data[at:].split(b"\x00")
    if parts[-1] or len(parts) - 1 != count:
        raise GmdError(f"{len(parts) - 1} strings, the header says {count}")
    return [part.decode("utf-8") for part in parts[:-1]]
