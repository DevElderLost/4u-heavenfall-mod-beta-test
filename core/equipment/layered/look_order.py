"""The order of the forge-style screens' lists.

Every list (armor, each weapon class, the Felyne rows) goes by the monster of its looks: first the looks of no monster,
then those of small monsters, then those of large monsters, each kind in the curated `monster_order` of
`layered_looks.json` (least to most powerful; a monster not in it takes its base's place, through `material_parent`).
Inside one monster: rank, then game (MH4U's first), then the real gear's original forge price (cheapest first), then the
catalogs' order. So rank All keeps a monster's looks together, low then high then G, and game All mixes both games'
looks by monster.

A look's monster, in this order:

1. the curated `monster_of` (`armor`, `weapons`, `felyne`: look key, or a Felyne row's model number -> a monster or
   "none");
2. its price record's `monster` (prices.py, xx_prices.py: the materials' family, or the XX set's monster);
3. its English name: a monster's whole name in it as words (the longest; Silver Rathalos before Rathalos), or a phrase
   of the curated words (the price table's `xx.words` and `monster_words`: "rath soul" is Rathalos', "narga"
   Nargacuga's);
4. else none.

A MH4U weapon's line family (`monster:N`, randomizer/equipment/models.weapon_families) is not used: where it is right
the price record has it already (prices.py, rule 2), and the rest give a line's first monster to the weapons of others
(Plesioth Watercutter to Tetsucabra, Arzuros Gun to Great Jaggi).

The block layered_rules holds one array of u16 per list (layered_rules.py): positions in the catalogs (an armor or
weapon look of XX after all of MH4U's: the screens' `look_at`) in that order; bit 15 (`ORDER_EVERY`) lists the look
under every rank and game filter: "Nothing" (looks.NOTHING_KEY), the first armor row, which puts the game's underwear
on every part; bit 14 (`ORDER_RELIC`, set by layered_rules.py) puts a relic of MH4U on the Relics screens and off the
others.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache, cached_property

from core.equipment.layered.looks import NOTHING_KEY, STATE_WEAPONS
from core.game.data.paths import CURATED_DIR, GENERATED_DIR

ORDER_EVERY = 0x8000               # an order entry listed under every rank and game (layered_forge.c, scan_rows)
ORDER_RELIC = 0x4000               # an order entry of the Relics screens only (layered_forge.c, on_screen)
ORDER_POSITION = 0x3FFF
NO_MONSTER, SMALL, LARGE = 0, 1, 2  # the three parts of a list, in order
SECTIONS = ("armor", "weapons", "felyne")   # curated monster_of's sections, as recipes'
GAME_MH4U = 0
NONE = "none"


class LookOrderError(ValueError):
    pass


@dataclass(frozen=True)
class MonsterOrder:
    """The curated order of the monsters (least to most powerful) and the bases of the variants (monster -> its
    `material_parent`)."""
    small: tuple[str, ...]
    large: tuple[str, ...]
    parents: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        names = (*self.small, *self.large)
        doubled = sorted({name for name in names if names.count(name) > 1})
        if doubled:
            raise LookOrderError(f"monster_order names {', '.join(doubled)} twice")

    def listed(self, monster: str) -> bool:
        return monster in self.small or monster in self.large

    def place(self, monster: str | None) -> tuple[int, int]:
        """(NO_MONSTER, 0), (SMALL, index) or (LARGE, index): where the looks of `monster` go. A monster not listed
        takes its base's place; one with neither goes after every large monster (tests/equipment/layered/
        test_look_order.py keeps every monster a look names in the list)."""
        if monster is None:
            return NO_MONSTER, 0
        seen = set()
        current = monster
        while current not in seen:
            seen.add(current)
            if current in self.small:
                return SMALL, self.small.index(current)
            if current in self.large:
                return LARGE, self.large.index(current)
            if current not in self.parents:
                break
            current = self.parents[current]
        return LARGE, len(self.large)


@dataclass(frozen=True)
class Namer:
    """What gives a look with no price record its monster: `phrases` (lowercase words -> monster: the monsters' own
    names and the curated words)."""
    phrases: Mapping[str, str]

    @cached_property
    def _patterns(self) -> tuple:
        """(compiled whole-word pattern, phrase length, monster) of each phrase, built once: `re`'s own cache holds 512
        patterns, fewer than the phrases, so compiling at each look recompiled them all."""
        return tuple((re.compile(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", re.IGNORECASE), len(phrase), monster)
                     for phrase, monster in self.phrases.items())

    def by_name(self, names: Iterable[str]) -> str | None:
        """The monster of the longest phrase found as whole words in any of `names`; two monsters at that length:
        none."""
        found: dict[str, int] = {}
        for name in names:
            for pattern, length, monster in self._patterns:
                if pattern.search(name):
                    found[monster] = max(found.get(monster, 0), length)
        if not found:
            return None
        longest = max(found.values())
        best = [monster for monster, length in found.items() if length == longest]
        return best[0] if len(best) == 1 else None


@dataclass(frozen=True)
class LookFacts:
    """What orders one look of a list: `where` its place (section, catalog, class index, position in its catalog),
    `key` its curated key, `names` its English names, `record` its price record, its listed `rank` (1-3), `game`
    (0 MH4U, 1 XX) and original forge `price`."""
    where: tuple[str, int, int, int]
    key: str
    names: tuple[str, ...] = ()
    record: Mapping | None = None
    rank: int = 1
    game: int = GAME_MH4U
    price: int = 0


def look_monster(facts: LookFacts, overrides: Mapping[str, Mapping[str, str]], namer: Namer) -> str | None:
    """The monster of a look (the module's rules 1-4), None for none."""
    curated = overrides.get(facts.where[0], {}).get(facts.key)
    if curated is not None:
        return None if curated == NONE else curated
    record = facts.record or {}
    if record.get("monster"):
        return record["monster"]
    return namer.by_name(facts.names)


def order_key(facts: LookFacts, monster: str | None, order: MonsterOrder) -> tuple:
    """Monster's place, rank, game, original price, then the catalogs' order."""
    return (*order.place(monster), facts.rank, facts.game, facts.price, facts.where[1], facts.where[3])


def sorted_looks(looks: Iterable[LookFacts], overrides: Mapping[str, Mapping[str, str]], namer: Namer,
                 order: MonsterOrder) -> list[LookFacts]:
    """`looks` (one list's) in the screens' order, "Nothing" first."""
    keyed = [((facts.key != NOTHING_KEY, order_key(facts, look_monster(facts, overrides, namer), order)), facts)
             for facts in looks]
    return [facts for _, facts in sorted(keyed, key=lambda pair: pair[0])]


def order_entries(looks: Sequence[LookFacts], first_of_catalog: Sequence[int]) -> list[int]:
    """The u16 entries of an order array: the position over both catalogs (`first_of_catalog`: where each catalog
    starts), "Nothing" with ORDER_EVERY."""
    out = []
    for facts in looks:
        position = first_of_catalog[facts.where[1]] + facts.where[3]
        if position > ORDER_POSITION:
            raise LookOrderError(f"a list of {position + 1} looks does not fit an order entry")
        out.append(position | (ORDER_EVERY if facts.key == NOTHING_KEY else 0))
    return out


# ----- the data ----------------------------------------------------------------------------------------------------

def _read(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def monster_parents() -> dict[str, str]:
    """Every monster of curated/monster_rules.json with a `material_parent` -> that parent's name; none where the file
    is left out (Heavenfall Beta has no randomizer: every monster a look names is listed anyway)."""
    path = CURATED_DIR / "monster_rules.json"
    if not path.is_file():
        return {}
    monsters = _read(path)["monsters"]
    return {m["name"]: monsters[str(m["material_parent"])]["name"] for m in monsters.values()
            if str(m.get("material_parent")) in monsters}


def monster_order(curated: Mapping) -> MonsterOrder:
    """The curated `monster_order` of layered_looks.json."""
    raw = curated.get("monster_order")
    if not isinstance(raw, Mapping) or set(raw) != {"small", "large"}:
        raise LookOrderError('layered_looks.json monster_order is {"small": [...], "large": [...]}')
    return MonsterOrder(tuple(raw["small"]), tuple(raw["large"]), monster_parents())


def monster_overrides(curated: Mapping) -> dict[str, dict[str, str]]:
    """The curated `monster_of`, by section."""
    raw = curated.get("monster_of", {})
    if set(raw) - set(SECTIONS):
        raise LookOrderError(f"layered_looks.json monster_of has the sections {', '.join(SECTIONS)}")
    return {section: {str(key): value for key, value in raw.get(section, {}).items()} for section in SECTIONS}


@cache
def english_names() -> dict:
    """generated/equipment_names.json: MH4U's weapon names by class and the Felyne pieces' by part, by id."""
    return _read(GENERATED_DIR / "equipment_names.json")


def word_phrases(curated: Mapping) -> dict[str, str]:
    """The curated words naming a monster: the price table's `xx.words`, then `monster_words`."""
    from core.equipment.layered.prices import load_curated_prices
    return {**load_curated_prices()["xx"]["words"], **curated.get("monster_words", {})}


def namer(curated: Mapping, order: MonsterOrder) -> Namer:
    """The names of the listed monsters and the curated words (word_phrases)."""
    phrases = {name.lower(): name for name in (*order.small, *order.large)}
    phrases.update(word_phrases(curated))
    return Namer(phrases)


# ----- a run's lists -----------------------------------------------------------------------------------------------

@dataclass
class ListFacts:
    """The facts of every look of a run, list by list: the armor looks (MH4U's, then XX's), each class' weapons
    (STATE_WEAPONS; MH4U's, then XX's) and the Felyne rows."""
    armor: list[LookFacts]
    weapons: list[list[LookFacts]]
    felyne: list[LookFacts]


def _english(table: Sequence[str], index: int) -> tuple[str, ...]:
    return (table[index],) if 0 <= index < len(table) else ()


def _named(names: Mapping[str, str]) -> tuple[str, ...]:
    return (names["eng"],) if names.get("eng") else ()


def list_facts(looks, gen, rows: Sequence, prices: Mapping, shown: Mapping[str, int], original) -> ListFacts:
    """The facts of `looks` (looks.Looks), `gen` (XX's GenLooks or None) and `rows` (felyne_looks.felyne_rows).
    `prices`: the price table; `shown`: prices.shown_ranks; `original(section, catalog, class index, position)`: the
    real gear's forge price (layered_rules._originals)."""
    names = english_names()
    xx = prices.get("xx", {})

    def rank(look) -> int:
        return max(look.rank, shown.get(look.key, 0))

    armor = [LookFacts(("armor", 0, 0, i), look.key, (look.group,), prices["armor"].get(look.key), rank(look), 0,
                       original("armor", 0, 0, i)) for i, look in enumerate(looks.armor)]
    armor += [LookFacts(("armor", 1, 0, i), s.look.key, (s.look.group,), xx.get("armor", {}).get(s.look.key),
                        rank(s.look), 1, original("armor", 1, 0, i)) for i, s in enumerate(gen.sets if gen else ())]
    weapons = []
    for c, key in enumerate(STATE_WEAPONS):
        by_class = [LookFacts(("weapons", 0, c, i), look.key,
                              _english(names["weapons"][key], look.weapon) or _named(look.names),
                              prices["weapons"].get(look.key), rank(look), 0, original("weapons", 0, c, i))
                    for i, look in enumerate(looks.weapons[key])]
        by_class += [LookFacts(("weapons", 1, c, i), look.key, _named(look.names), xx.get("weapons", {}).get(look.key),
                               rank(look), 1, original("weapons", 1, c, i))
                     for i, look in enumerate(gen.weapons[key] if gen else ())]
        weapons.append(by_class)
    felyne = []
    for i, row in enumerate(rows):
        if row.game == GAME_MH4U:
            # named as the screens name it (texts.felyne_row_labels): by its armor, else by its weapon
            parts = [part for part in ("head", "body") if part in row.pieces] or list(row.pieces)
            english = tuple(name for part in parts for name in _english(names["palico"][part], row.pieces[part]))
            record = prices.get("felyne", {}).get(str(row.number))
        else:
            english, record = _named(row.names), None
        felyne.append(LookFacts(("felyne", 0, 0, i), str(row.number), english, record, row.rank, row.game,
                                original("felyne", 0, 0, i)))
    return ListFacts(armor, weapons, felyne)


@dataclass
class Orders:
    """The order arrays' entries (order_entries) of a run."""
    armor: list[int]
    weapons: list[list[int]]
    felyne: list[int]


def run_orders(facts: ListFacts, curated: Mapping) -> Orders:
    """The screens' order of every list of `facts`, by the curated `monster_order`, `monster_of` and words."""
    order = monster_order(curated)
    overrides = monster_overrides(curated)
    found = namer(curated, order)

    def entries(looks: list[LookFacts]) -> list[int]:
        return order_entries(sorted_looks(looks, overrides, found, order),
                             (0, sum(1 for facts in looks if facts.where[1] == 0)))

    return Orders(entries(facts.armor), [entries(by_class) for by_class in facts.weapons], entries(facts.felyne))
