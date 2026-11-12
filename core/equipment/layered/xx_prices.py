"""What a look of MH XX costs, when it appears, and which relics are offered.

* **A look of a monster MH4U has** (xx_monsters.py names it; generated/layered_xx_monsters.json) costs **1 unit** of the
  material a look of that very monster would ask in MH4U at the XX look's rank (prices.hardest_material); when the
  monster has none at that rank, the next ranks' (high, then G), and only when none is above, the nearest below. A
  variant MH4U has (Stygian Zinogre, Molten Tigrex) asks its own; a variant or deviant it lacks (the Cyclops set,
  Hellblade) is its base's in the file, so it asks its base's. XX's own items never take part.
* **A look of a ported monster** (Mizutsune, Glavenus, Alatreon, Great Maccao; ported_prices.py) asks one of his items
  by name, by the same rule over his drop lists, and the next ranks' like the others; it carries `ported`. In a run
  without him it costs his XX materials of its rank like a monster MH4U lacks (`absent`: xx_materials.py, new items
  traded at the Wyporium; a Hellblade or Soulseer set asks the deviant's), as that monster's looks do.
* **A look of a monster MH4U lacks** (the monsters file's `xx_monster`: Lagiacrus, Redhelm Arzuros) costs 1 unit of
  that monster's rare material of its rank (xx_materials.py; the next rank's when he has none at it, a deviant with none
  of his own his base's): MH4U's item when MH4U has it (a Wyporium material), else a new item, named by its English
  name (`named`) so that a run without it costs zenny only; it appears from the start, as the other looks of XX.
* **A look its name and vote give no monster** (generated/layered_xx_monsters.json "recipes") gets one when its name
  holds a monster's whole name (Ukanlos Trampler; not the curated words, which name sets: a bow's "Arc" is no Shagaru
  Magala), else by its recipe read in MH4U's items: a family whose exclusive items hold the XX vote's share of the
  recipe's units with a clear lead makes it that monster's look (`recipe_owners`: Demon Rod is Rajang's), priced and
  offered like the rest above.
* **A look of no monster** (the Leather set, Hunter's Knife) costs what MH4U's do: the first materials of its recipe,
  each capped at a few units (prices._cut), when MH4U has every one of them by English name and a player can get it
  (`mh4u_items`); else zenny only. A look of a monster MH4U lacks (Lagiacrus) is no exception to the rule, its own
  items are simply not MH4U's.
* **A Felyne's look** has no record: it costs zenny only.
* **It appears** when the MH4U looks of the same monster and rank do (their forge conditions, joined; a weapon takes
  those of the weapons of its class, else of any class, else the armor's); with none at the rank, the next ranks'
  like the material; with none at all, "always". A ported monster's look appears by the forge rule of his own gear
  (layered_rules.py) and "always" in a run without him.
* **Relics** (looks no piece of which has a recipe) are offered once per model: a part of one whose every model is
  already worn by the same part of another look, of either game, is not offered; a look with no part left is dropped.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from core.equipment.layered.forge_rule import ALWAYS, conditions_list
from core.equipment.layered.looks import ArmorLook, Looks, WeaponLook
from core.equipment.layered.prices import (
    Families, _exclusive_units, first_material, hardest_material, member_of, monster_materials, shown_rank,
)
from core.equipment.mhgen.looks import GenLooks
from core.game.data.paths import GENERATED_DIR

if TYPE_CHECKING:
    from core.equipment.layered.ported_prices import PortedMonster

XX_MONSTERS_PATH = GENERATED_DIR / "layered_xx_monsters.json"


def xx_material(families: Families, monster: int, rank: int, rules: dict) -> tuple[int, int] | None:
    """(the item, the rank it was found at) a look at `rank` of the MH4U monster asks: the hardest material of the first
    rank of `rank_order` that has one; None when the monster has no material at any rank."""
    return first_material(lambda at: hardest_material(families, monster, at, rules), rank)


def xx_materials_at(families: Families, monster: int, rank: int, rules: dict) -> tuple[list[list[int]], int] | None:
    """([[item, units]], the rank they were found at) a look at `rank` of the MH4U monster asks: `monster_materials` of
    the first rank of `rank_order` that has any; None when the monster has none at any rank."""
    return first_material(lambda at: monster_materials(families, monster, at, rules), rank)


def equivalent_forge(rank: int, monster: str, armor: Iterable[tuple[int, str, Sequence[str]]],
                     weapons: Iterable[tuple[str, int, str, Sequence[str]]] = (),
                     cls: str | None = None) -> tuple[str, ...] | None:
    """The conditions an XX look of `monster` at `rank` appears under: the union of the forge conditions of the MH4U
    looks of the monster and the first rank that has any: its own, the lower ones, then the higher ones, nearest first
    (a lower rank's conditions are met sooner, and the screens' rank gate keeps the look hidden until its own rank).
    `armor`: (rank, monster, forge) of the MH4U armor looks; `weapons`: (class, rank, monster, forge) of its weapon
    looks; `cls` the XX weapon's class (None: an armor set). None when the monster has no MH4U look."""
    armor, weapons = list(armor), list(weapons)
    for at in [*range(rank, 0, -1), *range(rank + 1, 4)]:
        candidates = []
        if cls is not None:
            candidates.append([forge for c, r, m, forge in weapons if c == cls and r == at and m == monster])
            candidates.append([forge for _, r, m, forge in weapons if r == at and m == monster])
        candidates.append([forge for r, m, forge in armor if r == at and m == monster])
        for forges in candidates:
            if forges:
                return conditions_list(condition for forge in forges for condition in forge)
    return None


