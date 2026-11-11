"""Which monster of MH4U a look of MH XX is of: armor sets and weapons.

A look of MH XX costs a material of the MH4U monster it is made of (xx_prices.py). The monster is named, never taken
from XX's own items (XX's materials are not MH4U's):

* **An armor set** by its name: a word of its group name or of its pieces' names that names a large monster of MH4U
  (curated `xx.words`: "Rathian Helm R", "EX Zinogre", "Arc/Storge" are Rathian, Zinogre and Shagaru Magala). A name
  that says no monster, or says one MH4U lacks (Lagiacrus, Mizutsune), gives none, unless the curated `xx.monster`
  names it (the deviants: "Deadeye" is Yian Garuga's; each entry was checked against the set's own recipe).
* **A weapon** by its recipes: the items of its create and upgrade recipes, each mapped to the family of monsters
  whose armor sets ask it (and no other family's), vote; the family holding `weapon_share` of the units of the
  non-common items (those few armor series ask), with the second at most `weapon_lead` of its units, owns the weapon;
  inside the family the member whose own sets ask most of those items (each mapped to that member alone) has it, a
  tie or none the base.

A set or weapon of a variant MH4U has (Stygian Zinogre, Silver Rathalos) is the variant's; one of a variant or deviant
MH4U lacks (Dreadqueen, Hellblade) is its base's, which the curated `xx.monster` says. The ported monsters (Mizutsune,
Glavenus, Alatreon, Great Maccao) have looks like any other (ported_prices.py). The result is written once by
tools/build/build_layered_xx.py (generated/layered_xx_monsters.json), so a build of the prices needs neither game of the
pack. XX's Felyne gear and the monsters MH4U lacks (Lagiacrus) get none.

**A look of no monster** gets its recipe instead (the file's "recipes"), by English name, which xx_prices prices like
MH4U's: an armor set the create recipe of its first piece (head to legs) of its first series (its rank's first, then by
rarity), a weapon look the create row of its first weapon (lowest rarity), else the upgrade that makes it; the
materials in their order, the unlock item included (it is spent too), a placeholder (XX's "DUMMY") left out. XX has
only Japanese text: the names are MH Generations Ultimate's (`english_item_names`), whose item table is XX's. Such a
look of a monster MH4U lacks (Lagiacrus, Redhelm Arzuros) says so (`xx_monster`: xx_materials.owner over all its
recipes' items), and costs that monster's rare material (xx_materials.py).
"""

import re
import struct
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from core.equipment.mhgen import gear_recipes
from core.equipment.mhgen.equipment_pack import WEAPON_FOLDERS
from core.equipment.mhgen.gear_data import table_records
from core.equipment.mhgen.looks import CLASS_KEYS, GenLooks
from core.game.files.text.gmd import gmd_strings

WORD = re.compile(r"[A-Za-z'\-]+")
PROCESS_SIZE = 32          # a weaponProcessWNN row
PLACEHOLDER = "DUMMY"      # XX's name of an item that stands for none (an event recipe's unlock slot)
RECIPE_ROLES = ("unlock", "material")   # what a recipe spends (gear_recipes.ROLES): not its scrap or spare slots
ARMOR_PIECES = ("head", "body", "arms", "waist", "legs")   # gear_data.PARTS, the order a set's first piece is taken in


@dataclass(frozen=True)
class SetMonster:
    """The monster of one armor set: its name (None: none) and how it was found ("name", "curated" or "none")."""
    monster: str | None
    how: str
    group: str
    rank: int
    series: tuple[int, ...]    # the armorSeriesData indexes of the set's pieces


def set_monster(group: str, names: Iterable[str], xx: Mapping) -> tuple[str | None, str]:
    """The monster of a set called `group` whose pieces are `names` (English), by the curated `xx` rules."""
    if group in xx["monster"]:
        monster = xx["monster"][group][0]
        return (None if monster == "none" else monster), "curated"
    found = {xx["words"][word.lower()] for text in (group, *names) for word in WORD.findall(text)
             if word.lower() in xx["words"]}
    if len(found) == 1:
        return next(iter(found)), "name"
    return None, "ambiguous" if found else "none"


