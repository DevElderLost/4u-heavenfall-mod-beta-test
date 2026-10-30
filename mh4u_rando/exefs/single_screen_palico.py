"""Single-screen mode, the Palico menus of the Tablón de camaradas (emulator
only), the screen of "Main Palico Info" (ui471).

The board's submenus (ui470, on the top screen by the game) show ui471, the main Palico's paper, on the touch screen
while one of them lists the Palicoes ("Desplegar / entrenar", "Set 1st Stringers"). The rooms' lists load ui471 with the
byte 0 (the top) already; the code that binds and shows its groups puts each on the GUI's touch screen byte
(`ldrb rN, [rM, #0x246]`), which becomes `#0x245` (the top screen), as the facilities' loops do
(exefs/single_screen_facilities.py). The layout side places it at the top of the screen between the board's list and
the Palico's status (curated "ui471"); the frames make room for it (hud/single_screen_frames.py).

`SCREEN_PATCHES` is merged into exefs/single_screen.py's: applied when "ui471" is in the curated `top_screen`.
"""

from .single_screen_facilities import forced

SCREEN_PATCHES: dict[str, tuple[tuple[int, bytes, bytes], ...]] = {
    # FUN_006166e0, which binds ui471's groups (r1 / r1), and FUN_006226c0, which shows its paper (ui471_bace) and the
    # main Palico's page (ui471_1P or ui471_23P) for the submenus that list Palicoes, setting each one's screen
    # (r0 / r0, one load per group)
    "ui471": ((0x616704, *forced(1 << 12 | 1 << 16)), (0x6226FC, *forced(0)), (0x622774, *forced(0))),
}
