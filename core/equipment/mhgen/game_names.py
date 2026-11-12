"""The Western names of the gear read from MH XX (game/data/curated/mhxx_names.json).

MH XX (Japan) has only Japanese text, and a player has only XX. The names of a ported monster's gear in the five
languages the mod writes are taken **once** from MH Generations Ultimate (Switch), whose tables are XX's byte for byte,
so a string has the same index in both games: `research/porting/xx_names.py` copies, for
the ids of the monster's gear that `gear_data.read_monster_gear` reads from XX, the strings of MHGU's `eng`, `fre`,
`ger`, `ita` and `spa` text into the file, and a run puts them over the Japanese text it reads (`GenGame.messages`).

The file has a block per monster (`monsters.<key>`), each holding the records of one kind, keyed by their id in XX:

* `items` (an `itemData` id): `names` and `descriptions`, each `{lang: text}`;
* `armor` (an `armorSeriesData` index): `names`, `descriptions`, each `{lang: [five texts, head to legs]}`;
* `weapons` (`{class number: {line: ...}}`): `names`, `descriptions`, `final_names`, `final_descriptions`,
  `best_names`, `best_descriptions` (the six messages of a line in XX's `weaponNNMsgData`);
* `felyne_armor` (an `otArmorData` id): `names`, `descriptions`, each `{lang: [head, body]}`;
* `felyne_weapons` (an `otWeaponData` id), `skill_trees` (`skillTypeData`), `skills` (`skillData`): `names`,
  `descriptions` as items;
* `categories` (an item category id): `{lang: text}`.

The same id in two monsters' blocks must hold the same text (`load_names` refuses a difference).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path

from core.game.data.paths import CURATED_DIR

LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
NAMES_FILE = CURATED_DIR / "mhxx_names.json"

# kind -> the resident text table whose messages hold it
TABLES = {"items": "itemData", "armor": "armorSeriesData", "felyne_armor": "otArmorData",
          "felyne_weapons": "otWeaponData", "skill_trees": "skillTypeData", "skills": "skillData"}
WEAPON_FIELDS = ("names", "descriptions", "final_names", "final_descriptions", "best_names", "best_descriptions")
WEAPON_STRINGS = 6          # messages per line in XX's weaponNNMsgData
KINDS = (*TABLES, "weapons", "categories")


def positions(kind: str, record: int, number: int | None = None) -> list[tuple[str, int | None, int]]:
    """Where the texts of one record are in its table's messages: (field, place in the field's list or None, message
    index). `number` is the message number of a weapon line (`weaponNNMsgData`)."""
    if kind in ("items", "felyne_weapons", "skill_trees", "skills"):
        return [("names", None, 2 * record), ("descriptions", None, 2 * record + 1)]
    if kind == "armor":
        return ([("names", part, 10 * record + part) for part in range(5)]
                + [("descriptions", part, 10 * record + 5 + part) for part in range(5)])
    if kind == "felyne_armor":
        return [("names", 0, 4 * record), ("names", 1, 4 * record + 1), ("descriptions", 0, 4 * record + 2),
                ("descriptions", 1, 4 * record + 3)]
    if kind == "weapons":
        if number is None:
            raise ValueError("a weapon line needs its message number")
        return [(name, None, WEAPON_STRINGS * number + k) for k, name in enumerate(WEAPON_FIELDS)]
    raise ValueError(f"no such kind of record: {kind}")


def collect(kind: str, record: int, texts: Mapping[str, Sequence[str]], number: int | None = None) -> dict:
    """The entry of one record from the messages `texts` ({lang: messages}) of its table."""
    entry: dict = {}
    for name, part, index in positions(kind, record, number):
        for lang in LANGUAGES:
            if part is None:
                entry.setdefault(name, {})[lang] = texts[lang][index]
            else:
                entry.setdefault(name, {}).setdefault(lang, [None] * (5 if kind == "armor" else 2))[part] = \
                    texts[lang][index]
    return entry


def apply(kind: str, record: int, entry: Mapping, texts: dict[str, list[str]], number: int | None = None) -> None:
    """Put the entry of one record over the messages `texts` ({lang: messages}, edited in place)."""
    for name, part, index in positions(kind, record, number):
        for lang in LANGUAGES:
            value = entry[name][lang]
            texts[lang][index] = value if part is None else value[part]


@cache
def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_names(path: Path = NAMES_FILE) -> dict[str, dict]:
    """The file's blocks merged: {kind: {id: entry}} (`weapons`: {class number: {line: entry}}), keyed by int. A record
    two blocks share must hold the same text."""
    merged: dict[str, dict] = {kind: {} for kind in KINDS}
    for monster, block in _read(path)["monsters"].items():
        for kind, records in block.items():
            if kind not in merged:
                raise ValueError(f"{monster}: unknown kind {kind!r} in {path.name}")
            for key, entry in records.items():
                if kind == "weapons":
                    for line, line_entry in entry.items():
                        _put(merged[kind].setdefault(key, {}), int(line), line_entry, f"{monster} {kind} {key}")
                else:
                    _put(merged[kind], int(key), entry, f"{monster} {kind}")
    return merged


def _put(into: dict, key: int, entry: Mapping, where: str) -> None:
    if key in into and into[key] != entry:
        raise ValueError(f"{where} {key}: two blocks give different texts")
    into[key] = entry
