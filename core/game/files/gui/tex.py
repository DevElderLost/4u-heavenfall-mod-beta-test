"""MT Framework (3DS) textures: "TEX" files, ARC type 0x241F5DEB, version 0xA5.

Header (0x14 bytes):
    0x00  magic "TEX\\0"
    0x04  u32 version (low byte, 0xA5) and unknown bits
    0x08  u32 mip count (bits 0-5), width (bits 6-18), height (bits 19-31)
    0x0C  u32 texture count (bits 0-7), pixel format (bits 8-15), unknown
    0x10  u32 unknown (0 in the GUI textures)

Pixels follow, mip 0 first, as on the 3DS GPU: 8x8 tiles left to right, top to
bottom, each tile's pixels in Morton (Z) order. The formats the GUI's textures use (every texture a layout of the
RomFS names) are read; the first four are also written:

    1  RGBA4444, little-endian u16: R in bits 12-15, G 8-11, B 4-7, A 0-3
       (the GUI icon atlases, e.g. cmn_micon_BM_MQ_NOMIP)
    2  RGBA5551, little-endian u16: R in bits 11-15, G 6-10, B 1-5, A bit 0 (the status icons of the party list,
       qst_icon_BM_MQ_NOMIP). Channels are widened to 8 bits the usual way (v << 3 | v >> 2); a written pixel is
       opaque from alpha 128.
    12 ETC1A4 (the GUI textures with alpha, e.g. qst00_ID): per 4x4 block, a
       64-bit alpha word (4 bits per pixel, column by column) and a 64-bit ETC1
       colour word, both little-endian; the 4 blocks of an 8x8 tile are in
       Z order (top-left, top-right, bottom-left, bottom-right). Reading is
       exact; writing is limited to grey glyphs (Tex.set_glyph).
    16 LA4, a byte per pixel: luminance in the high nibble, alpha in the low one
       (the common icon sheet, cmn_icon_GSM_NOMIP, tinted when drawn)
    3  RGBA8888, little-endian u32: R in bits 24-31, G 16-23, B 8-15, A 0-7 (demo_hadairo_BM_HQ_NOMIP)
    11 ETC1, the colour word of ETC1A4 alone (8 bytes per 4x4 block), opaque (cmn_win04_ID, sel_icon02_ID)
    14 A4, half a byte per pixel, the low nibble first: alpha only, read as white (the font, font_loc_00_AM_NOMIP;
       lby_otomo_icon_AM_NOMIP)
    15 L4, half a byte per pixel, the low nibble first: luminance, opaque (cmn_under_GSM_NOMIP)

`to_array` reads mip 0 of any of them into a numpy array (the renderer's way); `get_region` reads the same pixels as
bytes.

A Tex is a view over the original bytes: the header and the smaller mips are
kept; write it back with to_bytes().
"""

import struct
from dataclasses import dataclass

TEX_TYPE_HASH = 0x241F5DEB
MAGIC = b"TEX\x00"
VERSION = 0xA5
HEADER_SIZE = 0x14
TILE = 8
RGBA5551 = 2
RGBA4444 = 1
ETC1A4 = 12
LA4 = 16
RGBA8888 = 3
ETC1 = 11
A4 = 14
L4 = 15
BYTES_PER_PIXEL = {RGBA4444: 2, RGBA5551: 2, ETC1A4: 1, LA4: 1}     # the formats written pixel by pixel or by block
BITS_PER_PIXEL = {RGBA4444: 16, RGBA5551: 16, RGBA8888: 32, ETC1: 4, ETC1A4: 8, A4: 4, L4: 4, LA4: 8}
# ETC1 intensity modifiers per table: (small, large).
ETC1_MODIFIERS = ((2, 8), (5, 17), (9, 29), (13, 42), (18, 60), (24, 80), (33, 106), (47, 183))
# Grey levels a glyph can use (see Tex.set_glyph): every block has base 132 and modifier table 7, so its
# four ETC1 pixel indices give 132 + 183 (white), 132 + 47, 132 - 47 and 132 - 183 (black).
GLYPH_LEVELS = {"W": 255, "L": 179, "D": 85, "K": 0}  # white, light grey, dark grey, black
GLYPH_INDEX = {"W": 1, "L": 0, "D": 2, "K": 3}
GLYPH_BASE, GLYPH_TABLE = 16, 7  # 5-bit base 16 -> 132


