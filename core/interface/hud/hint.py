"""The hint of the target switch (option touchless_target, L + D-pad up): a D-pad glyph with only its up arm
lit, in the item selector's L bar, to the left of the target face.

The game has no "D-pad up" glyph, so the hint has a texture of its own, HINT_TEXTURE, in each language's
core_quest.arc right before ui205 (a layout binds its textures as it loads), and a sprite showing it is added to
ui205, animated like the bar's Y button glyph (shown only while the bar opened with L is open). The texture is cut,
tile for tile, from the game's quest atlas qst00_ID with the glyph drawn in a free corner of it (GLYPH_AT), so the
glyph and the transparent texels the filter reads around it are those of the atlas; the atlas itself keeps its bytes,
so an HD texture pack's picture of it applies with any installer. Each language's copy differs in one block no
sprite reaches (MARKER_BLOCK), so a pack can tell them apart.
"""

import struct

from core.game.files.arc import ArcEntry, parse_arc, write_arc
from core.interface.hud.code_patch import FACE_RIGHT_GAP, FACE_SCALE, ITEM_ICON_Y
from core.game.files.gui.lanl import LANL_TYPE_HASH, parse_lanl
from core.game.files.gui.lyt import LYT_TYPE_HASH, name_hash, parse_lyt
from core.game.files.gui.tex import ETC1A4, HEADER_SIZE, MAGIC, TEX_TYPE_HASH, TILE, parse_tex

LAYOUT = "ui205"
ANIMATION = "ui205_select"      # opens / closes the L bar
PARENT = "ui205_shita_ita"      # the L bar of the item selector
TEMPLATE = "ui205_y_button01"   # a 16 x 16 glyph sprite shown only in the open bar: the copy keeps its
NAME = "ui205_dpad_up"          # colours and flags, and gets its animation
TEXTURE = "qst00_ID"            # the game's quest atlas (ui205's third texture); nothing uses its lower right quarter
TEXTURE_SIZE = 512
QUEST_ARC = "core_quest.arc"    # the layout and one copy of the atlas
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
GLYPH_AT = (448, 448)           # where the glyph is drawn in the atlas, in pixels, multiples of 4
HINT_TEXTURE = "lyt\\quest\\texture\\hf_dpad_ID"
HINT_SIZE = 32                  # the square cut from the atlas, whole 8 x 8 tiles
CUT_AT = (440, 440)             # its corner in the atlas
HINT_GLYPH_AT = (GLYPH_AT[0] - CUT_AT[0], GLYPH_AT[1] - CUT_AT[1])
MARKER_BLOCK = (28, 28)         # a transparent 4 x 4 block of the cut, past the filter's reach: its colour the
# language's grey (its number + 1 in the 4-bit R, G and B of both halves of ETC1's individual mode; tables and pixel
# indices 0), so its decoded texels differ too (the old picture naming hashes those), its alpha 0
MARKER_SHIFTS = (60, 56, 52, 48, 44, 40)
GLYPH_ROWS = [
    "     KKKKKK     ",
    "    KWWWWWWK    ",
    "    KWWWWWWK    ",
    "    KWWWWWWK    ",
    " KKKKWWWWWWKKKK ",
    "KDDDDDDDDDDDDDDK",
    "KDDDDDDDDDDDDDDK",
    "KDDDDDDDDDDDDDDK",
    "KDDDDDDDDDDDDDDK",
    "KDDDDDDDDDDDDDDK",
    "KDDDDDDDDDDDDDDK",
    " KKKKDDDDDDKKKK ",
    "    KDDDDDDK    ",
    "    KDDDDDDK    ",
    "    KDDDDDDK    ",
    "     KKKKKK     ",
]
GLYPH_SIZE = 16
GAP = 2.0                       # between the glyph and the lock mark of the face


def hint_position() -> tuple[float, float]:
    """Layout coordinates of the glyph at 100 %: at the height of the item's icon and the face, left of the
    face's lock mark (60 x 60 at the face's scale; the face is 48 wide), which sticks out by 6 on each side.
    The group scales towards the bottom-right corner like the face does, so the gap stays at any HUD size."""
    distance_from_right_edge = FACE_RIGHT_GAP + (48 + 6) * FACE_SCALE + GAP + GLYPH_SIZE / 2
    return distance_from_right_edge - 200, ITEM_ICON_Y