def xx_records(xx_monsters: dict, families: Families, rules: dict, monsters: dict[str, int], prices: dict,
               armor_looks: Sequence[ArmorLook], weapon_looks: dict[str, Sequence[WeaponLook]],
               ported: Mapping[str, tuple[str, PortedMonster]] | None = None,
               absent: Callable[[str, str, int], tuple[list, int] | None] | None = None) -> dict:
    """The "xx" part of generated/layered_prices.json: {"armor": {XX look key: record}, "weapons": {...}}, a record
    {"monster", "rank", "materials": [[item, 1]], "forge": [...]} (+ "material_rank" when the material is another
    rank's) for each look of `xx_monsters` (the generated file) whose monster has a material. `monsters`: the large
    monsters' ids by lower case name; `prices`: the MH4U records ({"armor": ..., "weapons": ...}), `armor_looks` /
    `weapon_looks` the MH4U looks with their forge. `ported`: a ported monster's name -> (its key, its drops): its looks
    get {"materials": [...], "ported": {"key", "materials": [[English name, units]]}, "forge": ["always"]}: the
    `ported` material is the one of a run that has the monster (layered_rules.py), the record's own `materials` that
    of a run without him, as for a monster MH4U lacks. `absent`: (the ported monster's name, the look's armor set or
    weapon name, its rank) -> ([[MH4U's id or a new item's English name, units]], the rank they were found at), what
    a look of his asks in a run without him (xx_materials.Materials.materials); None: nothing, then the materials are
    empty and the look costs zenny only there."""
    armor_forge = [(look.rank, prices["armor"][look.key]["monster"], look.forge or ())
                   for look in armor_looks if "monster" in prices["armor"].get(look.key, {})]
    weapon_forge = [(cls, look.rank, prices["weapons"][look.key]["monster"], look.forge or ())
                    for cls, class_looks in weapon_looks.items() for look in class_looks
                    if "monster" in prices["weapons"].get(look.key, {})]
    out: dict[str, dict] = {"armor": {}, "weapons": {}}
    if ported:      # the ported monsters' drops are the builder's: a run reads the written file
        from core.equipment.layered.ported_prices import ported_first_materials, ported_rank
    for kind, records in out.items():
        for key, found in xx_monsters.get(kind, {}).items():
            name, rank = found["monster"], found["rank"]
            if ported and name in ported:
                port_key, monster = ported[name]
                material = ported_first_materials(monster, families, rank, rules)
                own = absent(name, found.get("name", ""), rank) if absent else None
                if material is not None:
                    # listed under the higher of the two ranks, so that no look shows before either run can pay it,
                    # and never below the rank his item belongs to (Alatreon's lists at every rank are his G one's)
                    shown = max(material[1], ported_rank(monster, material[0]),
                                shown_rank(families, rank, own[0], own[1]) if own else 0)
                    records[key] = {
                        "monster": name, "rank": rank, "materials": own[0] if own else [],
                        "ported": {"key": port_key, "materials": [[monster.english[item], units]
                                                                  for item, units in material[0]]},
                        **({"material_rank": material[1]} if material[1] != rank else {}),
                        **_shown(rank, shown), "forge": [ALWAYS]}
                continue
            monster_id = monsters[name.lower()]
            material = xx_materials_at(families, monster_id, rank, rules)
            if material is None:
                continue
            shown = shown_rank(families, rank, material[0], material[1])
            cls = key.split("-")[0] if kind == "weapons" else None
            forge = equivalent_forge(shown, families.names[monster_id], armor_forge, weapon_forge, cls)
            records[key] = {
                "monster": families.names[monster_id], "rank": rank, "materials": material[0],
                **({"material_rank": material[1]} if material[1] != rank else {}), **_shown(rank, shown),
                "forge": list(forge) if forge else [ALWAYS]}
    return out


