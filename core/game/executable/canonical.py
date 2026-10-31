"""The player's executable laid out as the canonical one.

`to_canonical` moves every run of a version's code.bin to its canonical place, re-encodes the branches whose
target moved by another delta than the branch itself, translates the words that hold a moved address, and fills
the holes (canonical code or data the version does not have) with a trap word, so that a patcher's own byte checks
refuse a site in one. The way back (`from_canonical`) is another module's.
"""

import struct

from core.game.executable.versions import VersionMap

BASE = 0x100000           # virtual address of code.bin's first byte (every version of both games)
TRAP = 0xE7F000F0         # ARM's permanently undefined instruction: not zero, not a branch, never game code
_ARM_BRANCH = 0b101       # bits 27-25 of B/BL (any condition but 0xF) and BLX imm (0xFA/0xFB)


class CanonicalError(ValueError):
    """A map that does not fit the executable (its slots name words that are not branches or pointers)."""


def arm_branch_target(word: int, at: int) -> int | None:
    """Target of the ARM B/BL/BLX imm `word` placed at `at`, or None if it is no such branch."""
    if word >> 25 & 7 != _ARM_BRANCH:
        return None
    offset = word & 0xFFFFFF
    offset -= (offset & 0x800000) << 1
    target = at + 8 + offset * 4
    if word >> 28 == 0xF:                       # BLX imm: H (bit 24) adds a halfword, the target is Thumb
        target += (word >> 24 & 1) * 2
    return target


def arm_branch(word: int, at: int, target: int) -> int | None:
    """`word` (an ARM B/BL with its condition, or a BLX imm) re-encoded at `at` for `target`; None if out of reach
    or not encodable."""
    delta = target - at - 8
    if not -(1 << 25) <= delta < (1 << 25):
        return None
    if word >> 28 == 0xF:
        return 0xFA000000 | (delta >> 1 & 1) << 24 | (delta >> 2 & 0xFFFFFF)
    if delta & 3:
        return None
    return word & 0xFF000000 | (delta >> 2 & 0xFFFFFF)


def thumb_branch_target(first: int, second: int, at: int) -> int | None:
    """Target of the Thumb BL/BLX pair (halfwords `first`, `second`) at halfword address `at`, or None."""
    if first & 0xF800 != 0xF000 or second & 0xE800 != 0xE800:
        return None
    offset = (first & 0x7FF) << 12 | (second & 0x7FF) << 1
    offset -= (offset & 0x400000) << 1
    if second & 0xF800 == 0xF800:               # BL: Thumb target
        return at + 4 + offset
    return (at + 4 & ~3) + offset               # BLX: ARM target, from the word-aligned pc


def thumb_branch(first: int, second: int, at: int, target: int) -> tuple[int, int] | None:
    """The Thumb BL/BLX pair re-encoded at `at` for `target`; None if out of reach or not encodable."""
    blx = second & 0xF800 == 0xE800
    delta = target - ((at + 4 & ~3) if blx else at + 4)
    if not -(1 << 22) <= delta < (1 << 22) or delta & 1 or (blx and delta & 2):
        return None
    return 0xF000 | (delta >> 12 & 0x7FF), (second & 0xF800) | (delta >> 1 & 0x7FF)


def _canonical_of(version: VersionMap, address: int, what: str) -> int:
    out = version.to_canonical(address)
    if out is None:
        raise CanonicalError(f"{version.key}: {what} {address:#x} has no canonical counterpart")
    return out


def to_canonical(code: bytes, version: VersionMap) -> bytes:
    """`code` (the decompressed code.bin of `version`) as the canonical executable of its game: the same length,
    every byte at its canonical address. Branch slots at an odd address are Thumb BL/BLX pairs (at the address
    minus one)."""
    if version.is_canonical:
        return bytes(code)
    end = BASE + len(code)
    out = bytearray(len(code))
    for run in version.runs:
        start, stop = max(run.start, BASE, BASE - run.delta), min(run.end, end, end - run.delta)
        if start < stop:
            out[start - BASE:stop - BASE] = code[start + run.delta - BASE:stop + run.delta - BASE]
    for slot in version.branch_slots:
        if slot & 1:
            at = slot - 1
            first, second = struct.unpack_from("<2H", code, at - BASE)
            target = thumb_branch_target(first, second, at)
            here = _canonical_of(version, at, "Thumb branch")
            encoded = None if target is None else thumb_branch(
                first, second, here, _canonical_of(version, target, f"target of the Thumb branch at {at:#x},"))
            if encoded is None:
                raise CanonicalError(f"{version.key}: the Thumb branch slot {at:#x} does not re-encode")
            struct.pack_into("<2H", out, here - BASE, *encoded)
        else:
            word = struct.unpack_from("<I", code, slot - BASE)[0]
            target = arm_branch_target(word, slot)
            here = _canonical_of(version, slot, "branch")
            encoded = None if target is None else arm_branch(
                word, here, _canonical_of(version, target, f"target of the branch at {slot:#x},"))
            if encoded is None:
                raise CanonicalError(f"{version.key}: the branch slot {slot:#x} does not re-encode")
            struct.pack_into("<I", out, here - BASE, encoded)
    for slot in version.pointer_slots:
        word = struct.unpack_from("<I", code, slot - BASE)[0]
        struct.pack_into("<I", out, _canonical_of(version, slot, "pointer") - BASE,
                         _canonical_of(version, word, f"value of the pointer at {slot:#x},"))
    trap = struct.pack("<I", TRAP)
    for start, stop in version.holes:
        start, stop = max(start, BASE), min(stop, end)
        if start < stop:
            out[start - BASE:stop - BASE] = trap * ((stop - start) // 4)
    return bytes(out)