def hint_texture(atlas: bytes, lang: str) -> bytes:
    """HINT_TEXTURE for `lang` (LANGUAGES): the HINT_SIZE square at CUT_AT of the game's atlas `atlas` (a TEX file of
    qst00_ID) with the glyph drawn in, tile for tile, and the language's marker."""
    if lang not in LANGUAGES:
        raise ValueError(f"no language {lang!r}")
    texture = parse_tex(atlas)
    if (texture.width, texture.height, texture.format) != (TEXTURE_SIZE, TEXTURE_SIZE, ETC1A4):
        raise ValueError(f"unexpected {TEXTURE}: {texture.width}x{texture.height}, format {texture.format}")
    texture.set_glyph(*GLYPH_AT, GLYPH_ROWS)
    tile, per_row, side = TILE * TILE, TEXTURE_SIZE // TILE, HINT_SIZE // TILE
    version, _, info, extra = struct.unpack_from("<4I", atlas, 4)
    out = bytearray(MAGIC + struct.pack("<4I", version, 1 | HINT_SIZE << 6 | HINT_SIZE << 19, info, extra))
    for ty in range(side):
        for tx in range(side):
            at = HEADER_SIZE + ((CUT_AT[1] // TILE + ty) * per_row + CUT_AT[0] // TILE + tx) * tile
            out += texture.raw[at:at + tile]
    x, y = MARKER_BLOCK                 # an ETC1A4 tile: four 16-byte blocks in Z order, each its alpha then its colour
    at = HEADER_SIZE + ((y // TILE) * side + x // TILE) * tile + ((y % TILE) // 4 * 2 + (x % TILE) // 4) * 16
    if struct.unpack_from("<Q", out, at)[0]:
        raise ValueError(f"{TEXTURE} has texels in the hint's marker block")
    grey = LANGUAGES.index(lang) + 1
    struct.pack_into("<Q", out, at + 8, sum(grey << shift for shift in MARKER_SHIFTS))
    return bytes(out)


def add_hint(raw_arc: bytes) -> bytes:
    """A core_quest.arc with HINT_TEXTURE right before ui205 and the hint sprite in ui205 drawing from it, animated
    like TEMPLATE. The game's atlas keeps its bytes."""
    arc = parse_arc(raw_arc)
    atlases = [e for e in arc.entries if e.type_hash == TEX_TYPE_HASH and e.name.split("\\")[-1] == TEXTURE]
    if len(atlases) != 1:
        raise ValueError(f"expected one {TEXTURE} in the ARC, found {len(atlases)}")
    arc.entries = [e for e in arc.entries if not (e.type_hash == TEX_TYPE_HASH and e.name == HINT_TEXTURE)]
    done = set()
    for entry in list(arc.entries):
        short = entry.name.split("\\")[-1]
        if entry.type_hash == LYT_TYPE_HASH and short == LAYOUT:
            lang = entry.name.split("\\")[0]
            texture = ArcEntry(HINT_TEXTURE, TEX_TYPE_HASH, hint_texture(atlases[0].data, lang), atlases[0].flags)
            arc.entries.insert(arc.entries.index(entry), texture)
            layout = parse_lyt(entry.data)
            index = layout.add_texture(HINT_TEXTURE)
            region = (HINT_GLYPH_AT[0] / HINT_SIZE, HINT_GLYPH_AT[1] / HINT_SIZE,
                      GLYPH_SIZE / HINT_SIZE, GLYPH_SIZE / HINT_SIZE)
            # TEMPLATE starts hidden and the code shows it by name, so the copies are shown from the start; the
            # hint is transparent until the bar's animation fades it in, like TEMPLATE
            hint = layout.insert_sprite(layout.find(PARENT), layout.find(TEMPLATE), NAME, hint_position(), region,
                                        index)
            hint.visible = True
            hint.colors = [(r, g, b, 0) for r, g, b, _ in hint.colors]
            entry.data = layout.to_bytes()
            done.add("layout")
        elif entry.type_hash == LANL_TYPE_HASH and short == ANIMATION:
            animations = parse_lanl(entry.data)
            if animations.copy_pane(name_hash(TEMPLATE), name_hash(NAME)) == 0:
                raise ValueError(f"{ANIMATION} does not animate {TEMPLATE}")
            entry.data = animations.to_bytes()
            done.add("animation")
    if done != {"layout", "animation"}:
        raise ValueError(f"core_quest.arc has no {LAYOUT} or no {ANIMATION}")
    return write_arc(arc)