# ----- looks of no monster -----------------------------------------------------------------------------------------

def mh4u_items(data, unobtainable: Iterable[str]) -> dict[str, int]:
    """English name (lower case) -> the item of MH4U (`data`: GameData) a player can hold by that name: usable and of
    no category in `unobtainable` (curated: an event's, an account item, one the wiki does not know); the lowest id
    when two share a name."""
    barred = set(unobtainable)
    out: dict[str, int] = {}
    for item in sorted(data.items):
        info = data.items[item]
        if info.usable and info.category.value not in barred:
            out.setdefault(info.name.lower(), item)
    return out


def _in_mh4u(materials: Sequence, items: Mapping[str, int], names: Mapping[str, str]) -> list[tuple[int | None, int]]:
    """[[English name, units]] -> [(MH4U's item or None when it lacks one, units)]."""
    return [(items.get(names.get(name, name).lower()), units) for name, units in materials]


def named_monster(name: str, known: Iterable[str]) -> str | None:
    """The monster of `known` whose whole name is in `name` as words (the longest when several are: Silver Rathalos
    before Rathalos), or None."""
    found = [monster for monster in known
             if re.search(rf"(?<![A-Za-z]){re.escape(monster)}(?![A-Za-z])", name, re.IGNORECASE)]
    return max(found, key=len, default=None)


def recipe_owners(recipes: Mapping, items: Mapping[str, int], names: Mapping[str, str], families: Families,
                  xx: Mapping, known: Iterable[str]) -> dict:
    """The looks of `recipes` (the monsters file's "recipes") that get a monster: {kind: {look key: {"monster", "rank",
    "name"}}}, the monsters file's own records' shape. A look the curated `xx["monster"]` names "none" is nobody's; one
    whose name holds the whole name of a monster of `known` (MH4U's large monsters and the ported ones:
    `named_monster`) is his; else its recipe in MH4U's items (`items`: mh4u_items; an item MH4U lacks counts in the
    units, for no family) is voted like XX's weapons: the family whose exclusive items hold `weapon_share` of the
    units, the second at most `weapon_lead` of its units, and inside it the member prices.member_of says."""
    known = list(known)
    share, lead = xx["rules"]["weapon_share"], xx["rules"]["weapon_lead"]
    out: dict[str, dict] = {"armor": {}, "weapons": {}}
    for kind, records in out.items():
        for key, look in recipes.get(kind, {}).items():
            if look["name"] in xx["monster"]:
                continue                       # curated: a set of a monster MH4U lacks
            named = named_monster(look["name"], known)
            if named is not None:
                records[key] = {"monster": named, "rank": look["rank"], "name": look["name"]}
                continue
            recipe = [(-1 if item is None else item, units)
                      for item, units in _in_mh4u(look["materials"], items, names)]
            units = sorted(_exclusive_units(families, [recipe]).items(), key=lambda pair: (-pair[1], pair[0]))
            total = sum(quantity for _, quantity in recipe)
            if not units or units[0][1] < share * total or (len(units) > 1 and units[1][1] > lead * units[0][1]):
                continue
            monster = member_of(families, units[0][0], [recipe])
            records[key] = {"monster": families.names[monster], "rank": look["rank"], "name": look["name"]}
    return out


