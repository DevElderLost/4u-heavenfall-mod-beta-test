"""MT Framework (3DS) GUI layouts: "lyt" files, ARC type 0x15302EF4, version 0x70C.

Header (0x30 bytes):
    0x00  magic "lyt\\0"
    0x04  u32 version (0x70C)
    0x08  u32 group count
    0x0C  u32 texture count
    0x10  u32 null count (can exceed the nulls in the file)
    0x14  u32 sprite count
    0x18  u32 window count (0 but in the software keyboard's layouts)
    0x1C  u32 text count
    0x20  u32 boundary count
    0x24  u32 offset of the texture table: (u32 unknown, u32 name offset) per texture
    0x28  u32 offset of the pane table
    0x2C  u32 offset of a trailing table (not decoded)

The pane table starts with (u32 kind, u32 depth) of the first pane, then holds
every pane of the tree in pre-order. Each pane record ends with the kind and
depth of the *next* pane (kind 0xFF = end). Depth 0 are groups; a pane's parent
is the closest previous pane one level up. Record layouts:

    all kinds  0x00 u32 ~crc32(name), 0x04 u32 name offset, 0x08 u32 size
               (record size, or for groups/nulls the size of their subtree
               without text panes). Unnamed panes have hash 0 and name offset 0.
    group      0x0C f32 x, y, z
    null       0x0C f32 x, y, z; 0x18 f32 scale x, y; 0x20 RGBA; 0x2C u32 visible
    sprite     0x0C f32 x, y, z; 0x18 f32 width, height; 0x20 f32 scale x, y;
               0x28 f32 u, v, width, height (texture); 0x38 RGBA x4 (corners);
               0x50 u32 origin (0: x, y is the top-left corner, the touch layouts'; 4: the
               centre, e.g. ui801_bg, ui804_back00); 0x58 u32 texture index; 0x60 u32 visible
    text       0x0C u32 text offset; 0x18 f32 font width, height;
               0x20 f32 spacing x, y; 0x28 f32 x, y, z; 0x34 f32 width, height;
               0x44 RGBA x4; 0x70 u32 flags: bits 0-1 the lines' alignment in the box (0 left, 1 right, 2 centred),
               bits 4-7 the box's origin (0: x, y is its top-left corner; 4: its centre, e.g. ui500_pl_name)
    boundary   0x0C f32 x, y; 0x14 f32 width, height; 0x1C f32 scale x, y
    window     0x0C f32 x, y, z; 0x18 f32 width, height; 0x38 RGBA x4 (corners); 0x50 u32 origin (4: the centre);
               only the keyboard's layouts (system/swkbd) have them: the header's word at 0x18 counts them

Positions are relative to the parent pane. A Layout is a view over the
original bytes: only the decoded fields are ever written, so everything else
(names, texts, the trailing table, unknown fields) is kept unchanged.
"""

import struct
import zlib
from dataclasses import dataclass, field
from enum import IntEnum

LYT_TYPE_HASH = 0x15302EF4
MAGIC = b"lyt\x00"
VERSION = 0x70C
END = 0xFF
# The deepest level of a pane (root groups are 0): the loader (FUN_00b03a2c / FUN_00b04310) keeps one slot per level
# of its tree on a six-slot stack and does not check it; a seventh level reads the stack's own depth counter as a node
# (addresses 0x19 and 0x21, a crash on a real 3DS). The Layout methods that add a level refuse to pass it.
MAX_DEPTH = 5


class LytFormatError(ValueError):
    pass


class PaneKind(IntEnum):
    SPRITE = 0
    NULL = 1
    GROUP = 2
    TEXT = 3
    BOUNDARY = 4
    WINDOW = 5


RECORD_SIZES = {PaneKind.SPRITE: 0x6C, PaneKind.NULL: 0x38, PaneKind.GROUP: 0x28, PaneKind.TEXT: 0x7C,
                PaneKind.BOUNDARY: 0x30, PaneKind.WINDOW: 0x88}
# Kinds that can have children.
CONTAINERS = (PaneKind.GROUP, PaneKind.NULL)
# Field offsets inside a record, per kind.
ORIGIN_AT = 0x50   # sprite: 0 top-left corner, 4 centre
POSITION_AT = {PaneKind.SPRITE: 0x0C, PaneKind.NULL: 0x0C, PaneKind.GROUP: 0x0C, PaneKind.TEXT: 0x28,
               PaneKind.BOUNDARY: 0x0C, PaneKind.WINDOW: 0x0C}
