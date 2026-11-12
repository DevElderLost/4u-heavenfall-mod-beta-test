"""CityHash64 (CityHash v1.1), the hash Citra and Azahar name custom textures with. A port in plain Python: the program
carries no library for it, and it only hashes a few textures of an install.

Copyright (c) 2011 Google, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import struct

K0 = 0xC3A5C85C97CB3127
K1 = 0xB492B66FBE98F273
K2 = 0x9AE16A3B2F90404F
HASH_MUL = 0x9DDFEA08EB382D69
MASK = (1 << 64) - 1


def _fetch64(data: bytes, at: int) -> int:
    return struct.unpack_from("<Q", data, at)[0]


def _fetch32(data: bytes, at: int) -> int:
    return struct.unpack_from("<I", data, at)[0]


def _rotate(value: int, shift: int) -> int:
    return value if shift == 0 else (value >> shift | value << (64 - shift)) & MASK


def _shift_mix(value: int) -> int:
    return value ^ value >> 47


def _swap(value: int) -> int:
    return int.from_bytes(value.to_bytes(8, "little"), "big")


def _hash16(u: int, v: int, mul: int = HASH_MUL) -> int:
    a = (u ^ v) * mul & MASK
    a ^= a >> 47
    b = (v ^ a) * mul & MASK
    b ^= b >> 47
    return b * mul & MASK


def _hash_0_to_16(data: bytes, length: int) -> int:
    if length >= 8:
        mul = K2 + length * 2
        a = (_fetch64(data, 0) + K2) & MASK
        b = _fetch64(data, length - 8)
        c = (_rotate(b, 37) * mul + a) & MASK
        d = (_rotate(a, 25) + b) * mul & MASK
        return _hash16(c, d, mul & MASK)
    if length >= 4:
        mul = K2 + length * 2
        return _hash16(length + (_fetch32(data, 0) << 3), _fetch32(data, length - 4), mul & MASK)
    if length > 0:
        y = data[0] + (data[length >> 1] << 8)
        z = length + (data[length - 1] << 2)
        return _shift_mix((y * K2 ^ z * K0) & MASK) * K2 & MASK
    return K2


def _hash_17_to_32(data: bytes, length: int) -> int:
    mul = K2 + length * 2
    a = _fetch64(data, 0) * K1 & MASK
    b = _fetch64(data, 8)
    c = _fetch64(data, length - 8) * mul & MASK
    d = _fetch64(data, length - 16) * K2 & MASK
    return _hash16((_rotate((a + b) & MASK, 43) + _rotate(c, 30) + d) & MASK,
                   (a + _rotate((b + K2) & MASK, 18) + c) & MASK, mul & MASK)


def _hash_33_to_64(data: bytes, length: int) -> int:
    mul = K2 + length * 2
    a = _fetch64(data, 0) * K2 & MASK
    b = _fetch64(data, 8)
    c = _fetch64(data, length - 24)
    d = _fetch64(data, length - 32)
    e = _fetch64(data, 16) * K2 & MASK
    f = _fetch64(data, 24) * 9 & MASK
    g = _fetch64(data, length - 8)
    h = _fetch64(data, length - 16) * mul & MASK
    u = (_rotate((a + g) & MASK, 43) + (_rotate(b, 30) + c) * 9) & MASK
    v = (((a + g) & MASK ^ d) + f + 1) & MASK
    w = (_swap((u + v) * mul & MASK) + h) & MASK
    x = (_rotate((e + f) & MASK, 42) + c) & MASK
    y = (_swap((v + w) * mul & MASK) + g) * mul & MASK
    z = (e + f + c) & MASK
    a = (_swap(((x + z) * mul + y) & MASK) + b) & MASK
    b = _shift_mix(((z + a) * mul + d + h) & MASK) * mul & MASK
    return (b + x) & MASK


def _weak_hash32(data: bytes, at: int, a: int, b: int) -> tuple[int, int]:
    w, x, y, z = struct.unpack_from("<4Q", data, at)
    a = (a + w) & MASK
    b = _rotate((b + a + z) & MASK, 21)
    c = a
    a = (a + x + y) & MASK
    b = (b + _rotate(a, 44)) & MASK
    return (a + z) & MASK, (b + c) & MASK


def city_hash64(data: bytes) -> int:
    """The 64-bit hash of `data`."""
    length = len(data)
    if length <= 16:
        return _hash_0_to_16(data, length)
    if length <= 32:
        return _hash_17_to_32(data, length)
    if length <= 64:
        return _hash_33_to_64(data, length)

    x = _fetch64(data, length - 40)
    y = (_fetch64(data, length - 16) + _fetch64(data, length - 56)) & MASK
    z = _hash16((_fetch64(data, length - 48) + length) & MASK, _fetch64(data, length - 24))
    v = _weak_hash32(data, length - 64, length, z)
    w = _weak_hash32(data, length - 32, (y + K1) & MASK, x)
    x = (x * K1 + _fetch64(data, 0)) & MASK

    for at in range(0, (length - 1) & ~63, 64):
        x = _rotate((x + y + v[0] + _fetch64(data, at + 8)) & MASK, 37) * K1 & MASK
        y = _rotate((y + v[1] + _fetch64(data, at + 48)) & MASK, 42) * K1 & MASK
        x ^= w[1]
        y = (y + v[0] + _fetch64(data, at + 40)) & MASK
        z = _rotate((z + w[0]) & MASK, 33) * K1 & MASK
        v = _weak_hash32(data, at, v[1] * K1 & MASK, (x + w[0]) & MASK)
        w = _weak_hash32(data, at + 32, (z + w[1]) & MASK, (y + _fetch64(data, at + 16)) & MASK)
        z, x = x, z
    return _hash16((_hash16(v[0], w[0]) + _shift_mix(y) * K1 + z) & MASK, (_hash16(v[1], w[1]) + x) & MASK)
