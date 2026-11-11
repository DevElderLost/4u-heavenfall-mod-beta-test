"""What a relic costs on the Relics screens.

A relic is a look of MH4U whose price record is free (prices.py: no piece wearing it has a recipe; the game gives it as
a relic found on quests) and that the relic rule keeps (layered_rules.relic_trim: each model offered once). The Relics
screens list every relic of the ranks open, for sale; one the hunter has had once is bought already.

The curated table (curated/layered_relics.json) prices each relic one way (`relic_price`), by kind ("armor",
"weapons") and look key:
* `counterparts`: {"armor": {relic key: look key}, "weapons": {...}}, over every other rule: the relic costs exactly
  what the run asks for that look (a look of MH4U or of XX, not a relic; a numbered relic of the same name). When the
  run lacks it (a look of XX without XX's catalog) the relic costs as one of no monster;
* else `monsters`: {"armor": {relic key: monster}, "weapons": {...}}: a monster, a family (a list of monsters), or
  "none" for a relic of no monster or of one in neither game. A relic of a monster costs what the run asks for the
  dearest look of its kind of that monster, or of any of the family (`dearest_look`: armor for armor, a weapon of any
  class for a weapon; MH4U's and XX's looks, with their records' monsters; the highest zenny, then the most material
  units) at the relic's listed rank. When the run has no look of its kind of theirs, their looks of the other kind
  count instead (an armor relic copies a weapon, a weapon relic an armor);
* `rank_gaps`: {"armor": {relic key: {"materials", "zenny"}}, "weapons": {...}}: when those looks have none of the
  relic's rank in the run, the relic costs its entry: up to two materials (each an item the run must have, else
  RelicTableError) and a zenny point of its rank's range of its kind. Never another rank's look: its materials may
  drop above the relic's rank.
A relic of none, of monsters with no look in the run, of a rank gap without an entry or of a counterpart the run lacks
costs its rank's tier (`no_monster_cost`) with its zenny times `no_monster_zenny_factor`.

The tiers: each rank (low, high, G) has its tiers by rarity: from a rarity on, up to two materials (an item id or MH4U
English name, a quantity) and a zenny point of the rank's range of the relic's kind (curated `recipes.zenny`, zenny.py:
0 its minimum, 1 its maximum). A relic takes the last tier its rarity reaches; a rarity below the first tier, or
unknown (a run without the equipment tables), takes the first. A material this game lacks leaves the relic zenny only,
as a look of the price table whose material is missing.
"""

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache

from core.equipment.layered.looks import STATE_WEAPONS, ArmorLook, Looks, WeaponLook
from core.equipment.layered.zenny import ZennyScale
from core.game.data.paths import CURATED_DIR

RELICS_PATH = CURATED_DIR / "layered_relics.json"
RANK_KEYS = ("low", "high", "G")          # ranks 1, 2, 3
TIER_KEYS = frozenset({"from", "materials", "zenny"})
MAX_MATERIALS = 2                         # the materials box shows two rows
RARITIES = range(1, 11)                   # MH4U's equipment rarities (a record's rarity index + 1)
MAX_QUANTITY = 99                         # an item's most in the box
KINDS = ("armor", "weapons")              # the map's kinds: the price table's sections
OTHER_KIND = {"armor": "weapons", "weapons": "armor"}
NO_MONSTER = "none"                       # the map's word for a relic of no monster

Cost = tuple[tuple[tuple[int, int], ...], int]       # (materials: (item, quantity) each, zenny)


class RelicTableError(ValueError):
    pass


@dataclass(frozen=True)
class Tier:
    first: int                                       # the lowest rarity it prices
    materials: tuple[tuple[int | str, int], ...]     # (item id or English name, quantity)
    zenny: float                                     # the point of the rank's range


@dataclass(frozen=True)
class Invented:
    materials: tuple[tuple[int | str, int], ...]     # (item id or English name, quantity)
    zenny: float                                     # the point of the rank's range


