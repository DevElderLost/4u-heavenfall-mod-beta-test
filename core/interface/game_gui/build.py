"""Single-screen mode's arrangement in the run: the layouts of the
arrangement's blocks are placed by the engine, every other layout by today's mechanism
(interface/single_screen/layout/single_screen.py, interface/single_screen/executable/single_screen*.py).

`single_screen_build` takes the run's ARCs (the copies the other interface steps made, else the game's), makes the
fixes (fixes.py) of the arranged layouts, wraps their blocks' groups (engine.engine_files) and builds the engine's table
for the `single_screen` mode; interface/single_screen/executable/single_screen.patch_single_screen places the engine
with it. An empty arrangement changes no file and gives no table: the mod is today's.

A layout is the engine's or today's, never both (`check_handover`): a layout of the arrangement must have left
single_screen.json's `layouts`, `top_screen` and frame sets (its loader bytes and binder kinds then stay the game's: the
engine switches its screen at draw time, so touch stays where the game put it)."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from core.interface.hud.build import LANGUAGES
from core.interface.single_screen.layout.single_screen import ARCS, SETTINGS_FILE, WEAPON_ARCS
from core.interface.game_gui import engine
from core.interface.game_gui.config import Arrangement, load_arrangement
from core.interface.game_gui.fixes import fix_arc

MODE = "single_screen"
# The screen the game loads each arranged layout on: its loader byte and its binder's kind; a block's reference box is
# measured there
# (engine.engine_table's `own_screens`)
LAYOUT_SCREENS = {
    "ui011": "bottom",      # the help window: the common list's index 20, its binder table 0xDFA6E4 (kind 1)
    "ui560": "bottom",      # the Ayuda topics menu: the lobby list's index 19, the ending list's 1, binder 0xE033C4
    # the multiplayer menus: the lobby list's (0xEFDF44 /
    # 0xEFE000) index and the binder table (kind 1, the guild card's 2), or none (FUN_009E6910 keeps the loader's)
    "ui490": "bottom",      # Crear una sala de reunión: index 11, no table
    "ui501": "bottom",      # Lista de amigos: index 40, table 0xE02134
    "ui502": "bottom",      # Tarjeta del gremio: index 18, table 0xE024DC (kind 2)
    "ui503": "bottom",      # its edit and title windows: index 26, table 0xE02B44
    "ui504": "bottom",      # Lista de tarjetas: index 28, table 0xE02CD8
    "ui511": "bottom",      # Mensajero: the StreetPass menus: index 39, no table
    "ui510": "top",         # its information panels: top by byte and binder
    "ui530": "bottom",      # Multijugador en línea: index 33, table 0xE02FD0
    "ui060": "bottom",      # Búsqueda de cazador: the common list's (0xEFDC60 / 0xEFDCE8) index 29, table 0xDFCAE8
    # the quests and Arena theme: bound from plain hash lists (FUN_009e6910, the select scene's FUN_00ae63c8 loop),
    # which keep the loader's screen
    "ui413": "bottom",      # the quest board: the village list's index 3, the hall's 2, the third map's 0 (0xED922C)
    "ui495": "bottom",      # the Arena's counter: the village list's index 1, the hall's 0 (0xED9078)
    "ui496": "top",         # the ranking's information: the village list's index 2, the hall's 1 (0xED909C)
    "ui497": "bottom",      # the team and weapon choice: the select scene's index 0 (0xEC7CF8)
    "ui498": "top",         # its sign, item grid and time: the select scene's index 1 (0xEC7D08)
    # the Song Select: the stage lists' (FUN_00c10ce8) ui443, byte 1, binder
    # kind 2; a recording shows its four groups on the touch screen (bits 7)
    "ui443": "bottom",      # the song list, its title and cursor, and their wooden ground
    # the Wyceum: the stage kind 13 list's (FUN_00c10ce8) ui455, byte 0,
    # ui456, byte 1
    "ui455": "top",         # the Availability table, the Selected Wystones panel and the description panel
    "ui456": "bottom",      # the Select Wystones page: the list, its tooltip and portrait, and the wooden ground
    # the town minimap: the lobby list's (0xEFDF44 / 0xEFE000) index 22, its binder FUN_0059deac binds kind 1; the
    # minimap's block writes its groups' screen while it is on
    # (interface/single_screen/executable/single_screen_minimap.py)
    "ui422": "bottom",
    # the title: the title list's bytes (FUN_00c0f94c, 0xEFE150); their binder FUN_005d7d18 sets no screen
    "ui801": "top",         # the gold rug: index 1 (its block keeps the game's place and screen)
    "ui803": "bottom",      # the boot's menu and save list: index 3
    "ui804": "top",         # the title art and the creation's sign: index 4
    "ui805": "bottom",      # "press A": index 5
    # the weapon guide: the paper, title and page counter are the common list's index 32 (0xEFDD08), binder 0xDFDD40
    # (kind 1); the 14 weapon pages are loaded by FUN_00c105f4 with the literal screen 1 (0xC1066C), no table
    "ui223": "bottom",
    **{f"ui2{n}": "bottom" for n in range(30, 44)},
    # the hunters' name tags over the world: the common list's layout; its
    # code puts each name over its character on the top screen
    "ui001": "top",
}


@dataclass
class Build:
    files: dict[str, bytes] = field(default_factory=dict)   # RomFS path -> ARC (fixed and wrapped)
    table: bytes | None = None                               # the engine's table; None: no engine


def arc_paths() -> tuple[str, ...]:
    """The RomFS paths of the ARCs that may hold an arranged layout, per language: the ones today's mechanism places and
    the weapon archives (the weapon guide's pages)."""
    return tuple(f"{language}/data/{name}" for language in LANGUAGES for name in ARCS + WEAPON_ARCS)


def arranged_layouts(arrangement: Arrangement) -> set[str]:
    return {block.layout for block in arrangement.blocks.values()}


def check_handover(arrangement: Arrangement, path: Path = SETTINGS_FILE) -> None:
    """Raises ValueError naming every layout both the arrangement and today's single_screen.json place."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    today = set(data.get("layouts", {})) | set(data.get("top_screen", []))
    for groups in data.get("frames", {}).get("sets", {}).values():
        today |= {group.split("_")[0] for group in groups}
    both = sorted(arranged_layouts(arrangement) & today)
    if both:
        raise ValueError(f"placed by the engine and by single_screen.json: {', '.join(both)} (a migrated layout leaves "
                         "its layouts, top_screen and frames entries)")


def single_screen_build(read: Callable[[str], bytes], files: Mapping[str, bytes] | None = None,
                        arrangement: Arrangement | None = None, fixes=None, paths: tuple[str, ...] | None = None,
                        screens: Mapping[str, str] | None = None, settings_path: Path = SETTINGS_FILE) -> Build:
    """The engine's files and table for single-screen mode. `read(path)`: the game's bytes; `files`: the run's copies
    so far (taken first). The arrangement, ARC paths and layout screens are the curated ones by default, the fixes the
    arrangement's. Raises ValueError for a layout placed twice, a fix or block whose layout no ARC holds, or a layout
    without its screen."""
    files = files or {}
    arrangement = load_arrangement() if arrangement is None else arrangement
    layouts = arranged_layouts(arrangement)
    if not layouts:
        return Build()
    fixes = arrangement.fixes if fixes is None else fixes
    paths = arc_paths() if paths is None else paths
    screens = LAYOUT_SCREENS if screens is None else screens
    check_handover(arrangement, settings_path)
    stray = sorted(set(fixes) - layouts)
    if stray:
        raise ValueError(f"fixes.json: {', '.join(stray)} has no block (a fix is made only for an arranged layout)")
    names = [name.encode() for name in layouts]
    before: dict[str, bytes] = {}
    fixed: dict[str, bytes] = {}
    for path in paths:      # an ARC's entry names are stored as they are: one without the name holds no such layout
        raw = files.get(path) or read(path)
        if any(name in raw for name in names):
            before[path] = raw
            fixed[path] = fix_arc(raw, fixes, path.rsplit("/", 1)[-1])
    wrapped, targets, found = engine.engine_files(read, arrangement, list(fixed), fixed)
    missing = sorted(layouts - set(found))
    if missing:
        raise ValueError(f"arranged layouts in none of the ARCs: {', '.join(missing)}")
    if set(fixes) - set(found):
        raise ValueError(f"fixes.json: {', '.join(sorted(set(fixes) - set(found)))} in none of the ARCs")
    table = engine.engine_table(arrangement, MODE, targets, found, screens)
    out = {path: wrapped.get(path, data) for path, data in fixed.items()}
    return Build({path: data for path, data in out.items() if data != before[path]}, table)
