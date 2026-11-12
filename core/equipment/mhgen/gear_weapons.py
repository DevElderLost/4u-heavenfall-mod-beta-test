"""MH Generations' weapons, decoded from its tables.

A weapon is a **line** (a row of `table\\weaponNNBaseData`: model, rarity, price, the lines it upgrades into) with 1 to
8 **levels** (rows of `table\\weaponNNLevelData`: attack, sharpness, element, slots, and per class the horn notes,
shells, phials, coatings, ammo). `NN` is 00 great sword, 01 sword and shield, 02 hammer, 03 lance, 04 heavy bowgun, 06
light bowgun, 07 long sword, 08 switch axe, 09 gunlance, 10 bow, 11 dual blades, 12 hunting horn, 13 insect glaive, 14
charge blade (no 05). Each line's recipes are in arc/village/blacksmith.arc (`weaponCreateWNN`, `weaponProcessWNN`);
the parsers here take bytes, `gear_data.GenGame` reads a line complete.

**MH XX's tables** (they are MH Generations Ultimate's, byte for byte) are the
same with these changes, carried by `WeaponKind` (`XX_KINDS`): the base record has one byte more at +10 (the line's
number of G rank levels, 3 in every line of Great Maccao), so everything after +9 moves by one (`shift`); a bowgun's
level record has a 33rd shell slot and a bow's a 12th coating; the ammo indexes moved by one (the ammo items are not
decoded for XX); a line holds its G rank levels after MH Generations' (`WeaponBase.g_levels`); a sharpness row has a
7th column (red .. white, purple) and its rows are not Generations' (the 164 rows are numbered anew).
"""

import struct
from collections.abc import Sequence
from dataclasses import dataclass, field

from core.equipment.mhgen.gear_recipes import GenRecipe, weapon_create, weapon_upgrade

ELEMENTS = {0: None, 1: "fire", 2: "water", 3: "thunder", 4: "dragon", 5: "ice", 6: "poison", 7: "paralysis",
    8: "sleep",
            9: "blast"}
PHIALS = {0: "power", 1: "element", 2: "paralysis", 3: "dragon", 4: "exhaust", 5: "poison", 6: "impact"}  # switch axe
CHARGE_PHIALS = {0: "impact", 1: "element"}                                                              # charge blade
SHELLS = {0: "normal", 1: "wide", 2: "long"}
ARC_SHOTS = {1: "focus", 2: "wide", 3: "blast"}
COATINGS = ("power1", "power2", "element1", "element2", "close_range", "poison", "paralysis", "sleep", "exhaust",
    "blast",
            "unknown10", "unknown11")   # the last is XX's only
SHELL_SLOTS = ("Normal S Lv1", "Normal S Lv2", "Normal S Lv3", "Pierce S Lv1", "Pierce S Lv2", "Pierce S Lv3",
               "Pellet S Lv1", "Pellet S Lv2", "Pellet S Lv3", "Crag S Lv1", "Crag S Lv2", "Crag S Lv3", "Clust S Lv1",
               "Clust S Lv2", "Clust S Lv3", "Flaming S Lv1", "Water S Lv1", "Thunder S Lv1", "Freeze S Lv1",
               "Dragon S Lv1", "Poison S Lv1", "Poison S Lv2", "Para S Lv1", "Para S Lv2", "Sleep S Lv1", "Sleep S Lv2",
               "Exhaust S Lv1", "Exhaust S Lv2", "Recover S Lv1", "Recover S Lv2", "Paint S", "Tranq S",
               "unknown32")   # the last is XX's only
SHARPNESS_COLORS = ("red", "orange", "yellow", "green", "blue", "white", "purple")
NOTE_COLORS = {1: "white", 2: "purple", 3: "red", 4: "blue", 5: "green", 6: "yellow", 7: "cyan", 8: "orange"}
HEADER = 8                # every table: a float version and a u32 count


