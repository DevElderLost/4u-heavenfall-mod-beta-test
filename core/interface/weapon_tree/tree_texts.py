"""The weapon tree's words: messages appended to the Smithy's text file, E_makeshop, in the five languages
(core_lobby, core_arena and core_result of each, as Layered Gear does with the same file).

E_makeshop (lobby message file 6) holds 147 messages of the game's; Layered Gear appends its own after them and its
`add_messages` insists on exactly the game's 147, so the weapon tree appends after whatever the file holds: this
module's messages come second when both options are on, and `message_base` says where they begin in the files
actually written. Ours, in order:

* the cursor's row and the rows ("3/41": only the text renderer's string slot 0, which the screen's code fills);
* the key bar (curated: weapon_tree.json, `texts`), written with the game's own words of each language (the Smithy's
  "Forge", the common "Back", the Lobby's "View");
* copies of the game's own help lines and price questions of the forge and of Upgrade (`CAPS_SOURCES`) with the verb
  in capitals (curated `caps`: the words of each language), so the tree, where one node can be forged or upgraded,
  always says which of the two the materials shown are for; the game's own messages stay as they are for its lists;
* the window "upgrade or craft": its title and its two options.
"""

import json
import re
from collections.abc import Mapping

from core.game.data.paths import CURATED_DIR
from core.game.files.arc import parse_arc, write_arc
from core.game.files.text.lmd import LMD_TYPE_HASH, parse_lmd, write_lmd

LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
MAKESHOP_ARCS = ("core_lobby.arc", "core_arena.arc", "core_result.arc")
MAKESHOP_FILE = 6              # E_makeshop among the lobby's message files
MESSAGE_BASE = 147             # the game's own messages in E_makeshop
# The game's messages copied with their verb in capitals, in weapon_tree.c's CAPS_* order: the forge's help line
# (payable; no materials; no money; neither; the box full) and its price question, then Upgrade's help line (payable;
# the copy has decorations; no materials; no money; neither) and its price question.
CAPS_SOURCES = (0x29, 0x4C, 0x4D, 0x4E, 0x4F, 0x2B, 0x2F, 0x5E, 0x55, 0x56, 0x57, 0x30)
CHOICE = ("choice_title", "choice_upgrade", "choice_forge")
MESSAGES = ("count", "hint_tree") + tuple(f"caps_{source:02x}" for source in CAPS_SOURCES) + CHOICE
COUNTER = None                 # the "count" message: a number node, no text


class TreeTextError(ValueError):
    pass


def load_settings(curated: Mapping | None = None) -> Mapping:
    return curated or json.loads((CURATED_DIR / "weapon_tree.json").read_text(encoding="utf-8"))


def load_texts(curated: Mapping | None = None) -> Mapping:
    """The curated words: key -> language -> text."""
    return load_settings(curated)["texts"]


def message_index(key: str, base: int = MESSAGE_BASE) -> int:
    """The message of `key` in E_makeshop, when ours begin at `base` (the game's 147 unless another option appended
    first: `message_base` gives the real one)."""
    return base + MESSAGES.index(key)


def capitals(text: str, words) -> str:
    """`text` with every whole-word occurrence of one of `words` (any case) in capitals."""
    for word in words:
        text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", lambda found: found.group(0).upper(), text,
                      flags=re.IGNORECASE)
    return text


def tree_messages(lang: str, curated: Mapping | None = None) -> list:
    """Every message added in one language, in index order: COUNTER (the number message), a text, or the index of a
    message of the game's to copy with its verb in capitals."""
    texts = load_texts(curated)
    return [COUNTER if key == "count" else CAPS_SOURCES[index - 2] if key.startswith("caps_") else texts[key][lang]
            for index, key in enumerate(MESSAGES)]


def _makeshop(arc: bytes, lang: str):
    parsed = parse_arc(arc)
    name = f"{lang}\\msg\\lobby\\E_makeshop_{lang}"
    entry = next((e for e in parsed.entries if e.name == name and e.type_hash == LMD_TYPE_HASH), None)
    return parsed, entry


def add_messages(arc: bytes, lang: str, messages: list, curated: Mapping | None = None) -> bytes:
    """`arc` with `messages` (`tree_messages`) appended to its E_makeshop, after the game's messages and any another
    option appended."""
    parsed, entry = _makeshop(arc, lang)
    if entry is None:
        raise TreeTextError(f"no E_makeshop_{lang} in the ARC")
    lmd = parse_lmd(entry.data)
    if lmd.message_count < MESSAGE_BASE:
        raise TreeTextError(f"E_makeshop_{lang} has {lmd.message_count} messages, fewer than the game's {MESSAGE_BASE}")
    words = load_settings(curated)["caps"][lang]
    for message in messages:
        if message is COUNTER:
            lmd.add_number_message()
        elif isinstance(message, int):
            before = lmd.message(message)
            lmd.add_copy(message, lambda text: capitals(text, words))
            if lmd.message(lmd.message_count - 1) == before:
                raise TreeTextError(f"E_makeshop_{lang} message {message:#x} ({before!r}) has none of the words "
                                    f"to write in capitals ({', '.join(words)})")
        else:
            lmd.add_message(message)
    entry.data = write_lmd(lmd)
    return write_arc(parsed)


def message_base(read, lang: str = "eng") -> int:
    """The index of the first weapon tree message in the files written: `read(path)` gives a file's bytes (a mapping of
    the written ARCs falling back to the game's, as the pipeline's steps do). Call it after `weapon_tree_files`."""
    _, entry = _makeshop(read(f"{lang}/data/core_lobby.arc"), lang)
    if entry is None:
        raise TreeTextError(f"no E_makeshop_{lang} in core_lobby.arc")
    return parse_lmd(entry.data).message_count - len(MESSAGES)


__all__ = ["CAPS_SOURCES", "CHOICE", "COUNTER", "LANGUAGES", "MAKESHOP_ARCS", "MAKESHOP_FILE", "MESSAGES",
           "MESSAGE_BASE", "TreeTextError", "add_messages", "capitals", "load_texts", "message_base", "message_index",
           "tree_messages"]
