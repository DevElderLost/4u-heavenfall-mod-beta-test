"""Names and descriptions of new items and equipment, in the five languages.

Every name and description of the game's gear lives in a message file of `<lang>/data/core_common.arc`, and the
game finds a message by its index, with no limit in the executable (the lookup only checks the index against the
file's own message count). A new id therefore needs its name appended to the list: message index = id, so the
messages between the list's end and the new id are filled with empty ones. Descriptions:

* items and Felyne gear: the message with the same index as the id;
* hunter gear (the five armor parts and the 14 weapon classes): the game reads them through arrays with one entry
  per id it has (equipment/new_gear/gear_descriptions.py hooks the read). The descriptions of the new ids are appended
  to the Exp list in id order, one message per id from the list's old end: `description_message`.

`CommonTexts` collects the edits of every feature that changes these files (new gear, the hunting log's `emExp`
for the ported monsters...) and applies them to a core_common.arc in memory, so the ARC is parsed and written once
per language by whoever writes it: `apply`, or `files` over a reader of the mod's files so far
(pipeline.write_interface_files and monsters/porting/product.his_files do the same, each on the previous copy). The
generic part (any message file of the archive: `put`, `apply`, `files`) is game/files/text/common_texts.py; this
module extends it with the gear's lists.

Names follow MH4U's habit per language (rank_names, level_names, g_step_names), cut to the longest name the game's
lists hold
*in that language*: in characters and in estimated width (`NAME_LIMITS`, `name_width`). A word is cut only right after a
*syllable, and the monster's name
is always its fixed abbreviation ("Mizu."): `name_cut.py`.
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.game.files.text import common_texts
from core.game.files.text.common_texts import (  # noqa: F401  (re-exported: the callers import them from here)
    COMMON_ARC, LANGUAGES, CommonTextError, Texts, common_text_paths, complete_texts, remove_common_text_files,
)
from core.game.files.text.lmd import Lmd
from core.equipment.new_gear.gear_descriptions import HUNTER_LISTS
from core.equipment.new_gear import name_cut

NewTextError = CommonTextError      # one error for the generic edits and the gear's


@dataclass(frozen=True)
class TextList:
    """A name list and its description list in core_common."""
    key: str
    name_stem: str           # message file `<stem>_<lang>` of the names
    exp_stem: str            # ... and of the descriptions
    old_names: int           # messages the game's name list has (the ids the game has, DUMMY ones included)
    old_exp: int             # ... and its description list
    by_array: bool           # hunter gear: descriptions found through the game's arrays (the module doc)
    max_name: int            # the longest name the game's list holds, in any language
    max_lines: int           # lines of a description the game's list holds

    def description_message(self, piece: int) -> int:
        """The message of the description list that shows `piece`'s description."""
        if not self.by_array:
            return piece
        if piece < self.old_names:
            raise NewTextError(f"{self.key} {piece} is one of the game's ids: its description is in the game's array")
        return self.old_exp + piece - self.old_names


DESCRIPTION_WIDTH = 38    # characters of a description's line (the game's lists hold 38; one string in 39)
ARMOR_NAME, WEAPON_NAME, FELYNE_NAME, ITEM_NAME = 25, 23, 23, 24   # the longest names of the game's lists

# What a name may be, per kind of list and language: (characters, width) of the longest name MH4U's own lists hold
# (measured over every retail name of the lists of the kind; tests/equipment/new_gear/test_new_texts.py recomputes it
# from the game). A retail name fits its box, so a new name no longer than these in both measures fits too. The width is
# an estimate (`name_width`: Helvetica's advance widths in 1/1000 em; the game's font file has no readable table here),
# so it is a conservative proxy, not pixels: it catches wide letters ("M", "z", "w") that a character count does not.
NAME_LIMITS: dict[str, dict[str, tuple[int, int]]] = {
    "item": {"eng": (22, 10394), "fre": (24, 11394), "ger": (22, 11449), "ita": (23, 11088), "spa": (22, 10644)},
    "weapon": {"eng": (23, 11168), "fre": (23, 11450), "ger": (21, 11392), "ita": (22, 10670), "spa": (21, 10838)},
    "armor": {"eng": (25, 11614), "fre": (24, 11337), "ger": (21, 12005), "ita": (24, 11227), "spa": (22, 11006)},
    "felyne": {"eng": (19, 9501), "fre": (23, 10782), "ger": (20, 10672), "ita": (20, 9447), "spa": (21, 10505)},
}