@dataclass(frozen=True)
class WeaponKind:
    nn: str                # the two digits in the table names
    key: str               # the randomizer's class key (equipment/tables/layout.py)
    base_size: int
    level_size: int
    xx: bool = False       # the sizes are MH XX's (module docstring)

    @property
    def ranged(self) -> bool:
        return self.key in ("heavy_bowgun", "light_bowgun", "bow")

    @property
    def shift(self) -> int:
        """The bytes the base record has more past +9 (XX: the G rank level count at +10)."""
        return 1 if self.xx else 0

    @property
    def shells(self) -> int:
        """A bowgun level's shell slots."""
        return 33 if self.xx else 32

    @property
    def coatings(self) -> int:
        """A bow level's coatings."""
        return 12 if self.xx else 11

    @property
    def sharpness_columns(self) -> int:
        """The columns of a sharpness row: red .. white (XX: and purple)."""
        return 7 if self.xx else 6


def _kinds(xx: bool) -> dict[str, WeaponKind]:
    more = int(xx)   # XX: one byte more in every base record, and in the bows' and bowguns' level records
    return {k.nn: k for k in (
        WeaponKind("00", "great_sword", 32 + more, 15, xx), WeaponKind("01", "sword_and_shield", 32 + more, 15, xx),
        WeaponKind("02", "hammer", 32 + more, 15, xx), WeaponKind("03", "lance", 32 + more, 15, xx),
        WeaponKind("04", "heavy_bowgun", 31 + more, 98 + 2 * more, xx),
        WeaponKind("06", "light_bowgun", 31 + more, 98 + 2 * more, xx),
        WeaponKind("07", "long_sword", 32 + more, 15, xx), WeaponKind("08", "switch_axe", 33 + more, 17, xx),
        WeaponKind("09", "gunlance", 33 + more, 16, xx), WeaponKind("10", "bow", 32 + more, 30 + more, xx),
        WeaponKind("11", "dual_blades", 33 + more, 17, xx), WeaponKind("12", "hunting_horn", 32 + more, 16, xx),
        WeaponKind("13", "insect_glaive", 33 + more, 15, xx), WeaponKind("14", "charge_blade", 33 + more, 17, xx))}


KINDS = _kinds(False)
XX_KINDS = _kinds(True)
KIND_OF_KEY = {k.key: k for k in KINDS.values()}

# Ammo index of a bowgun's unique and squat / rapid shots -> the item id of the ammo in MHGen's itemData (derived
# against
# Kiranico, verified on 762 levels): 0-31 are items 99 + n, the rest are listed.
AMMO_ITEMS = {i: 99 + i for i in range(32)}
AMMO_ITEMS.update({59: 163, 32: 164, 33: 165, 34: 166, 35: 167, 36: 168, 64: 169, 65: 170, 66: 171, 67: 172, 37: 173,
                   38: 174, 39: 175, 40: 176, 41: 177, 42: 178, 43: 179, 44: 180, 45: 181, 46: 182, 47: 183, 48: 184,
                   49: 185, 50: 186, 51: 187, 52: 188, 53: 189, 54: 190, 55: 191, 56: 192, 57: 193, 58: 194, 60: 195,
                   61: 196, 62: 197, 63: 198, 68: 199, 69: 200, 70: 201, 71: 202, 72: 203})
NO_AMMO = (0, 0x49)       # an unused unique-ammo triple

# Horn notes: ids below 40 pick a pair of NOTE_PAIRS (id // 4); from 40, purple + orange and one of EXTRA_NOTES
NOTE_PAIRS = ((3, 4), (3, 5), (3, 7), (3, 6), (4, 5), (4, 7), (4, 6), (5, 7), (5, 6), (7, 6))
EXTRA_NOTES = (3, 4, 5, 7, 6)


def table_records(data: bytes, size: int) -> list[bytes]:
    """The records of a MHGen table (a float version, a u32 count, then `size` bytes each)."""
    count = struct.unpack_from("<I", data, 4)[0]
    if len(data) != HEADER + size * count:
        raise ValueError(f"{count} records of {size} bytes make {HEADER + size * count} bytes, not {len(data)}")
    return [data[HEADER + size * i:HEADER + size * (i + 1)] for i in range(count)]


