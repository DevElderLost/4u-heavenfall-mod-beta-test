"""The START menu's third page, Mod Settings (blocks `mod_settings_stub`,
`mod_settings_code`, `mod_settings_data`, `aspect_list_data`, variables `mod_settings_state`, `aspect_list_state`).

The game's START menu has two pages of eight lines each. These functions change, in the update's executable (canonical):

- FUN_0060cd50, which sets the menu up when it opens: the page count (+0x10) becomes 3, so Left and Right reach the new
  page and the pager prints "x/3" (`mov r2,#2` at PAGE_COUNT);
- FUN_005e8050, which fills the page's lines each frame: on a page past the second it calls mod_menu_page (`strhne` at
  PAGE_FILL becomes a `blne`), which sets the row count, the line table and the enable bytes, and its last test lets the
  third page reach the redraw (PAGE_TEST, three instructions);
- FUN_00600658, the action of the line under the cursor: where it would return 0xFF (`mov r0,#0xFF` at LINE_ACTION) it
  asks mod_line_action, which gives ACTION for the page's first row;
- FUN_005f6c8c, the list's frame: the jump past its table of actions (at PICK) goes through the stub, which on ACTION
  calls mod_menu_pick and goes on to the same decide sound;
- FUN_0060fc2c, a line's description: its first instruction (DESCRIPTION) goes through the stub, which keeps ACTION and
  over from the game's table and writes the line's help;
- FUN_005f6ae4, the sub-screen's frame: its call of FUN_00607910 (at SUBSCREEN) goes through the stub, which runs
  mod_menu_frame for the menu's kind KIND and the game's function for any other;
- FUN_0060d058, which every close of the menu runs: its call of FUN_005e86b0 (at CLOSE) goes through the stub, which
  first ends the bind of the big list's pager if a screen of ours held it.

From there it is the game's own widgets, driven as its sub-screens drive them: the small list of 5 rows, refilled
for each list of the table and for each page of a list of up to 10 rows (the menu's title bar then says "1/2" or "2/2"),
and from a list's row the big list of 8 rows a page with its title (aspect_list.c, the aspect ratios). The small lists
come from the curated mod_settings.json, in the data block (`settings_data`), so a new row or a new level costs only
data. Message indices come from `mod_texts`.
"""

import json
import struct
from collections.abc import Collection
from pathlib import Path

from core.cheats.aspect_table import menu_ratios, ratio_text
from core.game.data.paths import CURATED_DIR
from core.game.executable.blocks import ASPECT_LIST_DATA_SIZE, MOD_SETTINGS_DATA_SIZE
from core.game.executable.code_space import (
    BASE_ADDRESS, COND_HI, COND_NE, CodeSpaceError, Layout, encode_branch, load_layout,
)
from core.interface.mod_settings.mod_texts import message_index, message_indices

SETTINGS_FILE = CURATED_DIR / "mod_settings.json"
STUB, CODE, DATA, LIST_DATA = "mod_settings_stub", "mod_settings_code", "mod_settings_data", "aspect_list_data"
VARIABLES = ("mod_settings_state", "aspect_list_state")

ACTION = 0x14                   # the line's action: the game's table of actions (FUN_005f6c8c) ends at 0x13
KIND = 0x2F                     # the menu's sub-screen kind (+0xA) while the list is open: no reader of +0xA knows it
SUBLIST_ROWS = 5                # the rows of the game's small list (FUN_0060caec, FUN_005e87b4): one page
MAX_ROWS = 2 * SUBLIST_ROWS     # a list's rows: two pages of the small list, with the pager
MAX_LISTS = 6                   # the small lists the data block has room for (mod_settings.c)
MAX_TABLE = 40                  # their rows, together: the top list and three full lists below it
NO_LIST = 0xFF                  # in a list: it has no parent; in an entry: it opens a screen
# The screens an entry can open, by their number in mod_settings.c: the aspect ratios (aspect_list.c) and an
# option's values (option_list.c)
SCREENS = ("aspect_list", "option_list")
LIST_TEXTS = ("aspect_help", "aspect_row", "aspect_marked")      # struct aspect_list_data's, before the ratios' names
LIST_ROWS = 8                   # a page of the game's big list
LINES_PER_PAGE = 8              # the lines of a page's table (FUN_005e8050)
MENU_FILE = 3                   # core_common's file 3, Menu_<lang> (the game's own lines are there)
PLACEHOLDER_MESSAGE = 0x199     # Menu's "- - - - -", the empty lines of the game's second page in a quest