_ARMOR_STEMS = {"body": "Body", "arms": "Arm", "waist": "Waist", "legs": "Leg", "head": "Head", "talisman": "Acce"}
_WEAPON_STEMS = {
    "great_sword": "Lsword", "sword_and_shield": "Sword", "hammer": "Hammer", "lance": "Lance",
    "light_bowgun": "Light", "heavy_bowgun": "Heavy", "long_sword": "Lsword2", "switch_axe": "Axe",
    "gunlance": "Lance2", "bow": "Bow", "dual_blades": "Wsword", "hunting_horn": "Hammer2", "insect_glaive": "Rod",
    "charge_blade": "Gaxe",
}


def _build_lists() -> dict[str, TextList]:
    lists = {}
    for key, (_, old_names, old_exp) in HUNTER_LISTS.items():
        stem = _ARMOR_STEMS.get(key) or _WEAPON_STEMS[key]
        lists[key] = TextList(key, f"{stem}Name", f"{stem}Exp", old_names, old_exp, True,
                              ARMOR_NAME if key in _ARMOR_STEMS else WEAPON_NAME, 3)
    lists["item"] = TextList("item", "itemName", "itemExp", 1937, 1937, False, ITEM_NAME, 4)
    for key, stem, count in (("felyne_weapon", "OtWeapon", 179), ("felyne_head", "OtHelm", 168),
                             ("felyne_body", "OtArmor", 174)):
        lists[key] = TextList(key, f"{stem}Name", f"{stem}Exp", count, count, False, FELYNE_NAME, 3)
    return lists


LISTS = _build_lists()


def name_kind(key: str) -> str:
    """The kind of `NAME_LIMITS` that the list `key` belongs to."""
    if key == "item":
        return "item"
    return "felyne" if key.startswith("felyne_") else "armor" if key in _ARMOR_STEMS else "weapon"

ARMOR_KEYS = tuple(k for k in _ARMOR_STEMS if k != "talisman")
WEAPON_KEYS = tuple(_WEAPON_STEMS)
FELYNE_KEYS = ("felyne_weapon", "felyne_head", "felyne_body")


def description_message(key: str, piece: int) -> int:
    """The message of the Exp list of `key` that `piece` (a new id) shows; same as
    equipment/new_gear/gear_descriptions'."""
    return LISTS[key].description_message(piece)


# ----- fitting ---------------------------------------------------------------------------------------------------

_LOWER = (556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556,
          500, 722, 500, 500, 500)
_UPPER = (667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722,
          667, 944, 667, 667, 611)
_PUNCT = (278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278)   # " " ... "/"
_ADVANCE = {**dict(zip("abcdefghijklmnopqrstuvwxyz", _LOWER)), **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", _UPPER)),
            **dict(zip(" !\"#$%&'()*+,-./", _PUNCT)), **dict.fromkeys("0123456789", 556),
            **{":": 278, ";": 278, "?": 556, "=": 584, "Œ": 1000, "œ": 944, "ß": 611, "æ": 889, "Æ": 1000,
               "«": 556, "»": 556, "º": 365, "ª": 365, "¿": 611, "¡": 333}}


def name_width(text: str) -> int:
    """The estimated width of `text` in 1/1000 em (Helvetica's advances; an accented letter counts as its base
    letter). Only to compare names with the game's own (`NAME_LIMITS`), not pixels."""
    total = 0
    for char in text:
        base = char if char in _ADVANCE else unicodedata.normalize("NFD", char)[0]
        total += _ADVANCE.get(base, 600)
    return total


