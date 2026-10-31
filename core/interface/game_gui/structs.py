"""MH4U's GUI objects in memory, read only.

The readers take any `memory` with `read(address, size) -> bytes` and `word(address) -> int`:
`gamegui.memory.GameMemory` (the running game) and `tools/citra_state.DataView` (a save state) both fit, and so does
`MemoryImage` (a copy of `regions(...)`, parsed offline). Static addresses (.data / .bss) are canonical (the EUR
update's) and always go through `read`, which moves them to the running version; heap addresses are the process's
own. Vtables in memory are the running version's: `shifted(memory, canonical)` moves a canonical one there.

The objects:
    sMhLayout (*SLAYOUT_POINTER, 0x248)  fonts, animation players, the main uLayout (+0x100)
    sMhUnit (*SUNIT_POINTER)            32 move lines of units; every uLayout is a unit there
    uLayout (0x198)                     a GUI manager: pools, root groups, draw list
    group (0x50)                        a root group: name, place, layer, priority, view (screen), shown
    pane (0x24)                         tree node: name, kind, depth, links, its data by kind
    sprite 0x68 / null 0x30 / text 0x80 / boundary 0x30 / window 0x88   the panes' data
"""

import struct
from dataclasses import dataclass, field

# --- statics (canonical .bss) -----------------------------------------------------------------------------------------
SLAYOUT_POINTER = 0x1057534     # sMhLayout (sLayout's subclass): the main GUI
SUNIT_POINTER = 0x10572F8       # sMhUnit (sUnit): the units' move lines

# --- sMhLayout (DTI 0x10B514C, 0x248 bytes; base sLayout 0x100) -------------------------------------------------------
SLAYOUT_SIZE = 0x248
SLAYOUT_DRAW_BUFFER = 0xB0      # u32, 0/1: the vertex buffer being built (flipped once per frame, FUN_00af3d90)
SLAYOUT_FONTS = 0xDC            # rLayoutFont *[FONT_SLOTS] (FUN_00af3cfc)
FONT_SLOTS = 8
SLAYOUT_MAIN = 0x100            # uLayout *: the main GUI manager (FUN_00c0d854)
SLAYOUT_TOP_VIEW = 0x245        # u8, 0: the view (screen) the loaders give top-screen layouts
SLAYOUT_BOTTOM_VIEW = 0x246     # u8, 7: the touch screen's view
SLAYOUT_PLAYERS = 0x220         # pool of animation players (0x30 each); live ones are its array's first `used`

# --- sMhUnit ----------------------------------------------------------------------------------------------------------
UNIT_LINES = 0x14               # 32 lines of 0x18 bytes: +0x04 name, +0x08 flags, +0x0C first unit, +0x10 last unit
UNIT_LINE_COUNT = 32
UNIT_LINE_SIZE = 0x18
UNIT_NEXT = 0x0C                # cUnit: next unit of its line
UNIT_FLAGS = 0x04               # cUnit: bits 0-2 state, 3-9 move line, 16-25 mDrawView (one bit per view)
UNIT_HEAD = 0x10                # bytes of a unit the enumeration reads

# The uLayout family: canonical vtable -> class (DTIs: uLayout 0x10E9118, its subclasses' parents point at it).
MANAGER_VTABLES = {
    0xE6BB40: "uLayout",
    0xE60E14: "uLayoutMonnyan",         # the Meownster Hunters' trip (FUN_00375cb8); draws through FUN_00375724
    0xE5EF3C: "uSwkbdLayout",           # the software keyboard
    0xE61D68: "uLayoutScheduler",
    0xE62AC0: "uLytAnimeScheduler",
    0xE63520: "uLytMessageScheduler",
}

