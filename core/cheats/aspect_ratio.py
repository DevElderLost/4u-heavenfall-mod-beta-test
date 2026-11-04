"""The shape of the emulator's picture (option cheat_aspect_ratio, experimental; blocks
`aspect_stub`, `aspect_code`, `aspect_data`, `aspect_anchors`, variable `aspect_state`). The game's frame stays 400 x
240; the emulator stretches it to the player's shape. These functions change, in the update's executable (canonical), so
nothing looks stretched:

- FUN_00aeee7c, sCamera's update, computes each view's aspect and stores it at camera + 0x38: the store at VIEW_SITE
  goes through the stub, which multiplies the aspect by the ratio's factor, except the bottom screen's view;
- FUN_00af3db0, which builds the GUI's 2D projection: its two calls of FUN_00b70fc0 (GUI_CALLS) go through the stub,
  which gives the whole top screen more units on the side the frame has room on, so the interface fits undistorted,
  centred;
- FUN_00c042ec, which opens a sub-view (the forge's preview): the store of its rectangle's pointer (RECT_SITE) goes
  through the stub, which passes a copy moved with the interface and its frame's side, so the picture stays in it;
- FUN_00b972d8, which places a HUD panel: its store of the place on the top screen (PANEL_SITE) goes through the stub,
  which moves the minimap's panel (every map layout and icon) to its corner of the picture. The touch screen's place is
  another store, which stays. The rest of the HUD moves in its files (interface/hud/scale.py, `edge`);
- FUN_00ae65f8, which gives the GPU a group's place as it draws it: its load of the group's second translate
  (GROUP_SITE) goes through the stub, which adds the way to the group's side of the wider interface, from the table of
  interface/hud/anchors.py. So menus keep to the picture's sides whatever the game writes to their panes.

Each check of a site is of the update's word; carried to the base games by the version maps.
"""

import struct

from core.cheats.aspect_table import load_ratios
from core.game.executable.blocks import ASPECT_ANCHORS_SIZE, ASPECT_DATA_SIZE
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout
from core.interface.hud.anchors import AnchorRules, anchor_table, load_anchor_rules

STUB, CODE, DATA, ANCHORS = "aspect_stub", "aspect_code", "aspect_data", "aspect_anchors"
VARIABLES = ("aspect_state",)

VIEW_SITE, VIEW_WORD = 0xAEEFD0, 0xED860A0E     # FUN_00aeee7c: vstr s0, [r6, #0x38]
GUI_CALLS = (0xAF3EB4, 0xAF41F4)                # FUN_00af3db0: bl FUN_00b70fc0
GUI_PROJECTION = 0xB70FC0
RECT_SITE, RECT_WORD = 0xC0430C, 0xE58D2004     # FUN_00c042ec: str r2, [sp, #4]
PANEL_SITE, PANEL_WORD = 0xB97478, 0xE1C602F8   # FUN_00b972d8: strd r0, r1, [r6, #0x28]
GROUP_SITE, GROUP_WORD = 0xAE6678, 0xED941A0D   # FUN_00ae65f8: vldr s2, [r4, #0x34]


def aspect_data(name: str, rules: AnchorRules | None = None) -> bytes:
    """The block (struct aspect_data in aspect_ratio.c): the three factors of the curated ratio `name` (Ratio.factors,
    floats), then the anchors' `rules` (the curated ones by default)."""
    ratios = {ratio.name: ratio for ratio in load_ratios()}
    if name not in ratios:
        raise ValueError(f"no aspect ratio {name!r}: the curated ones are {', '.join(ratios)}")
    rules = rules or load_anchor_rules()
    data = struct.pack("<6fI", *ratios[name].factors(), rules.edge_margin, rules.half_margin, rules.dead_zone,
                       rules.sub_views)
    if len(data) != ASPECT_DATA_SIZE:
        raise ValueError(f"aspect_data holds {ASPECT_DATA_SIZE} bytes, the factors make {len(data)}")
    return data


def supports_aspect_ratio(code: bytes) -> bool:
    """`code` has what the option changes (the update's executable, canonical, not patched yet)."""
    word = lambda at: struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]  # noqa: E731
    return word(VIEW_SITE) == VIEW_WORD and word(RECT_SITE) == RECT_WORD and word(PANEL_SITE) == PANEL_WORD and \
        word(GROUP_SITE) == GROUP_WORD and all(bl_target(code, at) == GUI_PROJECTION for at in GUI_CALLS)


def patch_aspect_ratio(code: bytes, name: str, layout: Layout | None = None, anchors: bytes | None = None,
                       rules: AnchorRules | None = None) -> bytes:
    """`code` with the hooks (the module's docstring lists them) for the ratio `name`. `anchors`: the block
    `aspect_anchors` (interface/hud/anchors.py; none: no group moves), `rules`: the anchors' (the curated ones). Refuses
    an executable where any site is not the game's word."""
    if not supports_aspect_ratio(code):
        raise CodeSpaceError("the aspect ratio's sites are not the update's words: already patched or another game")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, STUB)
    layout.place(out, CODE)
    layout.place(out, DATA, aspect_data(name, rules))
    table = anchor_table({}) if anchors is None else anchors
    layout.place(out, ANCHORS, table + bytes(ASPECT_ANCHORS_SIZE - len(table)))
    layout.hook(out, VIEW_SITE, layout.symbol(STUB, "aspect_view"))
    for at in GUI_CALLS:
        layout.hook(out, at, layout.symbol(STUB, "aspect_gui"))
    layout.hook(out, RECT_SITE, layout.symbol(STUB, "aspect_sub_view"))
    layout.hook(out, PANEL_SITE, layout.symbol(STUB, "aspect_panel"))
    layout.hook(out, GROUP_SITE, layout.symbol(STUB, "aspect_group"))
    return bytes(out)