def name_fits(kind: str, lang: str, name: str) -> bool:
    """Whether `name` is no longer than the longest name of the game's lists of `kind` ("item", "weapon", "armor" or
    "felyne") in `lang`, in characters and in width."""
    chars, width = NAME_LIMITS[kind][lang]
    name = name.strip()
    return len(name) <= chars and name_width(name) <= width


def fit_name(name: str, limit: int, width: int | None = None, lang: str = "eng") -> str:
    """`name` in `limit` characters (and, with `width`, `name_width` units) in language `lang`: a filler word dropped,
    the monster's name abbreviated, then the longest words cut right after a syllable with a dot (`name_cut`). The rank
    suffix and a "+" (short words) are kept. Cuts the games' own texts made inside a syllable are written in full
    first."""
    def fits(text: str) -> bool:
        return len(text) <= limit and (width is None or name_width(text) <= width)
    return name_cut.fit(name_cut.expand(name.strip(), lang), lang, fits)


def tidy_names(names: Mapping[str, str], kind: str) -> dict[str, str]:
    """`names` ({language: name}) of a piece of `kind` ("item", "weapon", "armor" or "felyne") fitted to the game's box
    in each language (`NAME_LIMITS`): a name that already fits stays."""
    return {lang: fit_name(text, *NAME_LIMITS[kind][lang], lang=lang) if lang in NAME_LIMITS[kind] else text
            for lang, text in names.items()}

def fit_description(text: str, width: int = DESCRIPTION_WIDTH, lines: int = 3) -> str:
    """A description as the game stores it: lines joined with "\\n" (MH Generations' use "\\r\\n"), at most `lines`
    of `width` characters. A text whose lines already fit is kept as it is; otherwise its words are wrapped again.
    Raises NewTextError if it does not fit `lines` lines."""
    kept = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    rows = kept.split("\n")
    if len(rows) <= lines and all(len(row) <= width for row in rows):
        return kept
    words = kept.replace("\n", " ").split()
    wrapped, row = [], ""
    for word in words:
        if row and len(row) + 1 + len(word) > width:
            wrapped.append(row)
            row = word
        else:
            row = f"{row} {word}" if row else word
    if row:
        wrapped.append(row)
    if len(wrapped) > lines or any(len(row) > width for row in wrapped):
        raise NewTextError(f"a description of {len(kept)} characters does not fit {lines} lines of {width}: {kept!r}")
    return "\n".join(wrapped)


# ----- the edits ---------------------------------------------------------------------------------------------------

class CommonTexts(common_texts.CommonTexts):
    """The generic edits of the message files in core_common.arc (`put` for any list of the file: the hunting log's
    `emExp`, whatever stem) with the lists of gear: `name` / `description` / `piece` (`LISTS`, by key: "item", "head"
    ... "legs", the weapon classes of equipment.layout, "felyne_weapon" / "felyne_head" / "felyne_body"). A list the
    executable reads by its count is refused once something appended to it (`check_list`)."""

    def name(self, key: str, piece: int, texts: Texts, *, fit: bool = True) -> None:
        """The name of `piece` of the list `key`, cut to the game's longest name in each language (`NAME_LIMITS`: the
        characters and the width) unless `fit` is off."""
        info = LISTS[key]
        if fit:
            limits = NAME_LIMITS[name_kind(key)]
            texts = {lang: fit_name(text, limits[lang][0], limits[lang][1], lang)
                     for lang, text in complete_texts(texts, f"{key} {piece}").items()}
        self.put(info.name_stem, piece, texts)

    def description(self, key: str, piece: int, texts: Texts) -> None:
        """The description of `piece`, wrapped in the game's lines (fit_description). Hunter gear: only for ids
        past the game's (the game's descriptions are in its arrays)."""
        info = LISTS[key]
        fitted = {lang: fit_description(text, lines=info.max_lines)
                  for lang, text in complete_texts(texts, f"{key} {piece}").items()}
        self.put(info.exp_stem, info.description_message(piece), fitted)

    def piece(self, key: str, piece: int, names: Texts, descriptions: Texts) -> None:
        """Name and description of a new id."""
        self.name(key, piece, names)
        self.description(key, piece, descriptions)

    def check_list(self, stem: str, lang: str, lmd: Lmd) -> None:
        for list_ in LISTS.values():
            if stem == list_.exp_stem and list_.by_array and lmd.message_count != list_.old_exp:
                raise NewTextError(f"{stem}_{lang} has {lmd.message_count} messages, not the game's "
                                   f"{list_.old_exp}: something appended to it already, and the new ids' "
                                   "descriptions would not be where the executable looks")


