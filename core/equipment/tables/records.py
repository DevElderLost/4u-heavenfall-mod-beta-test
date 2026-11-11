"""Equipment records as views over their raw bytes.

Every record keeps all of its original bytes; only the named fields are
decoded, so writing a record back reproduces unknown data unchanged.
"""

import struct

ELEMENT_TYPES = {1: "Fire", 2: "Water", 3: "Thunder", 4: "Dragon", 5: "Ice"}
STATUS_TYPES = {1: "Poison", 2: "Paralysis", 3: "Sleep", 4: "Blast"}
SHARPNESS_COLORS = ("red", "orange", "yellow", "green", "blue", "white", "purple")
RESISTANCES = ("fire", "water", "thunder", "dragon", "ice")


class Record:
    FIELDS: dict[str, tuple[int, str]] = {}

    def __init__(self, offset: int, data: bytes):
        self.offset = offset
        self.data = bytearray(data)

    def __getitem__(self, name: str):
        position, fmt = self.FIELDS[name]
        return struct.unpack_from(fmt, self.data, position)[0]

    def __setitem__(self, name: str, value) -> None:
        position, fmt = self.FIELDS[name]
        struct.pack_into(fmt, self.data, position, value)

    def values(self) -> dict:
        return {name: self[name] for name in self.FIELDS}


class MeleeWeapon(Record):
    """24-byte slice of a melee table from `start + id * 24`. Element/status values are stored / 10; negative =
    needs Awaken. The game's own record of the weapon begins 4 bytes in (`GameMeleeWeapon`): these fields are the
    same bytes, and the first four bytes of the slice (sort key, flags, sound variant) are the previous weapon's."""
    FIELDS = {
        "model": (0x04, "<H"), "sharpness_profile": (0x06, "B"), "sharpness_level": (0x07, "B"),
        "price": (0x08, "<I"), "attack": (0x0C, "<H"), "defense": (0x0E, "B"), "affinity": (0x0F, "b"),
        "element_type": (0x10, "B"), "element_value": (0x11, "b"),
        "status_type": (0x12, "B"), "status_value": (0x13, "b"),
        "slots": (0x14, "B"), "rarity_index": (0x17, "B"),
    }


class RangedWeapon(Record):
    """40-byte record (bows and bowguns). +0x02 is the sort key, not the model (`FullRangedWeapon` has the rest)."""
    FIELDS = {
        "model": (0x00, "<H"), "rarity_index": (0x04, "B"), "price": (0x08, "<I"), "attack": (0x0C, "<H"),
        "defense": (0x0E, "B"), "slots": (0x10, "B"), "affinity": (0x11, "b"),
        "element_type": (0x12, "B"), "element_value": (0x13, "b"),
        "status_type": (0x14, "B"), "status_value": (0x15, "b"),
    }


