"""The installed title's SMDH: its names and icons on the HOME Menu. It is the game's own SMDH
(age ratings, StreetPass id, flags) with the edition's names (edition.json, `console_title`) in every language, the
icons made from the program's logo (icon_48.png and icon_24.png beside this file, tools/build/build_title_icon.py) and
no region lock. Format: 3dbrew "SMDH"."""

import struct
from pathlib import Path

from core.game.files.gui.png import read_png

SIZE = 0x36C0
MAGIC = b"SMDH"
TITLES = 0x8                    # 16 languages of (short name 0x80, long name 0x100, publisher 0x80), UTF-16
LANGUAGES = 16
TITLE_FIELDS = ((0x0, 0x80), (0x80, 0x100), (0x180, 0x80))   # (offset in the language's 0x200, size)
TITLE_SIZE = 0x200
REGION_LOCKOUT = 0x2018
REGION_FREE = 0x7FFFFFFF
ICONS = ((24, 0x2040), (48, 0x24C0))    # (side, offset); RGB565 in 8x8 tiles, each tile in Morton order
ICON_DIR = Path(__file__).resolve().parent
TILE = 8


class SmdhError(ValueError):
    pass


def tile_order(side: int) -> list[tuple[int, int]]:
    """(x, y) of each pixel in the order the SMDH stores them."""
    order = []
    for tile_y in range(0, side, TILE):
        for tile_x in range(0, side, TILE):
            for k in range(TILE * TILE):
                x = (k & 1) | ((k >> 1) & 2) | ((k >> 2) & 4)
                y = ((k >> 1) & 1) | ((k >> 2) & 2) | ((k >> 3) & 4)
                order.append((tile_x + x, tile_y + y))
    return order


def encode_icon(side: int, rgba: bytes) -> bytes:
    """A `side`-pixel square icon (RGBA rows, opaque) as the SMDH stores it."""
    if len(rgba) != side * side * 4:
        raise SmdhError(f"an icon of {side} pixels has {side * side * 4} bytes of RGBA, not {len(rgba)}")
    out = bytearray()
    for x, y in tile_order(side):
        r, g, b, a = rgba[(y * side + x) * 4:(y * side + x) * 4 + 4]
        if a != 255:
            raise SmdhError("the SMDH has no transparency: the icon must be opaque")
        out += struct.pack("<H", (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3))
    return bytes(out)


def decode_icon(side: int, data: bytes) -> bytes:
    """The RGBA rows of an SMDH icon (each channel's low bits are lost in RGB565)."""
    rgba = bytearray(side * side * 4)
    for n, (x, y) in enumerate(tile_order(side)):
        (value,) = struct.unpack_from("<H", data, n * 2)
        at = (y * side + x) * 4
        rgba[at:at + 4] = bytes((value >> 11 << 3, (value >> 5 & 0x3F) << 2, (value & 0x1F) << 3, 255))
    return bytes(rgba)


def _text(value: str, size: int) -> bytes:
    raw = value.encode("utf-16-le")
    if len(raw) >= size:      # one UTF-16 unit stays for the terminating zero
        raise SmdhError(f"{value!r} is too long for {size // 2 - 1} characters")
    return raw.ljust(size, b"\0")


def logo_icon(side: int) -> bytes:
    """The RGBA of icon_<side>.png."""
    width, height, rgba = read_png((ICON_DIR / f"icon_{side}.png").read_bytes())
    if (width, height) != (side, side):
        raise SmdhError(f"icon_{side}.png is {width}x{height}, not {side}x{side}")
    return rgba


def title_smdh(game_smdh: bytes, short_name: str, long_name: str, publisher: str,
               icons: dict[int, bytes] | None = None) -> bytes:
    """The game's SMDH with these names in every language, the icons (side -> RGBA; default the logo's) and no
    region lock."""
    if len(game_smdh) < SIZE or game_smdh[:4] != MAGIC:
        raise SmdhError("the game's icon is not an SMDH")
    smdh = bytearray(game_smdh[:SIZE])
    names = (_text(short_name, 0x80), _text(long_name, 0x100), _text(publisher, 0x80))
    for language in range(LANGUAGES):
        base = TITLES + language * TITLE_SIZE
        for (offset, size), text in zip(TITLE_FIELDS, names):
            smdh[base + offset:base + offset + size] = text
    struct.pack_into("<I", smdh, REGION_LOCKOUT, REGION_FREE)
    for side, at in ICONS:
        pixels = icons[side] if icons else logo_icon(side)
        smdh[at:at + side * side * 2] = encode_icon(side, pixels)
    return bytes(smdh)