def armor_monsters(gen: GenLooks, xx: Mapping) -> dict[str, SetMonster]:
    """Every set of `gen` (looks of MH XX) -> its monster."""
    out = {}
    for pack_set in gen.sets:
        look = pack_set.look
        series = sorted({position for halves in look.pieces.values() for position in halves})
        catalog = [gen.catalog.series[position] for position in series]
        names = [name for item in catalog for name in item.names["eng"]]
        monster, how = set_monster(look.group, names, xx)
        out[look.key] = SetMonster(monster, how, look.group, look.rank, tuple(item.index for item in catalog))
    return out


def common_items(series_items: Mapping[int, Mapping[int, int]], series_max: int) -> set[int]:
    """The items more than `series_max` armor series ask (Iron Ore, Warm Pelt): they say nothing of a monster."""
    asked = Counter(item for items in series_items.values() for item in items)
    return {item for item, count in asked.items() if count > series_max}


def item_monsters(sets: Iterable[SetMonster], series_items: Mapping[int, Mapping[int, int]],
                  common: set[int]) -> dict[int, str]:
    """Item (XX's id) -> the monster of the sets that ask it, when they are one monster's and the item is not common."""
    found: dict[int, set[str]] = defaultdict(set)
    for look in sets:
        if look.monster:
            for series in look.series:
                for item in series_items.get(series, ()):
                    found[item].add(look.monster)
    return {item: next(iter(monsters)) for item, monsters in found.items()
            if len(monsters) == 1 and item not in common}


def ported_item_monsters(records: Iterable, names: Mapping[str, str]) -> dict[int, str]:
    """XX's item id -> the ported monster it is a material of, for each curated ported monster (`records`:
    ported_gear.curated.MonsterRecord) read from XX: his weapons ask his own items, which few armor sets name.
    `names`: a monster's key -> the name the file uses for him."""
    return {item.mhgen: names[record.key] for record in records if record.source == "xx" and record.key in names
            for item in record.items if item.mhgen is not None and not item.shared}


def family_roots(data) -> dict[str, str]:
    """Every large monster of MH4U (`data`: GameData) -> the base of its family through `material_parent` (a monster
    with no parent is its own)."""
    large = {m.monster_id: m for m in data.monsters.values() if m.is_large}
    out = {}
    for monster in large.values():
        current, seen = monster, {monster.monster_id}
        while current.material_parent in large and current.material_parent not in seen:
            current = large[current.material_parent]
            seen.add(current.monster_id)
        out[monster.name] = current.name
    return out


def item_families(sets: Iterable[SetMonster], series_items: Mapping[int, Mapping[int, int]], common: set[int],
                  roots: Mapping[str, str]) -> dict[int, str]:
    """Item (XX's id) -> the family (`roots`: a monster's base) of the sets that ask it, when they are one family's and
    the item is not common."""
    found: dict[int, set[str]] = defaultdict(set)
    for look in sets:
        if look.monster:
            for series in look.series:
                for item in series_items.get(series, ()):
                    found[item].add(roots.get(look.monster, look.monster))
    return {item: next(iter(families)) for item, families in found.items() if len(families) == 1 and item not in common}


def weapon_monster(items: Mapping[int, int], mapped: Mapping[int, str], common: set[int], xx: Mapping,
                   families: Mapping[int, str] | None = None, roots: Mapping[str, str] | None = None) -> str | None:
    """The monster of a weapon whose recipes ask `items` (item -> units): see the module's docstring. `mapped`: item ->
    the one monster whose sets ask it; `families`: item -> the one family whose sets ask it (default: the root of
    `mapped`'s monster); `roots`: monster -> its family's base (default: each its own)."""
    roots = roots or {}
    families = families if families is not None else {item: roots.get(m, m) for item, m in mapped.items()}
    units: Counter = Counter()
    total = 0
    for item, quantity in items.items():
        if item in common:
            continue
        total += quantity
        if item in families:
            units[families[item]] += quantity
    if not units or not total:
        return None
    (top, top_units), *rest = units.most_common()
    if top_units < xx["rules"]["weapon_share"] * total:
        return None
    if rest and rest[0][1] > xx["rules"]["weapon_lead"] * top_units:
        return None
    members: Counter = Counter()
    for item, quantity in items.items():
        if item in mapped and families.get(item) == top and item not in common:
            members[mapped[item]] += quantity
    best = max(members.values(), default=0)
    tied = sorted(monster for monster, count in members.items() if count == best)
    return top if not tied or top in tied else tied[0]