class Armor(Record):
    """40-byte record. Price is stored halved."""
    FIELDS = {
        "model_m": (0x00, "<H"), "model_f": (0x02, "<H"), "rarity_index": (0x05, "B"), "defense": (0x07, "B"),
        "price_half": (0x08, "<I"), "res_fire": (0x0C, "b"), "res_water": (0x0D, "b"),
        "res_thunder": (0x0E, "b"), "res_dragon": (0x0F, "b"), "res_ice": (0x10, "b"), "slots": (0x11, "B"),
    }
    SKILLS_AT = 0x1E
    SKILL_SLOTS = 5
    # A worn piece whose defense or a resistance reaches these is flagged as tampered and quests
    # are refused.
    DEFENSE_LIMIT = 180
    RESISTANCE_LIMIT = 10
    # Upgrades: levels per stage at 0x14-0x1B, defense per level by stage; flag 0x10 picks the small steps.
    LEVELS_AT = 0x14
    MAX_LEVEL = 63
    DEFENSE_STEPS = (2, 3, 4, 5, 4, 2, 4, 2)
    DEFENSE_STEPS_SMALL = (2, 2, 3, 3, 2, 1, 3, 1)

    @property
    def defense_gain(self) -> int:
        """Defense the piece gains from its base to its maximum upgrade level."""
        steps = self.DEFENSE_STEPS_SMALL if self.data[0x04] & 0x10 else self.DEFENSE_STEPS
        levels = self.MAX_LEVEL
        gain = 0
        for stage, count in enumerate(self.data[self.LEVELS_AT:self.LEVELS_AT + 8]):
            taken = min(count, levels)
            gain += taken * steps[stage]
            levels -= taken
        return gain

    @property
    def skills(self) -> list[tuple[int, int]]:
        """[(skill tree id, points)], empty slots (tree 0) left out."""
        raw = struct.unpack_from(f"<{'Bb' * self.SKILL_SLOTS}", self.data, self.SKILLS_AT)
        return [(raw[i], raw[i + 1]) for i in range(0, len(raw), 2) if raw[i]]

    @skills.setter
    def skills(self, skills: list[tuple[int, int]]) -> None:
        if len(skills) > self.SKILL_SLOTS:
            raise ValueError(f"at most {self.SKILL_SLOTS} skills fit in an armor piece")
        flat = [value for pair in skills for value in pair] + [0] * (2 * (self.SKILL_SLOTS - len(skills)))
        struct.pack_into(f"<{'Bb' * self.SKILL_SLOTS}", self.data, self.SKILLS_AT, *flat)


class PalicoWeapon(Record):
    """20 bytes, naturally aligned. Element value / 10; rarity as shown (1-10); `sort_key` orders the box (the
    keys of a table are 0..count-1, each once). `flag` (0 or 1) and `motion` (0-17, the Felyne's pose in the
    lobby) are read by the model code and not understood further; +5 is 1 for four pieces."""
    FIELDS = {
        "model": (0x00, "<H"), "flag": (0x02, "B"), "element_type": (0x03, "B"), "attack": (0x04, "<H"),
        "ranged_attack": (0x06, "<H"), "affinity": (0x08, "b"), "element_value": (0x0A, "<H"),
        "motion": (0x0C, "B"), "defense": (0x0D, "B"), "rarity": (0x0E, "B"), "sort_key": (0x0F, "B"),
        "price": (0x10, "<I"),
    }


class PalicoArmor(Record):
    """16 bytes. Resistances are per piece (a set's are head + body); rarity as shown (1-10). `bonus` (0-20; the
    sum over head and body is the stat the Felyne's equipment screen reads as 11) and, in a head, `kind` (0-5,
    read by four model routines) are not understood further."""
    FIELDS = {
        "model": (0x00, "<H"), "res_fire": (0x02, "b"), "res_water": (0x03, "b"), "res_thunder": (0x04, "b"),
        "res_ice": (0x05, "b"), "res_dragon": (0x06, "b"), "bonus": (0x07, "B"), "defense": (0x08, "B"),
        "kind": (0x09, "B"), "rarity": (0x0A, "B"), "sort_key": (0x0B, "B"), "price": (0x0C, "<I"),
    }


class _Materials(Record):
    MATERIALS_AT = 0
    CAPACITY = 4

    @property
    def materials(self) -> list[tuple[int, int]]:
        pairs = struct.unpack_from(f"<{self.CAPACITY * 2}H", self.data, self.MATERIALS_AT)
        return [(pairs[i], pairs[i + 1]) for i in range(0, len(pairs), 2) if pairs[i]]

    @materials.setter
    def materials(self, materials: list[tuple[int, int]]) -> None:
        if len(materials) > self.CAPACITY:
            raise ValueError(f"at most {self.CAPACITY} materials fit in this recipe")
        flat = [value for pair in materials for value in pair]
        flat += [0] * (self.CAPACITY * 2 - len(flat))
        struct.pack_into(f"<{self.CAPACITY * 2}H", self.data, self.MATERIALS_AT, *flat)


