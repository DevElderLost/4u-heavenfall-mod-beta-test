"""Executable patches of the HUD size option, written for the update's code.bin (canonical).

Minimap icons: the map layouts are shrunk by data towards the map's top-right
corner, but the code places the minimap icons (ui250) every frame for the
full-size map, and likewise the visible circle of the stage map shown without
the Map item. These eight call sites of FUN_006c40e0 (world -> map
projection) are redirected to a wrapper (asm/minimap_wrapper.s) that maps the
projected position the same way.

Mount gauge: FUN_00b98454 moves the monster face (ui204_face) along the bar
with x = 45 - 98 * progress, in pixels; both constants of its literal pool are
scaled (the gauge's anchor is x = 0). Its bar fills are scales, so they follow
the data.

Target switch (not part of the HUD size): FUN_00b94854 runs the touch-screen
target camera panel and has a button shortcut test; it is redirected to
asm/target_button.s, which also accepts L held + D-pad up. That request comes from
asm/dpad_filter.s, a wrapper of the player's D-pad / C-stick action mapping, which
also keeps the D-pad from moving the camera while L is held (the C-stick still does).

Target face: a second instance of the target camera panel's layout (ui601) is
loaded on the top screen at fixed GUI manager slots (asm/face_loader.s,
released by asm/face_free.s, hidden with the touch panel by asm/face_show.s),
and asm/target_face.c shows one face of the touch-screen instance on it every
frame, left of the item selector.

The added code lives in the executable's free space, placed by the code space
manager (mh4u_rando/exefs/code_space.py): this module only
names its blocks. Each patch places and hooks only its own blocks, so they can
be applied in any order and next to other changes.

Addresses are virtual (file offset + 0x100000) in the update's executable
(0004000E00126100); the base game's code differs and is not supported yet.
Every patched place is checked first, so another executable is rejected
instead of being corrupted.
"""

import struct

from ..exefs.code_space import (
    BASE_ADDRESS, COND_EQ, CodeSpaceError, Layout, bl_target, encode_bl, encode_branch, load_layout,
)

__all__ = ["BASE_ADDRESS", "CodePatchError", "bl_target", "encode_bl", "encode_branch", "face_params",
           "patch_hud", "patch_interface", "patch_minimap_icons", "patch_mount_gauge", "patch_target_button",
           "patch_target_face"]

CodePatchError = CodeSpaceError

PROJECT = 0x6C40E0  # FUN_006c40e0
ICON_CALLS = (
    0xB83874,  # FUN_00b835e0
    0xB8F330,  # FUN_00b8efc8
    0xB95950,  # FUN_00b954ec
    0xB82F44, 0xB832C0, 0xB88124,  # FUN_00b87e74
    0xB8BC6C,  # FUN_00b8b9f8
    0xB97A90,  # FUN_00b9793c: the visible circle of the stage map without the Map item (sprite_mask_write)
)
# Literal pool of FUN_00b98454 (only read there): face x = START + STEP * progress.
MOUNT_FACE_FLOATS = {0xB987D4: -98.0, 0xB987D8: 45.0}
# Literal pool of FUN_00b9793c (only read there): the circle's y = 120 - 128 v - OFFSET. Through the
# wrapper the map's top edge (y 120, v = 0) stays put, so the offset scales with the map.
MINIMAP_CIRCLE_OFFSET = (0xB97AFC, 4.0)

