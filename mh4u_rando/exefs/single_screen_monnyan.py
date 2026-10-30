"""Single-screen mode, the Meownster Hunters' trip (emulator
only): the Felynes' minigame on the top screen.

The trip's scene (FUN_00375cb8) is a GUI manager of its own, not the main GUI's, and loads its layouts itself: the
boards with the three destinations (ui705) through FUN_0036c478, on the GUI's top screen byte (`#0x245`), and the
minigame through three loaders that set every group they create to the touch screen byte (`ldrb r0, [r0, #0x246]`):
FUN_0036d140 (ui700 the gauge, balloons and effects, ui701 the Felynes, ui702), FUN_0036d3f4 (each destination's
backdrop, ui710-ui713) and FUN_0036c238 (each destination's monsters, ui720 and ui730-ui737). Each read becomes
`#0x245`: the minigame is drawn on the top screen, over or under the boards as the scene's priorities say. No binder
or other code moves them afterwards (a scan of the scene's code, 0x340000-0x3B0000, finds only these three reads of
`#0x246`).

`SCREEN_PATCHES` is merged into exefs/single_screen.py's: applied when "ui700" is in the curated `top_screen`.
"""

from .single_screen_facilities import forced

SCREEN_PATCHES: dict[str, tuple[tuple[int, bytes, bytes], ...]] = {
    # FUN_0036c238, FUN_0036d140 and FUN_0036d3f4: one `ldrb r0, [r0, #0x246]` each, in their loops over the groups
    "ui700": ((0x36C320, *forced(0)), (0x36D29C, *forced(0)), (0x36D4DC, *forced(0))),
}
