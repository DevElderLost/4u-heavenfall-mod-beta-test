"""Single-screen mode, the facilities' menus (emulator
only).

Four menus made for the touch screen come up on the top screen, each beside what the scene already shows there:

* ui405, the Wyporio's menu of the farm (with the status ui404 on top);
* ui417, "Mi set";
* ui474, the talisman choice of the Caldero de fusión (beside ui473, the box's list);
* ui481, the Tablón de camaradas (beside ui480, which the game already puts on the top screen).

Each screen is decided in two places, both patched here (`SCREEN_PATCHES`, merged into
interface/single_screen/executable/single_screen.py's): the layout's loader byte in the list its scene reads (1 bottom,
0 top; FUN_00c0ff8c for the lobby's, the stage table 0xFB8088's lists for the Caldero's and the rooms'), and the loop
that binds the layout's groups, which sets every group to the screen byte `*(gui + 0x246)` (the bottom): `ldrb rN, [rM,
#0x246]` becomes `#0x245` (the top). The binder tables of these four already say top (kind 0); only the loaders and the
#loops do not.

One call is removed: FUN_009e9b44 (the Caldero's controller), in its box-list state (page 3, first sub-state), calls
FUN_00a93a18, which shows ui474's title00 and omamori00 (the "Meld talismans" panel, bottom left of the touch screen);
that state is the box's list (ui473), which owns the top screen, and the panel has nothing to do there. The call becomes
a nop (`NOP_WORD`): the panel stays hidden, as FUN_00a52234 leaves it every frame. The other two calls (page 1; the
talisman choice, page 3's second sub-state) still show it.

Nothing else is changed: the menus' own code (cursors, pages) runs as the game has it.
"""

import struct

NOP_WORD = bytes.fromhex("00f020e3")        # nop {0}, the compiler's own padding
FORCE_BOTTOM = 0xE5D00246       # ldrb rN, [rM, #0x246]: the group's screen from the gui's byte (the touch screen)


def forced(register_pair: int) -> tuple[bytes, bytes]:
    """(old, new) words of `ldrb rN, [rM, #0x246]` and its `#0x245` form; `register_pair` = (N << 12) | (M << 16)."""
    word = FORCE_BOTTOM | register_pair
    return struct.pack("<I", word), struct.pack("<I", word - 1)


SCREEN_PATCHES: dict[str, tuple[tuple[int, bytes, bytes], ...]] = {
    # the Wyporio's menu: the lobby list's byte (index 24) and FUN_009ee754's loop over its 11 groups
    "ui405": ((0xEFE018, b"\x01", b"\x00"), (0x9EE878, *forced(1 << 12 | 1 << 16))),
    # "Mi set": the lobby list's byte (index 41), FUN_0059bb14's loop (the layout's open) and FUN_0061e370's (its page)
    "ui417": ((0xEFE029, b"\x01", b"\x00"), (0x59BD2C, *forced(2 << 12 | 7 << 16)),
              (0x61E3A4, *forced(1 << 12 | 1 << 16))),
    # the talisman choice: the byte after ui473's in the Caldero's list, FUN_009fced4's loop, and the call that shows
    # its panels over the box's list (FUN_009e9b44, page 3 sub 0: `bl FUN_00a93a18` -> nop)
    "ui474": ((0x9EB1D0, bytes.fromhex("10a202eb"), NOP_WORD), (0x9FCFD0, *forced(1 << 12 | 1 << 16)),
              (0xEFE03D, b"\x01", b"\x00")),
    # the board: the room lists' byte (kinds 3, 5, 7, 10, 16) and the Camaradas' own (kind 8), and FUN_00a1e878's loop
    "ui481": ((0xEFE090, b"\x01", b"\x00"), (0xEFE0B4, b"\x01", b"\x00"), (0xA1E8F0, *forced(1 << 12 | 1 << 16))),
}
