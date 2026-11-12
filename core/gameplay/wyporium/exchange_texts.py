"""Texts of the Rare Materials Exchange: the messages added to the Wyporium's text file, D_shop, in every language.

The Wyporium's menu shows messages of msg\\lobby\\D_shop_<lang> (lobby message file 4; 135 messages in every
language, the four lines' names first). The exchange appends, at the indices `message_id` gives: its line's name and
help, the words of its two screens, and after them two messages for each distinct
list of owners (`owner_sets`): the second and third line written in the materials box, from the owners' names in the
game's own texts. Every copy of the file is changed (core_lobby, core_arena and core_result), as layered equipment
does with E_makeshop. The screens themselves are the game's trade list (ui407, ui402): no layout changes.
"""

import json
from collections.abc import Iterator, Mapping
from pathlib import Path

from core.equipment.new_gear.new_texts import name_width
from core.game.data.paths import CURATED_DIR
from core.game.files.arc import parse_arc, write_arc
from core.game.files.text.lmd import LMD_TYPE_HASH, parse_lmd, write_lmd
from core.gameplay.wyporium.wyporium_data import load_rare_exchange
from core.interface.hud.build import GameFiles

SCREEN_PATH = CURATED_DIR / "rare_exchange_screen.json"
NAMES_PATH = CURATED_DIR / "monster_names.json"
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
QUEST_LANGUAGES = {"eng": "en", "fre": "fr", "ger": "de", "ita": "it", "spa": "es"}   # monster_names.json's keys
# The messages added to D_shop, in order (the first is the menu line's name): rare_exchange_screen.json 'texts'.
TEXT_KEYS = ("name", "menu_help", "hand_over", "handed", "help_pool", "prompt")
MESSAGES = TEXT_KEYS
SHOP_ARCS = ("core_lobby.arc", "core_arena.arc", "core_result.arc")
SHOP_FILE = 4            # D_shop among the lobby's message files
SHOP_MESSAGES = 135      # the game's own messages in D_shop
OWNER_BASE = SHOP_MESSAGES + len(MESSAGES)     # the first owners' message; two for each distinct list of owners
BLANK = " "              # the third line of a list that two lines hold


class ExchangeTextError(ValueError):
    pass


def load_screen(curated: Mapping | None = None) -> Mapping:
    return curated or json.loads(SCREEN_PATH.read_text(encoding="utf-8"))


def message_id(key: str) -> int:
    """The message a key has in D_shop."""
    return SHOP_MESSAGES + MESSAGES.index(key)


# ----- the owners ----------------------------------------------------------------------------------------------------

def owner_sets(exchange: Mapping | None = None) -> list[tuple[str, ...]]:
    """The distinct lists of owners of the data's rows (every row, a ported monster's too), in order of appearance."""
    seen: dict[tuple[str, ...], None] = {}
    for row in (exchange or load_rare_exchange())["rows"]:
        seen.setdefault(tuple(row["owners"]), None)
    return list(seen)


def owners_message(owners: tuple[str, ...], exchange: Mapping | None = None) -> int:
    """The first of the two D_shop messages (the box's second and third line) that name `owners`."""
    return OWNER_BASE + 2 * owner_sets(exchange).index(tuple(owners))


def _monster_names() -> dict[str, Mapping[str, str]]:
    names = json.loads(NAMES_PATH.read_text(encoding="utf-8"))["names"]
    out: dict[str, Mapping[str, str]] = {}
    for record in names.values():
        out.setdefault(record["en"], record)
    return out


def owner_name(owner: str, lang: str, curated: Mapping | None = None) -> str:
    """An owner of generated/rare_exchange.json in `lang`: the game's own name of the monster
    (curated/monster_names.json, taken from the retail quests' texts); a ported monster's proper name is the same in
    every language."""
    screen = load_screen(curated)
    if owner in screen["proper_names"]:
        return screen["proper_names"][owner]
    record = _monster_names().get(screen["owner_names"].get(owner, owner))
    if record is None:
        raise ExchangeTextError(f"no name for the owner {owner!r}: add it to rare_exchange_screen.json")
    return record[QUEST_LANGUAGES[lang]]