# L + D-pad up: the D-pad / C-stick actions are called from FUN_00b1cdf0 through asm/dpad_filter.s.
DPAD_HOOK = 0xB1D0B0
DPAD_ACTIONS = 0xB3CC64
# Probe 19's hook, in the action copy of FUN_002c5470, which the D-pad actions never pass through;
# tools/hud_probe.py still undoes it in old patches.
ACTIONS_COPY = 0x2C5484
COPY_INDEX = 0x5C0          # GUI manager slots of the copy's 3 groups (the game uses 20-510 and 1526-1535)
HUD_REF = 0x1083EDC         # ui202 binder entry 1: ui202_tairyoku, the health bar; the face follows it
LAYOUT_LIST, LAYOUT_COUNT, UI601 = 0xEFE17C, 20, 12  # FUN_00c1017c's quest layout list; ui601's entry
LOADER_HOOK = 0xC10430      # FUN_00c1017c, after the stage map: ldr r7, =0xEFE1E8
LOADER_HOOK_ORIGINAL = bytes.fromhex("20719fe5")
FREE_HOOK = 0xC0F11C        # FUN_00c0f110 (releases the GUI layouts): ldr r0, [r0, #0x100]
FREE_HOOK_ORIGINAL = bytes.fromhex("000190e5")
SHOW_HOOK = 0xAE53E0        # FUN_00ae53e0 (show / hide a group), first instruction: push {r4, r5, r6}
SHOW_HOOK_ORIGINAL = bytes.fromhex("70002de9")
FACE_HOOK = 0xB82B50        # FUN_00b826bc: bl FUN_00b94854 (target panel update, every frame)
PANEL_UPDATE = 0xB94854
# Size of the face relative to the touch panel; the gap between the face's right edge and the screen's
# right edge at 100 %, in pixels (the item selector opened with L reaches 137 from the right edge,
# ui205_y_button01; the lock mark is 0.1 face wider on each side, plus 2); and the layout y of the
# selected item's icon (ui205_icon00 in ui205_shita_ita), whose height the face's centre follows.
FACE_SCALE = 0.6
FACE_RIGHT_GAP = 144.0
ITEM_ICON_Y = -87.0
# Shade of a dead (captured, gone...) monster's face on the top screen; the touch screen's is 0.78 (FUN_00b93788).
DEAD_SHADE = 0.65
# FUN_00b94854: the button shortcut test (ldr r0, pad; ldr r0, [r0]; ldr r0, [r0, #0x348]; tst r0, #0x8000) ...
TARGET_TEST = 0xB948AC
TARGET_TEST_ORIGINAL = bytes.fromhex("80009fe5000090e5480390e5020910e3")
TARGET_SET = 0xB948D8   # bl FUN_0013f230; mov r1, #1; strb r1, [r0, #0x27e]
TARGET_SKIP = 0xB948E4


def _offset(address: int) -> int:
    return address - BASE_ADDRESS


def patch_minimap_icons(code: bytes, factor: float, layout: Layout | None = None) -> bytes:
    """`code` with the minimap icons (and the visible circle without the Map item) scaled by `factor`
    towards the map's top-right corner."""
    layout = layout or load_layout()
    out = bytearray(code)
    circle, offset = MINIMAP_CIRCLE_OFFSET
    if len(out) < _offset(circle) + 4 or struct.unpack_from("<f", out, _offset(circle))[0] != offset:
        raise CodePatchError(f"unexpected value at {circle:#x}: not the update's executable")
    for site in ICON_CALLS:
        if bl_target(out, site) != PROJECT:
            raise CodePatchError(f"unexpected instruction at {site:#x}: not the update's executable")
    layout.place(out, "minimap_wrapper")
    struct.pack_into("<f", out, _offset(layout.symbol("minimap_wrapper", "scale")), factor)
    struct.pack_into("<f", out, _offset(layout.symbol("minimap_wrapper", "half_rest")), (1 - factor) / 2)
    for site in ICON_CALLS:
        layout.hook(out, site, "minimap_wrapper", calls=PROJECT)
    struct.pack_into("<f", out, _offset(circle), offset * factor)
    return bytes(out)


def patch_mount_gauge(code: bytes, factor: float) -> bytes:
    """`code` with the mount gauge's monster face moving along a bar scaled by `factor`."""
    out = bytearray(code)
    for address, value in MOUNT_FACE_FLOATS.items():
        if struct.unpack_from("<f", out, _offset(address))[0] != value:
            raise CodePatchError(f"unexpected value at {address:#x}: not the update's executable")
        struct.pack_into("<f", out, _offset(address), value * factor)
    return bytes(out)


def patch_hud(code: bytes, factor: float, layout: Layout | None = None) -> bytes:
    """Every executable patch of the HUD size option."""
    return patch_mount_gauge(patch_minimap_icons(code, factor, layout), factor)