# Where each patch goes, with the word the update's executable has there
PAGE_COUNT = 0x60CD64           # FUN_0060cd50: mov r2,#2
PAGE_FILL = 0x5E80EC            # FUN_005e8050: strhne r9,[r5,#0xC], only reached on a page past the second
PAGE_TEST = 0x5E810C            # FUN_005e8050: cmp r0,#0; cmpne r0,#1; bne PAGE_EXIT
PAGE_EXIT = 0x5E8470
LINE_ACTION = 0x6006C0          # FUN_00600658: mov r0,#0xFF
PICK = 0x5F6E80                 # FUN_005f6c8c: b 0x5F746C, the decide sound of an action past the table
DESCRIPTION = 0x60FC2C          # FUN_0060fc2c: str lr,[sp,#-4]!
SUBSCREEN = 0x5F6AF0            # FUN_005f6ae4: bl FUN_00607910
CLOSE = 0x60D06C                # FUN_0060d058: bl FUN_005e86b0
SITES = {
    PAGE_COUNT: 0xE3A02002,
    PAGE_FILL: 0x11C590BC,
    PAGE_TEST: 0xE3500000,
    PAGE_TEST + 4: 0x13500001,
    PAGE_TEST + 8: 0x1A0000D5,
    LINE_ACTION: 0xE3A000FF,
    PICK: 0xEA000179,
    DESCRIPTION: 0xE52DE004,
    SUBSCREEN: 0xEB004386,
    CLOSE: 0xEBFF6D8F,
}
MOV_R2_3, CMP_R0_2, NOP = 0xE3A02003, 0xE3500002, 0xE320F000


class ModSettingsError(ValueError):
    """The curated mod_settings.json is not what the menu can show."""


def _value(raw: dict, key: str):
    entry = raw.get(key)
    if not isinstance(entry, dict) or "value" not in entry or not isinstance(entry.get("description"), str):
        raise ModSettingsError(f"mod_settings.json: {key} must be {{\"value\": ..., \"description\": ...}}")
    return entry["value"]


def load_zone(path: Path = SETTINGS_FILE) -> dict:
    """The curated place of a character's choices: {"offset", "magic" (4 bytes), "version"}."""
    zone = _value(json.loads(Path(path).read_text(encoding="utf-8")), "save_zone")
    magic = zone.get("magic") if isinstance(zone, dict) else None
    if not isinstance(magic, str) or len(magic) != 4 or not magic.isascii():
        raise ModSettingsError("mod_settings.json: save_zone's magic must be 4 ASCII characters")
    return {"offset": zone["offset"], "magic": magic.encode("ascii"), "version": zone["version"]}