class TexFormatError(ValueError):
    pass


def _morton(index: int) -> tuple[int, int]:
    x = y = 0
    for bit in range(3):
        x |= (index >> (2 * bit) & 1) << bit
        y |= (index >> (2 * bit + 1) & 1) << bit
    return x, y


MORTON_INDEX = {_morton(i): i for i in range(TILE * TILE)}  # (x, y) in a tile -> position
# A pixel's position in its tile is the bits of its x and its y interleaved: the two parts add up.
_MORTON_X = [MORTON_INDEX[(i, 0)] for i in range(TILE)]
_MORTON_Y = [MORTON_INDEX[(0, i)] for i in range(TILE)]
# Lookup tables per byte or channel value, the same arithmetic as per pixel.
_NIBBLES = [bytes(((v >> 4) * 17, (v & 15) * 17)) for v in range(256)]     # a byte's two nibbles widened to 8 bits
_LA4_RGBA = [bytes(((v >> 4) * 17,) * 3 + ((v & 15) * 17,)) for v in range(256)]
_WIDE5 = [v << 3 | v >> 2 for v in range(32)]
_TO4 = [round(c / 17) for c in range(256)]
_TO5 = [round(c * 31 / 255) for c in range(256)]
_GREY4 = [round(total / 3) for total in range(3 * 15 + 1)]     # LA4: the mean of three 4-bit channels


def _decode_etc1(word: int) -> list[tuple[int, int, int]]:
    """RGB of the 16 pixels of an ETC1 colour word, indexed by x * 4 + y."""
    flip = word >> 32 & 1
    if word >> 33 & 1:  # differential: 5-bit base and 3-bit signed delta per channel
        def delta(v: int) -> int:
            return v - 8 if v > 3 else v
        base = [word >> s & 31 for s in (59, 51, 43)]
        second = [(b + delta(word >> s & 7)) & 31 for b, s in zip(base, (56, 48, 40))]
        colours = [tuple(v << 3 | v >> 2 for v in rgb) for rgb in (base, second)]
    else:
        colours = [tuple((word >> s & 15) * 17 for s in shifts) for shifts in ((60, 52, 44), (56, 48, 40))]
    tables = [ETC1_MODIFIERS[word >> s & 7] for s in (37, 34)]
    out = []
    for i in range(16):
        x, y = divmod(i, 4)
        part = (y >= 2) if flip else (x >= 2)
        index = (word >> (16 + i) & 1) << 1 | (word >> i & 1)
        modifier = tables[part][index & 1] * (-1 if index >= 2 else 1)
        out.append(tuple(max(0, min(255, c + modifier)) for c in colours[part]))
    return out