# --- uLayout (0x198) --------------------------------------------------------------------------------------------------
MANAGER_SIZE = 0x198
POOL_SIZE = 0x14                # pool: +0 slab, +4 element size, +8 count, +0xC used, +0x10 pointer array
POOLS = {                       # name -> (offset in the uLayout, element size)
    "groups": (0x64, 0x50),
    "panes": (0x78, 0x24),
    "sprites": (0x8C, 0x68),
    "windows": (0xA0, 0x88),
    "nulls": (0xB4, 0x30),
    "texts": (0xC8, 0x80),
    "boundaries": (0xDC, 0x30),
    "tracks": (0xF0, 0x18),     # animation tracks (a player's bindings of a key list to a pane)
}
DRAW_LIST = 0x120               # first group of the draw list (next: group + GROUP_NEXT)
GROUP_LIST = 0x154              # group *[group count]: the root groups by index
TEXTURE_LIST = 0x158
MANAGER_FLAGS = 0x15C           # bits 0-3 the view of new groups, 0x10 fill texts at load
GROUP_COUNT = 0x160
SLAB = 0x18C                    # the group list, texture lists and the groups' texture arrays, one allocation
SLAB_SIZE = 0x190

# --- group (0x50) -----------------------------------------------------------------------------------------------------
GROUP_SIZE = 0x50
GROUP_HASH, GROUP_NAME, GROUP_FIRST_PANE = 0x00, 0x04, 0x08
GROUP_REDRAW_FIRST, GROUP_REDRAW_LAST, GROUP_CONTEXT = 0x0C, 0x10, 0x14
GROUP_ORDER = 0x18              # bits 27-31 layer, 19-26 priority (FUN_00ae63c8)
GROUP_COMMANDS = 0x1C           # 2 cached GPU command lists, one per draw buffer
GROUP_TEXTURES = 0x24
GROUP_POSITION = 0x28           # f32 x, y, z (z: the loaders' depth, 22.0 for most)
GROUP_COLOR = 0x3C              # RGBA; byte +0x3F alpha
GROUP_REVISION = 0x40           # bits 24-30 changes, byte +0x42 the buffers to rebuild
GROUP_FLAGS = 0x44              # 0-7 textures, 0x100 cache, 0x400 shown, 14-17 view, 18-31 index
GROUP_NEXT, GROUP_PREVIOUS = 0x48, 0x4C
SHOWN = 0x400
VIEW_SHIFT, VIEW_MASK = 14, 0xF
INDEX_SHIFT = 18

# --- pane (0x24) ------------------------------------------------------------------------------------------------------
PANE_SIZE = 0x24
PANE_HASH, PANE_NAME, PANE_DATA, PANE_REDRAW, PANE_KIND = 0x00, 0x04, 0x08, 0x0C, 0x10
PANE_DEPTH, PANE_DIRTY = 0x11, 0x12
PANE_NEXT, PANE_PREVIOUS, PANE_PARENT, PANE_CHILD = 0x14, 0x18, 0x1C, 0x20
SPRITE, NULL, TEXT, BOUNDARY, WINDOW = 0, 1, 2, 3, 4           # the runtime kinds (the file's differ)
KIND_NAMES = {SPRITE: "sprite", NULL: "null", TEXT: "text", BOUNDARY: "boundary", WINDOW: "window"}
DATA_SIZES = {SPRITE: 0x68, NULL: 0x30, TEXT: 0x80, BOUNDARY: 0x30, WINDOW: 0x88}
MAX_PANES = 0x10000             # a guard against a broken tree
MAX_TREE_DEPTH = 32             # layout files go 5 deep, the game adds a few levels (texts' glyphs); more is broken

# --- text (0x80) ------------------------------------------------------------------------------------------------------
TEXT_FLAGS = 0x5C               # 0-3 align, 4-7 origin, 8-15 font, 24-27 outline layers (one sprite more each)
TEXT_LENGTH, TEXT_GLYPHS, TEXT_CAPACITY = 0x6C, 0x70, 0x74
TEXT_FONT_TEXTURE = 0x60        # the font's texture word; its glyph sprites hold it at + 0, with flags in the top byte
TEXTURE_ID = 0x00FFFFFF        # a texture word without its flags (0x40000000, 0x20000000 seen on glyphs)
ICON = "\ufffc"                 # an inline icon (a button...) in a decoded string: a sprite of another texture
NAME_LIMIT = 64                 # bytes read for a name (the layouts' names are shorter)

# --- rLayoutFont ------------------------------------------------------------------------------------------------------
FONT_DATA = 0x64                # -> "lfd\0": +0x08 glyph count, +0x0C page count, +0x14 size, +0x1C glyphs, +0x20 pages
GLYPH_SIZE, FONT_PAGE_SIZE = 0x14, 0x24

