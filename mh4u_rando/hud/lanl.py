"""MT Framework (3DS) GUI layout animations: "lanl" files, ARC type 0x708E0028, version 5.

They sit in the same ARC as the layout they animate (e.g. ui202_hp,
ui202_anim_list for ui202) and find their panes by name hash.

    0x00  magic "lanl"
    0x04  u32 version (5)
    0x08  u32 animation count
    0x0C  u32 offset of each animation (0 = empty slot)

Animation (0x20 bytes): u32 tracks offset, u32 0, u32 targets offset,
u32 track count, u32 target count, u32 frame count, u32 x2 unknown.

Target (0x0C bytes): u32 name_hash(root group), u32 name_hash(pane), u16
first and u16 last index of its tracks (each target's tracks are contiguous).

Track (0x10 bytes): u8 value format, u8 property, u16 key count, u32 keys
offset, u32 name_hash(root group), u32 name_hash(animated pane). Value format:
low nibble 0 = float, 2 = RGBA; high nibble = interpolation. Keys of 0x20 and
0x30 tracks carry two tangents; in the other tracks those bytes are leftovers
(often 0xCDCDCDCD).

Key (0x10 bytes): f32 frame, value (f32 or RGBA), f32 tangent x2.

Like Layout, Animations is a view over the original bytes.
"""

import struct
from dataclasses import dataclass, field
from enum import IntEnum

LANL_TYPE_HASH = 0x708E0028
MAGIC = b"lanl"
VERSION = 5
ANIMATION = struct.Struct("<IIIIIIII")
TRACK = struct.Struct("<BBHIII")
TARGET = struct.Struct("<IIHH")
KEY_SIZE = 0x10
TANGENT_FORMATS = (0x20, 0x30)


class LanlFormatError(ValueError):
    pass


class Property(IntEnum):
    """Animated property of a pane (meanings guessed from the values)."""
    X = 0x00
    Y = 0x01
    WIDTH = 0x03
    HEIGHT = 0x04
    SCALE_X = 0x05
    SCALE_Y = 0x06
    ROTATION = 0x0B     # 65536 = 360 degrees
    COLOR = 0x0E


@dataclass(eq=False)
class Track:
    animations: "Animations" = field(repr=False)
    animation: int
    offset: int
    value_format: int
    prop: int
    key_count: int
    keys_offset: int
    group_hash: int
    pane_hash: int

    @property
    def is_float(self) -> bool:
        return self.value_format & 0x0F == 0

    @property
    def has_tangents(self) -> bool:
        return self.is_float and self.value_format & 0xF0 in TANGENT_FORMATS

    def _key(self, index: int) -> int:
        return self.keys_offset + KEY_SIZE * index

    def values(self) -> list[float]:
        if not self.is_float:
            raise ValueError("not a float track")
        return [struct.unpack_from("<f", self.animations.data, self._key(i) + 4)[0] for i in range(self.key_count)]

    def transform(self, scale: float, offset: float = 0.0) -> None:
        """value -> value * scale + offset for every key; tangents (slopes) are only scaled."""
        if not self.is_float:
            raise ValueError("only float tracks can be transformed")
        data = self.animations.data
        for i in range(self.key_count):
            at = self._key(i)
            value = struct.unpack_from("<f", data, at + 4)[0]
            struct.pack_into("<f", data, at + 4, value * scale + offset)
            if self.has_tangents:
                tangents = struct.unpack_from("<2f", data, at + 8)
                struct.pack_into("<2f", data, at + 8, *(t * scale for t in tangents))


class Animations:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        if len(self.data) < 12 or self.data[:4] != MAGIC:
            raise LanlFormatError("not a layout animation (missing 'lanl' magic)")
        version, count = struct.unpack_from("<II", self.data, 4)
        if version != VERSION:
            raise LanlFormatError(f"unsupported animation version {version}")
        if 0x0C + 4 * count > len(self.data):
            raise LanlFormatError("animation table runs past the end of the file")
        self.tracks: list[Track] = []
        for index in range(count):
            at = struct.unpack_from("<I", self.data, 0x0C + 4 * index)[0]
            if at == 0:
                continue
            self._check(at, ANIMATION.size, "animation")
            tracks_at, _, _, track_count, *_ = ANIMATION.unpack_from(self.data, at)
            self._check(tracks_at, TRACK.size * track_count, "track list")
            for k in range(track_count):
                offset = tracks_at + TRACK.size * k
                fmt, prop, key_count, keys_at, group_hash, pane_hash = TRACK.unpack_from(self.data, offset)
                self._check(keys_at, KEY_SIZE * key_count, "key list")
                self.tracks.append(Track(self, index, offset, fmt, prop, key_count, keys_at, group_hash, pane_hash))

    def _check(self, offset: int, size: int, what: str) -> None:
        if offset + size > len(self.data):
            raise LanlFormatError(f"{what} at {offset:#x} runs past the end of the file")

    def copy_pane(self, source_hash: int, new_hash: int) -> int:
        """Animate the pane `new_hash` like `source_hash` in every animation that has it as a target: copies of
        its tracks and keys, and a target, are added. The grown track and target lists are appended at the end
        of the file (the old ones stay, unused). Returns how many animations changed. Tracks read earlier
        are stale afterwards: parse the bytes again."""
        changed = 0
        for index in range(struct.unpack_from("<I", self.data, 8)[0]):
            at = struct.unpack_from("<I", self.data, 0x0C + 4 * index)[0]
            if at == 0:
                continue
            fields = list(ANIMATION.unpack_from(self.data, at))
            tracks_at, _, targets_at, track_count, target_count = fields[:5]
            self._check(targets_at, TARGET.size * target_count, "target list")
            targets = [TARGET.unpack_from(self.data, targets_at + TARGET.size * i) for i in range(target_count)]
            source = next((t for t in targets if t[1] == source_hash), None)
            if source is None:
                continue
            if any(t[1] == new_hash for t in targets):
                raise LanlFormatError(f"pane {new_hash:#x} is already animated")
            group, _, first, last = source
            if not first <= last < track_count:
                raise LanlFormatError(f"target {source_hash:#x} points past the track list")
            tracks = bytearray(self.data[tracks_at:tracks_at + TRACK.size * track_count])
            for k in range(first, last + 1):
                fmt, prop, key_count, keys_at, track_group, _ = TRACK.unpack_from(self.data, tracks_at + TRACK.size * k)
                self._align()
                new_keys = len(self.data)
                self.data += self.data[keys_at:keys_at + KEY_SIZE * key_count]
                tracks += TRACK.pack(fmt, prop, key_count, new_keys, track_group, new_hash)
            new_targets = b"".join(TARGET.pack(*t) for t in targets)
            new_targets += TARGET.pack(group, new_hash, track_count, track_count + last - first)
            self._align()
            fields[0], fields[3] = len(self.data), len(tracks) // TRACK.size
            self.data += tracks
            fields[2], fields[4] = len(self.data), target_count + 1
            self.data += new_targets
            ANIMATION.pack_into(self.data, at, *fields)
            changed += 1
        self._align()
        return changed

    def _align(self) -> None:
        self.data += b"\x00" * (-len(self.data) % 4)

    def to_bytes(self) -> bytes:
        return bytes(self.data)


def parse_lanl(data: bytes) -> Animations:
    return Animations(data)
