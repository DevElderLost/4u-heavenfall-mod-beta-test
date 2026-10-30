"""Single-screen mode, the frames of the Palico menus (emulator only),
executable side.

The layout side puts everything under each framed root group in one null, `<group>_frame` (hud/single_screen_frames.py,
curated single_screen.json, "frames"). Block `single_screen_frames` (exefs/asm/single_screen_frames.c) is chained in
front of the town minimap's block in the pad update's call: every frame it finds the curated scene from the groups
shown and gives each framed group's null the scale and position of its set's frame there (the identity with no scene).
Its data is the separate block `single_screen_frame_table`, written here (`frame_table`). The block also carries the
minimap's place name unit (exefs/asm/single_screen_label.c), which scales and moves the frame null of the name's group
the same way while the group is on the top screen (hud/single_screen_minimap.py, the curated minimap's "label"): its
data is the block `single_screen_label_table` (`label_table`).

Applied by `patch_single_screen` (exefs/single_screen.py) on the canonical executable like every patcher: the block's
code and table are placed by the code space.
"""

import struct

from ..hud.lyt import name_hash
from ..hud.single_screen_frames import FRAME_SUFFIX, MAX_NAMES, MAX_SCENES, MAX_SETS, Frames, frame_settings
from ..hud.single_screen_minimap import Minimap, MinimapLabel, arranged_label, minimap_settings
from .blocks import SINGLE_SCREEN_FRAME_TABLE_SIZE, SINGLE_SCREEN_LABEL_TABLE_SIZE
from .code_space import CodeSpaceError, Layout, load_layout

BLOCK = "single_screen_frames"
ENTRY = "frames_pad"
TABLE = "single_screen_frame_table"
LABEL_TABLE = "single_screen_label_table"
LABEL_TABLE_SIZE = SINGLE_SCREEN_LABEL_TABLE_SIZE
MINIMAP_BLOCK, MINIMAP_ENTRY = "single_screen_minimap", "minimap_pad"
# FUN_00ae5e68 (a root group's first pane, the item lists' first row): its first instruction becomes `b` to the block's
# `frames_first_pane`, which skips the null single-screen mode put under a group
FIRST_PANE_SITE = 0xAE5E68
FIRST_PANE_ORIGINAL = bytes.fromhex("082091e5")     # ldr r2, [r1, #8]
FIRST_PANE_ENTRY = "frames_first_pane"
SCREEN_HALF = (200.0, 120.0)        # the top screen's centre, the layouts' origin (screen = (200 - x, 120 - y))
SCENE_SIZE, PARAM_SIZE, NAME_SIZE = 12, 16, 16
PARAMS_AT = 4 + SCENE_SIZE * MAX_SCENES
NAMES_AT = PARAMS_AT + PARAM_SIZE * MAX_SETS * MAX_SCENES
TABLE_SIZE = NAMES_AT + NAME_SIZE * (MAX_NAMES + 1)
IDENTITY = (0.0, 0.0, 1.0, 0.0)
PROMPT_OFF = 0x100               # in a name's set field: the set is left alone while a yes / no prompt is open
assert TABLE_SIZE == SINGLE_SCREEN_FRAME_TABLE_SIZE, "exefs/blocks.py and the block's table disagree"