# --- animation player (0x30) ------------------------------------------------------------------------------------------
PLAYER_SIZE = 0x30


def f32(word: int) -> float:
    return struct.unpack("<f", struct.pack("<I", word))[0]


def _u32(memory, address: int) -> int:
    """A static (canonical .data / .bss) word."""
    return struct.unpack("<I", memory.read(address, 4))[0]


def shifted(memory, address: int) -> int:
    """The running version's address of canonical `address` (a vtable): through the memory's own `shift` when it has
    one (gamegui.memory.GameMemory, the recorder's views), else its version map."""
    shift = getattr(memory, "shift", None)
    if shift is not None:
        return shift(address)
    version = getattr(memory, "version", None)
    moved = None if version is None else version.to_version(address)
    return address if moved is None else moved


def _words(memory, address: int, count: int) -> tuple[int, ...]:
    return struct.unpack(f"<{count}I", memory.read(address, 4 * count))


def _floats(memory, address: int, count: int) -> tuple[float, ...]:
    return struct.unpack(f"<{count}f", memory.read(address, 4 * count))


def _string(memory, address: int, limit: int = NAME_LIMIT) -> str | None:
    if not address:
        return None
    try:
        raw = memory.read(address, limit).split(b"\0")[0]
    except (ValueError, LookupError, OSError, struct.error):
        return None
    return raw.decode("ascii", "replace")


# --- dataclasses ------------------------------------------------------------------------------------------------------
@dataclass
class Pool:
    name: str
    slab: int               # the elements, `count` of `element_size`, then the pointer array
    element_size: int
    count: int
    used: int               # handed out (the free ones are the array's [used:])
    array: int

    @property
    def size(self) -> int:
        """Bytes from the slab to the pointer array's end (one allocation)."""
        return (self.element_size + 4) * self.count

    def contains(self, address: int) -> bool:
        return self.slab <= address < self.slab + self.element_size * self.count


@dataclass
class Manager:
    address: int
    class_name: str
    line: int                   # sMhUnit's move line
    draw_views: int             # mDrawView: bit v = drawn in view v (0 the top screen, 7 the touch screen)
    pools: dict[str, Pool]
    group_list: int
    group_count: int
    draw_list: int
    flags: int


@dataclass
class Sprite:
    position: tuple[float, float, float]
    size: tuple[float, float]
    scale: tuple[float, float]
    uv: tuple[float, float, float, float]       # texture region (u, v, width, height), in texture units
    colors: tuple[int, int, int, int]           # RGBA words, the four corners
    origin: int                                 # 0 top-left corner ... 4 centre (as the file's)
    visible: bool
    primitive: int                              # bits 8-31 of +0x58: the pane's own draw primitive
    texture: tuple[int, int, int]               # +0x00: the texture reference (glyphs: the font's, with flags)
    cell: int                                   # +0x04: a glyph's page in the low byte; an inline icon's number


@dataclass
class Null:
    position: tuple[float, float, float]
    scale: tuple[float, float]
    color: int
    visible: bool


@dataclass
class Text:
    font_size: tuple[float, float]
    spacing: tuple[float, float]
    position: tuple[float, float, float]
    box: tuple[float, float]
    colors: tuple[int, int, int, int]
    align: int                  # 0 left, 1 right, 2 centred
    origin: int                 # 0 the box's top-left corner, 4 its centre
    font: int
    layers: int                 # outline / shadow copies drawn under each glyph
    length: int                 # characters of the last string set
    glyphs: int                 # glyph sprites held
    font_texture: int           # the font texture word (+0x60)
    string: str | None = None   # decoded from the glyph sprites through the font (read_fonts), None without fonts


@dataclass
class Boundary:
    position: tuple[float, float]
    size: tuple[float, float]
    scale: tuple[float, float]
    origin: int
    rect: tuple[float, float, float, float]     # left, top, right, bottom (FUN_00ae87dc)