SIZE_AT = {PaneKind.SPRITE: 0x18, PaneKind.TEXT: 0x34, PaneKind.BOUNDARY: 0x14, PaneKind.WINDOW: 0x18}
SCALE_AT = {PaneKind.SPRITE: 0x20, PaneKind.NULL: 0x18, PaneKind.BOUNDARY: 0x1C}
COLORS_AT = {PaneKind.SPRITE: 0x38, PaneKind.TEXT: 0x44, PaneKind.WINDOW: 0x38}  # 4 corners, RGBA bytes
NULL_TINT_AT = 0x20  # a null's colour, RGBA bytes
VISIBLE_AT = {PaneKind.SPRITE: 0x60, PaneKind.NULL: 0x2C}  # u32 1 / 0: shown when the layout loads
FONT_SIZE_AT = 0x18  # text only
SPACING_AT = 0x20    # text only
TEXT_FLAGS_AT = 0x70  # text only: bits 0-1 alignment, bits 4-7 origin
HEADER = struct.Struct("<4sIIIIIIIIIII")


def name_hash(name: str) -> int:
    """Hash stored in front of each pane: the bitwise complement of the name's CRC32 (0 if unnamed)."""
    return zlib.crc32(name.encode("ascii")) ^ 0xFFFFFFFF if name else 0


def _vec2(table: dict[PaneKind, int]):
    """Property for a 2-float field whose offset per kind is in `table`."""
    def getter(self) -> tuple[float, float] | None:
        at = table.get(self.kind)
        return None if at is None else struct.unpack_from("<2f", self.layout.data, self.offset + at)

    def setter(self, value: tuple[float, float]) -> None:
        at = table.get(self.kind)
        if at is None:
            raise AttributeError(f"{self.kind.name.lower()} panes have no such field")
        struct.pack_into("<2f", self.layout.data, self.offset + at, *value)
    return property(getter, setter)


@dataclass(eq=False)
class Pane:
    layout: "Layout" = field(repr=False)
    kind: PaneKind
    depth: int
    offset: int
    name: str
    parent: "Pane | None" = field(default=None, repr=False)
    children: list["Pane"] = field(default_factory=list, repr=False)

    position = _vec2(POSITION_AT)   # (x, y), relative to the parent
    size = _vec2(SIZE_AT)           # (width, height): sprites, texts, boundaries
    scale = _vec2(SCALE_AT)         # (x, y): sprites, nulls, boundaries

    @property
    def texture(self) -> int | None:
        """Index in the layout's `textures` of a sprite's texture."""
        return struct.unpack_from("<I", self.layout.data, self.offset + 0x58)[0] \
            if self.kind == PaneKind.SPRITE else None

    @property
    def region(self) -> tuple[float, float, float, float] | None:
        """The part of its texture a sprite shows: u, v, width, height, 0-1."""
        return struct.unpack_from("<4f", self.layout.data, self.offset + 0x28) if self.kind == PaneKind.SPRITE else None

    @property
    def origin(self) -> int | None:
        """A sprite's (or window's) origin mode: 0 when its x, y is its top-left corner, 4 when it is its centre."""
        return struct.unpack_from("<I", self.layout.data, self.offset + ORIGIN_AT)[0] \
            if self.kind in (PaneKind.SPRITE, PaneKind.WINDOW) else None

    @origin.setter
    def origin(self, value: int) -> None:
        if self.kind not in (PaneKind.SPRITE, PaneKind.WINDOW):
            raise AttributeError(f"{self.kind.name.lower()} panes have no origin")
        struct.pack_into("<I", self.layout.data, self.offset + ORIGIN_AT, value)

    @property
    def tint(self) -> tuple[int, int, int, int] | None:
        """A null's colour (R, G, B, A), which multiplies its children's when they are drawn."""
        return tuple(self.layout.data[self.offset + NULL_TINT_AT:self.offset + NULL_TINT_AT + 4]) \
            if self.kind == PaneKind.NULL else None

    @property
    def font_size(self) -> tuple[float, float] | None:
        return struct.unpack_from("<2f", self.layout.data, self.offset + FONT_SIZE_AT) \
            if self.kind == PaneKind.TEXT else None

    @font_size.setter
    def font_size(self, value: tuple[float, float]) -> None:
        self._set_text_field(FONT_SIZE_AT, value)

    @property
    def spacing(self) -> tuple[float, float] | None:
        """(character spacing, line spacing) of a text pane."""
        return struct.unpack_from("<2f", self.layout.data, self.offset + SPACING_AT) \
            if self.kind == PaneKind.TEXT else None

    @spacing.setter
    def spacing(self, value: tuple[float, float]) -> None:
        self._set_text_field(SPACING_AT, value)

    @property
    def text_origin(self) -> int | None:
        """A text's origin: 0 when its x, y is the box's top-left corner, 4 when it is the box's centre."""
        return self._text_flags(4, 0xF)

    @text_origin.setter
    def text_origin(self, value: int) -> None:
        self._set_text_flags(4, 0xF, value)

    @property
    def text_align(self) -> int | None:
        """How a text's lines sit in its box: 0 left, 1 right, 2 centred."""
        return self._text_flags(0, 3)

    @text_align.setter
    def text_align(self, value: int) -> None:
        self._set_text_flags(0, 3, value)

    def _text_flags(self, shift: int, mask: int) -> int | None:
        if self.kind != PaneKind.TEXT:
            return None
        return (struct.unpack_from("<I", self.layout.data, self.offset + TEXT_FLAGS_AT)[0] >> shift) & mask

    def _set_text_flags(self, shift: int, mask: int, value: int) -> None:
        if self.kind != PaneKind.TEXT:
            raise AttributeError(f"{self.kind.name.lower()} panes have no text fields")
        if not 0 <= value <= mask:
            raise ValueError(f"{value}: a value from 0 to {mask}")
        at = self.offset + TEXT_FLAGS_AT
        word = struct.unpack_from("<I", self.layout.data, at)[0]
        struct.pack_into("<I", self.layout.data, at, word & ~(mask << shift) | value << shift)

    def _set_text_field(self, at: int, value: tuple[float, float]) -> None:
        if self.kind != PaneKind.TEXT:
            raise AttributeError(f"{self.kind.name.lower()} panes have no text fields")
        struct.pack_into("<2f", self.layout.data, self.offset + at, *value)

    @property
    def colors(self) -> list[tuple[int, int, int, int]] | None:
        """RGBA of the 4 corners (sprites, texts and windows)."""
        at = COLORS_AT.get(self.kind)
        if at is None:
            return None
        raw = self.layout.data[self.offset + at:self.offset + at + 16]
        return [tuple(raw[i:i + 4]) for i in range(0, 16, 4)]

    @colors.setter
    def colors(self, value: list[tuple[int, int, int, int]]) -> None:
        at = COLORS_AT.get(self.kind)
        if at is None or len(value) != 4:
            raise AttributeError(f"{self.kind.name.lower()} panes have no corner colors")
        self.layout.data[self.offset + at:self.offset + at + 16] = bytes(c for rgba in value for c in rgba)

    @property
    def visible(self) -> bool | None:
        """Whether a sprite or null is shown when the layout loads; the code shows and hides some panes later
        (e.g. the item selector's button glyphs start hidden)."""
        at = VISIBLE_AT.get(self.kind)
        return None if at is None else bool(struct.unpack_from("<I", self.layout.data, self.offset + at)[0])

    @visible.setter
    def visible(self, value: bool) -> None:
        at = VISIBLE_AT.get(self.kind)
        if at is None:
            raise AttributeError(f"{self.kind.name.lower()} panes have no visibility flag")
        struct.pack_into("<I", self.layout.data, self.offset + at, int(value))

    def walk(self):
        """This pane and all its descendants, in file order."""
        yield self
        for child in self.children:
            yield from child.walk()