def patch_target_button(code: bytes, layout: Layout | None = None, with_filter: bool = True) -> bytes:
    """`code` where L + D-pad up switches the large-monster target, like a tap on the target camera
    panel, and where the D-pad does not move the camera while L is held (asm/dpad_filter.s).

    `layout` may have a diagnostic routine as its target_button block (tools/hud_probe.py
    --target-asm); it must return r0 != 0 to switch, like the original test. `with_filter=False`
    leaves the D-pad filter out (the request then never comes; diagnostic layouts may not have it).
    """
    layout = layout or load_layout()
    out = bytearray(code)
    test = slice(_offset(TARGET_TEST), _offset(TARGET_TEST) + len(TARGET_TEST_ORIGINAL))
    if bytes(out[test]) != TARGET_TEST_ORIGINAL:
        raise CodePatchError(f"unexpected instructions at {TARGET_TEST:#x}: not the update's executable")
    if with_filter:
        layout.place(out, "dpad_filter")
        layout.hook(out, DPAD_HOOK, "dpad_filter", calls=DPAD_ACTIONS)
    layout.place(out, "target_button")
    routine = layout.address("target_button")
    out[test] = (encode_branch(TARGET_TEST, routine, link=True)
                 + struct.pack("<I", 0xE3500000)  # cmp r0, #0
                 + encode_branch(TARGET_TEST + 8, TARGET_SKIP, cond=COND_EQ)
                 + encode_branch(TARGET_TEST + 12, TARGET_SET))
    return bytes(out)


def face_params(factor: float) -> tuple[float, float, float]:
    """Top-screen position (layout coordinates) and scale of the target face for a HUD `factor`.

    Like the item selector (which shrinks towards the bottom-right corner), the face keeps its
    distances to that corner times `factor`: the one-monster face (ui601_icon00, 40 x 40 pixels at
    scale 1.2, centred at (120, 86) in ui601_target_icon00 at x -40, all scaled by `scale`) ends
    FACE_RIGHT_GAP from the right edge, and its centre is at the height of the selected item's
    icon (ITEM_ICON_Y). A sprite's position is its centre, at screen (200 - x, 120 - y) (measured
    in probe 12).
    """
    scale = FACE_SCALE * factor
    right = 400 - FACE_RIGHT_GAP * factor
    half = 40 * 1.2 / 2
    icon_y = -120 + (ITEM_ICON_Y + 120) * factor
    x = 200 - right + (half - (120 - 40)) * scale
    y = icon_y - 86 * scale
    return x, y, scale


def patch_target_face(code: bytes, factor: float = 1.0, layout: Layout | None = None) -> bytes:
    """`code` showing the target camera panel's monster face on the top screen too.

    asm/face_loader.s loads ui601 a second time, on the top screen, at the GUI manager slots
    COPY_INDEX..., asm/face_free.s releases it with the other layouts, asm/face_show.s hides it
    with the touch-screen panel, and the per-frame target panel update is redirected to
    asm/target_face.c, which mirrors the touch-screen face onto it. `layout` may have the
    diagnostic build as its target_face block (tools/hud_probe.py --face-debug).
    """
    layout = layout or load_layout()
    out = bytearray(code)
    if len(out) < _offset(LAYOUT_LIST) + 4 * (LAYOUT_COUNT + 1):
        raise CodePatchError("not the update's executable: too short")
    paths = struct.unpack_from(f"<{LAYOUT_COUNT + 1}I", out, _offset(LAYOUT_LIST))
    if paths[-1] != 0 or not all(paths[:-1]):
        raise CodePatchError("unexpected quest layout list: not the update's executable")
    for name in ("face_loader", "face_free", "face_show", "target_face"):
        layout.place(out, name)
    layout.place(out, "face_params", struct.pack("<4f", *face_params(factor), DEAD_SHADE))
    layout.hook(out, LOADER_HOOK, "face_loader", original=LOADER_HOOK_ORIGINAL)
    layout.hook(out, FREE_HOOK, "face_free", original=FREE_HOOK_ORIGINAL)
    layout.hook(out, SHOW_HOOK, "face_show", original=SHOW_HOOK_ORIGINAL, link=False)
    layout.hook(out, FACE_HOOK, "target_face", calls=PANEL_UPDATE)
    return bytes(out)


def patch_interface(code: bytes, factor: float, target_switch: bool = False, target_face: bool = False) -> bytes:
    """Every interface patch the randomizer's settings ask for: the HUD size (below 1), L + D-pad up, the target
    face."""
    if factor < 1:
        code = patch_hud(code, factor)
    if target_switch:
        code = patch_target_button(code)
    if target_face:
        code = patch_target_face(code, factor)
    return code