@dataclass
class Pane:
    address: int
    name_hash: int
    name: str | None
    kind: int
    depth: int
    data: int
    parent: int
    detail: Sprite | Null | Text | Boundary | None = None
    children: list["Pane"] = field(default_factory=list)

    @property
    def kind_name(self) -> str:
        return KIND_NAMES.get(self.kind, f"kind {self.kind}")

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class Group:
    address: int
    manager: int
    index: int
    name_hash: int
    name: str | None
    layer: int
    priority: int
    view: int                   # the screen: the view it is drawn in (0 top, 7 touch screen)
    shown: bool
    position: tuple[float, float, float]
    color: int
    revision: int
    flags: int
    panes: list[Pane] = field(default_factory=list)     # the top-level panes, each with its subtree

    def walk(self):
        for pane in self.panes:
            yield from pane.walk()


@dataclass
class Font:
    address: int
    size: int
    glyphs: dict[tuple[int, int, int], int]     # (page, x, y) in texels -> character
    scales: list[tuple[float, float]]           # per page: texture units per texel (u, v)


@dataclass
class Player:
    address: int
    resource: int
    clip: int
    frame: float
    start: float
    end: float
    speed: float
    flags: int


# --- readers ----------------------------------------------------------------------------------------------------------
def read_pool(memory, manager: int, name: str) -> Pool:
    offset, _ = POOLS[name]
    slab, size, count, used, array = _words(memory, manager + offset, 5)
    return Pool(name, slab, size, count, used, array)


def units(memory):
    """(line, unit) of every unit in sMhUnit's move lines."""
    unit_system = _u32(memory, SUNIT_POINTER)
    if not unit_system:
        return
    for line in range(UNIT_LINE_COUNT):
        unit = memory.word(unit_system + UNIT_LINES + UNIT_LINE_SIZE * line + 0x0C)
        seen = 0
        while unit and seen < 0x4000:
            yield line, unit
            unit = memory.word(unit + UNIT_NEXT)
            seen += 1


def read_managers(memory) -> list[Manager]:
    """Every live GUI manager (uLayout and its subclasses), from sMhUnit's lines: the main GUI's and the scenes' own
    (the Meownster Hunters' trip, the keyboard). Each is told by its vtable."""
    classes = {shifted(memory, vtable): name for vtable, name in MANAGER_VTABLES.items()}
    out = []
    for line, unit in units(memory):
        name = classes.get(memory.word(unit))
        if name is None:
            continue
        pools = {pool: read_pool(memory, unit, pool) for pool in POOLS}
        flags = memory.word(unit + UNIT_FLAGS)
        out.append(Manager(unit, name, line, flags >> 16 & 0x3FF, pools, memory.word(unit + GROUP_LIST),
                           memory.word(unit + GROUP_COUNT), memory.word(unit + DRAW_LIST),
                           memory.word(unit + MANAGER_FLAGS)))
    return out


def main_manager(memory) -> int:
    """The main GUI's uLayout (*(sMhLayout + 0x100)), 0 before the GUI exists."""
    layout = _u32(memory, SLAYOUT_POINTER)
    return memory.word(layout + SLAYOUT_MAIN) if layout else 0


def group_addresses(memory, manager: Manager) -> list[tuple[int, int]]:
    """(index, group) of the manager's root groups."""
    if not manager.group_list or not manager.group_count:
        return []
    words = _words(memory, manager.group_list, manager.group_count)
    return [(index, group) for index, group in enumerate(words) if group]