def owner_lines(owners: tuple[str, ...], lang: str, curated: Mapping | None = None) -> tuple[str, str]:
    """The two lines under the materials box's first: the owners' names separated by commas, as many as fit one line of
    `line_px` pixels, then the next line; what does not fit ends with 'more'. The second line is BLANK when the first
    holds them all."""
    screen = load_screen(curated)
    limit = screen["owners"]

    def fits(text: str) -> bool:
        return name_width(text) * limit["line_font"] / 1000 <= limit["line_px"]

    rest: list[str] = []
    for owner in owners:
        name = owner_name(owner, lang, screen)
        if name not in rest:
            rest.append(name)

    def take(room: int) -> list[str]:
        """The names that go on a line (at least one), removed from `rest`."""
        line = [rest.pop(0)]
        while rest and fits(", ".join([*line, rest[0]]) + room * ","):
            line.append(rest.pop(0))
        return line

    first = take(1)
    if not rest:
        return ", ".join(first), BLANK
    second = take(0)
    if not rest:
        return ", ".join(first) + ",", ", ".join(second)
    while len(second) > 1 and not fits(", ".join(second) + limit["more"]):
        second.pop()
    return ", ".join(first) + ",", ", ".join(second) + limit["more"]


# ----- the files -----------------------------------------------------------------------------------------------------

def exchange_messages(lang: str, curated: Mapping | None = None, exchange: Mapping | None = None) -> list[str]:
    """Every message added to D_shop in one language, in message-id order: MESSAGES' (a '{}' is a number node), then the
    owners' two lines of each distinct list of owners."""
    texts = load_screen(curated)["texts"]
    out = [texts[key][lang] for key in TEXT_KEYS]
    for owners in owner_sets(exchange):
        out.extend(owner_lines(owners, lang, curated))
    return out


def add_messages(arc: bytes, lang: str, messages: list[str]) -> bytes:
    """`arc` with `messages` appended to its D_shop ('{}' in a message: a number node); unchanged when the ARC has no
    such file."""
    parsed = parse_arc(arc)
    name = f"{lang}\\msg\\lobby\\D_shop_{lang}"
    entry = next((e for e in parsed.entries if e.name == name and e.type_hash == LMD_TYPE_HASH), None)
    if entry is None:
        return arc
    lmd = parse_lmd(entry.data)
    if lmd.message_count != SHOP_MESSAGES:
        raise ExchangeTextError(f"{name} has {lmd.message_count} messages, not the game's {SHOP_MESSAGES}")
    for text in messages:
        if "{}" in text:
            lmd.add_mixed_message(text)
        else:
            lmd.add_message(text)
    entry.data = write_lmd(lmd)
    return write_arc(parsed)


def exchange_text_files(rom: GameFiles, files: Mapping[str, bytes] | None = None,
                        curated: Mapping | None = None) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of every copy of D_shop, for the 5 languages. An ARC already in `files` (the HUD, the
    icons, layered gear's texts) gets the messages on top of that version; the others start from the base game's
    (`rom`)."""
    files = files or {}
    for lang in LANGUAGES:
        messages = exchange_messages(lang, curated)
        for arc_name in SHOP_ARCS:
            path = f"{lang}/data/{arc_name}"
            raw = files.get(path) or rom.read(path)
            yield path, add_messages(raw, lang, messages)


def exchange_text_paths(mod_dir: Path) -> list[Path]:
    """Every file the option can leave in a mod folder."""
    return [Path(mod_dir) / "romfs" / lang / "data" / name for lang in LANGUAGES for name in SHOP_ARCS]


def remove_exchange_text_files(mod_dir: Path) -> None:
    for path in exchange_text_paths(mod_dir):
        path.unlink(missing_ok=True)
