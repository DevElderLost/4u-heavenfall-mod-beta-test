"""Equipment as the randomizer sees it: real pieces, their rank, recipes and upgrade tree."""

import json
from dataclasses import dataclass, field
from functools import cache

from core.game.data.paths import GENERATED_DIR
from core.equipment.tables.layout import ARMOR_PARTS, WEAPON_CLASSES
from core.equipment.tables.records import CreateRecipe, UpgradeRecipe
from core.equipment.tables.tables import EquipmentTables
from core.equipment.tables.records import Record

LOW, HIGH, G = 1, 2, 3
RANK_NAMES = {LOW: "low rank", HIGH: "high rank", G: "G rank"}
CLASS_BY_KEY = {wc.key: wc for wc in WEAPON_CLASSES}
PART_BY_KEY = {part.key: part for part in ARMOR_PARTS}


def rank_of(rarity: int) -> int:
    if rarity <= 3:
        return LOW
    if rarity <= 7:
        return HIGH
    return G


@cache
def load_equipment_names() -> dict:
    return json.loads((GENERATED_DIR / "equipment_names.json").read_text(encoding="utf-8"))


def is_real_name(name: str) -> bool:
    """Index 0 is "(None)"; unused slots are called "dummyNNN" or "DUMMY"."""
    return bool(name) and name not in ("(None)", "DUMMY") and not name.lower().startswith("dummy")


@dataclass(eq=False)
class Piece:
    kind: str                 # "weapon" or "armor"
    group: str                # weapon class key or armor part key
    index: int                # id in its table / name list
    name: str
    record: Record
    rank: int
    original: dict = field(default_factory=dict)   # field values before any change
    create: CreateRecipe | None = None
    upgrade: UpgradeRecipe | None = None            # materials to upgrade into this weapon
    parent: int | None = None                       # weapon it is upgraded from (first one)
    parents: list[int] = field(default_factory=list)  # every weapon it can be upgraded from
    children: list[int] = field(default_factory=list)
    original_materials: list[tuple[int, int]] = field(default_factory=list)  # create + upgrade, before changes

    @property
    def rarity(self) -> int:
        return self.original["rarity_index"] + 1


@dataclass
class Catalog:
    tables: EquipmentTables
    weapons: dict[str, dict[int, Piece]]   # class key -> id -> real weapon
    armor: dict[str, dict[int, Piece]]     # part key -> id -> real armor piece
    palico: dict = field(default_factory=dict)  # "weapon"/"head"/"body" -> id -> PalicoPiece (palico.py)

    def pieces(self):
        for group in (*self.weapons.values(), *self.armor.values()):
            yield from group.values()


def build_catalog(tables: EquipmentTables, names: dict | None = None) -> Catalog:
    """The catalog of `tables`; `names` (default: the game's, equipment_names.json) must reach the new pieces'
    ids too when the tables have any (ported_gear.plan.GearPlan.equipment_names)."""
    names = names or load_equipment_names()
    weapons: dict[str, dict[int, Piece]] = {}
    for wc in WEAPON_CLASSES:
        weapons[wc.key] = {}
        for index, record in enumerate(tables.weapons[wc.key]):
            name = names["weapons"][wc.key][index]
            if is_real_name(name):
                values = record.values()
                weapons[wc.key][index] = Piece("weapon", wc.key, index, name, record,
                                               rank_of(values["rarity_index"] + 1), values)
        for index, upgrade in enumerate(tables.upgrades[wc.key]):
            piece = weapons[wc.key].get(index)
            if piece:
                piece.upgrade = upgrade if upgrade.materials else None
                piece.children = [c for c in upgrade.children if c in weapons[wc.key]]
        for piece in weapons[wc.key].values():
            for child in piece.children:
                weapons[wc.key][child].parents.append(piece.index)
                if weapons[wc.key][child].parent is None:
                    weapons[wc.key][child].parent = piece.index

    armor: dict[str, dict[int, Piece]] = {}
    for part in ARMOR_PARTS:
        armor[part.key] = {}
        for index, record in enumerate(tables.armor[part.key]):
            name = names["armor"][part.key][index]
            if is_real_name(name):
                values = record.values()
                values["skills"] = record.skills
                armor[part.key][index] = Piece("armor", part.key, index, name, record,
                                               rank_of(values["rarity_index"] + 1), values)

    by_type = {wc.recipe_type: weapons[wc.key] for wc in WEAPON_CLASSES}
    by_type.update({part.recipe_type: armor[part.key] for part in ARMOR_PARTS})
    for recipe in (*tables.weapon_recipes, *tables.armor_recipes):
        piece = by_type.get(recipe["equipment_type"], {}).get(recipe["equipment_id"])
        if piece and piece.create is None:
            piece.create = recipe
    catalog = Catalog(tables, weapons, armor)
    for piece in catalog.pieces():
        piece.original_materials = [m for r in (piece.create, piece.upgrade) if r is not None for m in r.materials]
    return catalog