class Layout:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        if len(self.data) < HEADER.size:
            raise LytFormatError("file too short for a layout header")
        (magic, self.version, groups, textures, self.null_capacity, sprites, windows, texts, boundaries,
         self.texture_table, self.pane_table, self.tail_offset) = HEADER.unpack_from(self.data)
        if magic != MAGIC:
            raise LytFormatError("not a layout (missing 'lyt' magic)")
        if self.version != VERSION:
            raise LytFormatError(f"unsupported layout version {self.version:#x}")
        self.textures = [self._string(struct.unpack_from("<I", self.data, self.texture_table + 8 * i + 4)[0])
                         for i in range(textures)]
        self.panes = self._parse_panes(self.pane_table)
        self._names = {p.name for p in self.panes}
        expected ={PaneKind.GROUP: groups, PaneKind.SPRITE: sprites, PaneKind.TEXT: texts,
                    PaneKind.BOUNDARY: boundaries, PaneKind.WINDOW: windows}
        for kind, count in expected.items():
            found = sum(1 for p in self.panes if p.kind == kind)
            if found != count:
                raise LytFormatError(f"header announces {count} {kind.name.lower()} panes, found {found}")

    def _string(self, offset: int) -> str:
        end = self.data.find(b"\x00", offset)
        if offset >= len(self.data) or end < 0:
            raise LytFormatError(f"string offset {offset:#x} outside the file")
        return self.data[offset:end].decode("ascii", "replace")

    def _parse_panes(self, offset: int) -> list[Pane]:
        panes: list[Pane] = []
        stack: list[Pane] = []  # stack[d] = last pane seen at depth d
        kind, depth = struct.unpack_from("<II", self.data, offset)
        offset += 8
        while kind != END:
            if kind not in RECORD_SIZES:
                raise LytFormatError(f"unknown pane kind {kind} at {offset:#x}")
            if depth > len(stack) or (depth == 0) != (kind == PaneKind.GROUP):
                raise LytFormatError(f"pane at {offset:#x} has an impossible depth {depth}")
            size = RECORD_SIZES[PaneKind(kind)]
            if offset + size > len(self.data):
                raise LytFormatError(f"pane at {offset:#x} runs past the end of the file")
            del stack[depth:]
            parent = stack[-1] if stack else None
            if parent is not None and parent.kind not in CONTAINERS:
                raise LytFormatError(f"pane at {offset:#x} is a child of a {parent.kind.name.lower()}")
            name_offset = struct.unpack_from("<I", self.data, offset + 4)[0]
            name = self._string(name_offset) if name_offset else ""
            pane = Pane(self, PaneKind(kind), depth, offset, name, parent)
            if parent is not None:
                parent.children.append(pane)
            panes.append(pane)
            stack.append(pane)
            kind, depth = struct.unpack_from("<II", self.data, offset + size - 8)
            offset += size
        return panes

    @property
    def roots(self) -> list[Pane]:
        return [p for p in self.panes if p.parent is None]

    def find(self, name: str) -> Pane:
        for pane in self.panes:
            if pane.name == name:
                return pane
        raise KeyError(name)

    def add_texture(self, name: str) -> int:
        """The index of the texture `name` in `textures`, added to the table when it is not there: a table entry
        after the others and the name after the other texture names (right before the pane table); every offset
        behind them moves. Panes obtained earlier stay valid (their offsets follow)."""
        if name in self.textures:
            return self.textures.index(name)
        if not name or not name.isascii():
            raise LytFormatError(f"the texture name {name!r} is empty or not ASCII")
        if any(self.data[self.tail_offset:]):
            raise LytFormatError("layouts with a trailing table are not supported")
        table_end = self.texture_table + 8 * len(self.textures)
        at = self.pane_table    # where the new name goes: the pane table starts after it
        if not table_end <= at:
            raise LytFormatError("unexpected order of the texture table and the pane table")
        encoded = name.encode("ascii") + b"\x00"
        encoded += b"\x00" * (-len(encoded) % 4)

        def moved(offset: int) -> int:
            return offset + (8 if offset >= table_end else 0) + (len(encoded) if offset >= at else 0)

        data = (self.data[:table_end] + struct.pack("<II", 0, at + 8) + self.data[table_end:at] + encoded
                + self.data[at:])
        shift = 8 + len(encoded)
        for i in range(len(self.textures)):
            where = self.texture_table + 8 * i + 4
            struct.pack_into("<I", data, where, moved(struct.unpack_from("<I", data, where)[0]))
        for pane in self.panes:
            where = pane.offset + shift
            if struct.unpack_from("<I", data, where + 4)[0]:
                struct.pack_into("<I", data, where + 4, moved(struct.unpack_from("<I", data, where + 4)[0]))
            if pane.kind == PaneKind.TEXT:
                struct.pack_into("<I", data, where + 0x0C, moved(struct.unpack_from("<I", data, where + 0x0C)[0]))
        struct.pack_into("<I", data, 0x0C, len(self.textures) + 1)
        struct.pack_into("<I", data, 0x28, moved(self.pane_table))
        struct.pack_into("<I", data, 0x2C, moved(self.tail_offset))
        self.data = data
        self.pane_table = moved(self.pane_table)
        self.tail_offset = moved(self.tail_offset)
        self.textures.append(name)
        for pane in self.panes:
            pane.offset += shift
        return len(self.textures) - 1

    def insert_sprite(self, parent: Pane, template: Pane, name: str, position: tuple[float, float],
                      region: tuple[float, float, float, float] | None = None, texture: int | None = None,
                      first: bool = False, behind: Pane | None = None) -> Pane:
        """Add a sprite as the last child of `parent` (the first with `first`: panes draw in file order, so it then
        draws behind its siblings; right after the child `behind` with `behind`, in front of it and behind the
        siblings that follow): a copy of `template` with a new name and position,
        optionally another texture region (u, v, width, height, 0-1) and texture (index in `textures`).

        The pane table grows by one record, the name goes after the other names, and every file offset
        behind them (names, texts, trailing table) moves; the sizes of `parent` and its ancestors and the
        header's sprite count follow. Panes obtained earlier stay valid; the returned one is the new pane."""
        def edit(record: bytearray, _text_at: int) -> None:
            struct.pack_into("<2f", record, POSITION_AT[PaneKind.SPRITE], *position)
            if region is not None:
                struct.pack_into("<4f", record, 0x28, *region)
            if texture is not None:
                struct.pack_into("<I", record, 0x58, texture)
        return self._insert(parent, template, PaneKind.SPRITE, name, edit, b"", first, behind=behind)

    def insert_null(self, parent: Pane, template: Pane, name: str, position: tuple[float, float],
                    visible: bool = True, first: bool = False) -> Pane:
        """Add a null as the last child of `parent` (the first with `first`): a copy of `template`'s record (scale,
        colour), without its children, with a new name, position and visibility at load. As insert_sprite; panes
        inserted into it later grow its subtree size."""
        def edit(record: bytearray, _text_at: int) -> None:
            struct.pack_into("<I", record, 0x08, RECORD_SIZES[PaneKind.NULL])
            struct.pack_into("<2f", record, POSITION_AT[PaneKind.NULL], *position)
            struct.pack_into("<I", record, VISIBLE_AT[PaneKind.NULL], int(visible))
        return self._insert(parent, template, PaneKind.NULL, name, edit, b"", first)

    def plain_null(self) -> Pane:
        """A null of this layout with no scale, tint nor offset of its own (z 0, scale 1, opaque white): the template
        of a wrapper."""
        for pane in self.panes:
            if (pane.kind == PaneKind.NULL and pane.scale == (1.0, 1.0)
                    and struct.unpack_from("<f", self.data, pane.offset + 0x14)[0] == 0.0
                    and bytes(self.data[pane.offset + 0x20:pane.offset + 0x24]) == bytes(4 * [255])):
                return pane
        raise LytFormatError("the layout has no plain null to copy for a wrapper")

    def wrap_in_null(self, pane: Pane, name: str, template: Pane, subtree: bool = False) -> Pane:
        """Put the childless `pane` (not a null nor a group) inside a new null `name`, a copy of `template`'s record
        at (0, 0) and shown, that takes the pane's place among its siblings: positions are relative to the parent,
        so nothing moves, and the draw order is kept. What the null is moved by, the pane follows; what the game's
        code writes to the pane's own position is then relative to the null. As insert_null, the null count of the
        header grows and the ancestors' sizes with it; the null's own size takes the pane's record (a text's is left
        out, like everywhere). With `subtree` the pane may be a null with children: they all go one level deeper and
        the new null's size takes the whole subtree's. Refused when the deepest pane would pass `MAX_DEPTH`. Panes
        obtained earlier stay valid; the returned one is the new null."""
        if pane.layout is not self or pane.parent is None or (pane.kind in CONTAINERS and not (
                subtree and pane.kind == PaneKind.NULL)):
            raise LytFormatError("only a childless pane of this layout, under another pane, can be wrapped (a null "
                                 "with children only with `subtree`)")
        if pane.kind in CONTAINERS:
            extra = struct.unpack_from("<I", self.data, pane.offset + 8)[0]
        else:
            extra = 0 if pane.kind == PaneKind.TEXT else RECORD_SIZES[pane.kind]

        def edit(record: bytearray, _text_at: int) -> None:
            struct.pack_into("<I", record, 0x08, RECORD_SIZES[PaneKind.NULL] + extra)
            struct.pack_into("<2f", record, POSITION_AT[PaneKind.NULL], 0.0, 0.0)
            struct.pack_into("<I", record, VISIBLE_AT[PaneKind.NULL], 1)
        return self._insert(pane.parent, template, PaneKind.NULL, name, edit, b"", before=pane)

    def wrap_children(self, group: Pane, name: str, template: Pane) -> Pane:
        """Put everything under the root group `group` inside one new null `name` (a copy of `template`'s record at
        (0, 0) and shown), the group's only child: every pane under the group goes one level deeper and keeps its own
        position, so nothing moves and the draw order is kept; what the null is scaled and moved by, the whole group
        follows (the executable's frames). The null's size takes
        the whole subtree's (texts left out, like everywhere), the group's grows by the null's record. Refused when the
        deepest pane would pass `MAX_DEPTH`. Panes obtained earlier stay valid; the returned one is the new null."""
        if group.layout is not self or group.kind != PaneKind.GROUP or not group.children:
            raise LytFormatError("only a root group of this layout with panes under it can have them wrapped")
        lowest = max(pane.depth for pane in group.walk()) + 1
        if lowest > MAX_DEPTH:
            raise LytFormatError(f"{name}: a pane would be at depth {lowest}, the loader's last is {MAX_DEPTH}")
        extra =sum(RECORD_SIZES[p.kind] for p in list(group.walk())[1:] if p.kind != PaneKind.TEXT)

        def edit(record: bytearray, _text_at: int) -> None:
            struct.pack_into("<I", record, 0x08, RECORD_SIZES[PaneKind.NULL] + extra)
            struct.pack_into("<2f", record, POSITION_AT[PaneKind.NULL], 0.0, 0.0)
            struct.pack_into("<I", record, VISIBLE_AT[PaneKind.NULL], 1)
        wrapper = self._insert(group, template, PaneKind.NULL, name, edit, b"", before=group.children[0])
        # the group's other children (and what is under them) one level deeper too: each depth is stored in the record
        # that precedes the pane
        others = [child for child in group.children if child is not wrapper]
        deeper = {id(pane) for child in others for pane in child.walk()}
        previous = None
        for pane in self.panes:
            if id(pane) in deeper:
                struct.pack_into("<I", self.data, previous.offset + RECORD_SIZES[previous.kind] - 4, pane.depth + 1)
            previous = pane
        for child in others:
            for pane in child.walk():
                pane.depth += 1
            child.parent = wrapper
        wrapper.children.extend(others)
        group.children = [wrapper]
        return wrapper

    def split_off(self, first: Pane, name: str) -> Pane:
        """Move `first` and the siblings after it out of their parent null into a new null `name`, a copy of the
        parent's record (its place, scale, colour and visibility) that follows the parent among its siblings: the panes
        keep their depth and their positions are relative to the same frame, so nothing moves and the draw order is
        kept; animations find them by name in the same root group. The parent keeps at least its first child. The
        null count of the header grows, the ancestors' sizes by the null's record; the parent's size gives the moved
        panes' records to the new null (texts left out, like everywhere).
        Panes obtained earlier stay valid; the returned one is the new null."""
        parent = first.parent
        if first.layout is not self or parent is None or parent.kind != PaneKind.NULL or parent.parent is None:
            raise LytFormatError("only panes of a null under another pane of this layout can be split off")
        at = parent.children.index(first)
        if at == 0:
            raise LytFormatError(f"{first.name}: the null {parent.name} would be left empty")
        moved = [pane for child in parent.children[at:] for pane in child.walk()]
        moved_size = sum(RECORD_SIZES[p.kind] for p in moved if p.kind != PaneKind.TEXT)
        kept_size = sum(RECORD_SIZES[p.kind] for p in parent.walk() if p.kind != PaneKind.TEXT) - moved_size
        null_size = RECORD_SIZES[PaneKind.NULL]

        def edit(record: bytearray, _text_at: int) -> None:
            struct.pack_into("<I", record, 0x08, null_size)
        new = self._insert(parent.parent, parent, PaneKind.NULL, name, edit, b"", behind=parent)
        start, end = first.offset, new.offset + null_size
        first_at, new_at = self.panes.index(first), self.panes.index(new)
        before = self.panes[first_at - 1]
        last = self.panes[new_at - 1]
        # the three links of the pane table (each record ends with the kind and depth of the next one) turn round:
        # the pane before the moved ones now leads to the null, the null to the first moved pane, the last moved pane
        # to what followed the null
        to_null = bytes(self.data[last.offset + RECORD_SIZES[last.kind] - 8:last.offset + RECORD_SIZES[last.kind]])
        to_first = bytes(self.data[before.offset + RECORD_SIZES[before.kind] - 8:
                                   before.offset + RECORD_SIZES[before.kind]])
        after_null = bytes(self.data[end - 8:end])
        record = bytearray(self.data[new.offset:end])
        record[-8:] = to_first
        panes = bytearray(self.data[start:new.offset])
        panes[-8:] = after_null
        self.data[start:end] = record + panes
        self.data[before.offset + RECORD_SIZES[before.kind] - 8:before.offset + RECORD_SIZES[before.kind]] = to_null
        struct.pack_into("<I", self.data, parent.offset + 8, kept_size)
        struct.pack_into("<I", self.data, start + 8, null_size + moved_size)
        # the pane objects follow: the new null leads the moved panes, which shift behind it and become its children
        moving = self.panes[first_at:new_at]
        for pane in moving:
            pane.offset += null_size
        new.offset = start
        self.panes[first_at:new_at + 1] = [new] + moving
        new.children = parent.children[at:]
        del parent.children[at:]
        for child in new.children:
            child.parent = new
        return new

    def insert_text(self, parent: Pane, template: Pane, name: str, position: tuple[float, float],
                    size: tuple[float, float], text: str, first: bool = False) -> Pane:
        """Add a text pane as the last child of `parent` (the first with `first`): a copy of `template` (font,
        colours, alignment) with a new name, position, size and string (UTF-16, as the game's, after the other
        texts). As insert_sprite, except that the ancestors' sizes stay (they leave text panes out) and the header's
        text count grows."""
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        encoded += b"\x00" * (-len(encoded) % 4)

        def edit(record: bytearray, text_at: int) -> None:
            struct.pack_into("<I", record, 0x0C, text_at)
            struct.pack_into("<2I", record, 0x10, len(text), len(text))
            struct.pack_into("<2f", record, POSITION_AT[PaneKind.TEXT], *position)
            struct.pack_into("<2f", record, SIZE_AT[PaneKind.TEXT], *size)
        return self._insert(parent, template, PaneKind.TEXT, name, edit, encoded, first)

    def _insert(self, parent: Pane, template: Pane, kind: PaneKind, name: str, edit, text: bytes,
                first: bool = False, before: Pane | None = None, behind: Pane | None = None) -> Pane:
        """Add a copy of `template` (a `kind` pane, of this layout or another one: its texture index is then the
        caller's to set) named `name` as the last child of `parent`, or the first with `first`, or right after the
        child `behind` (and what is under it); `edit(record, text offset)` changes the new record, `text` (bytes,
        padded) goes after the other texts. With `before` (a child of `parent`) the new pane goes right before it and
        takes it as its only child, one level deeper. No pane may end below `MAX_DEPTH`."""
        if parent.layout is not self or template.kind != kind:
            raise LytFormatError(f"the parent must belong to this layout and the template be a {kind.name.lower()}")
        if parent.kind not in CONTAINERS:
            raise LytFormatError(f"a {parent.kind.name.lower()} cannot have children")
        if not name or not name.isascii() or name in self._names:
            raise LytFormatError(f"the name {name!r} is empty, not ASCII or already used")
        if any(self.data[self.tail_offset:]):
            raise LytFormatError("layouts with a trailing table are not supported")
        # the new pane at the parent's next level; with `before` its subtree goes one level deeper than it is
        lowest = parent.depth + 1 if before is None else max(pane.depth for pane in before.walk()) + 1
        if lowest > MAX_DEPTH:
            raise LytFormatError(f"{name}: a pane would be at depth {lowest}, the loader's last is {MAX_DEPTH}")
        size = RECORD_SIZES[kind]
        if (before is not None and before.parent is not parent) or (behind is not None and behind.parent is not parent):
            raise LytFormatError("`before` and `behind` must be children of the parent")
        if before is not None:     # the new record goes right behind this pane's
            after = self.panes[self.panes.index(before) - 1]
        elif behind is not None:   # ... or behind the last pane of this one's subtree
            after = list(behind.walk())[-1]
        else:
            after = parent if first else list(parent.walk())[-1]
        insert_at = after.offset + RECORD_SIZES[after.kind]
        text_offsets = [struct.unpack_from("<I", self.data, p.offset + 0x0C)[0]
                        for p in self.panes if p.kind == PaneKind.TEXT]
        boundary = min(text_offsets, default=self.tail_offset)  # the names end where the texts start
        panes_end = self.panes[-1].offset + RECORD_SIZES[self.panes[-1].kind]
        name_offsets = [struct.unpack_from("<I", self.data, p.offset + 4)[0] for p in self.panes]
        names_in_place = all(not o or panes_end <= o < boundary for o in name_offsets)
        if not panes_end <= boundary <= self.tail_offset or not names_in_place:
            raise LytFormatError("unexpected order of the pane table, names and texts")
        encoded = name.encode("ascii") + b"\x00"
        encoded += b"\x00" * (-len(encoded) % 4)

        def moved(offset: int) -> int:  # offsets before the pane table (the texture names) stay
            if offset < panes_end:
                return offset
            return offset + size + (len(encoded) if offset >= boundary else 0) + \
                (len(text) if offset >= self.tail_offset else 0)

        record = bytearray(template.layout.data[template.offset:template.offset + size])
        struct.pack_into("<II", record, 0, name_hash(name), boundary + size)
        edit(record, self.tail_offset + size + len(encoded))
        record[-8:] = self.data[insert_at - 8:insert_at]  # what followed the pane before follows the new one
        if before is not None:     # ... which is now the new pane's child
            struct.pack_into("<I", record, size - 4, before.depth + 1)

        data = (self.data[:insert_at] + record + self.data[insert_at:boundary] + encoded
                + self.data[boundary:self.tail_offset] + text + self.data[self.tail_offset:])
        struct.pack_into("<II", data, insert_at - 8, kind, parent.depth + 1)

        chain, pane = [], parent  # the parent and its ancestors: their subtrees grow (text panes left out)
        while pane is not None and kind != PaneKind.TEXT:
            chain.append(pane)
            pane = pane.parent
        chain_set = set(chain)
        for pane in self.panes:
            at = pane.offset + (size if pane.offset >= insert_at else 0)
            if struct.unpack_from("<I", data, at + 4)[0]:
                struct.pack_into("<I", data, at + 4, moved(struct.unpack_from("<I", data, at + 4)[0]))
            if pane.kind == PaneKind.TEXT:
                struct.pack_into("<I", data, at + 0x0C, moved(struct.unpack_from("<I", data, at + 0x0C)[0]))
            if pane in chain_set:
                struct.pack_into("<I", data, at + 8, struct.unpack_from("<I", data, at + 8)[0] + size)
        for i in range(len(self.textures)):
            at = self.texture_table + 8 * i + 4
            struct.pack_into("<I", data, at, moved(struct.unpack_from("<I", data, at)[0]))
        count_at = {PaneKind.TEXT: 0x1C, PaneKind.SPRITE: 0x14, PaneKind.NULL: 0x10}[kind]
        struct.pack_into("<I", data, count_at, struct.unpack_from("<I", data, count_at)[0] + 1)
        struct.pack_into("<I", data, 0x2C, moved(self.tail_offset))
        if before is not None:     # the wrapped pane's descendants go one level deeper too (each depth is stored in
            for pane in list(before.walk())[1:]:       # the record that precedes it)
                previous = self.panes[self.panes.index(pane) - 1]
                struct.pack_into("<I", data, previous.offset + size + RECORD_SIZES[previous.kind] - 4, pane.depth + 1)
        # the pane objects follow the file: the ones from the new record on shift, the new one takes its place
        index = self.panes.index(after) + 1
        for pane in self.panes[index:]:
            pane.offset += size
        new = Pane(self, PaneKind(kind), parent.depth + 1, insert_at, name, parent)
        self.panes.insert(index, new)
        self._names.add(name)
        if before is not None:
            parent.children[parent.children.index(before)] = new
            new.children.append(before)
            before.parent = new
            for pane in before.walk():
                pane.depth += 1
        elif behind is not None:
            parent.children.insert(parent.children.index(behind) + 1, new)
        elif first:
            parent.children.insert(0, new)
        else:
            parent.children.append(new)
        self.data = data
        self.tail_offset = moved(self.tail_offset)
        return new

    def insert_group(self, template: Pane, name: str, position: tuple[float, float] = (0.0, 0.0)) -> Pane:
        """Add an empty root group as the last of the layout: a copy of `template`'s record (a group, of this layout or
        another) with a new name and position. The header's group count grows, and so does the trailing table by one
        zero word (the loader fills it with one pointer per root group). The game creates the group, hidden, with the
        layout; panes go into it with insert_sprite, insert_text and insert_null. As the others: the name goes after
        the other names and every offset behind them moves; panes obtained earlier stay valid."""
        if template.kind != PaneKind.GROUP:
            raise LytFormatError("a group is copied from a group")
        if not name or not name.isascii() or name in self._names:
            raise LytFormatError(f"the name {name!r} is empty, not ASCII or already used")
        if any(self.data[self.tail_offset:]):
            raise LytFormatError("layouts with a trailing table are not supported")
        size = RECORD_SIZES[PaneKind.GROUP]
        insert_at = self.panes[-1].offset + RECORD_SIZES[self.panes[-1].kind]
        text_offsets = [struct.unpack_from("<I", self.data, p.offset + 0x0C)[0]
                        for p in self.panes if p.kind == PaneKind.TEXT]
        boundary = min(text_offsets, default=self.tail_offset)
        name_offsets = [struct.unpack_from("<I", self.data, p.offset + 4)[0] for p in self.panes]
        if not insert_at <= boundary <= self.tail_offset or not all(not o or insert_at <= o < boundary
                                                                    for o in name_offsets):
            raise LytFormatError("unexpected order of the pane table, names and texts")
        encoded = name.encode("ascii") + b"\x00"
        encoded += b"\x00" * (-len(encoded) % 4)

        def moved(offset: int) -> int:  # the pane table ends where the record goes: everything behind it moves
            if offset < insert_at:
                return offset
            return offset + size + (len(encoded) if offset >= boundary else 0)

        record = bytearray(template.layout.data[template.offset:template.offset + size])
        struct.pack_into("<III", record, 0, name_hash(name), boundary + size, size)
        struct.pack_into("<2f", record, POSITION_AT[PaneKind.GROUP], *position)
        record[-8:] = self.data[insert_at - 8:insert_at]   # what ended the table ends it now
        data = (self.data[:insert_at] + record + self.data[insert_at:boundary] + encoded
                + self.data[boundary:] + b"\x00" * 4)
        struct.pack_into("<II", data, insert_at - 8, PaneKind.GROUP, 0)
        for pane in self.panes:
            if struct.unpack_from("<I", data, pane.offset + 4)[0]:
                struct.pack_into("<I", data, pane.offset + 4, moved(struct.unpack_from("<I", data, pane.offset + 4)[0]))
            if pane.kind == PaneKind.TEXT:
                struct.pack_into("<I", data, pane.offset + 0x0C,
                                 moved(struct.unpack_from("<I", data, pane.offset + 0x0C)[0]))
        for i in range(len(self.textures)):
            at = self.texture_table + 8 * i + 4
            struct.pack_into("<I", data, at, moved(struct.unpack_from("<I", data, at)[0]))
        struct.pack_into("<I", data, 0x08, struct.unpack_from("<I", data, 0x08)[0] + 1)
        struct.pack_into("<I", data, 0x2C, moved(self.tail_offset))
        self.data = data
        self.tail_offset = moved(self.tail_offset)
        group = Pane(self, PaneKind.GROUP, 0, insert_at, name)   # no pane's offset moves: all are before it
        self.panes.append(group)
        self._names.add(name)
        return group

    def to_bytes(self) -> bytes:
        return bytes(self.data)


def parse_lyt(data: bytes) -> Layout:
    return Layout(data)
