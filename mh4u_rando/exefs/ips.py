"""IPS patches ("PATCH" ... "EOF"), the format Citra loads as exefs/code.ips."""

HEADER = b"PATCH"
FOOTER = b"EOF"
MAX_OFFSET = 0xFFFFFF
MAX_RECORD = 0xFFFF
# A record must not start at 0x454F46 or it reads as the footer.
EOF_OFFSET = 0x454F46
# Equal stretches are skipped this many bytes at a time (the executable is ~10 MB, the changes a few KB).
CHUNK = 0x1000


class IpsError(ValueError):
    pass


def _next_difference(original: bytes, modified: bytes, i: int) -> int:
    """The first offset from `i` where the buffers differ, or their length."""
    size = len(original)
    while i < size:
        end = min(i + CHUNK, size)
        if original[i:end] != modified[i:end]:
            while original[i] == modified[i]:
                i += 1
            return i
        i = end
    return size


def make_ips(original: bytes, modified: bytes) -> bytes:
    """Patch turning `original` into `modified` (same length, changed bytes only)."""
    if len(original) != len(modified):
        raise IpsError("IPS patches cannot change the file size")
    out = bytearray(HEADER)
    size = len(original)
    i = _next_difference(original, modified, 0)
    while i < size:
        start = i
        if start == EOF_OFFSET:
            start -= 1
        end = i
        # Merge changes separated by a few equal bytes: cheaper than a new record header.
        while end < size and end - start < MAX_RECORD:
            if original[end] != modified[end]:
                end += 1
                continue
            gap = end
            while gap < size and gap - end < 5 and original[gap] == modified[gap]:
                gap += 1
            if gap < size and gap - end < 5 and original[gap] != modified[gap]:
                end = gap
            else:
                break
        end = min(end, start + MAX_RECORD)
        if start > MAX_OFFSET:
            raise IpsError(f"offset {start:#x} does not fit in an IPS patch")
        out += start.to_bytes(3, "big") + (end - start).to_bytes(2, "big") + modified[start:end]
        i = _next_difference(original, modified, end)
    out += FOOTER
    return bytes(out)


def apply_ips(original: bytes, patch: bytes) -> bytes:
    if not patch.startswith(HEADER):
        raise IpsError("not an IPS patch")
    out = bytearray(original)
    pos = len(HEADER)
    while patch[pos:pos + 3] != FOOTER:
        offset = int.from_bytes(patch[pos:pos + 3], "big")
        length = int.from_bytes(patch[pos + 3:pos + 5], "big")
        pos += 5
        if length:
            data = patch[pos:pos + length]
            pos += length
        else:  # RLE record
            run = int.from_bytes(patch[pos:pos + 2], "big")
            data = patch[pos + 2:pos + 3] * run
            pos += 3
        if offset + len(data) > len(out):
            out.extend(bytes(offset + len(data) - len(out)))
        out[offset:offset + len(data)] = data
    return bytes(out)
