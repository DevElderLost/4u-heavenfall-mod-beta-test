"""Single-screen mode, the hall's member list on the top screen (emulator).

One layout of the touch screen, loaded on the top screen by its bytes alone (`SCREEN_PATCHES`, merged into
interface/single_screen/executable/single_screen.py's): `ui500`, the hall's member list, the players' box (its rows are
laid out by interface/single_screen/layout/single_screen_players.py and the executable shows it in the hub states where
the game does not: interface/single_screen/executable/single_screen_players.c).

The screen of a layout is decided twice: the loader byte of its index in its scene's list (1 is the bottom screen, 0 the
top: FUN_00c0ff8c for the lobby's list at 0xEFDF44 / 0xEFE000) and, for a layout with a binder table, the kind byte of
each of its root groups (12-byte entries, kind at +4: FUN_00584C08 reads it at every opening; kinds 1 and 2 are the
bottom screen). `ui500`'s table is the one its binder FUN_005A0460 is given.

The other multiplayer menus (`ui490`, `ui501`-`ui504`, `ui511`, `ui530`, `ui060`) were moved the same way before
the game GUI engine placed them, their loader bytes and binder kinds
stay the game's. Y on the guild card is the photo mode's (the game GUI engine); block `single_screen_card_info`
(interface/single_screen/executable/single_screen_card_info.py) shows its hint.
"""

LOBBY_BYTES = 0xEFE000          # the lobby's loader list: paths 0xEFDF44, the layout's index is the byte's offset

# layout -> (the byte's address, the binder table's address and number of root groups)
_MENUS = {
    "ui500": (LOBBY_BYTES + 42, 0xE02008, 1),
}


def _edits(name: str) -> tuple[tuple[int, bytes, bytes], ...]:
    loader, table, entries = _MENUS[name]
    return ((loader, b"\x01", b"\x00"), *((table + 12 * n + 4, b"\x01", b"\x00") for n in range(entries)))


SCREEN_PATCHES: dict[str, tuple[tuple[int, bytes, bytes], ...]] = {name: _edits(name) for name in _MENUS}