def frame_table(frames: Frames) -> bytes:
    """The block's table for `frames`: the scene count; per scene its all / any / none masks (bit n: the n-th name
    `Frames.rules` gives); per set and scene the null's (cx, cy, scale, scale - 1), the identity where the scene does
    not frame the set (cx = 200 (1 - scale) - at x, cy = 120 (1 - scale) - at y: a point at (x, y) on the screen goes
    to (scale x + at x, scale y + at y) whatever the group's translate, which the block adds times scale - 1); per name
    its hash, its rule bit, its set + 1 (0: a rule only; bit 8 more for a set of `prompt_off`) and its null's hash; a 0
    hash after the last name."""
    rules = frames.rules()
    bit = {name: 1 << n for n, name in enumerate(rules)}
    if len(frames.scenes) > MAX_SCENES or len(frames.sets) > MAX_SETS or len(rules) > 32:
        raise CodeSpaceError("frames: more scenes, sets or scene groups than the block holds")
    out = bytearray(TABLE_SIZE)
    struct.pack_into("<I", out, 0, len(frames.scenes))
    for j, scene in enumerate(frames.scenes):
        masks = [sum(bit[name] for name in names) for names in (scene.all, scene.any, scene.none)]
        struct.pack_into("<3I", out, 4 + SCENE_SIZE * j, *masks)
    for i, (set_name, _groups) in enumerate(frames.sets):
        for j in range(MAX_SCENES):
            frame = frames.scenes[j].frame(set_name) if j < len(frames.scenes) else None
            values = IDENTITY
            if frame is not None:
                s, (ax, ay) = frame.scale, frame.at
                # + 0.0: no negative zero (the block compares the bits it writes with the null's)
                values = (SCREEN_HALF[0] * (1 - s) - ax + 0.0, SCREEN_HALF[1] * (1 - s) - ay + 0.0, s, s - 1 + 0.0)
            struct.pack_into("<4f", out, PARAMS_AT + PARAM_SIZE * (i * MAX_SCENES + j), *values)
    names: dict[str, list[int]] = {name: [bit[name], 0, 0] for name in rules}
    for i, (set_name, groups) in enumerate(frames.sets):
        for group in groups:
            flag = PROMPT_OFF if set_name in frames.prompt_off else 0
            names.setdefault(group, [0, 0, 0])[1:] = [i + 1 | flag, name_hash(group + FRAME_SUFFIX)]
    if len(names) > MAX_NAMES:
        raise CodeSpaceError(f"frames: {len(names)} group names, the block's table holds {MAX_NAMES}")
    hashes = [name_hash(name) for name in names]
    if len(set(hashes)) != len(hashes) or 0 in hashes:
        raise CodeSpaceError("frames: two group names with one hash")
    for n, (name, (rule, set_number, wrapper)) in enumerate(names.items()):
        struct.pack_into("<4I", out, NAMES_AT + NAME_SIZE * n, name_hash(name), rule, set_number, wrapper)
    return bytes(out)


def label_table(label: MinimapLabel | None) -> bytes:
    """The label unit's table: the place name's group hash, its frame null's hash, the null's (cx, cy, scale,
    scale - 1) on the top screen, worked out as the frames' (above: a point at (x, y) goes to (scale x + at x, scale y +
    at y)), and the hash of the group's null that is shrunk to nothing there (`hide`: the shop-name bar); all zero with
    no label (the unit does nothing)."""
    if label is None:
        return bytes(LABEL_TABLE_SIZE)
    s, (ax, ay) = label.scale, label.at
    # + 0.0: no negative zero (the unit compares the bits it writes with the null's)
    return struct.pack("<2I4fI", name_hash(label.group), name_hash(label.frame), SCREEN_HALF[0] * (1 - s) - ax + 0.0,
                       SCREEN_HALF[1] * (1 - s) - ay + 0.0, s, s - 1 + 0.0, name_hash(label.hide))


def patch_frames(code: bytes, hook: int, layout: Layout | None = None, frames: Frames | None = None,
                 minimap: Minimap | None = None) -> bytes:
    """`code` (extended, the minimap's block already hooked at `hook`, the pad update's call) with the frames' block,
    its table (the curated frames by default) and the table of the minimap's place name (`minimap`'s label: the curated
    minimap by default; its place from the arranged map's corner, hud/single_screen_minimap.arranged_label) placed,
    called first by the pad update (it calls the minimap's block itself), and FUN_00ae5e68 branching to the block's
    first pane (`FIRST_PANE_SITE`). Each hook checks the instruction it replaces."""
    layout = layout or load_layout()
    frames = frame_settings() if frames is None else frames
    minimap = minimap or minimap_settings()
    out = bytearray(code)
    try:
        layout.place(out, TABLE, frame_table(frames))
        layout.place(out, LABEL_TABLE, label_table(arranged_label(minimap)))
        layout.place(out, BLOCK)
        layout.hook(out, hook, layout.symbol(BLOCK, ENTRY), calls=layout.symbol(MINIMAP_BLOCK, MINIMAP_ENTRY))
        layout.hook(out, FIRST_PANE_SITE, layout.symbol(BLOCK, FIRST_PANE_ENTRY), original=FIRST_PANE_ORIGINAL,
                    link=False)
    except CodeSpaceError as error:
        raise CodeSpaceError(f"frames: {error}") from None
    return bytes(out)