class CreateRecipe(_Materials):
    """24 bytes: equipment type (low byte) + flag, equipment id, 4 materials, 2 unknown u16."""
    MATERIALS_AT = 4
    FIELDS = {"equipment_type": (0x00, "B"), "equipment_id": (0x02, "<H")}


class UpgradeRecipe(_Materials):
    """24 bytes: 4 materials to upgrade into this weapon, then the 4 weapons it upgrades into."""
    CHILDREN_AT = 16
    CHILDREN = 4

    @property
    def children(self) -> list[int]:
        return [c for c in struct.unpack_from(f"<{self.CHILDREN}H", self.data, self.CHILDREN_AT) if c]


class ShortUpgradeRecipe(UpgradeRecipe):
    """12 bytes (Insect Glaive): 2 materials, the weapon it upgrades into, then a u16 (kinsect level?)."""
    CAPACITY = 2
    CHILDREN_AT = 8
    CHILDREN = 1


class SharpnessProfile(Record):
    """Cumulative end of each color (red ... purple), in hits x 5."""

    @property
    def ends(self) -> list[int]:
        return list(struct.unpack_from("<7H", self.data, 0))

    @ends.setter
    def ends(self, ends: list[int]) -> None:
        struct.pack_into("<7H", self.data, 0, *ends)

    @property
    def lengths(self) -> list[int]:
        ends = self.ends
        return [ends[0]] + [ends[i] - ends[i - 1] for i in range(1, 7)]

    @lengths.setter
    def lengths(self, lengths: list[int]) -> None:
        total, ends = 0, []
        for length in lengths:
            total += length
            ends.append(total)
        self.ends = ends


class GameMeleeWeapon(Record):
    """24 bytes: a melee weapon's record as the game reads it.

    The game's pointer into a melee table is `start + 4` (`MeleeWeapon` and `EquipmentTables` slice the table
    from `start`, so their records begin 4 bytes before the game's). The fields up to the rarity are the same bytes
    in both views (offset +4 there); the sort key, the flags and the sound variant are the last four bytes of the
    game's record, which are the first four of the next slice (the last weapon's are the next table's first bytes).
    """
    FIELDS = {
        "model": (0x00, "<H"), "sharpness_profile": (0x02, "B"), "sharpness_level": (0x03, "B"),
        "price": (0x04, "<I"), "attack": (0x08, "<H"), "defense": (0x0A, "B"), "affinity": (0x0B, "b"),
        "element_type": (0x0C, "B"), "element_value": (0x0D, "b"),
        "status_type": (0x0E, "B"), "status_value": (0x0F, "b"),
        "slots": (0x10, "B"), "class_byte": (0x11, "B"), "colour": (0x12, "B"), "rarity_index": (0x13, "B"),
        "sort_key": (0x14, "<H"), "flags": (0x16, "B"), "sound_variant": (0x17, "B"),
    }


class FullRangedWeapon(RangedWeapon):
    """40 bytes: a bow's or bowgun's record with every field decoded. Ranged tables are not shifted. Bowgun and bow
    differ in what four fields mean: `deviation` is the
    bow's arc icon, `reload` the bow's charge levels, `shot_1..4` the bow's shot type per charge level (`shot_5`
    is always 0xFF) and the bowgun's special and rapid-fire ammo slots (-1 = empty)."""
    FIELDS = {
        **RangedWeapon.FIELDS,
        "sort_key": (0x02, "<H"), "recoil": (0x05, "B"), "deviation": (0x06, "B"), "ammo_row": (0x07, "B"),
        "reload": (0x0F, "B"),
        "shot_1": (0x16, "b"), "shot_2": (0x17, "b"), "shot_3": (0x18, "b"), "shot_4": (0x19, "b"),
        "shot_5": (0x1A, "b"), "colour": (0x1B, "B"), "flags": (0x1C, "B"), "sound_variant": (0x1D, "B"),
        "ammo_mask": (0x20, "<Q"),
    }
