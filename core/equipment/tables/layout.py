"""Where the equipment tables live in code.bin (EUR 0004000000126100).

Offsets are file offsets in the decompressed executable. They are identical in
the base game and in the update (0004000E00126100).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WeaponClass:
    key: str
    name: str
    recipe_type: int          # equipment type in the create recipe table
    stats_offset: int
    count: int                # records = names in the class's LMD name list
    upgrade_offset: int
    upgrade_count: int
    attack_multiplier: float = 1.0   # displayed attack = stored (true) attack x multiplier
    ranged: bool = False
    upgrade_materials: int = 4

    @property
    def has_sharpness(self) -> bool:
        return not self.ranged

    @property
    def has_element(self) -> bool:
        """Bowguns use ammo instead: their element fields are always empty."""
        return self.key not in ("light_bowgun", "heavy_bowgun")

    @property
    def record_size(self) -> int:
        return 40 if self.ranged else 24

    @property
    def upgrade_record_size(self) -> int:
        return 24 if self.upgrade_materials == 4 else 12


@dataclass(frozen=True)
class ArmorPart:
    key: str
    name: str
    recipe_type: int
    offset: int
    count: int

    record_size = 40


WEAPON_CLASSES: tuple[WeaponClass, ...] = (
    WeaponClass("great_sword", "Great Sword", 7, 0xE70850, 246, 0xE61FEA, 228, 4.8),
    WeaponClass("sword_and_shield", "Sword & Shield", 8, 0xE71F60, 247, 0xE6354A, 235, 1.4),
    WeaponClass("hammer", "Hammer", 9, 0xE73688, 247, 0xE64B52, 231, 5.2),
    WeaponClass("lance", "Lance", 10, 0xE74DB0, 216, 0xE660FA, 200, 2.3),
    WeaponClass("long_sword", "Long Sword", 13, 0xE761F0, 227, 0xE6870A, 207, 3.3),
    WeaponClass("switch_axe", "Switch Axe", 14, 0xE77738, 198, 0xE69A72, 182, 5.4),
    WeaponClass("gunlance", "Gunlance", 15, 0xE789C8, 221, 0xE673BA, 206, 2.3),
    WeaponClass("dual_blades", "Dual Blades", 17, 0xE79E80, 229, 0xE6AB82, 214, 1.4),
    WeaponClass("hunting_horn", "Hunting Horn", 18, 0xE7B3F8, 185, 0xE6BF92, 171, 5.2),
    WeaponClass("insect_glaive", "Insect Glaive", 19, 0xE7C550, 160, 0xE569AC, 134, 3.1, upgrade_materials=2),
    WeaponClass("charge_blade", "Charge Blade", 20, 0xE7D450, 125, 0xE6CF9A, 101, 3.6),
    WeaponClass("heavy_bowgun", "Heavy Bowgun", 12, 0xE7E00C, 157, 0xE6D912, 142, 1.5, ranged=True),
    WeaponClass("light_bowgun", "Light Bowgun", 11, 0xE7F894, 185, 0xE6E662, 172, 1.3, ranged=True),
    WeaponClass("bow", "Bow", 16, 0xE8157C, 206, 0xE6F682, 190, 1.2, ranged=True),
)

ARMOR_PARTS: tuple[ArmorPart, ...] = (
    ArmorPart("head", "Head", 5, 0xE835AC, 987),
    ArmorPart("body", "Body", 1, 0xE8CFE4, 972),
    ArmorPart("arms", "Arms", 2, 0xE967C4, 956),
    ArmorPart("waist", "Waist", 3, 0xE9FD24, 956),
    ArmorPart("legs", "Legs", 4, 0xEA9284, 964),
)

@dataclass(frozen=True)
class PalicoTable:
    """Felyne gear: one stats table and one create recipe table (no upgrades), as the game's readers address
    them. Both are the game's own, in the clean
    executable: `recipe_count` records, the (None) piece's first, then a record whose first byte is 0xFF. Gear added to
    the game moves them (equipment/new_gear/new_felyne.py, which also finds them again)."""
    key: str
    name: str
    offset: int
    count: int
    record_size: int
    recipe_offset: int
    recipe_count: int
    recipe_type: int          # the recipes' type byte: 0 body, 1 head, 2 weapon


PALICO_TABLES: tuple[PalicoTable, ...] = (
    PalicoTable("weapon", "Weapon", 0xE58C04, 179, 20, 0xE5CFE8, 170, 2),
    PalicoTable("head", "Head", 0xE5A4E0, 168, 16, 0xE5B128, 161, 1),
    PalicoTable("body", "Body", 0xE59A00, 174, 16, 0xE5C058, 165, 0),
)

ARMOR_RECIPES = (0xE400FC, 3039)    # (offset, records), 24 bytes each
WEAPON_RECIPES = (0xE51DFC, 565)
RECIPE_RECORD_SIZE = 24
SHARPNESS = (0xE581E4, 119)         # 7 x u16 per profile
SHARPNESS_RECORD_SIZE = 14

CODE_SIZE = 16_261_120
