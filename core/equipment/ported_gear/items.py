"""The ported monsters' items in a run: their ids (item slots), records and texts, and the flattening of MH Generations'
recipes into MH4U's (scraps, armor
spheres and category slots are dropped; the unlock item becomes the recipe's gated first material). The rare materials
of XX's monsters (equipment/layered/xx_materials.py) join them in a run with XX's Layered Gear looks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from typing import TYPE_CHECKING

from core.equipment.tables.item_data import FIRST_NEW_ID, MAX_NEW_ITEMS
from core.equipment.new_gear.new_items import ItemRecord
from core.equipment.mhgen.gear_data import GameSet, GenGame, GenItem, MonsterGear
from core.equipment.mhgen.gear_recipes import GenRecipe
from core.equipment.new_gear.new_texts import CommonTexts, NewTextError, fit_description, tidy_names
from core.equipment.ported_gear.curated import (
    MAX_ITEM_SLOTS, ORDER, RANKS, CuratedError, ItemSpec, MonsterRecord, item_ids, mh4u_item_rarities,
)

if TYPE_CHECKING:
    from core.equipment.layered.xx_materials import Materials

LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
MATERIALS = "xx_materials"     # the key the rare materials of XX's monsters have in `ids` and `english`


NewItem = tuple[ItemRecord, dict[str, str], dict[str, str], str]   # record, names, descriptions, key


@dataclass(frozen=True)
class Flat:
    """A recipe in MH4U's form: (item, quantity) of at most four materials; the first is the gate when `gated`."""
    materials: tuple[tuple[int, int], ...]
    gated: bool = False


def mh4u_item_ids(names: Mapping[int, str]) -> dict[str, int]:
    """MH4U's items by lower case English name (the lowest id of a name two items share)."""
    out: dict[str, int] = {}
    for item_id_ in sorted(names):
        out.setdefault(names[item_id_].lower(), item_id_)
    return out


