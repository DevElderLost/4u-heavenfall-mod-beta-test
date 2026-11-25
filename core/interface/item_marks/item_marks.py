"""Item marks: a star on the icon of an upgraded consumable, everywhere, inside the
icon's square, and the rare materials' highlight on the quest rewards screen. The options are the START menu's (Mod
Settings > Interface > Item Icons: Show Upgrade Stars, Star Colour, Rare Rewards; the page's only: on, Yellow, on), so a
mod with that page carries the code and a character's choice acts at once. The art is a texture of its own (art.py),
which the C binds into the last texture slot of each group it adds marks to (item_marks.c marks_slot).

These game functions change, in the update's executable (canonical; the version maps carry them to the base games):

- FUN_00c0de18 and FUN_00c0e268 (an item's 24- and 16-px icon into a sprite): their `stmdb` (second instruction) and
  their one `ldmia` (epilogue) branch to stubs that keep the item and then write its upgrade level into the sprite's u
  (item_marks_icon);
- FUN_00602b58, FUN_0069f61c, FUN_006a7700, FUN_00aad98c, FUN_00ab8188, FUN_00aba7c8, FUN_00ac0d90, FUN_00ad1604: their
  calls of FUN_00c118f4 (an icon by its shape, the item read inline) go through a stub that marks the sprite after it;
- FUN_00ae56a4 (a group's tree walk) and FUN_00ae5514 (its redraw queue): their call of FUN_00ae7098 (a sprite's
  vertices) notes the sprites drawn with a mark first (item_marks_seen);
- FUN_00af52a0 (sMhMain::frame), through the quest's shared frame hook (interface/quest_layouts/, a frame-only entry):
  item_marks_frame makes and places the stars and the rewards' highlight.
"""

from __future__ import annotations

import math
import struct

from core.game.executable.blocks import ITEM_MARKS_DATA_SIZE
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout
from core.game.files.gui.lyt import name_hash
from core.interface.item_marks import art
from core.interface.item_marks.data import (STAR_COLOURS, Marks, back_shift, load_marks, rare_ids, star_colours,
                                             upgrade_levels)
from core.interface.quest_layouts.quest_layouts import add_quest_layout, frame_only, supports_quest_layouts

STUB, CODE, DATA, STATE = "item_marks_stub", "item_marks_code", "item_marks_data", "item_marks_state"
FRAME = "item_marks_frame"
OPTIONS = ("upgrade_stars", "rare_rewards")     # the two switches (Show Upgrade Stars, Rare Rewards)
COLOUR_OPTION = "upgrade_stars_colour"          # Star Colour: Yellow / White (item_marks.c star_rgb, by its value)

# The item setters: (address, the word the game has there, the stub's label); a `b`, not a `bl`
STMDB, LDMIA = bytes.fromhex("70402de9"), bytes.fromhex("7080bde8")    # stmdb / ldmia sp!, {r4, r5, r6, lr / pc}
SETTER_HOOKS = (
    (0xC0DE1C, STMDB, "im_big_entry"), (0xC0DEB4, LDMIA, "im_big_exit"),             # FUN_00c0de18
    (0xC0E26C, STMDB, "im_small_entry"), (0xC0E310, LDMIA, "im_small_exit"),         # FUN_00c0e268
)
SHAPE_WRITER = 0xC118F4             # FUN_00c118f4(any, data + 0x10, shape, &tint)
SITES = (0x602C44, 0x603010, 0x603298, 0x69F854, 0x6A79A4, 0x6A7F9C, 0xAADEF4, 0xAB7E88, 0xAB85F0, 0xABACB8, 0xABB0DC,
         0xAC10FC, 0xAD19E8)
VERTICES = 0xAE7098                 # FUN_00ae7098(data + 0x10, context, state)
SEEN_HOOKS = ((0xAE5808, "im_seen_walk"), (0xAE5584, "im_seen_queue"))  # FUN_00ae56a4, FUN_00ae5514