@dataclass(frozen=True)
class RelicTable:
    tiers: Mapping[int, tuple[Tier, ...]]            # rank 1-3 -> its tiers, by rarity
    no_monster_zenny_factor: float = 1.0             # a relic of no monster: its tier's zenny times this
    # kind -> relic key -> its monsters (one, a family; none: empty)
    monsters: Mapping[str, Mapping[str, tuple[str, ...]]] = field(default_factory=dict)
    counterparts: Mapping[str, Mapping[str, str]] = field(default_factory=dict)  # kind -> relic key -> look key
    rank_gaps: Mapping[str, Mapping[str, Invented]] = field(default_factory=dict)  # kind -> relic key -> its price

    def owners(self, kind: str, key: str) -> tuple[str, ...]:
        """The monsters whose looks a relic's price copies: one, a family, or none (empty: none, a relic with a
        counterpart, or a look the map does not name)."""
        return self.monsters.get(kind, {}).get(key, ())

    def counterpart(self, kind: str, key: str) -> str | None:
        """The look whose price a relic copies over every other rule, or None."""
        return self.counterparts.get(kind, {}).get(key)

    def rank_gap(self, kind: str, key: str) -> Invented | None:
        """A relic's own price for a run whose looks of its monsters have none of its rank, or None."""
        return self.rank_gaps.get(kind, {}).get(key)


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tier(raw, where: str) -> Tier:
    if not isinstance(raw, dict) or set(raw) != TIER_KEYS:
        raise RelicTableError(f"{where}: a tier is {{\"from\", \"materials\", \"zenny\"}}, got {raw!r}")
    first, materials, zenny = raw["from"], raw["materials"], raw["zenny"]
    if type(first) is not int or first not in RARITIES:
        raise RelicTableError(f"{where}: from {first!r}, a rarity {RARITIES.start}-{RARITIES.stop - 1}")
    if not isinstance(materials, list) or len(materials) > MAX_MATERIALS:
        raise RelicTableError(f"{where}: at most {MAX_MATERIALS} materials")
    for entry in materials:
        if not _material(entry):
            raise RelicTableError(f"{where}: a material is [item, quantity 1-{MAX_QUANTITY}], got {entry!r}")
    if not _point(zenny):
        raise RelicTableError(f"{where}: zenny {zenny!r}, a point of the rank's range from 0 to 1")
    return Tier(first, tuple((ref, quantity) for ref, quantity in materials), float(zenny))


def _material(entry) -> bool:
    """[item id or English name, quantity 1-MAX_QUANTITY]."""
    return isinstance(entry, list) and len(entry) == 2 and type(entry[1]) is int and 1 <= entry[1] <= MAX_QUANTITY \
        and ((type(entry[0]) is int and entry[0] > 0) or (isinstance(entry[0], str) and bool(entry[0].strip())))


def _point(zenny) -> bool:
    return _number(zenny) and 0 <= zenny <= 1


def _invented(value) -> Invented | None:
    """A rank gap's price: {"materials": one or two materials, "zenny": a point}; None when it is not one."""
    if not isinstance(value, Mapping) or set(value) != {"materials", "zenny"} or not _point(value["zenny"]) \
            or not isinstance(value["materials"], list) or not 1 <= len(value["materials"]) <= MAX_MATERIALS \
            or not all(_material(entry) for entry in value["materials"]):
        return None
    return Invented(tuple((ref, quantity) for ref, quantity in value["materials"]), float(value["zenny"]))


def price_monsters(prices: Mapping) -> frozenset[str]:
    """The monsters the price table gives a look that is not a relic: MH4U's records (but the free ones) and XX's."""
    names = set()
    for kind in KINDS:
        for table in (prices.get(kind, {}), prices.get("xx", {}).get(kind, {})):
            names |= {record["monster"] for record in table.values()
                      if isinstance(record, Mapping) and record.get("monster") and record.get("rule") != "free"}
    return frozenset(names)