@dataclass
class Tex:
    raw: bytearray
    width: int
    height: int
    mips: int
    format: int

    def _region_offsets(self, x0: int, y0: int, width: int, height: int) -> tuple[list[int], list[int]]:
        """(rows, columns) of a rectangle: pixel (x0 + i, y0 + j) is at byte rows[j] + columns[i], in tile
        (y // TILE) * tiles per row + x // TILE, at its Morton position inside it."""
        size, tile = BYTES_PER_PIXEL[self.format], TILE * TILE
        columns = [HEADER_SIZE + (x // TILE * tile + _MORTON_X[x % TILE]) * size for x in range(x0, x0 + width)]
        rows = [(y // TILE * (self.width // TILE) * tile + _MORTON_Y[y % TILE]) * size for y in range(y0, y0 + height)]
        return rows, columns

    def _block_offset(self, x: int, y: int) -> int:
        """Offset of the 16-byte ETC1A4 block that holds pixel (x, y)."""
        tile = (y // TILE) * (self.width // TILE) + x // TILE
        return HEADER_SIZE + (tile * 4 + (y % TILE // 4) * 2 + x % TILE // 4) * 16

    def get_rgba(self) -> bytes:
        """Mip 0 as RGBA bytes, rows from the top-left corner."""
        return self.get_region(0, 0, self.width, self.height)

    def get_region(self, x0: int, y0: int, width: int, height: int) -> bytes:
        """RGBA bytes of a rectangle of mip 0."""
        if self.format not in BYTES_PER_PIXEL:
            return self.to_array()[y0:y0 + height, x0:x0 + width].tobytes()
        out = bytearray()
        if self.format == ETC1A4:
            blocks: dict[int, tuple[int, list[tuple[int, int, int]]]] = {}
            for y in range(y0, y0 + height):
                for x in range(x0, x0 + width):
                    at = self._block_offset(x, y)
                    if at not in blocks:
                        alpha, colour = struct.unpack_from("<QQ", self.raw, at)
                        blocks[at] = (alpha, _decode_etc1(colour))
                    alpha, colours = blocks[at]
                    i = x % 4 * 4 + y % 4
                    out += bytes((*colours[i], (alpha >> (4 * i) & 15) * 17))
            return bytes(out)
        raw, (rows, columns) = self.raw, self._region_offsets(x0, y0, width, height)
        if self.format == LA4:
            return b"".join(_LA4_RGBA[raw[row + column]] for row in rows for column in columns)
        if self.format == RGBA5551:
            for row in rows:
                for column in columns:
                    v = raw[row + column] | raw[row + column + 1] << 8
                    out += bytes((_WIDE5[v >> 11], _WIDE5[v >> 6 & 31], _WIDE5[v >> 1 & 31], 255 * (v & 1)))
            return bytes(out)
        # RGBA4444, little-endian: the high byte holds red and green, the low byte blue and alpha
        return b"".join(_NIBBLES[raw[row + column + 1]] + _NIBBLES[raw[row + column]]
                        for row in rows for column in columns)

    def to_array(self):
        """Mip 0 as a numpy array of RGBA bytes (height, width, 4), rows from the top-left corner: the same pixels as
        `get_region`, decoded all at once."""
        import numpy as np
        count = self.width * self.height
        size = count * BITS_PER_PIXEL[self.format] // 8
        raw = np.frombuffer(bytes(self.raw[HEADER_SIZE:HEADER_SIZE + size]), np.uint8)
        if self.format in (ETC1, ETC1A4):
            return _etc_array(raw, self.width, self.height, self.format == ETC1A4)
        out = np.empty((count, 4), np.uint8)
        if self.format in (A4, L4):
            nibbles = np.stack((raw & 15, raw >> 4), axis=1).reshape(-1) * 17
            out[:] = 255
            out[:, 3 if self.format == A4 else 0] = nibbles
            if self.format == L4:
                out[:, 1] = out[:, 2] = nibbles
        elif self.format == LA4:
            out[:, 0] = out[:, 1] = out[:, 2] = (raw >> 4) * 17
            out[:, 3] = (raw & 15) * 17
        elif self.format == RGBA8888:
            out[:] = raw.reshape(-1, 4)[:, ::-1]
        else:
            words = raw.view("<u2").astype(np.uint32)
            if self.format == RGBA5551:
                for channel, shift in enumerate((11, 6, 1)):
                    value = words >> shift & 31
                    out[:, channel] = value << 3 | value >> 2
                out[:, 3] = (words & 1) * 255
            else:
                for channel, shift in enumerate((12, 8, 4, 0)):
                    out[:, channel] = (words >> shift & 15) * 17
        return out[_tile_order(self.width, self.height)]

    def set_glyph(self, x0: int, y0: int, rows: list[str]) -> None:
        """Draw a small grey picture into an ETC1A4 texture, replacing whole 4x4 blocks.

        `rows` are strings of equal length (and, like `x0` and `y0`, multiples of 4): a space is a
        transparent pixel (drawn black, so that filtering does not bleed white into the edges), "W"
        white, "L" light grey, "D" dark grey, "K" black; all of them opaque.
        """
        height, width = len(rows), len(rows[0]) if rows else 0
        if self.format != ETC1A4:
            raise TexFormatError("glyphs can only be drawn into ETC1A4 textures")
        if any(len(row) != width for row in rows) or width % 4 or height % 4 or x0 % 4 or y0 % 4:
            raise TexFormatError("a glyph and its position must be made of whole 4x4 blocks")
        if x0 < 0 or y0 < 0 or x0 + width > self.width or y0 + height > self.height:
            raise TexFormatError(f"glyph {width}x{height} at ({x0}, {y0}) is outside the texture")
        if any(c not in " " + "".join(GLYPH_LEVELS) for row in rows for c in row):
            raise TexFormatError("glyph pixels must be spaces or one of W, L, D, K")
        for by in range(0, height, 4):
            for bx in range(0, width, 4):
                alpha = 0
                indices = 0
                for x in range(4):
                    for y in range(4):
                        pixel = rows[by + y][bx + x]
                        i = x * 4 + y
                        index = GLYPH_INDEX["K" if pixel == " " else pixel]
                        alpha |= (0 if pixel == " " else 15) << (4 * i)
                        indices |= (index & 1) << i | (index >> 1) << (16 + i)
                colour = (GLYPH_BASE << 59 | GLYPH_BASE << 51 | GLYPH_BASE << 43 | GLYPH_TABLE << 37
                          | GLYPH_TABLE << 34 | 1 << 33 | indices)
                struct.pack_into("<QQ", self.raw, self._block_offset(x0 + bx, y0 + by), alpha, colour)

    def set_region(self, x0: int, y0: int, width: int, height: int, rgba: bytes) -> None:
        """Write RGBA bytes into a rectangle of mip 0 (rounded to 4 bits per channel; RGBA5551: 5 bits and an alpha
        bit, set from alpha 128; LA4: the luminance is the mean of red, green and blue)."""
        if self.format not in (RGBA4444, RGBA5551, LA4):
            raise TexFormatError("only RGBA4444, RGBA5551 and LA4 textures can be written pixel by pixel")
        if x0 < 0 or y0 < 0 or x0 + width > self.width or y0 + height > self.height:
            raise TexFormatError(f"region {width}x{height} at ({x0}, {y0}) is outside the texture")
        if len(rgba) != width * height * 4:
            raise TexFormatError(f"{len(rgba)} bytes for a {width}x{height} region")
        raw, (rows, columns) = self.raw, self._region_offsets(x0, y0, width, height)
        at = 0
        for row in rows:
            for column in columns:
                r, g, b, a = rgba[at], rgba[at + 1], rgba[at + 2], rgba[at + 3]
                at += 4
                pixel = row + column
                if self.format == RGBA5551:
                    v = _TO5[r] << 11 | _TO5[g] << 6 | _TO5[b] << 1 | (a >= 128)
                    raw[pixel], raw[pixel + 1] = v & 0xFF, v >> 8
                elif self.format == LA4:
                    raw[pixel] = _GREY4[_TO4[r] + _TO4[g] + _TO4[b]] << 4 | _TO4[a]
                else:
                    raw[pixel], raw[pixel + 1] = _TO4[b] << 4 | _TO4[a], _TO4[r] << 4 | _TO4[g]

    def to_bytes(self) -> bytes:
        return bytes(self.raw)


def _tile_order(width: int, height: int):
    """For each pixel of the picture (rows from the top), its index in the tiled storage order."""
    import numpy as np
    y, x = np.mgrid[0:height, 0:width]
    morton = np.zeros_like(x)
    for bit in range(3):
        morton |= (x >> bit & 1) << (2 * bit) | (y >> bit & 1) << (2 * bit + 1)
    return ((y // TILE) * (width // TILE) + x // TILE) * TILE * TILE + morton


def _etc_array(raw, width: int, height: int, with_alpha: bool):
    """ETC1 / ETC1A4 pixels as RGBA (height, width, 4): `_decode_etc1` for every block at once."""
    import numpy as np
    words = raw.view("<u8").reshape(-1, 2 if with_alpha else 1)
    colour, alpha = words[:, -1], words[:, 0] if with_alpha else None

    def bits(shift: int, mask: int):
        return (colour >> np.uint64(shift) & np.uint64(mask)).astype(np.int32)

    flip, differential = bits(32, 1), bits(33, 1)
    base = np.stack([bits(s, 31) for s in (59, 51, 43)], axis=1)
    delta = np.stack([bits(s, 7) for s in (56, 48, 40)], axis=1)
    second = (base + np.where(delta > 3, delta - 8, delta)) & 31
    first_d, second_d = base << 3 | base >> 2, second << 3 | second >> 2
    first_i = np.stack([bits(s, 15) * 17 for s in (60, 52, 44)], axis=1)
    second_i = np.stack([bits(s, 15) * 17 for s in (56, 48, 40)], axis=1)
    colours = np.where(differential[:, None, None] == 1, np.stack((first_d, second_d), axis=1),
                       np.stack((first_i, second_i), axis=1))                          # (blocks, 2, 3)
    modifiers = np.array(ETC1_MODIFIERS, np.int32)
    tables = np.stack((bits(37, 7), bits(34, 7)), axis=1)                             # (blocks, 2)
    blocks = len(colour)
    pixels = np.empty((blocks, 16, 4), np.uint8)
    for i in range(16):
        x, y = divmod(i, 4)
        part = np.where(flip == 1, int(y >= 2), int(x >= 2))
        index = bits(16 + i, 1) << 1 | bits(i, 1)
        modifier = modifiers[tables[np.arange(blocks), part], index & 1] * np.where(index >= 2, -1, 1)
        pixels[:, i, :3] = np.clip(colours[np.arange(blocks), part] + modifier[:, None], 0, 255)
        pixels[:, i, 3] = 255 if alpha is None else (alpha >> np.uint64(4 * i) & np.uint64(15)).astype(np.int32) * 17
    # block b: tile b // 4, its quarter b % 4 (Z order); pixel i of a block: x = i // 4, y = i % 4
    out = np.empty((height, width, 4), np.uint8)
    tiles_per_row = width // TILE
    b = np.arange(blocks)
    left = (b // 4 % tiles_per_row) * TILE + (b % 4 % 2) * 4
    top = (b // 4 // tiles_per_row) * TILE + (b % 4 // 2) * 4
    for i in range(16):
        out[top + i % 4, left + i // 4] = pixels[:, i]
    return out


def new_tex(width: int, height: int, fmt: int = RGBA4444) -> Tex:
    """A blank (fully transparent) texture of `width` x `height` pixels, one mip, in a format `set_region` can write
    (RGBA4444, RGBA5551 or LA4): the header the game's own "NOMIP" textures have (lby_deco_BM_MQ_NOMIP, RGBA4444).
    The sides are whole 8 x 8 tiles."""
    if fmt not in (RGBA4444, RGBA5551, LA4):
        raise TexFormatError(f"a new texture can be RGBA4444, RGBA5551 or LA4, not format {fmt}")
    if not (0 < width <= 0x1FFF and 0 < height <= 0x1FFF) or width % TILE or height % TILE:
        raise TexFormatError(f"size {width}x{height} is not made of 8x8 tiles")
    header = MAGIC + struct.pack("<4I", 0x200000A5, 1 | width << 6 | height << 19, 1 | fmt << 8 | 1 << 16, 0)
    return Tex(bytearray(header + bytes(width * height * BYTES_PER_PIXEL[fmt])), width, height, 1, fmt)


def parse_tex(data: bytes) -> Tex:
    if data[:4] != MAGIC:
        raise TexFormatError("not a TEX file")
    version, dims, info = struct.unpack_from("<3I", data, 4)
    if version & 0xFF != VERSION:
        raise TexFormatError(f"unsupported TEX version {version & 0xFF:#x}")
    mips, width, height = dims & 0x3F, dims >> 6 & 0x1FFF, dims >> 19 & 0x1FFF
    fmt = info >> 8 & 0xFF
    if fmt not in BITS_PER_PIXEL:
        raise TexFormatError(f"unsupported pixel format {fmt}")
    if width % TILE or height % TILE:
        raise TexFormatError(f"size {width}x{height} is not made of 8x8 tiles")
    if len(data) < HEADER_SIZE + width * height * BITS_PER_PIXEL[fmt] // 8:
        raise TexFormatError("pixel data is truncated")
    return Tex(bytearray(data), width, height, mips, fmt)