def weapon_monsters(gen: GenLooks, plan, weapon_items: Mapping[str, Mapping[int, int]], mapped: Mapping[int, str],
                    common: set[int], xx: Mapping, families: Mapping[int, str] | None = None,
                    roots: Mapping[str, str] | None = None) -> dict[str, tuple[str | None, int, str]]:
    """Every weapon look of `gen` -> (its monster or None, rank, its English name). `plan`: the pack's models
    (equipment_pack.PackModel), `weapon_items`: "<class>:<line>" -> item -> units over the line's recipes."""
    packed = {(model.slot, model.source): model.model for model in plan}
    members: dict[tuple[str, int], list[int]] = defaultdict(list)
    for weapon in gen.catalog.weapons:
        model = packed.get((weapon.cls, weapon.model))
        if model is not None:
            members[weapon.cls, model].append(weapon.index)
    out = {}
    for key, looks in gen.weapons.items():
        cls = next(cls for cls, class_key in CLASS_KEYS.items() if class_key == key)
        for look in looks:
            items: Counter = Counter()
            for line in members.get((cls, look.model), ()):
                items.update(weapon_items.get(f"{cls}:{line}", {}))
            out[look.key] = (weapon_monster(items, mapped, common, xx, families, roots), look.rank,
                             look.names.get("eng", ""))
    return out


# ----- XX's recipes ------------------------------------------------------------------------------------------------

def recipe_items(game) -> tuple[dict[int, dict[int, int]], dict[str, dict[int, int]]]:
    """The items of MH XX's recipes (`game`: gear_data.GenGame of its romfs): armor series index -> item -> units over
    its create and upgrade recipes (a series is asked by the pair it is in), and "<class>:<line>" (the pack's class,
    the weapon's table index) -> item -> units over the create and upgrade rows of the weapon."""
    armor: dict[int, dict[int, int]] = defaultdict(dict)
    pairs = [(key, recipe) for key, parts in game._armor_create.items() for recipe in parts.values()]
    pairs += [(key, recipe) for key, levels in game._armor_upgrade.items() for recipe in levels.values()]
    for (blademaster, gunner), recipe in pairs:
        for material in recipe.materials:
            for series in (blademaster, gunner):
                if series:
                    armor[series][material.item] = armor[series].get(material.item, 0) + material.qty
    weapons: dict[str, dict[int, int]] = defaultdict(dict)
    for folder, cls in WEAPON_FOLDERS.items():
        number = folder[1:]
        try:
            creates = table_records(game.recipe_table(f"weaponCreateW{number}"), game.fmt.weapon_create_size)
            upgrades = table_records(game.recipe_table(f"weaponProcessW{number}"), PROCESS_SIZE)
        except KeyError:
            continue
        rows = [(gear_recipes.create_line(data, True), gear_recipes.weapon_create(row, data, True))
                for row, data in enumerate(creates)]
        rows += [(struct.unpack_from("<H", data, 0)[0], gear_recipes.weapon_upgrade(row, data))
                 for row, data in enumerate(upgrades)]
        for line, recipe in rows:
            items = weapons[f"{cls}:{line}"]
            for material in recipe.materials:
                items[material.item] = items.get(material.item, 0) + material.qty
    return dict(armor), dict(weapons)


