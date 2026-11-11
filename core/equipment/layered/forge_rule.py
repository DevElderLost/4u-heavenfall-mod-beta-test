"""The Smithy's forge rule for a look: when does the forge offer a piece that wears it.

A look is offered when any piece wearing its models is. A piece is, in the forge's own terms (`FUN_009be7bc`):

* with a create recipe whose flag byte or gate byte is 1: always;
* with one whose gate byte is 2: once its first material has been seen, for a gender the piece is made for;
* a weapon, once any of its parents in the upgrade tree has been had once (the save's "had it once" bit);
* with neither a recipe nor a parent: once it has been had itself (its own bit), so that a relic look appears when the
  piece does.

A condition is a short text in the generated look lists and a u16 word in the executable (`word`):
"always", "i<item>" (the first material seen), "i<item>m" / "i<item>f" (seen, and the piece is for that gender only) and
"g<bit>" (the gear bit, `FUN_00c1fe40`). The generated file keeps them as texts.
"""

from collections import defaultdict
from collections.abc import Iterable

from core.equipment.tables.layout import ARMOR_PARTS, WEAPON_CLASSES

# The i16 table at 0xFD0918 (file offset 0xED0918) of the update's executable: the first bit of each equipment type in
# the save's "had it once" array (data + 0xCE14); the bit of a piece is GEAR_BASE[type] + its id.
GEAR_BASE_AT = 0xFD0918
GEAR_BASE = (0, 0, 1040, 2070, 3120, 4170, 5200, 5220, 5520, 5830, 6130, 6410, 6650, 6880, 7160, 7420, 7700, 7950,
             8230, 8470, 8670)
ALWAYS = "always"
ALWAYS_WORD = 0xFFFF
GEAR_FLAG, MALE_ONLY, FEMALE_ONLY = 0x8000, 0x4000, 0x2000     # a condition word's bits (item in bits 0-12)
ITEM_MASK = 0x1FFF
MALE, FEMALE = 1, 2                                             # armor record +4
GATE_AT, GATE_SEEN = 0x14, 2                                    # a recipe's first gate byte; "seen" is 2


class ForgeRuleError(ValueError):
    pass


def gear_bit(equipment_type: int, piece: int) -> int:
    """The "had it once" bit of a piece (`FUN_00c1fe40`)."""
    bit = GEAR_BASE[equipment_type] + piece
    if bit >= GEAR_FLAG:
        raise ForgeRuleError(f"type {equipment_type} piece {piece}: bit {bit} does not fit a condition word")
    return bit


def condition_word(condition: str) -> int:
    """The u16 word of a condition text (see the module's docstring)."""
    if condition == ALWAYS:
        return ALWAYS_WORD
    kind, rest = condition[0], condition[1:]
    if kind == "g" and rest.isdigit():
        return GEAR_FLAG | gear_bit_checked(int(rest))
    if kind == "i" and rest.rstrip("mf").isdigit():
        item = int(rest.rstrip("mf"))
        if not 0 < item <= ITEM_MASK:
            raise ForgeRuleError(f"condition {condition!r}: the item does not fit 13 bits")
        return item | (MALE_ONLY if rest.endswith("m") else FEMALE_ONLY if rest.endswith("f") else 0)
    raise ForgeRuleError(f"unknown condition {condition!r}")


def gear_bit_checked(bit: int) -> int:
    if not 0 <= bit < GEAR_FLAG:
        raise ForgeRuleError(f"gear bit {bit} does not fit a condition word")
    return bit


def item_condition(item: int, gender: int = MALE | FEMALE) -> str:
    return f"i{item}" + ("m" if gender == MALE else "f" if gender == FEMALE else "")


def conditions_list(conditions: Iterable[str]) -> tuple[str, ...]:
    """The conditions of a look, without repeats: "always" alone when it is there, else items before bits."""
    found = set(conditions)
    if ALWAYS in found:
        return (ALWAYS,)
    return tuple(sorted(found, key=lambda c: (c[0] == "g", int("".join(ch for ch in c[1:] if ch.isdigit())), c)))


class ForgeRules:
    """The forge's rule for every armor piece and weapon of the equipment tables `tables` (EquipmentTables), by
    (part, id) and (class, id)."""

    def __init__(self, tables):
        self.tables = tables
        self._recipes: dict[tuple[int, int], list] = defaultdict(list)
        for recipe in (*tables.armor_recipes, *tables.weapon_recipes):
            if recipe.data[0] != 0xFF and recipe["equipment_id"]:
                self._recipes[recipe.data[0], recipe["equipment_id"]].append(recipe)
        self._parents: dict[str, dict[int, list[int]]] = {}
        for cls in WEAPON_CLASSES:
            parents = self._parents[cls.key] = defaultdict(list)
            for parent, record in enumerate(tables.upgrades[cls.key]):
                for child in record.children:
                    parents[child].append(parent)
        self._type = {part.key: part.recipe_type for part in ARMOR_PARTS}
        self._type.update({cls.key: cls.recipe_type for cls in WEAPON_CLASSES})
        self._palico: dict[tuple[str, int], list] = defaultdict(list)
        for key, recipes in tables.palico_recipes.items():
            for recipe in recipes:
                if recipe["equipment_id"]:
                    self._palico[key, recipe["equipment_id"]].append(recipe)

    @staticmethod
    def _from_list(recipes, gender: int) -> set[str]:
        found = set()
        for recipe in recipes:
            flag, gate = recipe.data[1], recipe.data[GATE_AT]
            if flag or gate in (0, 1):
                found.add(ALWAYS)
            elif gate == GATE_SEEN and recipe.materials:
                found.add(item_condition(recipe.materials[0][0], gender))
        return found

    def _from_recipes(self, kind: str, piece: int, gender: int) -> set[str]:
        return self._from_list(self._recipes[self._type[kind], piece], gender)

    def palico(self, kind: str, piece: int) -> set[str]:
        """The conditions of a Felyne piece (`kind` "weapon", "head" or "body"): its recipe's; it has no "had it once"
        bit, so a piece with no recipe gives none."""
        return self._from_list(self._palico[kind, piece], MALE | FEMALE)

    def armor(self, part: str, piece: int) -> set[str]:
        """The conditions of one armor piece (its id in the part's table)."""
        gender = self.tables.armor[part][piece].data[4] & (MALE | FEMALE)
        if not gender:
            return set()
        return self._from_recipes(part, piece, gender) or {f"g{gear_bit(self._type[part], piece)}"}

    def weapon(self, cls: str, piece: int) -> set[str]:
        """The conditions of one weapon (its id in the class' table)."""
        found = self._from_recipes(cls, piece, MALE | FEMALE)
        found |= {f"g{gear_bit(self._type[cls], parent)}" for parent in self._parents[cls].get(piece, ())}
        return found or {f"g{gear_bit(self._type[cls], piece)}"}