def read_sprite(memory, data: int) -> Sprite:
    words = _words(memory, data, DATA_SIZES[SPRITE] // 4)
    floats = struct.unpack("<26f", struct.pack("<26I", *words))
    flags = words[0x58 // 4]
    return Sprite(floats[4:7], floats[8:10], floats[10:12], floats[12:16], words[16:20], flags & 0xF,
                  bool(flags & 0x80), flags >> 8, words[0:3], words[1])


def read_null(memory, data: int) -> Null:
    words = _words(memory, data, DATA_SIZES[NULL] // 4)
    floats = struct.unpack("<12f", struct.pack("<12I", *words))
    return Null(floats[0:3], floats[4:6], words[6], bool(words[9] & 1))


def read_boundary(memory, data: int) -> Boundary:
    words = _words(memory, data, DATA_SIZES[BOUNDARY] // 4)
    floats = struct.unpack("<12f", struct.pack("<12I", *words))
    return Boundary(floats[0:2], floats[2:4], floats[4:6], words[6] & 0xFF, floats[8:12])


def read_text(memory, data: int) -> Text:
    words = _words(memory, data, DATA_SIZES[TEXT] // 4)
    floats = struct.unpack("<32f", struct.pack("<32I", *words))
    flags = words[TEXT_FLAGS // 4]
    return Text(floats[2:4], floats[4:6], floats[6:9], floats[12:14], words[14:18], flags & 0xF, flags >> 4 & 0xF,
                flags >> 8 & 0xFF, bin(flags >> 24 & 0xF).count("1"), words[TEXT_LENGTH // 4],
                words[TEXT_GLYPHS // 4], words[TEXT_FONT_TEXTURE // 4])


READERS = {SPRITE: read_sprite, NULL: read_null, TEXT: read_text, BOUNDARY: read_boundary}


class BrokenTree(ValueError):
    """A pane tree whose links loop or go deeper than any GUI's: read while the game changed it, or not a tree."""


def read_pane_tree(memory, first: int, depth: int = 1, parent: int = 0, budget: list | None = None,
                   details: bool = True, names: bool = True, seen: set | None = None) -> list[Pane]:
    """The panes from `first` along its siblings, each with its subtree (pre-order, as the layout file). Without
    `names` the names' strings are not read (the recorder names panes from the layout files). BrokenTree when a link
    leads back to a pane already read or the tree is deeper than MAX_TREE_DEPTH."""
    budget = budget if budget is not None else [MAX_PANES]
    seen = seen if seen is not None else set()
    if depth > MAX_TREE_DEPTH:
        raise BrokenTree(f"pane {first:#x}: deeper than {MAX_TREE_DEPTH}")
    out = []
    pane = first
    while pane and budget[0] > 0:
        if pane in seen:
            raise BrokenTree(f"pane {pane:#x} is reached twice: the links loop")
        seen.add(pane)
        budget[0] -= 1
        words = _words(memory, pane, PANE_SIZE // 4)
        kind = words[PANE_KIND // 4] & 0xFF
        node = Pane(pane, words[0], _string(memory, words[1]) if names else None, kind,
                    words[PANE_KIND // 4] >> 8 & 0xFF, words[PANE_DATA // 4], parent)
        if details and node.data and kind in READERS:
            node.detail = READERS[kind](memory, node.data)
        child = words[PANE_CHILD // 4]
        if child:
            node.children = read_pane_tree(memory, child, depth + 1, pane, budget, details, names, seen)
        out.append(node)
        pane = words[PANE_NEXT // 4]
    return out


def read_group(memory, group: int, manager: int = 0, panes: bool = True, details: bool = True,
               names: bool = True) -> Group:
    words = _words(memory, group, GROUP_SIZE // 4)
    flags, order = words[GROUP_FLAGS // 4], words[GROUP_ORDER // 4]
    out = Group(group, manager, flags >> INDEX_SHIFT, words[0], _string(memory, words[1]) if names else None,
                order >> 27, order >> 19 & 0xFF, flags >> VIEW_SHIFT & VIEW_MASK, bool(flags & SHOWN),
                struct.unpack("<3f", struct.pack("<3I", *words[10:13])), words[GROUP_COLOR // 4],
                words[GROUP_REVISION // 4], flags)
    if panes and words[GROUP_FIRST_PANE // 4]:
        out.panes = read_pane_tree(memory, words[GROUP_FIRST_PANE // 4], details=details, names=names)
    return out


def read_groups(memory, manager: Manager, panes: bool = True, details: bool = True) -> list[Group]:
    return [read_group(memory, group, manager.address, panes, details) for _, group in group_addresses(memory, manager)]


def draw_list(memory, manager: Manager) -> list[int]:
    """The groups in the manager's draw list, in its order (shown ones; FUN_00ae53e0 links them)."""
    out, group = [], manager.draw_list
    while group and len(out) < 0x4000:
        out.append(group)
        group = memory.word(group + GROUP_NEXT)
    return out


# --- fonts and texts --------------------------------------------------------------------------------------------------
def font_addresses(memory) -> dict[int, int]:
    layout = _u32(memory, SLAYOUT_POINTER)
    if not layout:
        return {}
    words = _words(memory, layout + SLAYOUT_FONTS, FONT_SLOTS)
    return {slot: font for slot, font in enumerate(words) if font}


def read_font(memory, font: int) -> Font | None:
    data = memory.word(font + FONT_DATA)
    if not data or memory.read(data, 4) != b"lfd\0":
        return None
    header = _words(memory, data, 9)
    count, pages, size, glyph_table, page_table = header[2], header[3], header[5], header[7], header[8]
    scales = []
    for page in range(pages):
        scales.append(_floats(memory, page_table + FONT_PAGE_SIZE * page + 0x0C, 2))
    raw = memory.read(glyph_table, GLYPH_SIZE * count)
    glyphs = {}
    for at in range(0, len(raw), GLYPH_SIZE):
        code, where, _, _, _ = struct.unpack_from("<5I", raw, at)
        glyphs.setdefault((where & 0xFF, where >> 8 & 0xFFF, where >> 20 & 0xFFF), code)
    return Font(font, size, glyphs, scales)


def read_fonts(memory) -> dict[int, Font]:
    """The GUI's fonts by slot (a text's `font`)."""
    out = {}
    for slot, font in font_addresses(memory).items():
        try:
            read = read_font(memory, font)
        except (ValueError, LookupError, OSError):  # outside the memory read (a state without the linear heap, a copy
            continue                                # without the fonts)
        if read is not None:
            out[slot] = read
    return out


def glyph_char(font: Font, glyph: Sprite) -> str | None:
    """The character a glyph sprite draws, from its texture region in the font's page."""
    page = glyph.cell & 0xFF
    if page >= len(font.scales):
        return None
    su, sv = font.scales[page]
    if not su or not sv:
        return None
    key = (page, round(glyph.uv[0] / su), round(glyph.uv[1] / sv))
    code = font.glyphs.get(key)
    return None if code is None else chr(code)


def decode_text(memory, pane: Pane, fonts: dict[int, Font]) -> str | None:
    """A text pane's string: the glyph sprites under its own null (the pane after it, FUN_00b03f90), `layers` + 1 per
    character, a zero-size one for a line break (FUN_00ae4034), one of another texture for an inline icon (ICON).
    None when its font is not read; U+FFFD for a glyph not in the font."""
    text = pane.detail
    if not isinstance(text, Text) or text.font not in fonts:
        return None
    holder = memory.word(pane.address + PANE_NEXT)
    if not holder:
        return ""
    sprites = []
    child = memory.word(holder + PANE_CHILD)
    while child and len(sprites) < text.glyphs:
        sprites.append(child)
        child = memory.word(child + PANE_NEXT)
    step = text.layers + 1
    out = []
    for at in range(0, min(len(sprites), step * text.length), step):
        glyph = read_sprite(memory, memory.word(sprites[at] + PANE_DATA))
        if glyph.size == (0.0, 0.0):
            out.append("\n")
            continue
        if glyph.texture[0] & TEXTURE_ID != text.font_texture & TEXTURE_ID:
            out.append(ICON)
            continue
        char = glyph_char(fonts[text.font], glyph)
        out.append("\ufffd" if char is None else char)
    return "".join(out)


def fill_texts(memory, group: Group, fonts: dict[int, Font]) -> None:
    for pane in group.walk():
        if pane.kind == TEXT and isinstance(pane.detail, Text):
            pane.detail.string = decode_text(memory, pane, fonts)


# --- animation players ------------------------------------------------------------------------------------------------
def read_players(memory) -> list[Player]:
    """sMhLayout's live animation players (its pool's array[:used]); scenes keep players of their own (the trip's at
    +0x204, +0x258...), not listed here."""
    layout = _u32(memory, SLAYOUT_POINTER)
    if not layout:
        return []
    slab, size, count, used, array = _words(memory, layout + SLAYOUT_PLAYERS, 5)
    out = []
    for player in (_words(memory, array, used) if used and used <= count else ()):
        words = _words(memory, player, PLAYER_SIZE // 4)
        out.append(Player(player, words[0], words[1], f32(words[9]), f32(words[6]), f32(words[7]), f32(words[10]),
                          words[11]))
    return out


# --- regions and the memory image -------------------------------------------------------------------------------------
def regions(memory, managers: list[Manager] | None = None, fonts: bool = False) -> list[tuple[int, int]]:
    """The (address, size) ranges that hold everything a snapshot reads: the statics, sMhLayout, sMhUnit's lines and
    the units' heads (the enumeration), each manager and its pools and slab, the animation players; with `fonts`, the
    fonts' tables too (they do not change while a game runs: copy them once). Static ranges are canonical."""
    layout = _u32(memory, SLAYOUT_POINTER)
    unit_system = _u32(memory, SUNIT_POINTER)
    out = [(SLAYOUT_POINTER, 4), (SUNIT_POINTER, 4)]
    if unit_system:
        out.append((unit_system, UNIT_LINES + UNIT_LINE_COUNT * UNIT_LINE_SIZE))
        out += [(unit, UNIT_HEAD) for _, unit in units(memory)]
    if layout:
        out.append((layout, SLAYOUT_SIZE))
        slab, size, count, _, _ = _words(memory, layout + SLAYOUT_PLAYERS, 5)
        if slab and count:
            out.append((slab, (size + 4) * count))
    for manager in read_managers(memory) if managers is None else managers:
        out.append((manager.address, MANAGER_SIZE))
        for pool in manager.pools.values():
            if pool.slab and pool.count:
                out.append((pool.slab, pool.size))
        slab, slab_size = _words(memory, manager.address + SLAB, 2)
        if slab and slab_size:
            out.append((slab, slab_size))
    if fonts:
        for font in font_addresses(memory).values():
            try:
                out += font_regions(memory, font)
            except ValueError:
                pass
    return merge(out)


def font_regions(memory, font: int) -> list[tuple[int, int]]:
    data = memory.word(font + FONT_DATA)
    out = [(font, FONT_DATA + 4)]
    if data:
        header = _words(memory, data, 9)
        out += [(data, 0x30), (header[7], GLYPH_SIZE * header[2]), (header[8], FONT_PAGE_SIZE * header[3])]
    return out


def name_regions(memory, groups: list[Group]) -> list[tuple[int, int]]:
    """The names' strings (in the layouts' resources, which stay while their groups live; the few a scene's code
    names point into the executable, left out when `memory` cannot read them)."""
    out = []
    for group in groups:
        names = [memory.word(group.address + GROUP_NAME)] + [memory.word(p.address + PANE_NAME) for p in group.walk()]
        for name in names:
            if name:
                try:
                    memory.read(name, NAME_LIMIT)
                except ValueError:
                    continue
                out.append((name, NAME_LIMIT))
    return merge(out)


def merge(ranges: list[tuple[int, int]], gap: int = 0x40) -> list[tuple[int, int]]:
    """Sorted ranges, those closer than `gap` joined."""
    out: list[list[int]] = []
    for start, size in sorted(r for r in ranges if r[1] > 0):
        if out and start <= out[-1][0] + out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], start + size - out[-1][0])
        else:
            out.append([start, size])
    return [(start, size) for start, size in out]


class MemoryImage:
    """A copy of some ranges of the game's memory, read as the game's: `read` / `word` over the copied bytes (static
    ranges by their canonical address, as the source's `read` takes them). Anything outside raises ValueError."""

    def __init__(self, chunks: dict[int, bytes], version=None):
        self.chunks = dict(sorted(chunks.items()))
        self.version = version
        self._starts = list(self.chunks)

    @classmethod
    def copy(cls, memory, ranges: list[tuple[int, int]]) -> "MemoryImage":
        return cls({start: memory.read(start, size) for start, size in ranges}, getattr(memory, "version", None))

    def covers(self, ranges: list[tuple[int, int]]) -> bool:
        return all(self._find(start, size) is not None for start, size in ranges)

    def _find(self, address: int, size: int):
        import bisect
        at = bisect.bisect_right(self._starts, address) - 1
        if at < 0:
            return None
        start = self._starts[at]
        data = self.chunks[start]
        if address + size <= start + len(data):
            return data, address - start
        return None

    def read(self, address: int, size: int) -> bytes:
        found = self._find(address, size)
        if found is None:
            raise ValueError(f"{address:#x} + {size:#x} is not in the image")
        data, at = found
        return data[at:at + size]

    def word(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]
