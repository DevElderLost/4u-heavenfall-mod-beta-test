"""The START menu page's RomFS files: one step for every edition's run, so no run
ships the page's code without the panes it shows.

Each language's core_common.arc gets Mod Settings' texts in `Menu_<lang>` (mod_texts.py), ui020's panes for the lists of
every size, 1 to 10 rows a page (ten_rows.py: the lines past the game's five and eight, the frames and row strips the
game lacks) and, with the item wheel, Edit Slots' picture in ui020's big list (interface/radial_menu/radial_draw.py).
"""

from collections.abc import Mapping

from core.interface.hud.build import GameFiles
from core.interface.mod_settings.mod_texts import mod_settings_texts
from core.interface.mod_settings.ten_rows import ten_row_files


def menu_page_files(rom: GameFiles, files: Mapping[str, bytes] | None = None, wheel: bool = False) -> dict[str, bytes]:
    """{RomFS path: core_common.arc} of the five languages with the page's texts and ui020's panes of every list size,
    and with Edit Slots' picture when the mod has the item wheel (`wheel`); each made on the copy in `files` (an
    earlier step's) or on the game's."""
    files = dict(files or {})
    made = mod_settings_texts().files(lambda path: files.get(path) or rom.read(path))
    made |= dict(ten_row_files(rom, {**files, **made}))
    if wheel:
        from core.interface.radial_menu.radial_draw import menu_wheel_files
        made |= menu_wheel_files(rom, {**files, **made})
    return made


__all__ = ["menu_page_files"]
