"""Single-screen mode, the guild card's "[Y] Toggle Display" hint (emulator only), layout side.

The Tarjeta del gremio (the lobby's `ui502`, placed for the top screen by its curated layout setting and loaded there:
interface/single_screen/executable/single_screen_multiplayer.py) covers much of the top screen, which in this mode is
the only one the player sees. Y on it turns on the photo mode (the game GUI engine, settings.json `photo`), which hides
the interface but the characters, the background and the hunter's greeting if it is on. This module adds, to each
language's core_lobby.arc, in the lobby's host layout (`ui430`, on the top screen) the hint that says so: a panel like
the minimap's "[L] Minimap" one (interface/single_screen/layout/single_screen_minimap.py, which builds it from the same
record), with the game's own glyph of the Y button, and a blank text pane the executable's block
(interface/single_screen/executable/single_screen_card_info.py) fills with the game's own word (the lobby message
"Toggle Display", curated). The block shows it while the card is up alone, where Y is the photo mode's.

Everything is curated (single_screen.json, "card_info"). The group is added after the layouts are
placed, so the placing neither scales nor moves it.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from core.game.files.arc import parse_arc, write_arc
from core.interface.hud.build import LANGUAGES, GameFiles
from core.game.files.gui.lyt import LYT_TYPE_HASH, parse_lyt
from core.interface.single_screen.layout.single_screen import SETTINGS_FILE
from core.interface.single_screen.layout.single_screen_minimap import (
    ARC_NAME, MinimapHint, _hint, _keys, _name, add_minimap_hint,
)

MAX_GROUPS = 16               # the block's room for the groups of the card kept on the top screen
MAX_UNLESS = 3                # ... and for the groups that stop the hint while shown
_KEYS = {"when", "unless", "groups", "hint"}


@dataclass(frozen=True)
class CardInfo:
    """The curated "card_info" section: the `hint` (its layout, the lobby's host, gets the hint's group), the root
    group `when` whose shown bit says the card is open, the `unless` groups that stop the hint while any is shown (a
    window over the card, the card list, the monster page where the game uses Y itself) and the `groups` of the card
    that stay on the top screen."""
    when: str
    unless: tuple[str, ...]
    groups: tuple[str, ...]
    hint: MinimapHint


def _fail(where: str, what: str) -> ValueError:
    return ValueError(f"single_screen.json, card_info{where}: {what}")


def _names(value: object, where: str, low: int, high: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not low <= len(value) <= high:
        raise _fail(where, f"a list of {low} to {high} names" if low else f"a list of up to {high} names")
    return tuple(_name(item, where) for item in value)


def card_info_settings(path: Path = SETTINGS_FILE) -> CardInfo:
    """The card_info section of single_screen.json, validated (the hint's record as the minimap's: errors name this
    section)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    record = _keys(data.get("card_info"), _KEYS, "")
    try:
        hint = _hint(record["hint"])
    except ValueError as error:
        raise ValueError(str(error).replace("minimap", "card_info", 1)) from None
    groups = _names(record["groups"], ", groups", 1, MAX_GROUPS)
    unless = _names(record["unless"], ", unless", 0, MAX_UNLESS)
    when = _name(record["when"], ", when")
    if when not in groups:
        raise _fail(", when", "one of the groups of the card")
    if hint.group in groups or hint.group in unless:
        raise _fail("", "the hint's group may not be one of groups or unless")
    if len(set(unless)) != len(unless) or len(set(groups)) != len(groups):
        raise _fail("", "a name listed twice")
    return CardInfo(when, unless, groups, hint)


def card_info_arc(raw: bytes, card: CardInfo) -> bytes:
    """The ARC with the hint in the host layout. An ARC without the host is returned as it was."""
    arc = parse_arc(raw)
    entries = {e.name.split("\\")[-1]: e for e in arc.entries if e.type_hash == LYT_TYPE_HASH}
    if card.hint.layout not in entries:
        return raw
    others = {name: parse_lyt(entry.data) for name, entry in entries.items()}
    host = parse_lyt(entries[card.hint.layout].data)
    add_minimap_hint(host, others, card.hint)
    entries[card.hint.layout].data = host.to_bytes()
    return write_arc(arc)


def card_info_files(rom: GameFiles, files: Mapping[str, bytes] | None = None,
                    card: CardInfo | None = None) -> dict[str, bytes]:
    """(RomFS path -> ARC) of each language's core_lobby.arc with the card's hint: from the copy in
    `files` (the run's earlier interface files, the placed layouts and the other hints included) or the game's. The
    curated settings by default."""
    card = card or card_info_settings()
    out = {}
    for language in LANGUAGES:
        path = f"{language}/data/{ARC_NAME}"
        out[path] = card_info_arc((files or {}).get(path) or rom.read(path), card)
    return out
