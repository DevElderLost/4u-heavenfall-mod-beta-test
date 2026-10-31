"""Minimal PNG reader and writer (any non-interlaced PNG in, 8-bit RGBA out), so icons need no image library.

Pixels are RGBA bytes, row by row from the top-left corner.
"""

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Colour type -> (channels, allowed bit depths): grey, RGB, palette, grey + alpha, RGBA.
COLOUR_TYPES = {0: (1, (1, 2, 4, 8, 16)), 2: (3, (8, 16)), 3: (1, (1, 2, 4, 8)), 4: (2, (8, 16)), 6: (4, (8, 16))}


class PngFormatError(ValueError):
    pass


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def write_png(width: int, height: int, rgba: bytes) -> bytes:
    if len(rgba) != width * height * 4:
        raise PngFormatError(f"{len(rgba)} bytes for a {width}x{height} RGBA image")
    stride = width * 4
    raw = b"".join(b"\0" + rgba[y * stride:(y + 1) * stride] for y in range(height))
    return (SIGNATURE + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def _samples(row: bytes, depth: int, count: int) -> list[int]:
    """`count` samples of a row (1, 2, 4, 8 or 16 bits each, 16 bits keep their high byte)."""
    if depth == 8:
        return list(row[:count])
    if depth == 16:
        return list(row[0:2 * count:2])
    per_byte, mask = 8 // depth, (1 << depth) - 1
    return [(row[i // per_byte] >> (8 - depth * (i % per_byte + 1))) & mask for i in range(count)]


def read_png(data: bytes) -> tuple[int, int, bytes]:
    """(width, height, RGBA bytes) of a PNG: greyscale, RGB, palette, with or without alpha or tRNS, 1 to 16
    bits per sample, not interlaced (what image editors write by default)."""
    if not data.startswith(SIGNATURE):
        raise PngFormatError("not a PNG file")
    pos, header, idat, palette, trns = len(SIGNATURE), None, bytearray(), b"", b""
    while pos + 8 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + length
    if header is None:
        raise PngFormatError("no IHDR chunk")
    width, height, depth, colour, _, _, interlace = header
    if colour not in COLOUR_TYPES or depth not in COLOUR_TYPES[colour][1]:
        raise PngFormatError(f"unsupported PNG (colour type {colour}, {depth} bits)")
    if interlace:
        raise PngFormatError("interlaced PNGs are not supported: save it without interlacing")
    if colour == 3 and not palette:
        raise PngFormatError("palette PNG without a palette")
    channels = COLOUR_TYPES[colour][0]
    bpp = max(1, channels * depth // 8)                 # bytes per pixel for the filters
    stride = (width * channels * depth + 7) // 8
    raw = zlib.decompress(bytes(idat))
    scale = 255 // ((1 << depth) - 1) if depth < 8 else 1  # greyscale sample -> 0..255
    key = struct.unpack(f">{len(trns) // 2}H", trns) if colour in (0, 2) and trns else None
    prev = bytearray(stride)
    pixels = bytearray()
    for y in range(height):
        kind = raw[y * (stride + 1)]
        row = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            left = row[i - bpp] if i >= bpp else 0
            up_left = prev[i - bpp] if i >= bpp else 0
            row[i] = (row[i] + (0, left, prev[i], (left + prev[i]) // 2,
                                _paeth(left, prev[i], up_left))[kind]) & 0xFF
        prev = row
        if key is not None:  # a colour key compares full samples, before 16 bits are cut to 8
            full = (_samples(row, depth, width * channels) if depth < 16
                    else list(struct.unpack(f">{width * channels}H", row)))
        values = _samples(row, depth, width * channels)
        for x in range(width):
            v = values[x * channels:(x + 1) * channels]
            if colour == 3:
                index = v[0]
                rgb = palette[3 * index:3 * index + 3]
                alpha = trns[index] if index < len(trns) else 255
            elif colour in (0, 4):
                grey = v[0] * scale
                rgb, alpha = bytes((grey,) * 3), v[1] if colour == 4 else 255
            else:
                rgb, alpha = bytes(v[:3]), v[3] if colour == 6 else 255
            if key is not None and tuple(full[x * channels:(x + 1) * channels]) == key[:channels]:
                alpha = 0
            pixels += rgb + bytes((alpha,))
    return width, height, bytes(pixels)
