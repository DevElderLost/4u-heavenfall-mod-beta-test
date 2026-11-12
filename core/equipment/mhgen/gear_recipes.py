"""MH Generations' recipes (arc/village/blacksmith.arc).

A **create** row (weapon line, armor piece, Felyne piece) lists up to 8 slots of (u16 item, u8 quantity, u8 flag):
slot 0 is the *unlock item* (flag 2: it opens the recipe in the Smithy), 1-4 the materials, 5 the *scrap*, 6-7 spare. An
**upgrade** row (to one level of a weapon line or armor series) lists 4 (u16 item, u8 quantity), a *category* (u16
category id and u16 points: "N points of any item of this monster", see gear_data.GenItemCategory) and 4 more (u16 item,
u8 quantity) that are scraps. MH4U has none of the unlock item, the scrap, the category or the armor spheres: the
integration flattens them (`GenMaterial.role`, gear_data's `item_kind`, `scrap_exchange`, `category_members`).
"""

import struct
from dataclasses import dataclass

ROLES = ("unlock", "material", "scrap", "extra")
SCRAP_SLOT = 5
UNLOCK_FLAG = 2


@dataclass(frozen=True)
class GenMaterial:
    item: int
    qty: int
    role: str = "material"    # ROLES
    flag: int = 0


@dataclass(frozen=True)
class GenRecipe:
    kind: str                  # "create" or "upgrade"
    level: int                 # the level an upgrade leads to; 1 for a create row
    row: int                   # row in its table
    available: int             # a create row's availability word (0: always; a ticket or event), 0 for upgrades
    materials: tuple[GenMaterial, ...]
    category: int = 0          # item category (0: none) ...
    category_points: int = 0   # ... and the points of its items the upgrade asks

    @property
    def empty(self) -> bool:
        return not self.materials and not self.category

    def with_role(self, role: str) -> tuple[GenMaterial, ...]:
        return tuple(m for m in self.materials if m.role == role)


def _create_entries(data: bytes, start: int, count: int) -> tuple[GenMaterial, ...]:
    out = []
    for slot in range(count):
        item, qty, flag = struct.unpack_from("<HBB", data, start + 4 * slot)
        if item:
            role = ("unlock" if flag == UNLOCK_FLAG else "scrap" if slot == SCRAP_SLOT else
                    "extra" if slot > SCRAP_SLOT else "material")
            out.append(GenMaterial(item, qty, role, flag))
    return tuple(out)


def _upgrade_entries(data: bytes, start: int, role: str) -> tuple[GenMaterial, ...]:
    out = []
    for slot in range(4):
        item, qty = struct.unpack_from("<HB", data, start + 3 * slot)
        if item:
            out.append(GenMaterial(item, qty, role))
    return tuple(out)


def weapon_create(row: int, data: bytes, xx: bool = False) -> GenRecipe:
    """A `weaponCreateWNN` row (36 bytes): u16 line, u16 availability, 8 slots at +4. XX's (38 bytes) starts with a
    u16 kind (1: the line's ordinary create row; 2-8: extra rows of some lines, a start at a later rank that asks
    Commendation G in the G rank ones, not decoded: `create_kind`), so the line is at +2, the availability at +4 and
    the slots at +6."""
    if xx:
        return GenRecipe("create", 1, row, struct.unpack_from("<H", data, 4)[0], _create_entries(data, 6, 8))
    return GenRecipe("create", 1, row, struct.unpack_from("<H", data, 2)[0], _create_entries(data, 4, 8))


def create_line(data: bytes, xx: bool = False) -> int:
    """The line a `weaponCreateWNN` row creates."""
    return struct.unpack_from("<H", data, 2 if xx else 0)[0]


def create_kind(data: bytes, xx: bool = False) -> int:
    """XX's kind of a create row (1: the line's ordinary row; 2-8: the extra rows of `weapon_create`); Generations has
    only the ordinary rows, kind 1."""
    return struct.unpack_from("<H", data, 0)[0] if xx else 1


def armor_create(row: int, data: bytes) -> GenRecipe:
    """An `armorCreateA0p` row (42 bytes): u16 blademaster and gunner series, u32, u16 availability at +8, 8 slots at
    +10."""
    return GenRecipe("create", 1, row, struct.unpack_from("<H", data, 8)[0], _create_entries(data, 10, 8))


def _upgrade(row: int, data: bytes, level: int, materials: int, category: int, extra: int) -> GenRecipe:
    cat, points = struct.unpack_from("<HH", data, category)
    return GenRecipe("upgrade", level, row, 0, _upgrade_entries(data, materials, "material")
                     + _upgrade_entries(data, extra, "scrap"), cat, points if cat else 0)


def weapon_upgrade(row: int, data: bytes) -> GenRecipe:
    """A `weaponProcessWNN` row (32 bytes): u16 line, u16 level, 4 items at +4, category at +16, 4 scraps at +20."""
    return _upgrade(row, data, struct.unpack_from("<H", data, 2)[0], 4, 16, 20)


def armor_upgrade(row: int, data: bytes) -> GenRecipe:
    """An `armorProcessA00` row (38 bytes): u16 blademaster and gunner series, u32, u16 level at +8, 4 items at +10,
    category at +22, 4 scraps at +26."""
    return _upgrade(row, data, struct.unpack_from("<H", data, 8)[0], 10, 22, 26)


def felyne_create(data: bytes, start: int, count: int) -> tuple[GenMaterial, ...]:
    """`count` slots of a Felyne create row from `start` (armor: head at +12, body at +24, three slots each; weapon:
    six slots at +12). The roles are all "material": the Felyne rows keep the scrap in an ordinary slot."""
    return tuple(GenMaterial(m.item, m.qty, "material", m.flag) for m in _create_entries(data, start, count))
