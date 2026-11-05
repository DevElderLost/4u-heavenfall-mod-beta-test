"""The START menu's texts of Mod Settings, in the five languages.

The texts are curated (`menu_texts` in game/data/curated/mod_settings.json): the page's line, the list's rows and
descriptions, and a one-line description for each. A row's `{slot}` is a number node, which the code fills with the
game's string slot (game/files/text/lmd.py SLOT_MARK). They are appended to the common message file `Menu_<lang>` of
each `<lang>/data/core_common.arc` (game/files/text/common_texts.py). The game finds a message by its index: the index
of a text is the game's message count (MENU_MESSAGES) plus its position in the curated list. `message_index` /
`message_indices` give those indices to the code that shows the texts.
"""

import json
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.files.text.common_texts import LANGUAGES, CommonTexts
from core.game.files.text.lmd import SLOT_MARK

SETTINGS_FILE = CURATED_DIR / "mod_settings.json"
HELP_LINES = 2           # what the description panel shows
MENU_STEM = "Menu"          # the message file (core_common's file 3) the START menu's lines are in
MENU_MESSAGES = 929         # the messages `Menu_<lang>` has in the game, in every language


class ModTextError(ValueError):
    """The curated menu_texts are not what the menu can show."""


def load_texts(path: Path = SETTINGS_FILE) -> list[tuple[str, dict[str, str]]]:
    """The curated texts in message order: (key, {language: text}). Refuses an entry without a key or with a repeated
    one, a language missing or unknown, a text that is empty, has a line break (a row holds one line, a description
    `HELP_LINES`) or more than one string slot (the code fills only the first)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8")).get("menu_texts")
    entries = raw.get("value") if isinstance(raw, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ModTextError("mod_settings.json: menu_texts must be {\"value\": [entries], \"description\": ...}")
    texts, seen = [], set()
    for entry in entries:
        key = entry.get("key") if isinstance(entry, dict) else None
        if not isinstance(key, str) or not key or key in seen:
            raise ModTextError(f"mod_settings.json: menu_texts needs a key on every entry, each once ({key!r})")
        seen.add(key)
        if set(entry) - {"key"} != set(LANGUAGES):
            raise ModTextError(f"mod_settings.json: menu_texts {key} must have exactly the texts {LANGUAGES}")
        for lang in LANGUAGES:
            text = entry[lang]
            lines = HELP_LINES if key.endswith("_help") else 1
            if not isinstance(text, str) or not text.strip() or text.count("\n") >= lines or "\r" in text:
                raise ModTextError(f"mod_settings.json: menu_texts {key} {lang} must be text of up to {lines} line(s)")
            if text.count(SLOT_MARK) > 1:
                raise ModTextError(f"mod_settings.json: menu_texts {key} {lang} has more than one {SLOT_MARK}")
        texts.append((key, {lang: entry[lang] for lang in LANGUAGES}))
    return texts


def message_indices(texts: list[tuple[str, dict[str, str]]] | None = None) -> dict[str, int]:
    """{key: message index in Menu_<lang>} of every curated text, in message order."""
    texts = load_texts() if texts is None else texts
    return {key: MENU_MESSAGES + position for position, (key, _) in enumerate(texts)}


def message_index(key: str) -> int:
    """The index of the text `key` in Menu_<lang> (the same in every language)."""
    indices = message_indices()
    if key not in indices:
        raise ModTextError(f"no menu text {key!r}: the curated ones are {', '.join(indices)}")
    return indices[key]


def mod_settings_texts(texts: list[tuple[str, dict[str, str]]] | None = None) -> CommonTexts:
    """The edits that append the texts to Menu_<lang>: apply them with `.files(read)` or `.apply(arc, lang)`."""
    texts = load_texts() if texts is None else texts
    edits = CommonTexts()
    for index, (_, by_language) in enumerate(texts, MENU_MESSAGES):
        edits.put(MENU_STEM, index, by_language)
    return edits
