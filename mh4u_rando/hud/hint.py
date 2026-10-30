"""The hint of the target switch (option touchless_target, L + D-pad up): a D-pad glyph with only its up arm
lit, in the item selector's L bar, to the left of the target face.

The game has no "D-pad up" glyph, so one is drawn into a free corner of the quest texture qst00_ID and a
sprite showing it is added to the layout ui205, animated like the bar's Y button glyph (shown only while
the bar opened with L is open). Each language has three identical copies of qst00_ID under the same path
(GLYPH_ARCS); the game uses whichever is loaded first, so the glyph goes into all of them.
"""

from ..arc import parse_arc, write_arc
from .code_patch import FACE_RIGHT_GAP, FACE_SCALE, ITEM_ICON_Y
from .lanl import LANL_TYPE_HASH, parse_lanl
from .lyt import LYT_TYPE_HASH, name_hash, parse_lyt
from .tex import TEX_TYPE_HASH, parse_tex

LAYOUT = "ui205"
ANIMATION = "ui205_select"      # opens / closes the L bar
PARENT = "ui205_shita_ita"      # the L bar of the item selector
TEMPLATE = "ui205_y_button01"   # a 16 x 16 glyph sprite shown only in the open bar: the copy keeps its
NAME = "ui205_dpad_up"          # colours and flags, and gets its animation
TEXTURE = "qst00_ID"            # ui205's third texture; nothing uses its lower right quarter
TEXTURE_SIZE = 512
QUEST_ARC = "core_quest.arc"    # the layout and one copy of the texture
GLYPH_ARCS = (QUEST_ARC, "core_result.arc", "v05a00_map.arc")  # every copy of <lang>\lyt\quest\texture\qst00_ID
GLYPH_AT = (448, 448)           # in pixels of the texture, multiples of 4
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


def add_glyph(raw_arc: bytes) -> bytes:
    """The ARC with the glyph drawn into its qst00_ID."""
    arc = parse_arc(raw_arc)
    textures = [e for e in arc.entries if e.type_hash == TEX_TYPE_HASH and e.name.split("\\")[-1] == TEXTURE]
    if len(textures) != 1:
        raise ValueError(f"expected one {TEXTURE} in the ARC, found {len(textures)}")
    texture = parse_tex(textures[0].data)
    if (texture.width, texture.height) != (TEXTURE_SIZE, TEXTURE_SIZE):
        raise ValueError(f"unexpected size of {TEXTURE}: {texture.width}x{texture.height}")
    texture.set_glyph(*GLYPH_AT, GLYPH_ROWS)
    textures[0].data = texture.to_bytes()
    return write_arc(arc)


def add_hint(raw_arc: bytes) -> bytes:
    """A core_quest.arc with the glyph in its texture qst00_ID and the hint sprite in ui205, animated like
    TEMPLATE."""
    arc = parse_arc(add_glyph(raw_arc))
    done = set()
    for entry in arc.entries:
        short = entry.name.split("\\")[-1]
        if entry.type_hash == LYT_TYPE_HASH and short == LAYOUT:
            layout = parse_lyt(entry.data)
            index = next(i for i, name in enumerate(layout.textures) if name.endswith(TEXTURE))
            region = (GLYPH_AT[0] / TEXTURE_SIZE, GLYPH_AT[1] / TEXTURE_SIZE,
                      GLYPH_SIZE / TEXTURE_SIZE, GLYPH_SIZE / TEXTURE_SIZE)
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