# ----- names by rank -----------------------------------------------------------------------------------------------

_HIGH_RANK = re.compile(r"(?: S|(?<=[a-zäöüß])S)$")   # " S", or the German compounds' bare "S" ("MizutsuneArmschienS")


def g_rank_name(high_rank_name: str) -> str:
    """MH4U's G rank version of a high rank armor name: MH4U writes " X" where the high rank has " S"
    ("Rathalos Mail S" / "Velociprey Mail X"; the same Latin letter in the five languages). MH Generations' high
    rank names already end in " S"; the compound German names the game shortens carry a bare "S"
    ("MizutsuneBeinschienS" -> "MizutsuneBeinschienX"). A name without the mark gets " X"."""
    name = high_rank_name.strip()
    if _HIGH_RANK.search(name):
        return name[:-1] + "X"
    return f"{name} X"


def rank_names(low: str, high: str | None = None, limit: int = ARMOR_NAME, lang: str = "eng"
               ) -> tuple[str, str, str]:
    """(low rank, high rank, G rank) names of an armor piece, as MH4U names them: low rank without a suffix, high
    rank " S", G rank " X", each cut to `limit` (fit_name). `low` and `high` are MH Generations' names of the piece
    in its low rank and high rank series; without `high` the high rank name is `low` + " S"."""
    high = (high or f"{low} S").strip()
    return (fit_name(low, limit, lang=lang), fit_name(high, limit, lang=lang),
            fit_name(g_rank_name(high), limit, lang=lang))


def _roman(n: int) -> str:
    out = ""
    for value, digits in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out += digits
            n -= value
    return out


def level_names(first: Texts, count: int) -> list[dict[str, str]]:
    """The names of the first `count` weapons of a ported line, the levels of MH Generations' line (the standard of
    ): the line's first name and a Roman numeral, "Poetic Bell I" ...
    "Poetic Bell VI", in every language, each fitted to the game's box (`tidy_names`). The Roman numeral is kept whole
    when the name is cut (`fit_name`)."""
    first = complete_texts(first, "weapon line")
    return [tidy_names({lang: f"{first[lang]} {_roman(n)}" for lang in LANGUAGES}, "weapon")
            for n in range(1, count + 1)]


def g_step_names(steps: Sequence[Texts], best: Texts) -> list[dict[str, str]]:
    """The names of a line's G rank steps, MH Generations Ultimate's own (`steps`: the names of each step in order,
    `best`: the last step's name, the best version of the line). MHGU gives the first two steps of a line one name; the
    second of equal consecutive names gets a "+" in every language (the game's own habit: a step is the previous
    name plus "+"), a third one "++" (Valstrax's Great Sword has three equal steps). Each is fitted to the game's box
    (`tidy_names`)."""
    out, previous, run = [], None, 0
    for n, step in enumerate(steps):
        raw = complete_texts(best if n == len(steps) - 1 else step, "G rank step")
        run = run + 1 if previous == raw else 0
        names = {lang: text + "+" * run for lang, text in raw.items()}
        out.append(tidy_names(names, "weapon"))
        previous = raw
    return out


def line_descriptions(levels: int, g_steps: int, first: Texts, last: Texts) -> list[dict[str, str]]:
    """The description of each weapon of a ported line: the first form's text (`first`: MH Generations' line) for the
    `levels` of MH Generations, the final form's (`last`) for its `g_steps` G rank steps."""
    first, last = complete_texts(first, "line description"), complete_texts(last, "line description")
    return [dict(first) for _ in range(levels)] + [dict(last) for _ in range(g_steps)]
