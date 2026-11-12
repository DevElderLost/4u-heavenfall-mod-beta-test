"""What a look of MH4U costs in materials on the forge-style screens.

One record per armor look, weapon look and Felyne model, in game/data/generated/layered_prices.json, built from the
clean executable's tables (tools/build/build_layered_prices.py). Every number the rules use (how many materials, how
many units) and the cases a rule cannot decide are curated (curated/layered_prices.json).

* A look no piece of which has a recipe is **free** here (a relic: the Relics screens price it, relic_prices.py).
* A look belongs to **one monster**, a variant or a base, never a family: a Zinogre look never asks what only Stygian
  Zinogre drops. It costs **1 unit of that monster's hardest material** at the look's rank: an item of the monster's
  own drop lists at the rank that few monsters drop (the item's families, the monster's own included, are at most
  `max_families`, and no gathering spot gives it) that belongs to the rank (its home rank is the first rank whose lists
  of the monster hold it) with the lowest best chance in the monster's lists at that rank (ties: the rarest item, then
  the lowest id). When that chance is above the curated `rare_percent`, or the monster has no item of that home rank,
  the lowest chance among all its usable items that drop at the rank, wherever their home is. A variant may ask what
  its base drops too, when it drops it itself.
* A look of MH XX of a monster MH4U has costs 1 unit of the same material, at the look's rank or else the next ranks'
  (xx_prices.py); a variant or deviant MH4U lacks asks its base's. It is offered when the monster's MH4U looks of that
  rank are. The ported monsters' looks ask their own items (ported_prices.py).
* Any other look, and a monster's look that has no usable material at that rank, costs the first materials of its
  normal recipe, each capped at a few units.
* A Felyne model costs the first materials of the recipe of its piece of lowest rarity.

Which monster a look belongs to: first the family with the most units of exclusive materials (items only that family
drops) in the recipes of the look's pieces of its rank, when they make at least `min_share` of the recipes' units (a
set that borrows a material or two from a monster is not that monster's); for a weapon its group's monster
(`monster:N`, randomizer/equipment/models.py) is preferred when its family reaches that share (a group is scored on
shared materials such as Iron Ore, and sends the Iron Striker to Gypceros). Then, inside the family, the member whose
own drops hold most of those units; a tie goes to the base.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache, cached_property
from typing import TYPE_CHECKING

from core.equipment.layered.looks import NAME_PARTS, build_armor_looks, build_weapon_looks, game_pieces, with_forge
from core.equipment.tables.layout import PALICO_TABLES
from core.game.data.paths import CURATED_DIR, GENERATED_DIR
from core.randomizer.equipment.catalog import Catalog, Piece, build_catalog

if TYPE_CHECKING:
    from core.equipment.layered.ported_prices import PortedMonster

PRICES_PATH = GENERATED_DIR / "layered_prices.json"
CURATED_PRICES_PATH = CURATED_DIR / "layered_prices.json"
DROPS_PATH = GENERATED_DIR / "monster_drops.json"
ITEM_MONSTERS_PATH = GENERATED_DIR / "item_monsters.json"
ITEM_DROPS_PATH = GENERATED_DIR / "item_drops.json"
WYPORIUM_TRADES_PATH = GENERATED_DIR / "wyporium_trades.json"
RANK_NAMES = ("low", "high", "g")           # the drop lists' ranks, and the looks' ranks 1-3
PALICO_KINDS = ("head", "body", "weapon")   # the Felyne piece that decides a model, at equal rarity


@dataclass
class Families:
    """The large monsters grouped in families, and who drops what."""
    root: dict[int, int]                              # monster id -> its family's id (the monster at the top)
    name: dict[int, str]                              # family id -> name
    droppers: dict[int, set[int]]                     # item -> large monsters whose lists have it (executable)
    own: dict[int, dict[int, dict[int, int]]]         # monster -> rank index -> item -> best percent (executable)
    elsewhere: dict[int, set[str]]                    # item -> Kiranico monster names that are not a large monster
    kiranico: dict[int, set[int]] = field(default_factory=dict)   # item -> family ids Kiranico lists
    unmatched: set[str] = field(default_factory=set)  # Kiranico names that are no monster of ours
    gathered: set[int] = field(default_factory=set)   # items a map gives too (a mining spot...)
    rarity: dict[int, int] = field(default_factory=dict)   # item -> rarity (the tie-break of "hardest")
    names: dict[int, str] = field(default_factory=dict)    # large monster id -> name
    not_asked: dict[int, set[int]] = field(default_factory=dict)   # monster -> items its looks never ask (curated)
    unheld: set[int] = field(default_factory=set)     # items a player never holds (curated `unobtainable` categories)
    traded: dict[int, tuple[int, int]] = field(default_factory=dict)   # Wyporium item -> (item its trade takes, rank)
    sourced: dict[int, int] = field(default_factory=dict)   # item -> its first rank by curated item_sources.json

    def exclusive(self, item: int, family: int) -> bool:
        """Only `family` drops `item`: no other large monster in the executable's lists, none (of any size) on
        Kiranico's page for it, and no gathering spot."""
        if item in self.gathered:
            return False
        mine = {self.root[m] for m in self.droppers.get(item, ()) if m in self.root}
        if mine != {family}:
            return False
        return not (self.kiranico.get(item, set()) - {family}) and not self.elsewhere.get(item)

    def families_of(self, item: int) -> set[int]:
        """The families that drop `item`: the executable's lists and Kiranico's pages."""
        return {self.root[m] for m in self.droppers.get(item, ()) if m in self.root} | self.kiranico.get(item, set())

    def shared_ok(self, item: int, family: int, max_families: int) -> bool:
        """`item` may be asked of a monster of `family`: at most `max_families` families drop it (its own and one other
        at 2), no monster that is not a large one of ours (any size, Guild Quest ones too) and no gathering spot."""
        if item in self.gathered or self.elsewhere.get(item):
            return False
        found = self.families_of(item)
        return family in found and len(found) <= max_families

    @cached_property
    def _first_ranks(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for lists in self.own.values():
            for rank, items in lists.items():
                for item in items:
                    out[item] = min(out.get(item, 3), rank + 1)
        return out

    def first_rank(self, item: int) -> int | None:
        """The first rank (1-3) any large monster's own lists hold `item` at, the rank it belongs to (a Wyporium item:
        the rank of the quest that opens its trade); None when neither says (a gathered item, a small monster's, a
        shop's) and no curated source (`sourced`: quests, small monsters) says."""
        found = self._first_ranks.get(item)
        if found is None:
            found = self.traded[item][1] if item in self.traded else self.sourced.get(item)
        return found

    def best_chance(self, item: int, rank: int) -> int | None:
        """The best chance (percent) of `item` in any large monster's own lists at `rank` (1-3), else at its first
        rank; None when no large monster drops it."""
        for at in (rank, self._first_ranks.get(item)):
            found = [lists.get(at - 1, {}).get(item) for lists in self.own.values()] if at else []
            found = [percent for percent in found if percent]
            if found:
                return max(found)
        return None

    def usable_at(self, monster: int, rank: int, max_families: int) -> dict[int, int]:
        """The items of the monster's own lists at `rank` (1-3) it may ask -> their best chance there: none it is
        curated never to ask (`not_asked`), none a player never holds (`unheld`: an account item)."""
        barred = self.not_asked.get(monster, set()) | self.unheld
        return {item: percent for item, percent in self.own.get(monster, {}).get(rank - 1, {}).items()
                if item not in barred and self.shared_ok(item, self.root[monster], max_families)}


def monster_families(data, drops: dict, item_monsters: dict | None, aliases: dict[str, str],
                     item_drops: dict | None = None, not_asked: Mapping[str, Iterable[str]] | None = None,
                     unobtainable: Iterable[str] = (), trades: Mapping | None = None,
                     item_sources: Mapping | None = None) -> Families:
    """The families of the large monsters of `data` (GameData) with their drop lists `drops` (monster_drops.json) and
    what Kiranico says (`item_monsters`: item_monsters.json; None = nothing to check against). `aliases`: Kiranico's
    monster name -> ours, for the names that differ. `item_drops`: item_drops.json, for the items a map gives.
    `not_asked`: curated, a large monster's name -> the names of the items its looks never ask (ValueError on a name
    that is no large monster or no item). `unobtainable`: curated item categories a player never holds (an account
    item is sold at the quest's end): their items are never asked. `trades`: wyporium_trades.json's "trades" (a
    Wyporium item's id -> the item its trade takes, the trade's rank). `item_sources`: curated/item_sources.json's
    "items": the first rank of an item no large monster's list holds (a quest reward, a small monster's carve)."""
    large = {m.monster_id for m in data.monsters.values() if m.is_large}
    root: dict[int, int] = {}
    for monster_id in large:
        seen, current = {monster_id}, monster_id
        while data.monsters[current].material_parent in large and data.monsters[current].material_parent not in seen:
            current = data.monsters[current].material_parent
            seen.add(current)
        root[monster_id] = current
    droppers: dict[int, set[int]] = defaultdict(set)
    own: dict[int, dict[int, dict[int, int]]] = defaultdict(lambda: defaultdict(dict))
    for key, record in drops.items():
        monster_id = int(key)
        if monster_id not in root:
            continue
        for slot in record["slots"]:
            for rank, rows in enumerate(slot["ranks"]):
                for item, percent, _ in rows:
                    droppers[item].add(monster_id)
                    best = own[monster_id][rank]
                    best[item] = max(best.get(item, 0), percent)
    families = Families(root, {r: data.monsters[r].name for r in set(root.values())}, droppers, own, {})
    families.names = {m: data.monsters[m].name for m in large}
    families.rarity = {i: info.rarity or 0 for i, info in getattr(data, "items", {}).items()}
    barred = set(unobtainable)
    families.unheld = {i for i, info in getattr(data, "items", {}).items()
                       if barred and info.category.value in barred}
    families.gathered = {int(item) for item, record in (item_drops or {}).items() if record["by_source"]["maps"]}
    families.traded = {int(item): (trade["give"], trade["rank"]) for item, trade in (trades or {}).items()}
    families.sourced = {int(item): min(source["rank"] for source in record["sources"])
                        for item, record in (item_sources or {}).items() if record["sources"]}
    by_name = {data.monsters[m].name.lower(): m for m in large}
    items_named: dict[str, set[int]] = defaultdict(set)
    for item, info in getattr(data, "items", {}).items():
        items_named[info.name].add(item)
    for name, barred in (not_asked or {}).items():
        if name.lower() not in by_name:
            raise ValueError(f"not_asked: {name!r} is no large monster")
        for item_name in barred:
            if item_name not in items_named:
                raise ValueError(f"not_asked.{name}: {item_name!r} is no item")
            families.not_asked.setdefault(by_name[name.lower()], set()).update(items_named[item_name])
    for item, record in (item_monsters or {}).items():
        for source in (record["monsters"] or []) + (record["guild"] or []):
            name = aliases.get(source[0], source[0])
            monster = by_name.get(name.lower())
            if monster is None:
                families.unmatched.add(source[0])
                families.elsewhere.setdefault(int(item), set()).add(source[0])
            else:
                families.kiranico.setdefault(int(item), set()).add(root[monster])
    return families


# ----- the rules ---------------------------------------------------------------------------------------------------

def _cut(materials: Iterable[tuple[int, int]], rules: dict) -> list[list[int]]:
    """The first `materials` entries of a recipe, each at most `quantity` units."""
    return [[item, min(quantity, rules["quantity"])] for item, quantity in list(materials)[:rules["materials"]]]


def _recipe(piece: Piece | None, upgrade: bool = False) -> list[tuple[int, int]]:
    """A piece's materials: its create recipe, else (`upgrade`) the upgrade that makes it."""
    if piece is None:
        return []
    if piece.create is not None and piece.create.materials:
        return list(piece.create.materials)
    return list(piece.upgrade.materials) if upgrade and piece.upgrade is not None else []


def _exclusive_units(families: Families, recipes: Iterable[Iterable[tuple[int, int]]]) -> dict[int, int]:
    """Family -> units of its exclusive materials over the recipes."""
    units: dict[int, int] = defaultdict(int)
    for materials in recipes:
        for item, quantity in materials:
            for family in {families.root[m] for m in families.droppers.get(item, ()) if m in families.root}:
                if families.exclusive(item, family):
                    units[family] += quantity
    return units


def _best_family(units: dict[int, int], total: int, rules: dict, preferred: int | None = None) -> int | None:
    """The `preferred` family when its units reach `min_share` of the `total` of the recipes' units, else the family
    with the most units (ties: the lowest id) when it does: a set that only borrows a material or two from a monster
    is not that monster's."""
    enough = rules["min_share"] * total
    if preferred is not None and units.get(preferred, 0) >= enough:
        return preferred
    best = min(units, key=lambda family: (-units[family], family), default=None)
    return best if best is not None and units[best] >= enough else None


def member_of(families: Families, family: int, recipes: Iterable[Iterable[tuple[int, int]]]) -> int:
    """The monster of `family` a look belongs to: the member whose own drop lists hold the most units of the recipes'
    materials that only the family drops; a tie goes to the base (the family's root), else to the lowest id."""
    units: dict[int, int] = defaultdict(int)
    for materials in recipes:
        for item, quantity in materials:
            if families.exclusive(item, family):
                for monster in families.droppers.get(item, ()):
                    if families.root.get(monster) == family:
                        units[monster] += quantity
    if not units:
        return family
    top = max(units.values())
    tied = sorted(monster for monster, count in units.items() if count == top)
    return family if family in tied else tied[0]


def home_rank(families: Families, monster: int, item: int) -> int | None:
    """The first rank (1-3) whose lists of the monster hold `item`: the rank the item belongs to."""
    lists = families.own.get(monster, {})
    return next((rank for rank in (1, 2, 3) if item in lists.get(rank - 1, {})), None)


def pick_material(found: Mapping, home: Mapping, rank: int, rare_percent: int, rarity: Mapping | None = None,
                  home_chance: Mapping | None = None, last_resort: bool = True):
    """The item a look at `rank` asks among `found` (item -> its best chance at `rank`), `home` item -> its home rank,
    `home_chance` item -> its best chance at its home rank. Among the items whose home rank is `rank`, the one with the
    lowest chance (ties: the rarest item by `rarity`, then the lowest id). When that chance is above `rare_percent`, the
    lowest chance among those and the lower ranks' items that are rare at their own home rank too (Teostra G asks the
    Teostra Gem of high rank, not the Flame Shard at 20%; Seltas high never asks the low Seltas Shell, 65 % in low and
    a leftover 10 % in high). With none of either, the lowest chance among all of `found` (`last_resort`; else None).
    None when `found` is empty."""
    rarity, home_chance = rarity or {}, home_chance or {}

    def hardest(items):
        return min(items, key=lambda item: (found[item], -rarity.get(item, 0), item))

    here = [item for item in found if home.get(item) == rank]
    if here and found[hardest(here)] <= rare_percent:
        return hardest(here)
    rare_below = [item for item in found if (home.get(item) or rank) < rank
                  and home_chance.get(item, 100) <= rare_percent]
    if here or rare_below:
        return hardest(here + rare_below)
    return hardest(found) if found and last_resort else None


def units_for(chance: int, rules: dict) -> int:
    """How many units a look asks of a material that drops at `chance` percent: curated `units_by_percent`, [bound,
    units] pairs by rising bound, the units of the first bound the chance does not pass (else the last pair's)."""
    table = rules["units_by_percent"]
    return next((units for bound, units in table if chance <= bound), table[-1][1])


def pick_two(found: Mapping, home: Mapping, rank: int, rare_percent: int, rarity: Mapping | None = None,
             home_chance: Mapping | None = None) -> list:
    """The items a look at `rank` asks among `found` (item -> its best chance at `rank`): `pick_material`'s, and when
    its chance is above `rare_percent` (it is not rare) the next pick among the others too, never a lower rank's
    leftover that is common at its own rank. [] when `found` is empty."""
    first = pick_material(found, home, rank, rare_percent, rarity, home_chance)
    if first is None:
        return []
    if found[first] <= rare_percent:
        return [first]
    second = pick_material({item: chance for item, chance in found.items() if item != first}, home, rank,
                           rare_percent, rarity, home_chance, last_resort=False)
    return [first] if second is None else [first, second]


def pick_materials(found: Mapping, home: Mapping, rank: int, rules: dict, rarity: Mapping | None = None,
                   home_chance: Mapping | None = None) -> list[list[int]] | None:
    """[[item, units]] a look at `rank` asks among `found` (item -> its best chance at `rank`): `pick_two`'s items,
    each with `units_for` its chance. None when `found` is empty."""
    picked = pick_two(found, home, rank, rules["rare_percent"], rarity, home_chance)
    return [[item, units_for(found[item], rules)] for item in picked] or None


def _homes(families: Families, monster: int, found: Mapping) -> tuple[dict, dict]:
    """({item: its home rank}, {item: its best chance in the monster's lists at that rank}) of `found`'s items."""
    home = {item: home_rank(families, monster, item) for item in found}
    lists = families.own.get(monster, {})
    return home, {item: lists[at - 1][item] for item, at in home.items() if at is not None}


def monster_materials(families: Families, monster: int, rank: int, rules: dict) -> list[list[int]] | None:
    """[[item, units]] a look of `monster` at `rank` (1-3) asks (`pick_materials` over the items it may ask there,
    `Families.usable_at`); None when it has none."""
    found = families.usable_at(monster, rank, rules["max_families"])
    home, home_chance = _homes(families, monster, found)
    return pick_materials(found, home, rank, rules, families.rarity, home_chance)


def hardest_material(families: Families, monster: int, rank: int, rules: dict) -> int | None:
    """The material a look of `monster` at `rank` (1-3) asks (`pick_material` over the monster's own lists at the rank,
    the items it may ask: `Families.usable_at`); None when it has none."""
    found = families.usable_at(monster, rank, rules["max_families"])
    home, home_chance = _homes(families, monster, found)
    return pick_material(found, home, rank, rules["rare_percent"], families.rarity, home_chance)


def rank_order(rank: int) -> list[int]:
    """The ranks to try for a look at `rank`: its own, the higher ones, then the lower ones, nearest first."""
    return [*range(rank, 4), *range(rank - 1, 0, -1)]


def first_material(pick: Callable[[int], int | None], rank: int) -> tuple[int, int] | None:
    """(the item, the rank it was found at) a look at `rank` asks: `pick(rank)` of the first rank of `rank_order` that
    gives one; None when no rank does."""
    for found_at in rank_order(rank):
        item = pick(found_at)
        if item is not None:
            return item, found_at
    return None


def shown_rank(families: Families, rank: int, materials: Iterable, found_at: int = 0) -> int:
    """The rank a look of `rank` is listed under (the screens' filter and rank gate, its zenny): its own, or higher
    when what it asks first drops at a higher rank (`materials`' MH4U items, by `Families.first_rank`) or was found
    there (`found_at`: the rank its monster's material comes from), so a low look never asks a high item."""
    return max([rank, found_at, *(families.first_rank(item) or 0 for item, _ in materials if isinstance(item, int))])


def _record(rule: str, materials: list[list[int]], monster: int | None, families: Families, rank: int) -> dict:
    shown = shown_rank(families, rank, materials)
    return {"rule": rule, **({"monster": families.names[monster]} if monster is not None else {}),
            "materials": materials, **({"shown_rank": shown} if shown != rank else {})}


def price(families: Families, rules: dict, rank: int, monster: int | None, recipe: list[tuple[int, int]],
          has_recipe: bool) -> dict:
    """The record of one armor or weapon look: `monster` its monster (None: no large monster's), `recipe` its normal
    recipe's materials (an item a player never holds left out: `Families.unheld`; a Wyporium item's units by the chance
    of the item its trade takes, `units_for`), `has_recipe` whether it has any recipe at all. "shown_rank": the rank it
    is listed under when higher than `rank` (`shown_rank`)."""
    if not has_recipe:
        return _record("free", [], monster, families, rank)
    if monster is not None:
        materials = monster_materials(families, monster, rank, rules)
        if materials:
            return _record("monster", materials, monster, families, rank)
    materials = _cut([(item, units) for item, units in recipe if item not in families.unheld], rules)
    at = shown_rank(families, rank, materials)
    for material in materials:
        if material[0] in families.traded:
            chance = families.best_chance(families.traded[material[0]][0], at)
            if chance is not None:
                material[1] = units_for(chance, rules)
    return _record("recipe", materials, monster, families, rank)


def shown_ranks(prices: Mapping) -> dict[str, int]:
    """Look key -> the rank it is listed under, for the looks whose record moves it up (`shown_rank`): MH4U's armor and
    weapons and MH XX's."""
    tables = [prices.get(kind, {}) for kind in ("armor", "weapons")] + \
             [prices.get("xx", {}).get(kind, {}) for kind in ("armor", "weapons")]
    return {key: record["shown_rank"] for table in tables for key, record in table.items() if "shown_rank" in record}


@dataclass(frozen=True)
class RankUp:
    """The curated `rank_up` (a high or G recipe look asks its rank's items) with the items it names resolved:
    `kinds` kind -> the item ids of ranks 1-3 (None: none), `items` item id -> its kind, `categories` item category
    -> kind (an item no large monster drops), `category` item id -> its category, `names` English name -> id."""
    kinds: Mapping[str, tuple[int | None, ...]]
    items: Mapping[int, str]
    categories: Mapping[str, str]
    category: Mapping[int, str]
    rarity_ranks: tuple[tuple[int, int], ...]
    min_units: int
    lone: tuple[tuple[str, int], ...]


def rank_up_rules(curated: Mapping, items: Mapping[str, int], categories: Mapping[int, str]) -> RankUp:
    """`RankUp` of the curated prices (`rank_up`, and `xx.recipe.replace.kinds` for the kinds) over the items a player
    can hold (`items`: lower case English name -> id, xx_prices.mh4u_items); `categories`: item id -> its category.
    ValueError on a name that is no such item or a kind the table lacks."""
    raw, kinds = curated["rank_up"], curated["xx"]["recipe"]["replace"]["kinds"]

    def item(name: str) -> int:
        if name.lower() not in items:
            raise ValueError(f"rank_up: {name!r} is no item a player can hold")
        return items[name.lower()]

    for kind in [*raw["items"].values(), *raw["categories"].values(), *(kind for kind, _ in raw["lone"])]:
        if kind not in kinds:
            raise ValueError(f"rank_up: the kind {kind!r} is not in xx.recipe.replace.kinds")
    return RankUp({kind: tuple(None if name is None else item(name) for name in names)
                   for kind, names in kinds.items()},
                  {item(name): kind for name, kind in raw["items"].items()}, dict(raw["categories"]),
                  dict(categories), tuple(tuple(pair) for pair in raw["rarity_ranks"]), raw["min_units"],
                  tuple((kind, units) for kind, units in raw["lone"]))


def ranked_up(materials: Sequence[Sequence], rank: int, families: Families, rules: dict, up: RankUp) -> list[list]:
    """The materials ([[item, units]]) a recipe look listed at `rank` asks by the `rank_up` rule: at high or G, each
    generic item (`up.items`, or of `up.categories` and no large monster's) of a lower rank (`Families.first_rank`, else
    its rarity by `up.rarity_ranks`) becomes its kind's item of `rank`; one that becomes an item already asked adds its
    units to it; a generic item asks `up.min_units` to `rules["quantity"]` units; a look left with one material adds
    the first `up.lone` kind it does not ask. A Wyporium item and a new item (by name) stay as they are. Low rank, and
    a look with no material, are left alone."""
    if rank < 2 or not materials:
        return [list(material) for material in materials]

    def kind_of(item: int) -> str | None:
        if item in up.items:
            return up.items[item]
        if families.droppers.get(item):
            return None
        return up.categories.get(up.category.get(item, ""))

    def rank_of(item: int) -> int:
        found = families.first_rank(item)
        if found is not None:
            return found
        rarity = families.rarity.get(item, 0)
        return next((at for bound, at in up.rarity_ranks if rarity <= bound), 3)

    out: list[list] = []
    for item, units in materials:
        kind = kind_of(item) if isinstance(item, int) and item not in families.traded else None
        if kind is not None:
            if rank_of(item) < rank and up.kinds[kind][rank - 1] is not None:
                item = up.kinds[kind][rank - 1]
            units = max(up.min_units, min(units, rules["quantity"]))
        same = next((material for material in out if material[0] == item), None)
        if same is not None:
            same[1] = min(same[1] + units, rules["quantity"])
        else:
            out.append([item, units])
    if len(out) == 1:
        lone = next(((up.kinds[kind][rank - 1], units) for kind, units in up.lone
                     if up.kinds[kind][rank - 1] not in (None, out[0][0])), None)
        if lone is not None:
            out.append(list(lone))
    return out


# ----- armor and weapons -------------------------------------------------------------------------------------------

def _override(curated: dict, kind: str, key: str, monsters: dict[str, int]):
    """The curated monster of a look: (True, monster id or None) when it has one."""
    value = curated.get("monster", {}).get(kind, {}).get(key)
    if value is None:
        return False, None
    return True, (None if value == "none" else monsters[value.lower()])


def _owner(families: Families, recipes: list[list[tuple[int, int]]], rules: dict,
           group: int | None = None) -> int | None:
    """The monster a look whose pieces have `recipes` belongs to (`group`: a weapon's group monster), or None."""
    family = _best_family(_exclusive_units(families, recipes), sum(q for r in recipes for _, q in r), rules,
                          preferred=families.root.get(group))
    return None if family is None else member_of(families, family, recipes)


def armor_prices(catalog: Catalog, looks, families: Families, rules: dict, curated: dict, monsters: dict) -> dict:
    out = {}
    for look in looks:
        pieces = [catalog.armor[part][index] for part, index in look.members]
        crafted = [p for p in pieces if _recipe(p)]
        of_rank = [p for p in crafted if p.rank == look.rank] or crafted
        order = {part: n for n, part in enumerate(NAME_PARTS)}
        of_rank.sort(key=lambda p: (order[p.group], p.index))
        has_override, monster = _override(curated, "armor", look.key, monsters)
        if not has_override:
            monster = _owner(families, [_recipe(p) for p in of_rank], rules)
        out[look.key] = price(families, rules, look.rank, monster, _recipe(of_rank[0]) if of_rank else [],
                              bool(crafted))
    return out


def weapon_prices(catalog: Catalog, looks: dict, families: Families, rules: dict, curated: dict,
                  monsters: dict) -> dict:
    out = {}
    for cls, class_looks in looks.items():
        for look in class_looks:
            pieces = [catalog.weapons[cls][index] for index in look.members]
            crafted = sorted((p for p in pieces if _recipe(p, upgrade=True)), key=lambda p: (p.rarity, p.index))
            has_override, monster = _override(curated, "weapons", look.key, monsters)
            if not has_override:
                of_rank = [p for p in crafted if p.rank == look.rank] or crafted
                group = int(look.group.split(":")[1]) if look.group.startswith("monster:") else None
                monster = _owner(families, [_recipe(p, upgrade=True) for p in of_rank], rules, group)
            out[look.key] = price(families, rules, look.rank, monster, _recipe(crafted[0], upgrade=True)
                                  if crafted else [], bool(crafted))
    return out


# ----- Felynes -----------------------------------------------------------------------------------------------------

def felyne_prices(tables, rules: dict, unheld: Iterable[int] = ()) -> dict:
    """Model number (text) -> the first materials of the recipe of the model's piece of lowest rarity (then head,
    body, weapon), an item a player never holds (`unheld`) left out; a model none of whose pieces has a recipe is
    free."""
    unheld = set(unheld)
    recipes: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for kind, records in tables.palico_recipes.items():
        for recipe in records:
            if recipe["equipment_id"] and recipe.materials:
                recipes.setdefault((kind, recipe["equipment_id"]), list(recipe.materials))
    pieces: dict[int, list[tuple]] = defaultdict(list)
    for table in PALICO_TABLES:
        for index, record in enumerate(tables.palico[table.key]):
            if record.values()["model"]:
                pieces[record.values()["model"]].append(
                    (record.values()["rarity"], PALICO_KINDS.index(table.key), index, table.key))
    out = {}
    for model in sorted(pieces):
        crafted = [p for p in sorted(pieces[model]) if (p[3], p[2]) in recipes]
        out[str(model)] = ({"rule": "recipe", "materials": _cut([(item, units) for item, units
                                                                 in recipes[crafted[0][3], crafted[0][2]]
                                                                 if item not in unheld], rules)}
                           if crafted else {"rule": "free", "materials": []})
    return out


# ----- the file ----------------------------------------------------------------------------------------------------

def mh4u_ported(armor: dict, looks, ported: Mapping[str, tuple[str, PortedMonster]], families: Families,
                rules: dict) -> None:
    """Mark the MH4U armor looks a ported monster's gear wears (Alatreon's armor is MH4U's Escadora, same models):
    their record gets {"ported": {"key", "materials": [[English name, units]]}} beside its own, which a run with the
    monster uses instead (layered_rules.py). The models are `ported_pack.GEAR`'s."""
    from core.equipment.layered.ported_prices import ported_first_materials, ported_rank
    from core.equipment.mhgen.ported_pack import GEAR
    for key, monster in ported.values():
        models = set(GEAR[key].armor)
        for look in looks:
            if look.male in models and look.female in models:
                found = ported_first_materials(monster, families, look.rank, rules)
                if found is not None:
                    record = armor[look.key]
                    record["ported"] = {"key": key, "materials": [[monster.english[item], units]
                                                                  for item, units in found[0]]}
                    # never listed below the rank his item belongs to (Escadora HR asks Alatreon's G gem)
                    shown = max(record.get("shown_rank", look.rank), found[1], ported_rank(monster, found[0]))
                    if shown > look.rank:
                        record["shown_rank"] = shown


def generated_prices(tables, data, drops: dict, item_monsters: dict | None, item_drops: dict | None,
                     curated: dict, xx_monsters: dict | None = None,
                     ported: Mapping[str, PortedMonster] | None = None, materials=None) -> dict:
    """What game/data/generated/layered_prices.json holds for these (clean) tables. `xx_monsters`:
    generated/layered_xx_monsters.json (None: no look of MH XX has a record). `ported`: the ported monsters' drops by
    key (ported_prices.ported_monsters; None: no look of theirs has a record). `materials`: the rare materials of XX's
    monsters MH4U lacks (xx_materials.Materials; default: the curated file)."""
    from core.equipment.layered.ported_prices import ported_first_materials
    from core.equipment.layered.xx_materials import load_materials, traded_materials   # they need this module's rules
    from core.equipment.layered.xx_prices import (
        material_records, mh4u_items, recipe_owners, recipe_records, xx_materials_at, xx_records,
    )
    catalog = build_catalog(tables)
    armor, weapons = game_pieces(tables, data)
    families = monster_families(data, drops, item_monsters, curated.get("kiranico_names", {}), item_drops,
                                curated.get("not_asked"), curated["unobtainable"], load_trades(),
                                json.loads((CURATED_DIR / "item_sources.json").read_text(encoding="utf-8"))["items"])
    monsters = {m.name.lower(): m.monster_id for m in data.monsters.values() if m.is_large}
    rules = curated["rules"]
    armor_looks, weapon_looks = build_armor_looks(armor), build_weapon_looks(weapons)
    by_name = {name: (key, ported[key]) for name, key in curated["xx"]["ported"].items() if ported and key in ported}
    out = {
        "armor": armor_prices(catalog, armor_looks, families, rules, curated, monsters),
        "weapons": weapon_prices(catalog, weapon_looks, families, rules, curated, monsters),
        "felyne": felyne_prices(tables, rules, families.unheld),
    }
    mh4u_ported(out["armor"], armor_looks, by_name, families, rules)
    recipe, xx_monsters = curated["xx"]["recipe"], xx_monsters or {}
    items = mh4u_items(data, curated["unobtainable"])
    up = rank_up_rules(curated, items, {i: info.category.value for i, info in data.items.items()})
    ranks = {look.key: look.rank for look in armor_looks}
    ranks.update({look.key: look.rank for class_looks in weapon_looks.values() for look in class_looks})
    for kind in ("armor", "weapons"):
        for key, record in out[kind].items():
            if record["rule"] == "recipe":
                record["materials"] = ranked_up(record["materials"], record.get("shown_rank", ranks[key]), families,
                                                rules, up)
    armor_looks, weapon_looks = with_forge(armor_looks, weapon_looks, tables)
    materials = materials or load_materials()
    trade_of = traded_materials(materials, load_trades())      # the Wyporium rule of XX's materials with a trade
    of_xx = material_records(xx_monsters.get("recipes", {}), materials, rules, families.first_rank, trade_of,
                             families.best_chance)
    recipes = {kind: {key: look for key, look in looks.items() if key not in of_xx[kind]}
               for kind, looks in xx_monsters.get("recipes", {}).items()}
    known = [*families.names.values(), *by_name]
    owned = recipe_owners(recipes, items, recipe["names"], families, curated["xx"], known)
    of_monsters = {kind: {**xx_monsters.get(kind, {}), **owned[kind]} for kind in owned}
    def own_materials(name: str, group: str, rank: int) -> tuple[list, int] | None:
        """What a look of the ported monster `name` (its armor set `group`) asks in a run without him: his XX
        materials of the rank, or those of the deviant whose set it is."""
        found = materials.materials(materials.of_set(group) or name, rank, rules, trade_of, families.best_chance) \
            if name in materials.monsters else None
        return None if found is None else (
            [[item.mh4u if item.mh4u is not None else item.name, units] for item, units in found[0]], found[1])

    out["xx"] = xx_records(of_monsters, families, rules, monsters, out, armor_looks, weapon_looks, by_name,
                           own_materials)
    rest = {kind: {key: look for key, look in recipes.get(kind, {}).items() if key not in owned[kind]}
            for kind in owned}

    def monster_material(name: str, rank: int) -> tuple[int | str, int, int] | None:
        """(the rare material, its units, the rank it was found at) a look of `name` at `rank` asks first
        (xx_prices.xx_records' rules): a ported monster's item by English name, an MH4U monster's id, an XX monster's
        (xx_materials) MH4U id or new item's name."""
        if name in by_name:
            port = by_name[name][1]
            found = ported_first_materials(port, families, rank, rules)
            return None if found is None else (port.english[found[0][0][0]], found[0][0][1], found[1])
        if name.lower() in monsters:
            found = xx_materials_at(families, monsters[name.lower()], rank, rules)
            return None if found is None else (*found[0][0], found[1])
        return xx_material(name, rank)

    def xx_material(name: str, rank: int) -> tuple[int | str, int, int] | None:
        """`monster_material` of a monster of XX's materials file (one MH4U lacks, or a ported one in a run without
        him)."""
        found = materials.materials(name, rank, rules, trade_of, families.best_chance) \
            if name in materials.monsters else None
        if found is None:
            return None
        item, units = found[0][0]
        return (item.mh4u if item.mh4u is not None else item.name), units, found[1]

    def absent_material(name: str, rank: int) -> tuple[int | str, int, int] | None:
        """`monster_material` of a run without the ported monsters: theirs are their XX materials."""
        return xx_material(name, rank) if name in by_name else monster_material(name, rank)

    for kind, records in recipe_records(rest, items, rules, recipe["names"], recipe.get("replace"),
                                        monster_material, families.first_rank,
                                        {name: key for name, (key, _) in by_name.items()}, absent_material).items():
        for record in records.values():
            at = record.get("shown_rank", record["rank"])
            record["materials"] = ranked_up(record["materials"], at, families, rules, up)
            if "ported" in record:
                record["ported"]["materials"] = ranked_up(record["ported"]["materials"], at, families, rules, up)
        out["xx"][kind].update(records)
    for kind, records in of_xx.items():
        out["xx"][kind].update(records)
    return out


@cache
def load_trades() -> dict:
    """generated/wyporium_trades.json's "trades" (tools/build/fetch_wyporium_trades.py): Wyporium item id (text) ->
    {"name", "give" (the item its trade takes), "give_name", "rank", "quest"}."""
    return json.loads(WYPORIUM_TRADES_PATH.read_text(encoding="utf-8"))["trades"]


@cache
def load_curated_prices() -> dict:
    return json.loads(CURATED_PRICES_PATH.read_text(encoding="utf-8"))


@cache
def load_prices() -> dict:
    """The generated prices: {"armor": {look key: record}, "weapons": {look key: record}, "felyne": {model: record},
    "xx": {"armor": {XX look key: record}, "weapons": {...}}}. A record is {"rule": "free" | "monster" | "recipe",
    "monster": family (when it has one), "materials": [[item, units]]}; an XX record (xx_prices.py) is {"monster",
    "rank", "materials": [[item, 1]], "forge": [conditions]} (+ "material_rank")."""
    return json.loads(PRICES_PATH.read_text(encoding="utf-8"))
