"""Single-screen mode, the other touch menus: the
screen bytes of "Contenido adicional" (the DLC scene's ui521 and ui541) and "Gestos y frases" (ui038). Only bytes of the
game's loader tables and binder table change; no code is added (`SCREEN_PATCHES` of
interface/single_screen/executable/single_screen.py takes them).

Each byte is checked against the update's before it is written (`patch_screens`) and mapped to the player's base game
through its version map like the other single-screen bytes.
"""

# The DLC scene's loader, FUN_00c0f608 (loader 4 of FUN_00c0e6d0): the layouts' paths at 0xEFE6CC (ui520, ui521, ui540,
# ui541, then 0) and a screen byte for each at 0xEFE6E0 (0 top, 1 bottom: FUN_00c0f474's second argument). Nothing binds
# the groups afterwards (no kind table, no forcing site), so the byte alone puts the layout on a screen.
DLC_SCREEN_BYTES = 0xEFE6E0
DLC_UI521, DLC_UI541 = 1, 3

# The common list's loader, FUN_00c10740: the paths at 0xEFDC60, the bytes at 0xEFDCE8; ui038 is index 30. Its binder
# (FUN_00595E5C, run by the opener FUN_00603F68 at every opening) calls FUN_00584c08(owner, 0xDFC02C, 12): twelve
# 12-byte entries, the group's name hash first and the kind byte at +4 (1: bottom screen, any other: top), which would
# put the groups back on the bottom at every opening.
COMMON_SCREEN_BYTES = 0xEFDCE8
UI038_INDEX = 30
UI038_TABLE = 0xDFC02C
UI038_GROUPS = 12

SCREEN_PATCHES: dict[str, tuple[tuple[int, bytes, bytes], ...]] = {
    "ui521": ((DLC_SCREEN_BYTES + DLC_UI521, b"\x01", b"\x00"),),
    "ui541": ((DLC_SCREEN_BYTES + DLC_UI541, b"\x01", b"\x00"),),
    "ui038": ((COMMON_SCREEN_BYTES + UI038_INDEX, b"\x01", b"\x00"),
              *((UI038_TABLE + 12 * n + 4, b"\x01", b"\x00") for n in range(UI038_GROUPS))),
}