def sharpness_rows(data: bytes, columns: int = 6) -> list[tuple[int, ...]]:
    """`table\\kireajiData`: per row the cumulative ends of red .. white (XX: .. purple, `columns` 7) in hits x 5."""
    return [struct.unpack(f"<{columns}H", r) for r in table_records(data, 2 * columns)]


def visible_sharpness(row: Sequence[int], cut: int) -> tuple[int, ...]:
    """The lengths of red .. white (XX: .. purple) (hits x 5) of a sharpness `row` cut at `cut` hits x 5."""
    out, prev = [], 0
    for end in row:
        out.append(max(0, min(end, cut) - prev))
        prev = max(prev, min(end, cut))
    return tuple(out)


def sharpness_cut(v: int) -> int:
    """The cut of a level record's byte +7: the row is shown up to 150 + 25 v (v/2 is MH4U's sharpness level)."""
    return 150 + 25 * v


def level_price(base: int, change_level: int, level: int) -> int:
    """The price of upgrading a line to `level` (1-based): base x level, from `change_level` on base x (level + 9); a
    `change_level` of 0 never changes."""
    return base * (level if not change_level or level < change_level else level + 9)


def note_colors(note_id: int) -> tuple[int, int, int]:
    """The three horn notes (NOTE_COLORS numbers) of a hunting horn level's note id."""
    if note_id < 40:
        x, y = NOTE_PAIRS[note_id // 4]
        first = 1 + ((note_id >> 1) & 1)
    else:
        x, y = EXTRA_NOTES[(note_id - 40) // 2], 8
        first = 2
    return (first, y, x) if note_id & 1 else (first, x, y)


@dataclass(frozen=True)
class WeaponBase:
    """A `weaponNNBaseData` record."""
    index: int
    model: int
    model2: int
    sound_material: int
    levels: int
    rarity: int
    price: int
    price_change_level: int
    element: str | None            # ELEMENTS (the line's element or status), None for bowguns
    element2: str | None           # dual blades' second element
    shell: str | None              # gunlance SHELLS
    phial: str | None              # switch axe PHIALS, charge blade CHARGE_PHIALS
    color: int
    sort: int
    named: int
    children: tuple[tuple[int, int], ...]   # (upgrade level of this line, child line)
    g_levels: int = 0                       # XX: the G rank levels the line has after `levels` (Generations': none)


def parse_weapon_base(kind: WeaponKind, index: int, r: bytes) -> WeaponBase:
    """Common bytes: +4 model, +6 second model, +8 sound material, +9 levels, +10 rarity - 1, +11 u32 price, +15 price
    change level; then per class element id (+16, bowguns none), the class byte, the colour, sort and the children (the
    last ten bytes: five (level, line) pairs). XX has the G rank level count at +10 and every later byte one place
    on."""
    s = kind.shift
    model, model2 = struct.unpack_from("<HH", r, 4)
    kids = kind.base_size - 10
    children = tuple((r[kids + 2 * i], r[kids + 2 * i + 1]) for i in range(5) if r[kids + 2 * i + 1])
    element = element2 = shell = phial = None
    nn = kind.nn
    if nn in ("04", "06"):
        color, sort, named = r[16 + s], struct.unpack_from("<H", r, 17 + s)[0], r[19 + s]
    else:
        element = ELEMENTS.get(r[16 + s])
        if nn in ("00", "01", "02", "03", "07", "12", "10"):
            color, at = r[17 + s], 18 + s
        else:
            color, at = r[18 + s], 19 + s
            if nn == "08":
                phial = PHIALS.get(r[17 + s])
            elif nn == "14":
                phial, color = CHARGE_PHIALS.get(r[17 + s]), r[18 + s]
            elif nn == "09":
                shell = SHELLS.get(r[17 + s])
            elif nn == "11":
                element2 = ELEMENTS.get(r[17 + s])
        sort, named = struct.unpack_from("<H", r, at)[0], r[at + 2]
    return WeaponBase(index, model, model2, r[8], r[9], r[10 + s] + 1, struct.unpack_from("<I", r, 11 + s)[0],
                      r[15 + s], element, element2, shell, phial, color, sort, named, children, r[10] if s else 0)


@dataclass(frozen=True)
class WeaponLevel:
    """A `weaponNNLevelData` record. `attack` is the displayed attack (rounded to tens); `class_data` has what the class
    adds (horn notes, shells, coatings, ammo ...)."""
    level: int
    attack: int
    defense: int
    affinity: int
    element_value: int            # the line's element (bows, bowguns: see class_data)
    slots: int
    sharp_row: int                # a row of kireajiData, -1 for the ranged classes
    sharp_cut: int                # byte +7, -1 for the ranged classes
    sharpness: tuple[int, ...]    # visible lengths of red .. white in hits x 5 (empty for the ranged classes)
    sharp_ends: tuple[int, ...]   # the whole row: cumulative ends of red .. white (empty for the ranged classes)
    price: int
    recipe: GenRecipe | None      # what upgrading to this level (or, level 1, creating the line) asks
    class_data: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def sharpness_level(self) -> int:
        """The sharpness bar's level in MH4U terms: its cut is (30 + 10 x level) x 5 hits x 5 (-1: ranged classes)."""
        return (self.sharp_cut - 150) // 50 if self.sharp_cut >= 0 else -1


def parse_level_record(kind: WeaponKind, r: bytes) -> dict:
    """The fields of a level record: global index, line, level and the stats; class data under "class_data"."""
    nn = kind.nn
    out = {"index": struct.unpack_from("<I", r, 0)[0], "line": r[4], "level": r[5], "class_data": {}}
    cd = out["class_data"]
    if nn in ("04", "06"):
        out.update(attack=struct.unpack_from("<H", r, 6)[0], defense=r[8], affinity=struct.unpack_from("<b", r, 9)[0],
                   slots=r[10], element_value=0, sharp_row=-1, sharp_cut=-1)
        cd.update(deviation=r[11] + 1, reload=r[12], recoil=r[13], shot_indexes=tuple(r[14:19]))
        triples = (tuple(r[19 + 3 * j:22 + 3 * j]) for j in range(5))
        # XX numbers the ammo anew (its items are not decoded): the unused triple is 0x4a, the item unknown
        no_ammo = (0, 0x4a) if kind.xx else NO_AMMO
        cd["unique_ammo"] = tuple({"ammo_index": a, "item": None if kind.xx else AMMO_ITEMS.get(a), "total": b,
                                   "count": c} for a, b, c in triples if a not in no_ammo)
        cd["shells"] = {SHELL_SLOTS[i]: r[34 + 2 * i] for i in range(kind.shells) if r[35 + 2 * i]}
        cd["shells_disabled"] = {SHELL_SLOTS[i]: r[34 + 2 * i] for i in range(kind.shells)
                                 if not r[35 + 2 * i] and r[34 + 2 * i]}
        return out
    if nn == "10":
        out.update(attack=struct.unpack_from("<H", r, 6)[0], defense=r[8], affinity=struct.unpack_from("<b", r, 9)[0],
                   element_value=struct.unpack_from("<H", r, 10)[0], slots=r[12], sharp_row=-1, sharp_cut=-1)
        cd.update(arc_shot=ARC_SHOTS.get(r[13] + 1), charge_levels=r[14],
            charge_shots=tuple(r[15 + i] + 1 for i in range(4)),
                  coatings=tuple(name for name, on in zip(COATINGS, r[19:19 + kind.coatings]) if on))
        return out
    out.update(sharp_row=r[6], sharp_cut=sharpness_cut(r[7]), attack=struct.unpack_from("<H", r, 8)[0], defense=r[10],
               affinity=struct.unpack_from("<b", r, 11)[0], element_value=r[12])
    if nn in ("00", "01", "02", "03", "07", "13"):
        out["slots"] = r[14]
    elif nn == "11":
        out["slots"] = r[16]
        cd["element2_value"] = r[14]
    elif nn == "12":
        out["slots"] = r[15]
        cd.update(note_id=r[14], notes=tuple(NOTE_COLORS[c] for c in note_colors(r[14])))
    elif nn == "09":
        out["slots"] = r[15]
        cd["shell_level"] = r[14] + 1
    elif nn == "08":
        out["slots"] = r[16]
        cd["phial_value"] = r[14]
    elif nn == "14":
        out["slots"] = r[16]
    return out


@dataclass(frozen=True)
class WeaponLine:
    """A weapon line of MHGen: base data, its levels with their recipes, its names in every language."""
    kind: WeaponKind
    base: WeaponBase
    names: dict = field(compare=False, hash=False)               # language -> name
    descriptions: dict = field(compare=False, hash=False)
    final_names: dict = field(compare=False, hash=False)         # the last level's own name
    final_descriptions: dict = field(compare=False, hash=False)
    levels: tuple[WeaponLevel, ...]
    create: GenRecipe | None
    upgrade_to_first: GenRecipe | None    # level 1 bought as the last level of its parent, if also created
    g_levels: tuple[WeaponLevel, ...] = ()      # XX: the G rank levels after `levels` (MHGU's G steps)
    best_names: dict = field(default_factory=dict, compare=False, hash=False)   # XX: the last G level's name ...
    best_descriptions: dict = field(default_factory=dict, compare=False, hash=False)   # ... and description

    @property
    def cls(self) -> str:
        return self.kind.key

    @property
    def index(self) -> int:
        return self.base.index

    @property
    def start_recipe(self) -> GenRecipe | None:
        """What makes level I from scratch: the create row or, for a line the game only reaches by upgrading another
        weapon (Great Maccao's Hammer in XX), level I's upgrade recipe."""
        return self.create or (self.levels[0].recipe if self.levels else None)

    def true_attack(self, level: int, multiplier: float) -> int:
        """The weapon's attack before the class's display multiplier (the displayed attack / `multiplier`, rounded)."""
        return round(self.levels[level - 1].attack / multiplier)


def build_line(kind: WeaponKind, base: WeaponBase, level_records: Sequence[dict], sharp: Sequence[Sequence[int]],
               create_row: tuple[int, bytes] | None, process_rows: dict[int, tuple[int, bytes]],
               names: dict, descriptions: dict, final_names: dict, final_descriptions: dict,
               best_names: dict | None = None, best_descriptions: dict | None = None) -> WeaponLine:
    """Assemble a line. `create_row` is (row, bytes) of weaponCreateWNN for the line, `process_rows` level ->
    (row, bytes) of weaponProcessWNN. Level 1 of a created line has an empty upgrade row; a created line that also has
    a non-empty one is reachable as the upgrade of its parent (`upgrade_to_first`). XX's records past `base.levels` are
    the G rank levels (`g_levels`), not part of `levels`."""
    create = weapon_create(*create_row, xx=kind.xx) if create_row else None
    upgrades = {lv: weapon_upgrade(row, data) for lv, (row, data) in process_rows.items()}
    first = upgrades.get(1)
    upgrade_to_first = first if first and not first.empty and create else None
    levels = []
    for lr in level_records:
        lv = lr["level"]
        recipe = create if lv == 1 and create else upgrades.get(lv)
        if lv == 1 and recipe is not None and recipe.empty:
            recipe = None
        ends = tuple(sharp[lr["sharp_row"]]) if lr["sharp_row"] >= 0 else ()
        lengths = visible_sharpness(ends, lr["sharp_cut"]) if ends else ()
        levels.append(WeaponLevel(lv, lr["attack"], lr["defense"], lr["affinity"], lr["element_value"], lr["slots"],
                                  lr["sharp_row"], lr["sharp_cut"], lengths, ends,
                                  level_price(base.price, base.price_change_level, lv), recipe, lr["class_data"]))
    g_levels = tuple(levels[base.levels:]) if kind.xx else ()
    levels = levels[:base.levels] if kind.xx else levels
    return WeaponLine(kind, base, names, descriptions, final_names, final_descriptions, tuple(levels), create,
                      upgrade_to_first, g_levels, best_names or {}, best_descriptions or {})