def material_records(recipes: Mapping, materials, rules: dict,
                     first_rank: Callable[[int], int | None] = lambda item: None,
                     trade_of: Mapping[int, tuple[int, int]] | None = None,
                     chance: Callable[[int, int], int | None] | None = None) -> dict:
    """The records of the looks of `recipes` (the monsters file's "recipes") of a monster MH4U lacks (`xx_monster`):
    {kind: {look key: {"monster", "rank", "materials", "material_rank"?, "shown_rank"?, "forge": ["always"]}}} with
    his materials of the rank and their units (`materials`: xx_materials.Materials): MH4U's id when MH4U has the item,
    else the new item's English name (resolved in the run, layered_rules._base_cost). `first_rank`: the rank an MH4U
    item first drops at (prices.Families.first_rank), for `shown_rank`. `trade_of`, `chance`: the Wyporium rule of the
    materials with a trade (xx_materials.Materials.materials)."""
    out: dict[str, dict] = {"armor": {}, "weapons": {}}
    for kind, records in out.items():
        for key, look in recipes.get(kind, {}).items():
            name = look.get("xx_monster")
            found = materials.materials(name, look["rank"], rules, trade_of, chance) if name else None
            if found is None:
                continue
            asked = [[item.mh4u if item.mh4u is not None else item.name, units] for item, units in found[0]]
            shown = max([look["rank"], found[1], *(first_rank(item) or 0 for item, _ in asked
                                                   if isinstance(item, int))])
            records[key] = {"monster": name, "rank": look["rank"], "materials": asked,
                            **({"material_rank": found[1]} if found[1] != look["rank"] else {}),
                            **_shown(look["rank"], shown), "forge": [ALWAYS]}
    return out


def _shown(rank: int, shown: int) -> dict:
    """A record's "shown_rank" when its look is listed under a higher rank than its own (prices.shown_rank)."""
    return {"shown_rank": shown} if shown > rank else {}


SKIP = "skip"
KIND, MONSTER = "kind:", "monster:"


def _replaced(name: str, units: int, rank: int, items: Mapping[str, int], names: Mapping[str, str],
              replace: Mapping, monster_material: Callable[[str, int], tuple[int | str, int] | None] | None,
              rules: dict) -> tuple | str | None:
    """What a recipe's material asks in MH4U: (item, units), SKIP, or None when nothing covers it. The curated
    `replace["items"]` rule first (it may cover an item MH4U also has by name): "skip"; "kind:K", the
    item of kind K of the look's rank (`replace["kinds"][K]`: low, high, G; null: skipped); "monster:M", the rare
    material monster M's look of that rank asks (`monster_material`: (an MH4U id or a new item's English name, its
    units by prices.units_for, the rank it was found at); a third value marks units the recipe's cap does not cut, and
    is that rank); or an MH4U item's English name. Without a rule, MH4U's own item (`items`, by English name or the
    curated spelling `names`) as it is."""
    rule = replace.get("items", {}).get(name)
    if rule is None:
        own = items.get(names.get(name, name).lower())
        return None if own is None else (own, units)
    if rule == SKIP:
        return rule
    if rule.startswith(MONSTER):
        found = monster_material(rule[len(MONSTER):], rank) if monster_material else None
        return None if found is None else tuple(found)
    if rule.startswith(KIND):
        rule = replace["kinds"][rule[len(KIND):]][rank - 1]
        if rule is None:
            return SKIP
    found = items.get(rule.lower())
    return None if found is None else (found, units)