# Our panes' names, and the rewards grid's (ui209, every language's core_result.arc)
STAR_NAMES = ("hf_mark_star", "hf_mark_star_back")
TWINKLE_NAME, HALO_NAME = "hf_mark_twinkle", "hf_mark_halo"
REWARDS_GROUP, REWARDS_GRID = "ui209_l_housyu", "ui209_icon_s_housyu"
PAGE_CELLS = (0x4A, 0x10A)          # the result scene's cells of pages 1 and 2
PHASES = 64                         # item_marks.c PHASES
MAX_UPGRADES, MAX_RARE = 64, 128    # item_marks.c
HIDDEN = 0xFF                       # a twinkle's cell when it is not shown
FRAMES_PER_SECOND = 30              # the frame's time unit (game_main + 0x5C: 1.0 a 30th of a second)
ITEM_LIMIT = 0x1000                 # item_marks.c ITEM_LIMIT
TEXTURE_PATH = 40                   # item_marks.c TEXTURE_PATH: the marks' texture's path, NUL ended


class ItemMarksError(ValueError):
    pass


def _f(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def _rgb(colour) -> int:
    return colour[0] | colour[1] << 8 | colour[2] << 16


def phase_tables(look: dict) -> tuple[list[int], list[int]]:
    """The halo's alpha (0-255) and a twinkle's cell (art.STAR_SIZES index, HIDDEN) at each of PHASES steps of a
    cycle: the halo pulses on a sine between halo_alpha's low and high; a twinkle grows and shrinks through
    twinkle_sizes, each size for the same time, over twinkle_life of the cycle."""
    low, high = look["halo_alpha"]
    sizes, life = look["twinkle_sizes"], look["twinkle_life"]
    alpha, cells = [], []
    for i in range(PHASES):
        phase = (i + 0.5) / PHASES
        alpha.append(round(255 * (low + (high - low) * (0.5 + 0.5 * math.sin(2 * math.pi * phase)))))
        if phase < life:
            cells.append(art.STAR_SIZES.index(sizes[min(int(phase / (life / len(sizes))), len(sizes) - 1)]))
        else:
            cells.append(HIDDEN)
    return alpha, cells


def data_block(marks: Marks | None = None, ported: bool = True) -> bytes:
    """The block item_marks_data (item_marks.c struct marks_data). `ported`: the ported monsters' items resolve too."""
    from core.interface.mod_settings.mod_options import OPTION_IDS, load_options
    marks = marks or load_marks()
    colour = next(option for option in load_options() if option["key"] == COLOUR_OPTION)
    rgbs = star_colours(marks, [value["setting"] for value in colour["values"]])
    if len(rgbs) != len(STAR_COLOURS):
        raise ItemMarksError(f"mod_settings.json: {COLOUR_OPTION} has {len(STAR_COLOURS)} values (item_marks.c "
                             f"STAR_COLOURS)")
    look = marks.look
    levels = upgrade_levels(marks, ported)
    rare = rare_ids(marks, ported)
    if len(levels) > MAX_UPGRADES or len(rare) > MAX_RARE:
        raise ItemMarksError(f"item_marks.json: at most {MAX_UPGRADES} upgrade and {MAX_RARE} rare ids")
    if any(i >= ITEM_LIMIT for i in [*levels, *rare]):
        raise ItemMarksError(f"item_marks.json: an item id past {ITEM_LIMIT:#x}")
    for size in [*look["star_size"].values(), *look["twinkle_sizes"]]:
        if size not in art.STAR_SIZES:
            raise ItemMarksError(f"item_marks.json: no star cell of {size} texels (art.STAR_SIZES)")
    alpha, cells = phase_tables(look)
    sides = [look["star_size"]["16"], look["star_size"]["24"]]
    data = struct.pack("<3I", *(OPTION_IDS[key] for key in (*OPTIONS, COLOUR_OPTION)))
    data += struct.pack("<4I", *(name_hash(n) for n in (*STAR_NAMES, TWINKLE_NAME, HALO_NAME)))
    for size in art.STAR_SIZES:
        data += struct.pack("<4I", *(_f(v) for v in art.cell_uv(size)))
    data += struct.pack("<4I", *(_f(v) for v in art.cell_uv("halo")))
    data += struct.pack("<2I", _rgb(look["gold"]), _rgb(look["glow"]))
    data += struct.pack(f"<{len(rgbs)}I", *(_rgb(rgb) for rgb in rgbs))
    data += struct.pack("<2f", *(float(s) for s in sides))
    data += struct.pack("<2I", *(art.STAR_SIZES.index(s) for s in sides))
    data += struct.pack("<2f", *(float(back_shift(look, cell)) for cell in ("16", "24")))
    data += struct.pack("<3f", float(look["star_inset"]), float(look["back_lift"]), float(look["halo_size"]))
    places = look["twinkle_places"]
    data += struct.pack("<3f", *(float(p[0]) for p in places)) + struct.pack("<3f", *(float(p[1]) for p in places))
    data += struct.pack("<f", float(look["cycle_seconds"]) * FRAMES_PER_SECOND)
    data += struct.pack("<2I", look["reserve"]["panes"], look["reserve"]["sprites"])
    data += struct.pack("<2I", name_hash(REWARDS_GROUP), name_hash(REWARDS_GRID))
    data += struct.pack("<2H", *PAGE_CELLS) + struct.pack("<2H", len(levels), len(rare))
    data += bytes(alpha) + bytes(cells)
    ids = list(levels)
    data += struct.pack(f"<{MAX_UPGRADES}H", *ids, *[0] * (MAX_UPGRADES - len(ids)))
    data += bytes([levels[i] for i in ids] + [0] * (MAX_UPGRADES - len(ids)))
    data += struct.pack(f"<{MAX_RARE}H", *rare, *[0] * (MAX_RARE - len(rare)))
    path = art.TEXTURE.encode("ascii")
    if len(path) >= TEXTURE_PATH:
        raise ItemMarksError(f"art.TEXTURE is longer than item_marks.c TEXTURE_PATH ({TEXTURE_PATH})")
    data += path.ljust(TEXTURE_PATH, b"\0")
    if len(data) != ITEM_MARKS_DATA_SIZE:
        raise ItemMarksError(f"item_marks_data holds {ITEM_MARKS_DATA_SIZE} bytes, made {len(data)}")
    return data


def _word(code: bytes | bytearray, at: int) -> bytes:
    return bytes(code[at - BASE_ADDRESS:at - BASE_ADDRESS + 4])


def supports_item_marks(code: bytes) -> bool:
    """`code` (the update's executable, canonical, not patched yet) has every instruction the hooks replace."""
    return (supports_quest_layouts(code) and all(_word(code, at) == word for at, word, _ in SETTER_HOOKS)
            and all(bl_target(code, at) == SHAPE_WRITER for at in SITES)
            and all(bl_target(code, at) == VERTICES for at, _ in SEEN_HOOKS))


def patch_item_marks(code: bytes, layout: Layout | None = None, ported: bool = True) -> bytes:
    """`code` (the update's executable) with the item marks' stubs, code, data and state, their hooks and the frame-only
    entry in the quest's shared hooks. Refuses an executable where a site is not the game's instruction (one patched
    already, or not the update's)."""
    layout = layout or load_layout()
    out = bytearray(code)
    try:
        layout.place(out, STUB)
        layout.place(out, CODE)
        layout.place(out, DATA, data_block(ported=ported))
        for at, word, label in SETTER_HOOKS:
            layout.hook(out, at, layout.symbol(STUB, label), original=word, link=False)
        for at in SITES:
            layout.hook(out, at, layout.symbol(STUB, f"im_site_{at:x}"), calls=SHAPE_WRITER)
        for at, label in SEEN_HOOKS:
            layout.hook(out, at, layout.symbol(STUB, label), calls=VERTICES)
        layout.reserve(out, STATE)
    except CodeSpaceError as error:
        raise CodeSpaceError(f"item marks: {error}") from error
    add_quest_layout(out, frame_only(layout.symbol(CODE, FRAME)), layout)
    return bytes(out)


__all__ = ["CODE", "COLOUR_OPTION", "DATA", "FRAME", "HALO_NAME", "HIDDEN", "ItemMarksError", "LDMIA", "OPTIONS",
           "PAGE_CELLS", "PHASES", "REWARDS_GRID", "REWARDS_GROUP", "SEEN_HOOKS", "SETTER_HOOKS", "SHAPE_WRITER",
           "SITES", "STAR_NAMES", "STATE", "STMDB", "STUB", "TWINKLE_NAME", "VERTICES", "data_block",
           "patch_item_marks", "phase_tables", "supports_item_marks"]