def english_item_names(mhgu_romfs: Path) -> dict[int, str]:
    """XX's item id -> its English name, from MH Generations Ultimate's extracted files (local.ini `mhgu_romfs`): its
    item table is XX's, so a name has the item's index."""
    strings = gmd_strings((mhgu_romfs / "eng" / "table" / "itemData_eng.gmd").read_bytes())
    return {index: strings[2 * index] for index in range(len(strings) // 2)}


def _spent(recipe: gear_recipes.GenRecipe | None, names: Mapping[int, str]) -> list[list]:
    """[[English name, units]] of what a recipe spends, in its order; placeholders left out."""
    if recipe is None:
        return []
    return [[names[m.item], m.qty] for m in recipe.materials
            if m.role in RECIPE_ROLES and names.get(m.item, PLACEHOLDER) != PLACEHOLDER]


def first_recipes(game) -> tuple[dict[int, list[gear_recipes.GenRecipe]], dict[str, gear_recipes.GenRecipe]]:
    """(armor series index -> the create recipe of its first piece that has one, one per pair the series is in;
    "<class>:<line>" -> the line's create row, else its upgrade of lowest level), of MH XX's `game`."""
    armor: dict[int, list] = defaultdict(list)
    for pair, parts in sorted(game._armor_create.items()):
        piece = next((parts[part] for part in ARMOR_PIECES if part in parts and parts[part].materials), None)
        for series in pair:
            if series and piece is not None:
                armor[series].append(piece)
    weapons: dict[str, gear_recipes.GenRecipe] = {}
    for folder, cls in WEAPON_FOLDERS.items():
        number = folder[1:]
        try:
            creates = table_records(game.recipe_table(f"weaponCreateW{number}"), game.fmt.weapon_create_size)
            upgrades = table_records(game.recipe_table(f"weaponProcessW{number}"), PROCESS_SIZE)
        except KeyError:
            continue
        lowest: dict[int, gear_recipes.GenRecipe] = {}
        for row, data in enumerate(upgrades):
            recipe = gear_recipes.weapon_upgrade(row, data)
            line = struct.unpack_from("<H", data, 0)[0]
            if recipe.materials and (line not in lowest or recipe.level < lowest[line].level):
                lowest[line] = recipe
        for line, recipe in lowest.items():
            weapons[f"{cls}:{line}"] = recipe
        for row, data in enumerate(creates):
            recipe = gear_recipes.weapon_create(row, data, True)
            if gear_recipes.create_kind(data, True) == 1 and recipe.materials:
                weapons[f"{cls}:{gear_recipes.create_line(data, True)}"] = recipe
    return dict(armor), weapons


def recipe_looks(gen: GenLooks, plan, game, names: Mapping[int, str], skip: Mapping[str, Iterable[str]]) -> dict:
    """The "recipes" of generated/layered_xx_monsters.json: {"armor": {look key: {"rank", "name", "materials":
    [[English name, units]]}}, "weapons": {...}} for the looks of `gen` not in `skip` (kind -> the looks with a
    monster) that have a recipe (see the module's docstring). `names`: english_item_names."""
    armor, weapons = first_recipes(game)
    out: dict[str, dict] = {"armor": {}, "weapons": {}}
    for pack_set in gen.sets:
        look = pack_set.look
        if look.key in skip.get("armor", ()):
            continue
        positions = sorted({position for halves in look.pieces.values() for position in halves})
        series = sorted((gen.catalog.series[position] for position in positions),
                        key=lambda s: (s.rank != look.rank, s.rarity, s.index))
        spent = next((found for s in series for recipe in armor.get(s.index, ())
                      if (found := _spent(recipe, names))), [])
        if spent:
            out["armor"][look.key] = {"rank": look.rank, "name": look.group, "materials": spent}
    packed = {(model.slot, model.source): model.model for model in plan}
    members: dict[tuple[str, int], list] = defaultdict(list)
    for weapon in gen.catalog.weapons:
        model = packed.get((weapon.cls, weapon.model))
        if model is not None:
            members[weapon.cls, model].append(weapon)
    for key, looks in gen.weapons.items():
        cls = next(cls for cls, class_key in CLASS_KEYS.items() if class_key == key)
        for look in looks:
            if look.key in skip.get("weapons", ()):
                continue
            lines = sorted(members.get((cls, look.model), ()), key=lambda w: (w.rarity, w.index))
            spent = next((found for w in lines if (found := _spent(weapons.get(f"{cls}:{w.index}"), names))), [])
            if spent:
                out["weapons"][look.key] = {"rank": look.rank, "name": look.names.get("eng", ""), "materials": spent}
    return out


def look_items(gen: GenLooks, plan, series_items: Mapping[int, Mapping[int, int]],
               weapon_items: Mapping[str, Mapping[int, int]]) -> dict[str, dict[str, Counter]]:
    """Every look's items over all its recipes ({kind: {look key: XX item -> units}}): a set's series', a weapon look's
    lines' (the weapons of the pack `plan` that wear its model)."""
    out: dict[str, dict[str, Counter]] = {"armor": {}, "weapons": {}}
    for pack_set in gen.sets:
        items: Counter = Counter()
        for position in {p for halves in pack_set.look.pieces.values() for p in halves}:
            items.update(series_items.get(gen.catalog.series[position].index, {}))
        out["armor"][pack_set.look.key] = items
    packed = {(model.slot, model.source): model.model for model in plan}
    members: dict[tuple[str, int], list[int]] = defaultdict(list)
    for weapon in gen.catalog.weapons:
        model = packed.get((weapon.cls, weapon.model))
        if model is not None:
            members[weapon.cls, model].append(weapon.index)
    for key, looks in gen.weapons.items():
        cls = next(cls for cls, class_key in CLASS_KEYS.items() if class_key == key)
        for look in looks:
            items = Counter()
            for line in members.get((cls, look.model), ()):
                items.update(weapon_items.get(f"{cls}:{line}", {}))
            out["weapons"][look.key] = items
    return out


def monsters_file(gen: GenLooks, plan, game, xx: Mapping, roots: Mapping[str, str] | None = None,
                  ported_items: Mapping[int, str] | None = None, item_names: Mapping[int, str] | None = None,
                  xx_items=None, materials=None) -> dict:
    """What generated/layered_xx_monsters.json holds for the looks `gen` of the pack `plan` and MH XX's `game`
    (gear_data.GenGame): {"armor": {look key: {"monster", "rank", "name"}}, "weapons": {...}} for the looks with a
    monster of MH4U or a ported one, and "recipes" (`recipe_looks`) for the others when `item_names`
    (english_item_names) is given, each with `xx_monster` when it is of a monster of `materials`
    (xx_materials.Materials, read with `xx_items`: xx_materials.XxItems). `roots`: `family_roots` of MH4U's data
    (default: no family); `ported_items`: `ported_item_monsters` (default: none)."""
    series_items, weapon_items = recipe_items(game)
    sets = armor_monsters(gen, xx)
    common = common_items(series_items, xx["rules"]["series_max"])
    mapped = item_monsters(sets.values(), series_items, common)
    roots = roots or {}
    families = item_families(sets.values(), series_items, common, roots)
    for item, monster in (ported_items or {}).items():
        mapped[item], families[item] = monster, roots.get(monster, monster)
    weapons = weapon_monsters(gen, plan, weapon_items, mapped, common, xx, families, roots)
    out = {
        "armor": {key: {"monster": s.monster, "rank": s.rank, "name": s.group} for key, s in sets.items() if s.monster},
        "weapons": {key: {"monster": monster, "rank": rank, "name": name}
                    for key, (monster, rank, name) in weapons.items() if monster},
    }
    if item_names is not None:
        out["recipes"] = recipe_looks(gen, plan, game, item_names, {kind: set(out[kind]) for kind in out})
        if xx_items is not None and materials is not None:
            from core.equipment.layered.xx_materials import owner
            items = look_items(gen, plan, series_items, weapon_items)
            for kind, looks in out["recipes"].items():
                for key, look in looks.items():
                    found = owner(items[kind][key], xx_items, materials, common, xx["rules"]["weapon_share"],
                                  xx["rules"]["weapon_lead"])
                    if found is not None:
                        look["xx_monster"] = found
    return out