class ItemBook:
    """The items of the monsters `records` (curated.MonsterRecord) in the run. `game`: MH Generations (the items that
    are its own); `mh4u`: MH4U's item names by id. `materials`: the rare materials of XX's monsters, read from XX
    (xx_materials.Materials; their keys in `ids` and `english` are (MATERIALS, English name))."""

    def __init__(self, records: Sequence[MonsterRecord], game: GenGame | GameSet | None, mh4u: Mapping[int, str],
                 rarities: Mapping[int, int] | None = None, materials: Materials | None = None):
        games = GameSet.wrap(game)
        self.records = {r.key: r for r in records}
        self.mh4u_ids = mh4u_item_ids(mh4u)
        self.mh4u_rarities = mh4u_item_rarities() if rarities is None else rarities
        self.groups: dict[int, tuple[str, str]] = {}   # slot -> (monster, rank) of each new material of his
        self.ids: dict[tuple[str, str], int] = {}
        self.english: dict[tuple[str, str], str] = {}
        self.new: dict[int, NewItem] = {}   # slot -> record, names, descriptions
        taken: dict[int, str] = {}
        for record in records:
            slot = record.slot
            ids = item_ids(record)
            for spec in record.items:
                if not spec.is_new:
                    self.ids[record.key, spec.key] = spec.mh4u
                    self.english[record.key, spec.key] = spec.name or mh4u[spec.mh4u]
                    continue
                if slot in taken or slot >= MAX_ITEM_SLOTS:
                    raise CuratedError(f"{record.key}: item slot {slot} is taken or past {MAX_ITEM_SLOTS}")
                taken[slot] = f"{record.key}.{spec.key}"
                row = self._read(record.key, spec, games.of(record.source), record.source)
                self.english[record.key, spec.key] = row[1]["eng"]     # recipes find an item by its English name
                self.new[slot] = (row[0], record.renamed(row[1], "item"), row[2], row[3])
                if not spec.shared:
                    self.groups[slot] = (record.key, spec.rank)
                self.ids[record.key, spec.key] = ids[spec.key]
                slot += 1
        for item in materials.defined if materials else ():
            slot = materials.id(item) - FIRST_NEW_ID
            if slot in taken or not MAX_ITEM_SLOTS <= slot < MAX_NEW_ITEMS:
                raise CuratedError(f"xx_materials: {item.name}'s slot {slot} is taken or out of 0-{MAX_NEW_ITEMS - 1}")
            taken[slot] = item.name
            if item.mhgen in materials.records:   # the committed record: the same with XX's game or without it
                row = self._curated(materials.records[item.mhgen], item.name)
            else:
                row = self._read(MATERIALS, ItemSpec(item.name, item.rank, mhgen=item.mhgen, name=item.name),
                                 games.of("xx"), "xx")
            self.english[MATERIALS, item.name] = row[1]["eng"]
            self.new[slot] = (row[0], tidy_names(row[1], "item"), row[2], row[3])
            self.ids[MATERIALS, item.name] = FIRST_NEW_ID + slot
        for scrap in materials.scraps if materials else ():
            slot = materials.first_id + scrap.slot - FIRST_NEW_ID
            name = scrap.names["eng"]
            if slot in taken or not MAX_ITEM_SLOTS <= slot < MAX_NEW_ITEMS:
                raise CuratedError(f"xx_materials: {name}'s slot {slot} is taken or out of 0-{MAX_NEW_ITEMS - 1}")
            taken[slot] = name
            record = ItemRecord(rarity=scrap.rarity, sell=scrap.sell, buy=scrap.buy, carry=scrap.carry,
                                shape=scrap.shape, colour=scrap.colour)
            self.english[MATERIALS, name] = name
            self.new[slot] = (record, tidy_names(scrap.names, "item"), dict(scrap.descriptions), name)
            self.ids[MATERIALS, name] = FIRST_NEW_ID + slot

    @staticmethod
    def _curated(record: Mapping, name: str) -> NewItem:
        """An item of xx_item_records.json: record, names, descriptions, key."""
        values = {field: record[field] for field in ("rarity", "sell", "buy", "carry", "shape", "colour")}
        if record["names"]["eng"] != name:
            raise CuratedError(f"xx_item_records: {record['names']['eng']!r} is recorded for {name!r}")
        return ItemRecord(**values), dict(record["names"]), dict(record["descriptions"]), name

    @staticmethod
    def _read(monster: str, spec: ItemSpec, game: GenGame | None, source: str = "gen") -> NewItem:
        if spec.mhgen is not None:
            label = "MH XX" if source == "xx" else "MH Generations"
            if game is None:
                raise CuratedError(f"{monster}: item {spec.key} is {label}'s: its ROM is needed")
            item: GenItem = game.item(spec.mhgen)
            if spec.name and item.name != spec.name:
                raise CuratedError(f"{monster}: {label}'s item {spec.mhgen} is {item.name!r}, not {spec.name!r}")
            names, descriptions = dict(item.names), dict(item.descriptions)
            values = dict(rarity=item.rarity, sell=item.sell, buy=item.buy, carry=item.carry_max,
                          shape=item.icon_shape, colour=item.icon_color)
        else:
            names, descriptions = dict(spec.names), {"eng": spec.description or ""}
            values = {}
        for name in ("rarity", "sell", "buy", "carry", "shape", "colour"):
            if getattr(spec, name) is not None:
                values[name] = getattr(spec, name)
        return ItemRecord(**values), {lang: names.get(lang) or names["eng"] for lang in LANGUAGES}, \
            {lang: descriptions.get(lang) or descriptions.get("eng", "") for lang in LANGUAGES}, spec.key

    def slots(self) -> list[ItemRecord | None]:
        """`patch_items`' records: slot i is item 0x791 + i, None where no monster in the run has an item."""
        if not self.new:
            return []
        return [self.new[s][0] if s in self.new else None for s in range(max(self.new) + 1)]

    def slot_groups(self) -> list[int | None]:
        """For each slot of `slots()`, the "ever obtained" group its item belongs to, or None: every new material of a
        monster and rank shares one group (the Smithy's gate on one of them opens when any is obtained,
        equipment/new_gear/new_items.patch_items). The number is fixed by the monster's place in `curated.ORDER` and the
        rank, so it does not depend on which monsters are on."""
        if not self.new:
            return []
        out: list[int | None] = []
        for slot in range(max(self.new) + 1):
            where = self.groups.get(slot)
            out.append(None if where is None else ORDER.index(where[0]) * len(RANKS) + RANKS.index(where[1]))
        return out

    def rarity(self, item: int) -> int:
        """The rarity of an item as the game shows it (1-10): a new item's record, else MH4U's table; 1 if unknown."""
        if item >= FIRST_NEW_ID:
            return self.new[item - FIRST_NEW_ID][0].rarity
        return self.mh4u_rarities.get(item, 1)

    def id(self, monster: str, key: str) -> int:
        return self.ids[monster, key]

    def new_ids(self, monster: str) -> list[int]:
        """The ids of the monster's own new items, in curated order."""
        return [self.ids[monster, i.key] for i in self.records[monster].items if i.is_new]

    def all_ids(self, monster: str) -> list[int]:
        return [self.ids[monster, i.key] for i in self.records[monster].items]

    def texts(self):
        """(item id, names, descriptions) of every new item, by language."""
        for slot in sorted(self.new):
            _, names, descriptions, _ = self.new[slot]
            yield FIRST_NEW_ID + slot, names, descriptions

    # ---- names -> ids -------------------------------------------------------------------------------------

    def resolve(self, monster: str, name: str, substitutes: Mapping[str, str | None] | None = None) -> int | None:
        """The item an MH Generations item (or MHGU's) of English name `name` is in the monster's recipes: his own
        item of that name; else the curated substitute (an MH4U item name, one of his own as "@key", None to drop
        it: `substitutes` first, then the record's); else the MH4U item of that name. None means dropped; an unknown
        name raises."""
        record = self.records[monster]
        for spec in record.items:
            if self.english[monster, spec.key] == name:
                return self.ids[monster, spec.key]
        table = {**record.substitutes, **(substitutes or {})}
        if name in table:
            target = table[name]
            if target is None:
                return None
            if target.startswith("@"):
                return self.ids[monster, target[1:]]
            name = target
        found = self.mh4u_ids.get(name.lower())
        if found is None:
            raise CuratedError(f"{monster}: the item {name!r} is neither his, nor substituted, nor MH4U's")
        return found

    def flatten(self, monster: str, recipe: GenRecipe, gear: MonsterGear, keep_scraps: bool = False,
                substitutes: Mapping[str, str | None] | None = None) -> Flat:
        """`recipe` (MH Generations') as MH4U's: the unlock item first and gating, scraps (unless `keep_scraps`, the
        Felyne's), armor spheres and the category slot left out, the rest resolved (`resolve`, with `substitutes`),
        equal ones summed."""
        merged: dict[int, int] = {}
        unlock: int | None = None
        for material in recipe.materials:
            item = gear.items[material.item]
            if item.kind == "sphere" or (item.kind == "scrap" and not keep_scraps):
                continue
            if material.role == "scrap" and not keep_scraps:
                continue
            target = self.resolve(monster, item.name, substitutes)
            if target is None:
                continue
            merged[target] = merged.get(target, 0) + material.qty
            if material.role == "unlock" and unlock is None:
                unlock = target
        order = sorted(merged, key=lambda i: i != unlock)        # the gate first, the others as MHGen lists them
        return Flat(tuple((i, merged[i]) for i in order[:4]), unlock is not None and unlock in order[:4])

    def flatten_forge(self, monster: str, recipe: GenRecipe, gear: MonsterGear, rank: str,
                      promote: Mapping[str, str], substitutes: Mapping[str, str | None] | None = None) -> Flat:
        """The recipe a rank's first weapon is forged from when the original game cannot create it: level I's create
        `recipe` with each material moved to `rank`'s version (`promote`: English name to English name; a material with
        no entry stays), scraps, armor spheres and the category slot left out. The first material, the Smithy's gate, is
        the first of the monster's own materials of that rank. Raises CuratedError when none is."""
        merged: dict[int, int] = {}
        for material in recipe.materials:
            item = gear.items[material.item]
            if item.kind in ("sphere", "scrap") or material.role == "scrap":
                continue
            target = self.resolve(monster, promote.get(item.name, item.name), substitutes)
            if target is not None:
                merged[target] = merged.get(target, 0) + material.qty
        own = self._own(monster, rank)
        order = sorted(merged, key=lambda i: i not in own)
        if not order or order[0] not in own:
            raise CuratedError(f"{monster}: the {rank} rank forge recipe has no material of his of that rank: add "
                               "the missing ones to weapons.promote")
        return Flat(tuple((i, merged[i]) for i in order[:4]), True)

    def _own(self, monster: str, rank: str) -> set[int]:
        """The ids of the monster's own materials of `rank` (the shared items are not his)."""
        return {self.ids[monster, spec.key] for spec in self.records[monster].items
                if not spec.shared and spec.rank == rank}

    def gate_on_own(self, monster: str, flat: Flat, rank: str) -> Flat:
        """`flat` with the first of the monster's own materials of `rank` first and gating: the recipe a line is forged
        from when the original game reaches it only by upgrading another weapon (XX's Hammer, `WeaponLine.start_recipe`)
        has no unlock item to gate it. Raises CuratedError when it holds none of his of that rank."""
        own = self._own(monster, rank)
        order = sorted((item for item, _ in flat.materials), key=lambda i: i not in own)
        if not order or order[0] not in own:
            raise CuratedError(f"{monster}: the {rank} rank forge recipe holds no material of his of that rank")
        quantity = dict(flat.materials)
        return Flat(tuple((item, quantity[item]) for item in order), True)

    def parse(self, monster: str, terms: Sequence[tuple[str, int, bool]],
              substitutes: Mapping[str, str | None] | None = None) -> Flat:
        """A recipe written in the curated file (parse_recipe), or MHGU's (name, quantity), as a Flat."""
        merged: dict[int, int] = {}
        gate: int | None = None
        for name, qty, gated in terms:
            target = self.resolve(monster, name, substitutes)
            if target is None:
                continue
            merged[target] = merged.get(target, 0) + qty
            if gated:
                gate = target
        order = sorted(merged, key=lambda i: i != gate)
        return Flat(tuple((i, merged[i]) for i in order[:4]), gate is not None)


def _fit(text: str, lines: int) -> str:
    try:
        return fit_description(text, lines=lines)
    except NewTextError:
        pass
    words = text.replace("\r\n", " ").replace("\n", " ").split()
    while len(words) > 1:
        words.pop()
        try:
            return fit_description(" ".join(words), lines=lines)
        except NewTextError:
            continue
    return words[0] if words else ""


def item_texts(book: ItemBook) -> CommonTexts:
    """The names and descriptions of every new item of `book`."""
    texts = CommonTexts()
    for item_id, names, descriptions in book.texts():
        texts.name("item", item_id, names)
        texts.description("item", item_id, fitted(descriptions, 4))
    return texts


def fitted(texts: Mapping[str, str], lines: int) -> dict[str, str]:
    """Descriptions that fit the game's lines: a text too long loses its last words until it does."""
    return {lang: _fit(texts.get(lang) or texts["eng"], lines) for lang in LANGUAGES}