def load_settings(path: Path = SETTINGS_FILE, available: Collection[str] | None = None, aspect: bool = True) -> dict:
    """The curated table with each text as its message index: {"line": {"name", "help"}, "pager": (x, y) (the big
    list's), "entries": [row]}, where a row is {"name", "help", "title", "screen"} (and "option", the option's number,
    on the screen of its values) when it opens a screen and {"name", "help", "entries": [row]} when it opens another
    small list. `available`: the options the player's game can have (none: all); `aspect`: the aspect ratio's switch
    is on. A row of an option that is not available, the aspect ratio's row without its switch, and a list left with no
    row, are left out. Refuses a list with more rows than two pages of the small list, a screen the code does not
    have, a place that is not two whole numbers, a text that is not one of its menu_texts, and more lists or rows than
    the data block holds."""
    from core.interface.mod_settings.mod_options import OPTION_IDS, load_options

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    known = message_indices()
    options = {option["key"]: option for option in load_options(path)}

    def message(key: object) -> int:
        if key not in known:
            raise ModSettingsError(f"mod_settings.json: no menu text {key!r}")
        return known[key]

    def small_list(entries: object) -> list[dict]:
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ROWS:
            raise ModSettingsError(f"mod_settings.json: entries must list 1 to {MAX_ROWS} rows")
        return [made for made in (row(entry) for entry in entries) if made is not None]

    def row(entry: dict) -> dict | None:
        if "option" in entry:
            option = options.get(entry["option"])
            if option is None:
                raise ModSettingsError(f"mod_settings.json: no option {entry['option']!r}")
            if available is not None and option["key"] not in available:
                return None
            return {"name": message(option["name"]), "help": message(option["help"]), "title": message(option["title"]),
                    "screen": SCREENS.index("option_list"), "option": OPTION_IDS[option["key"]]}
        if entry.get("aspect") and not aspect:
            return None
        opens = entry["opens"]
        texts = {"name": message(entry["name"]), "help": message(entry["help"])}
        if "entries" in opens:
            inner = small_list(opens["entries"])
            return {**texts, "entries": inner} if inner else None
        if opens.get("screen") not in SCREENS:
            raise ModSettingsError(f"mod_settings.json: {entry['name']} opens the screen {opens.get('screen')!r}, "
                                   f"one of {SCREENS} is needed")
        return {**texts, "title": message(opens["title"]), "screen": SCREENS.index(opens["screen"])}

    def place(key: str) -> tuple[int, int]:
        at = _value(raw, key)
        if not isinstance(at, list) or len(at) != 2 or \
                not all(isinstance(n, int) and not isinstance(n, bool) and -0x8000 <= n < 0x8000 for n in at):
            raise ModSettingsError(f"mod_settings.json: {key} must be [x, y], two whole numbers")
        return tuple(at)

    line = _value(raw, "line")
    entries = small_list(_value(raw, "entries"))
    settings = {"line": {"name": message(line["name"]), "help": message(line["help"])}, "pager": place("pager_place"),
                "entries": entries}
    _flat_table(settings)
    return settings


def _flat_table(settings: dict) -> tuple[list[tuple], list[tuple]]:
    """The lists, top one first, as (first row, rows, parent list, its row), and their rows as (name, help, title, list,
    screen, option): `list` is the list a row opens, NO_LIST for one that opens the screen `screen` (of the option
    `option`, on the screen of its values). Refuses a table past MAX_LISTS or MAX_TABLE."""
    queue, lists, table = [(settings["entries"], NO_LIST, 0)], [], []
    for rows, parent, parent_row in queue:          # the queue grows from inside the loop
        index = len(lists)
        lists.append((len(table), len(rows), parent, parent_row))
        for at, row in enumerate(rows):
            if "entries" in row:
                queue.append((row["entries"], index, at))
                table.append((row["name"], row["help"], 0, len(queue) - 1, 0, 0))
            else:
                table.append((row["name"], row["help"], row["title"], NO_LIST, row["screen"], row.get("option", 0)))
    if len(lists) > MAX_LISTS:
        raise ModSettingsError(f"mod_settings.json: {len(lists)} lists, the data block has room for {MAX_LISTS}")
    if len(table) > MAX_TABLE:
        raise ModSettingsError(f"mod_settings.json: {len(table)} rows, the data block has room for {MAX_TABLE}")
    return lists, table