def _name(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _owners(value) -> tuple[str, ...] | None:
    """A map entry's monsters: a monster, a family (a list of two or more, none of them "none") or "none" (empty);
    None when it is none of these."""
    if _name(value):
        return () if value == NO_MONSTER else (value,)
    if isinstance(value, list) and len(value) >= 2 and all(_name(name) and name != NO_MONSTER for name in value) \
            and len(set(value)) == len(value):
        return tuple(value)
    return None


def _section(raw, name: str, entry: Callable, what: str) -> dict[str, dict]:
    """A section of both kinds, each look key -> `entry(value)` (None: a bad entry)."""
    if not isinstance(raw, Mapping) or set(raw) != set(KINDS):
        raise RelicTableError(f"layered_relics {name}: {', '.join(KINDS)}, each look key -> {what}")
    out: dict[str, dict] = {}
    for kind in KINDS:
        if not isinstance(raw[kind], Mapping):
            raise RelicTableError(f"layered_relics {name}.{kind}: each look key -> {what}")
        out[kind] = {}
        for key, value in raw[kind].items():
            parsed = entry(value) if isinstance(key, str) else None
            if parsed is None:
                raise RelicTableError(f"layered_relics {name}.{kind}.{key}: {value!r}, not {what}")
            out[kind][key] = parsed
    return out


def _check_map(raw_monsters, raw_counterparts, raw_gaps, prices: Mapping) -> list[str]:
    """What the price table finds wrong with the map: each free look of the price table in exactly one section, each
    monster a monster of its records (`price_monsters`), each counterpart a look of its kind of MH4U (not a relic) or
    of XX, each rank gap's price a relic's of a monster (another is never read)."""
    known = price_monsters(prices)
    problems = []
    for kind in KINDS:
        table, xx = prices.get(kind, {}), prices.get("xx", {}).get(kind, {})
        free = {key for key, record in table.items() if _free(record)}
        monsters, counterparts = raw_monsters[kind], raw_counterparts[kind]
        problems += [f"{kind} {key}: a rank gap's price for a relic of no monster" for key in sorted(raw_gaps[kind])
                     if monsters.get(key, NO_MONSTER) == NO_MONSTER]
        named = set(monsters) | set(counterparts)
        problems += [f"{kind} {key}: not a relic" for key in sorted(named - free)]
        problems += [f"{kind} {key}: a relic the map lacks" for key in sorted(free - named)]
        problems += [f"{kind} {key}: a monster and a counterpart (one or the other)"
                     for key in sorted(set(monsters) & set(counterparts))]
        problems += [f"{kind} {key}: no look names the monster {name!r}" for key, value in sorted(monsters.items())
                     for name in ([value] if isinstance(value, str) else value) if name not in known | {NO_MONSTER}]
        for key, look in sorted(counterparts.items()):
            if look in table and _free(table[look]):
                problems.append(f"{kind} {key}: its counterpart {look} is a relic")
            elif look not in table and look not in xx:
                problems.append(f"{kind} {key}: its counterpart {look} is in neither price table")
    return problems


def _free(record) -> bool:
    return isinstance(record, Mapping) and record.get("rule") == "free"


def parse_relic_table(raw: Mapping, prices: Mapping | None = None) -> RelicTable:
    """The curated table checked: every rank (RANK_KEYS) with one tier or more, in rising rarity; a factor above 0; the
    map of the relics' monsters, counterparts and rank gaps' prices (with `prices`, the price table, checked against
    its looks and monsters: `_check_map`)."""
    ranks = raw.get("ranks") if isinstance(raw, Mapping) else None
    if not isinstance(ranks, Mapping) or set(ranks) != set(RANK_KEYS):
        raise RelicTableError(f"layered_relics: the ranks are {', '.join(RANK_KEYS)}")
    tiers: dict[int, tuple[Tier, ...]] = {}
    for rank, key in enumerate(RANK_KEYS, 1):
        listed = ranks[key]
        if not isinstance(listed, list) or not listed:
            raise RelicTableError(f"layered_relics {key}: one tier or more")
        parsed = tuple(_tier(raw_tier, f"layered_relics {key}[{i}]") for i, raw_tier in enumerate(listed))
        if any(a.first >= b.first for a, b in zip(parsed, parsed[1:])):
            raise RelicTableError(f"layered_relics {key}: the tiers in rising rarity")
        tiers[rank] = parsed
    factor = raw.get("no_monster_zenny_factor")
    if not _number(factor) or factor <= 0:
        raise RelicTableError(f"layered_relics no_monster_zenny_factor: {factor!r}, a number above 0")
    monsters = _section(raw.get("monsters"), "monsters", _owners,
                        "a monster, a family (a list of monsters) or \"none\"")
    counterparts = _section(raw.get("counterparts"), "counterparts", lambda value: value if _name(value) else None,
                            "a look key")
    rank_gaps = _section(raw.get("rank_gaps"), "rank_gaps", _invented,
                         "{\"materials\": one or two [item, quantity], \"zenny\": a point from 0 to 1}")
    if prices is not None:
        problems = _check_map(raw["monsters"], raw["counterparts"], raw["rank_gaps"], prices)
        if problems:
            raise RelicTableError("layered_relics map: " + "; ".join(problems))
    return RelicTable(tiers, float(factor), monsters, counterparts, rank_gaps)


@cache
def load_relic_table() -> RelicTable:
    """The curated table, its map checked against the generated price table."""
    from core.equipment.layered.prices import load_prices
    return parse_relic_table(json.loads(RELICS_PATH.read_text(encoding="utf-8")), load_prices())


def relic_cost(table: RelicTable, scale: ZennyScale, kind: str, rank: int, rarity: int | None,
               resolve: Callable[[int | str], int | None]) -> Cost:
    """(materials, zenny) of the tier of a relic of `kind` ("armor", "weapons") listed under `rank` (1-3), of `rarity`
    (None: unknown). `resolve`: an item reference to its id in this game, or None."""
    tiers = table.tiers[rank]
    tier = tiers[0]
    for candidate in tiers:
        if rarity is not None and rarity >= candidate.first:
            tier = candidate
    resolved = [(resolve(ref), quantity) for ref, quantity in tier.materials]
    materials = tuple((item, quantity) for item, quantity in resolved if item) \
        if all(item for item, _ in resolved) else ()
    return materials, scale.point(kind, rank, tier.zenny)


def no_monster_cost(table: RelicTable, scale: ZennyScale, kind: str, rank: int, rarity: int | None,
                    resolve: Callable[[int | str], int | None]) -> Cost:
    """What a relic of no monster costs (or of one with no look in the run, `relic_price`): its tier's materials
    (`relic_cost`), its zenny times the table's `no_monster_zenny_factor`."""
    materials, zenny = relic_cost(table, scale, kind, rank, rarity, resolve)
    return materials, round(zenny * table.no_monster_zenny_factor)


def dearest_look(looks: Iterable[tuple[int, Cost]], rank: int) -> Cost | None:
    """What a relic of a monster listed under `rank` costs: the dearest of his looks (`looks`: (listed rank, cost)
    each, as the run prices them, from both catalogs) of that rank, never another rank's (its materials may not drop
    there yet). The dearest: the highest zenny, then the most material units; between equals, the first. None when he
    has none of that rank."""
    found = [cost for listed, cost in looks if listed == rank]
    return max(found, key=lambda cost: (cost[1], sum(quantity for _, quantity in cost[0]))) if found else None


def invented_cost(table: RelicTable, scale: ZennyScale, kind: str, key: str, rank: int,
                  resolve: Callable[[int | str], int | None]) -> Cost:
    """A relic's rank gap price (`RelicTable.rank_gap`): its materials, each an item this run must have, and its
    point of the range of its kind and `rank`."""
    invented = table.rank_gaps[kind][key]
    materials = []
    for ref, quantity in invented.materials:
        item = resolve(ref)
        if not item:
            raise RelicTableError(f"layered_relics rank_gaps.{kind}.{key}: {ref!r} is no item of this run")
        materials.append((item, quantity))
    return tuple(materials), scale.point(kind, rank, invented.zenny)


def relic_price(table: RelicTable, scale: ZennyScale, kind: str, key: str, rank: int,
                looks: Mapping[str, Mapping[str, Iterable[tuple[int, Cost]]]], final_cost: Callable[[str], Cost | None],
                resolve: Callable[[int | str], int | None]) -> Cost | None:
    """What the relic of `kind` and look `key`, listed under `rank`, costs; None when it costs as one of no monster
    (`no_monster_cost`). `looks`: kind -> monster -> his looks of that kind in the run, (listed rank, cost) each;
    `final_cost`: a look key to what the run asks for it, None when the run lacks it; `resolve`: an item reference to
    its id in this run, or None.
    1. Its counterpart, over every other rule: that look's cost (one the run lacks: none).
    2. Its monster's, or any of its family's, looks of its kind; 3. when the run has none of them, their looks of the
       other kind (an armor relic their weapons, a weapon relic their armor); none at all: none.
    4. The dearest of those looks of its rank (`dearest_look`); when they have none of its rank, its own price for the
       gap (`invented_cost`); without one, none."""
    counterpart = table.counterpart(kind, key)
    if counterpart is not None:
        return final_cost(counterpart)
    owners, theirs = table.owners(kind, key), []
    for of_kind in (kind, OTHER_KIND[kind]):
        theirs = [look for name in owners for look in looks.get(of_kind, {}).get(name, ())]
        if theirs:
            break
    found = dearest_look(theirs, rank)
    if found is None and theirs and table.rank_gap(kind, key) is not None:
        return invented_cost(table, scale, kind, key, rank, resolve)
    return found


def relic_keys(looks: Looks, prices: Mapping, relics) -> frozenset[str]:
    """The keys of the relics (armor and weapon looks of MH4U) the Relics screens list: the free looks of the price
    table but those the relic rule drops (`relics`: layered_rules.Relics; a trimmed one stays)."""
    armor = {look.key for look in looks.armor if prices["armor"].get(look.key, {}).get("rule") == "free"}
    weapons = {look.key for key in STATE_WEAPONS for look in looks.weapons[key]
               if prices["weapons"].get(look.key, {}).get("rule") == "free"}
    return frozenset((armor - set(relics.dropped_armor)) | (weapons - set(relics.dropped_weapons)))


def relic_rarity(look: ArmorLook | WeaponLook, tables, weapon_class: str | None = None) -> int | None:
    """A relic's rarity in the run's equipment tables (`tables`; None: unknown): an armor look's is the highest of the
    pieces naming its parts, a weapon look's (`weapon_class` its class) the weapon naming it. None when the tables have
    none of its records."""
    if tables is None:
        return None
    if weapon_class is None:
        records = [_record(tables.armor[part], pieces[0]) for part, pieces in look.pieces.items() if pieces]
    else:
        records = [_record(tables.weapons[weapon_class], look.weapon)]
    rarities = [record["rarity_index"] + 1 for record in records if record is not None]
    return max(rarities) if rarities else None


def _record(records, index: int):
    return records[index] if 0 <= index < len(records) else None