def recipe_records(recipes: Mapping, items: Mapping[str, int], rules: dict, names: Mapping[str, str],
                   replace: Mapping | None = None,
                   monster_material: Callable[[str, int], tuple[int | str, int, int] | None] | None = None,
                   first_rank: Callable[[int], int | None] = lambda item: None,
                   ported: Mapping[str, str] | None = None,
                   absent: Callable[[str, int], tuple[int | str, int, int] | None] | None = None) -> dict:
    """The records of the looks of no monster: {"armor": {look key: record}, "weapons": {...}}, a record {"rule":
    "recipe", "rank", "materials": [[item, units]], "forge": ["always"]} with the first `rules["materials"]` different
    items the look's recipe asks in MH4U (`_replaced`: MH4U's own, else the curated replacement `replace`; a skipped
    one does not count; two recipe items replaced by one item add their units), at most `rules["quantity"]` units each
    but a monster's material (its units by its chance). A
    look with an item nothing covers among
    them, or with none, has no record. An item is an MH4U id or a new item's English name (a rare material of XX's
    monsters, a ported monster's item: resolved in the run, layered_rules._base_cost). `recipes`: the monsters file's
    "recipes" ({kind: {key: {"rank", "name", "materials": [[English name, units]]}}}); `items`: mh4u_items; `names`: an
    XX name -> MH4U's, where they spell one item otherwise. "shown_rank": the rank the look is listed under when what
    it asks first drops higher (`first_rank`: an MH4U item's, prices.Families.first_rank; a monster's material found at
    a higher rank). `ported`: a ported monster's name -> his key, and `absent` what `monster_material` gives for him
    in a run without him (his XX materials): a look whose recipe asks his material ("monster:M") gets {"ported": {"key",
    "materials"}} with his item, and its own materials those of a run without him (none: zenny only there)."""
    replace = replace or {}
    ported = ported or {}

    def asked(look: Mapping, material_of) -> tuple[list[list], int] | None:
        first: list[tuple] = []
        for name, units in look["materials"]:
            found = _replaced(name, units, look["rank"], items, names, replace, material_of, rules)
            if found is None:
                return None
            if found == SKIP:
                continue
            same = next((n for n, other in enumerate(first) if other[0] == found[0]), None)
            if same is not None:      # two of the recipe's items asking one (Dark Stone and Dark Piece: crystal)
                if len(found) == 2 and len(first[same]) == 2:
                    first[same] = (found[0], first[same][1] + found[1])
                continue
            first.append(found)
            if len(first) == rules["materials"]:
                break
        if not first:
            return None
        materials = [[found[0], found[1] if len(found) > 2 else min(found[1], rules["quantity"])] for found in first]
        return materials, max([look["rank"], *(found[2] for found in first if len(found) > 2),
                               *(first_rank(item) or 0 for item, _ in materials if isinstance(item, int))])

    out: dict[str, dict] = {"armor": {}, "weapons": {}}
    for kind, records in out.items():
        for key, look in recipes.get(kind, {}).items():
            found = asked(look, monster_material)
            if found is None:
                continue
            materials, shown = found
            port = next((ported[rule[len(MONSTER):]] for name, _ in look["materials"]
                         if (rule := replace.get("items", {}).get(name, "")).startswith(MONSTER)
                         and rule[len(MONSTER):] in ported), None)
            record: dict = {"rule": "recipe", "rank": look["rank"], "materials": materials}
            if port is not None:
                without = asked(look, absent) if absent else None
                record = {**record, "materials": without[0] if without else [],
                          "ported": {"key": port, "materials": materials}}
                shown = max(shown, without[1] if without else 0)
            records[key] = {**record, **_shown(look["rank"], shown), "forge": [ALWAYS]}
    return out


# ----- relics ------------------------------------------------------------------------------------------------------

def relic_offers(looks: Looks, prices: dict, gen: GenLooks | None) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    """The free looks (relics) to offer: ({armor look key: its parts to offer}, [weapon look keys]). A part is left out
    when each of its non-zero male and female models is already worn by that same part in another look of either
    catalog (`looks`: MH4U's, `gen`: MH XX's, None: MH4U's alone) and a look with no part left is dropped; a weapon look
    when another look of its class wears its model. The looks are taken in order, and one dropped no longer covers
    another, so every model stays reachable. A model number is one file: MH4U has no two identical files under two
    numbers that a relic wears."""
    worn: dict[tuple, set[str]] = defaultdict(set)   # (part, 0 male / 1 female, model) -> the looks wearing it
    for look in looks.armor:
        for part in look.parts:
            for gender, model in enumerate((look.male, look.female)):
                if model:
                    worn[part, gender, model].add(look.key)
    for pack_set in gen.sets if gen else ():
        for part, models in pack_set.models.items():
            for gender, model in enumerate(models):
                if model:
                    worn[part, gender, model].add(pack_set.look.key)
    armor: dict[str, tuple[str, ...]] = {}
    for look in looks.armor:
        if prices["armor"].get(look.key, {}).get("rule") != "free":
            continue
        kept = []
        for part in look.parts:
            models = [(part, gender, model) for gender, model in enumerate((look.male, look.female)) if model]
            if models and all(worn[model] - {look.key} for model in models):
                for model in models:
                    worn[model].discard(look.key)
            else:
                kept.append(part)
        if kept:
            armor[look.key] = tuple(kept)

    class_worn: dict[tuple[str, int], set[str]] = defaultdict(set)
    for cls, class_looks in looks.weapons.items():
        for look in class_looks:
            class_worn[cls, look.model].add(look.key)
    for cls, class_looks in (gen.weapons if gen else {}).items():
        for look in class_looks:
            class_worn[cls, look.model].add(look.key)
    weapons = []
    for cls, class_looks in looks.weapons.items():
        for look in class_looks:
            if prices["weapons"].get(look.key, {}).get("rule") != "free":
                continue
            if class_worn[cls, look.model] - {look.key}:
                class_worn[cls, look.model].discard(look.key)
            else:
                weapons.append(look.key)
    return armor, weapons


def load_xx_monsters() -> dict:
    """generated/layered_xx_monsters.json: {"armor": {XX look key: {"monster", "rank", "name"}}, "weapons": {...}}."""
    return json.loads(XX_MONSTERS_PATH.read_text(encoding="utf-8"))