def settings_data(settings: dict | None = None) -> bytes:
    """The block `mod_settings_data` (struct mod_settings_data in mod_settings.c): the page's line table, 8 of (u16
    file, u16 message), the first the line's and the rest the placeholder; the line's help, the placeholder and the file
    (u16 each); the pager's place (s16 x, y); MAX_LISTS of (u8 first row, rows, parent list, its row); MAX_TABLE of (u16
    name, help, title, u8 list, screen, option, 0). What is unused stays zero."""
    settings = settings or load_settings()
    lists, table = _flat_table(settings)
    data = struct.pack("<2H", MENU_FILE, settings["line"]["name"])
    data += struct.pack("<2H", MENU_FILE, PLACEHOLDER_MESSAGE) * (LINES_PER_PAGE - 1)
    data += struct.pack("<3H", settings["line"]["help"], PLACEHOLDER_MESSAGE, MENU_FILE)
    data += struct.pack("<2h", *settings["pager"])
    data += b"".join(struct.pack("<4B", *entry) for entry in lists).ljust(4 * MAX_LISTS, b"\0")
    data += b"".join(struct.pack("<3H3BB", *entry, 0) for entry in table).ljust(10 * MAX_TABLE, b"\0")
    if len(data) > MOD_SETTINGS_DATA_SIZE:
        raise ModSettingsError(f"mod_settings_data holds {MOD_SETTINGS_DATA_SIZE} bytes, the table makes {len(data)}")
    return data.ljust(MOD_SETTINGS_DATA_SIZE, b"\0")


def aspect_list_data() -> bytes:
    """The block `aspect_list_data` (struct aspect_list_data in aspect_list.c): the list's texts and each ratio's name,
    as message indices (u16 each); the room of the ratios it does not have stays zero."""
    keys = (*LIST_TEXTS, *(ratio_text(ratio) for ratio in menu_ratios()))
    if len(keys) > len(LIST_TEXTS) + LIST_ROWS:
        raise ModSettingsError(f"the aspect ratios' list shows {LIST_ROWS} rows, the curated ratios make "
                               f"{len(keys) - len(LIST_TEXTS)}")
    data = struct.pack(f"<{len(keys)}H", *(message_index(key) for key in keys))
    return data.ljust(ASPECT_LIST_DATA_SIZE, b"\0")


def supports_mod_settings(code: bytes) -> bool:
    """`code` has the words every patch replaces (the update's executable, canonical, not patched yet)."""
    return all(struct.unpack_from("<I", code, at - BASE_ADDRESS)[0] == word for at, word in SITES.items())


def patch_mod_settings(code: bytes, layout: Layout | None = None, settings: dict | None = None) -> bytes:
    """`code` with the third page (the module's docstring lists each change). Refuses an executable where any site is
    not the game's word: another version, or already patched."""
    if not supports_mod_settings(code):
        raise CodeSpaceError("the START menu's sites are not the update's words: already patched or another game")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, STUB)
    layout.place(out, CODE)
    layout.place(out, DATA, settings_data(settings))
    layout.place(out, LIST_DATA, aspect_list_data())
    for at, word in ((PAGE_COUNT, MOV_R2_3), (PAGE_TEST, CMP_R0_2), (PAGE_TEST + 4, NOP)):
        struct.pack_into("<I", out, at - BASE_ADDRESS, word)
    at = PAGE_TEST + 8 - BASE_ADDRESS
    out[at:at + 4] = encode_branch(PAGE_TEST + 8, PAGE_EXIT, cond=COND_HI)
    at = PAGE_FILL - BASE_ADDRESS
    out[at:at + 4] = encode_branch(PAGE_FILL, layout.symbol(STUB, "stub_page"), link=True, cond=COND_NE)
    for at, label, link in ((LINE_ACTION, "stub_action", False), (PICK, "stub_pick", False),
                            (DESCRIPTION, "stub_desc", False), (SUBSCREEN, "stub_frame", True),
                            (CLOSE, "stub_close", True)):
        offset = at - BASE_ADDRESS
        out[offset:offset + 4] = encode_branch(at, layout.symbol(STUB, label), link=link)
    return bytes(out)
