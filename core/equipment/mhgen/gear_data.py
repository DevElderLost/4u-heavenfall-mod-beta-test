"""MH Generations' gear data of a ported monster, read from the game at run time (task i7): his armor (blademaster and
gunner), weapons, Felyne pieces,
materials and the recipes for all of it, with the layouts of the tables decoded in `parse_*`.

Nothing here is committed game data: `GenGame(romfs)` opens MHGen's archives on demand, `read_monster_gear(game, key)`
returns what one ported monster (`mizutsune`, `alatreon`, `great_maccao`, `glavenus`) brings. Which armor series,
weapon lines, drop names and Felyne names are a monster's is our own knowledge
(`game/data/curated/mhgen_monsters.json`); the numbers all come from the game. MHGen-only materials stay recognisable
for the integration to flatten them: a recipe's `GenMaterial.role` (unlock item, scrap), `GenRecipe.category` (N points
of the monster's items), `item_kind` (armor spheres, Hyper items), `MonsterGear.scrap_exchange` and `categories` (their
members and points).

A monster's reward lists are read from XX by `gear_rewards`; his `drops` here are the curated names of items whose
records his gear reads, in the order of the community databases.

**MH XX as the source**: `GenGame(romfs)` recognises XX's RomFS (`SourceFormat`, `XX_FORMAT`) and reads the same tables
*from its
places (`arc/resident.arc`, `arc/facility/blacksmith.arc`) with the changes of its records: the armor series has one
byte more at +105, the Felyne armor three at the end, a weapon line has its G rank levels after Generations' ones
(`gear_weapons`), a create row starts with a kind. XX has only Japanese text: the names of the five languages come from
the curated names block (`game_names`) put over it, and a monster's gear is found by the ids of the `xx` part of its
`mhgen_monsters.json` entry (XX numbers its items, skills and weapon messages anew).
"""

import json
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from core.game.files.arc import parse_arc
from core.equipment.layered.looks import LANGUAGES
from core.equipment.mhgen import game_names
from core.equipment.mhgen.gear_recipes import (
    GenMaterial, GenRecipe, armor_create, armor_upgrade, create_kind, create_line, felyne_create,
)
from core.equipment.mhgen.gear_weapons import (
    AMMO_ITEMS, KINDS, XX_KINDS, WeaponKind, WeaponLine, build_line, parse_level_record, parse_weapon_base,
    sharpness_rows, table_records,
)
from core.game.files.text.gmd import gmd_strings
from core.game.data.paths import CURATED_DIR

RESIDENT = "loc/arc/resident.arc"
BLACKSMITH = "arc/village/blacksmith.arc"
LANG_RESIDENT = "{lang}/arc/resident_{lang}.arc"
LANG_VILLAGE = "{lang}/arc/village/common_{lang}.arc"
MONSTERS_FILE = CURATED_DIR / "mhgen_monsters.json"


PARTS = ("head", "body", "arms", "waist", "legs")
RESISTANCES = ("fire", "water", "thunder", "ice",
    "dragon")   # MHGen's order (MH4U's: fire, water, thunder, dragon, ice)
ITEM_SIZE, SERIES_SIZE, BUILD_SIZE, SKILL_TREE_SIZE = 44, 126, 20, 19
FELYNE_ARMOR_SIZE, FELYNE_WEAPON_SIZE, FELYNE_CREATE_SIZE = 30, 31, 36
ARMOR_CREATE_SIZE, ARMOR_UPGRADE_SIZE = 42, 38
WEAPON_CREATE_SIZE, WEAPON_UPGRADE_SIZE = 36, 32
SERIES_NAMES = 10         # messages per series: 5 names, then 5 descriptions
SKILL_POINTS = (-20, -15, -10, 10, 15, 20, 25)   # the thresholds of a skill tree's seven skill slots
FELYNE_ELEMENTS = {0: None, 1: "fire", 2: "water", 3: "thunder", 4: "dragon", 5: "ice", 6: "poison", 7: "paralysis",
                   8: "sleep", 9: "blast"}
FELYNE_TYPES = {0: "balanced", 1: "close_range", 2: "boomerang"}
SCRAP_PREFIX = "Hyper Scrap"   # the scrap items Felyne recipes may ask besides the monster's own


@dataclass(frozen=True)
class SourceFormat:
    """Where a source game keeps the gear tables and how its records differ from MH Generations' (the module's
    docstring)."""
    key: str                      # "gen" or "xx"
    resident: str                 # the archive of the resident tables
    blacksmith: str               # the archive of the recipes
    series_size: int              # an `armorSeriesData` record
    series_shift: int             # the bytes it has more from +105 (XX: one, the armor's upgrade tier)
    felyne_armor_size: int
    weapon_create_size: int       # a `weaponCreateWNN` row (XX: a kind more at the start)
    sharpness_columns: int        # a `kireajiData` row: red .. white (XX: .. purple)
    line_strings: int             # the messages of a weapon line (name, description, final name, final description,
    #                               and XX: the best one's)
    kinds: Mapping[str, WeaponKind] = field(compare=False, hash=False)
    western_text: bool = True     # the game has the five languages' text (else: Japanese, and the names block)


GEN_FORMAT = SourceFormat("gen", RESIDENT, BLACKSMITH, SERIES_SIZE, 0, FELYNE_ARMOR_SIZE, WEAPON_CREATE_SIZE, 6, 4,
                          KINDS)
XX_FORMAT = SourceFormat("xx", "arc/resident.arc", "arc/facility/blacksmith.arc", SERIES_SIZE + 1, 1,
                         FELYNE_ARMOR_SIZE + 3, WEAPON_CREATE_SIZE + 2, 7, 6, XX_KINDS, western_text=False)
XX_ITEM_CATEGORIES = "table/itemCategoryTypeData_jpn.gmd"   # the Japanese names of the item categories


def detect_format(romfs) -> SourceFormat:
    """XX's format when `romfs` has XX's resident archive and not Generations', else Generations'."""
    exists = getattr(romfs, "exists", None)
    if exists is not None and not exists(GEN_FORMAT.resident) and exists(XX_FORMAT.resident):
        return XX_FORMAT
    return GEN_FORMAT


# ----- items ----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class GenItem:
    id: int
    names: dict = field(compare=False, hash=False)           # language -> name
    descriptions: dict = field(compare=False, hash=False)
    rarity: int
    carry_max: int
    icon_shape: int
    icon_color: int
    sell: int
    buy: int
    category: int                # item category (0: none)
    category_points: int         # what it is worth in a recipe's "N points of category" slot
    sort: int

    @property
    def name(self) -> str:
        return self.names["eng"]

    @property
    def kind(self) -> str:
        return item_kind(self.name)


def item_kind(name: str) -> str:
    """What an item is for the integration: "scrap" (a currency of the Smithy: *Scrap*, *Scrap+*, Hyper Scrap), "sphere"
    (an armor sphere: MH4U has none), "hyper" (a Hyper item, dropped by MHGen's Hyper monsters) or "ordinary"."""
    if "Scrap" in name:
        return "scrap"
    if "Armor Sphere" in name:
        return "sphere"
    if name.startswith("Hyper "):
        return "hyper"
    return "ordinary"


def item_category(r: bytes) -> int:
    """An `itemData` record's category: a u16 at +28 (XX's go past 255; Generations' high byte is 0)."""
    return struct.unpack_from("<H", r, 28)[0]


def category_members(records: Sequence[bytes], category: int) -> tuple[tuple[int, int], ...]:
    """The (item, category points) of every item of `category` that is worth points."""
    return tuple((i, r[27]) for i, r in enumerate(records) if item_category(r) == category and r[27])


def parse_item(index: int, r: bytes, names: Mapping[str, Sequence[str]]) -> GenItem:
    """An `itemData` record (44 bytes); `names`: language -> the table's messages (2 per item: name, description).
    +5 rarity - 1, +6 carry maximum, +7 u32 sort, +16 icon shape, +17 icon colour, +19 u32 sell price, +23 u32 buy
    price, +27 category points, +28 u16 category (+30 a second one)."""
    return GenItem(index, {lang: names[lang][2 * index] for lang in names},
        {lang: names[lang][2 * index + 1] for lang in names},
                   r[5] + 1, r[6], r[16], r[17], struct.unpack_from("<I", r, 19)[0], struct.unpack_from("<I", r, 23)[0],
                   item_category(r), r[27], struct.unpack_from("<I", r, 7)[0])


@dataclass(frozen=True)
class GenItemCategory:
    """A recipe's "N points of any item of category C" slot: the items and the points each is worth."""
    id: int
    names: dict = field(compare=False, hash=False)
    members: tuple[tuple[int, int], ...]      # (item, points)


def parse_scrap_exchange(data: bytes) -> dict[int, tuple[tuple[int, int], ...]]:
    """`pieceCreateList` (6 bytes: u16 source item, u16 scrap item, u8 points): scrap item -> ((source, points) ...)."""
    out: dict[int, list[tuple[int, int]]] = {}
    for r in table_records(data, 6):
        source, scrap, points, _ = struct.unpack("<HHBB", r)
        out.setdefault(scrap, []).append((source, points))
    return {scrap: tuple(rows) for scrap, rows in out.items()}


# ----- armor ----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class GenSkill:
    tree: int       # MHGen's skill tree id (game/data/curated/mhgen_skill_map.json maps it to MH4U's)
    points: int


@dataclass(frozen=True)
class GenArmorPiece:
    series: int                 # armorSeriesData index
    part: str                   # PARTS
    names: dict = field(compare=False, hash=False)          # language -> name
    descriptions: dict = field(compare=False, hash=False)
    rank: str                   # "low" or "high" (MHGen has no G rank armor for these monsters)
    hunter: str                 # "blademaster", "gunner" or "both"
    genders: str                # "mf", "m" or "f"
    model: int                  # one model for every piece and gender of the series
    defense_base: int           # level 1
    defense_max: int            # last level (max_level); MH4U's armor has 63 levels: convert.armor_levels
    max_level: int
    resist: dict = field(compare=False, hash=False)         # RESISTANCES -> s8
    slots: int
    skills: tuple[GenSkill, ...]
    rarity: int
    price: int                  # the series' price: MHGen stores none per piece


@dataclass(frozen=True)
class GenArmorSeries:
    index: int
    list_id: int
    rank: str
    hunter: str
    genders: str
    model: int
    rarity: int
    price: int
    max_level: int
    defense_levels: tuple[int, ...]   # defense at each level 1 .. max_level
    pieces: tuple[GenArmorPiece, ...]  # the parts the series has, in PARTS order
    sounds: tuple[int, ...]

    def piece(self, part: str) -> GenArmorPiece | None:
        return next((p for p in self.pieces if p.part == part), None)


def defense_levels(build_row: bytes, base: int, max_level: int) -> tuple[int, ...]:
    """Defense at each level: `base` at level 1, the nonzero bytes of the `armorBuildData` row added per level."""
    out = [base]
    for step in [b for b in build_row if b][:max_level - 1]:
        out.append(out[-1] + step)
    return tuple(out)


def parse_armor_series(index: int, r: bytes, build_rows: Sequence[bytes],
                       texts: Mapping[str, Sequence[str]], shift: int = 0) -> GenArmorSeries:
    """An `armorSeriesData` record (126 bytes); `texts`: language -> the table's messages (10 per series). +4 Kiranico's
    list id, +6..10 which parts, +11 model, +13/14 male / female, +15/16 blademaster / gunner, +17 price, +23..27
    resistances (fire water thunder ice dragon), +28 + 15 p five (u16 tree, s8 points), +103 rarity - 1, +104 max
    level, +105 base defense, +106 build row, +107..111 slots, +112 high rank, +115..125 sounds. XX's (127 bytes,
    `shift` 1) has a byte more at +105 (a tier of the armor's upgrades: 0 low rank, 2-4 for the others) and no high rank
    flag: its rank is read from the rarity (low 1-3, high 4-7, G 8 and up)."""
    s = shift
    has = [bool(b) for b in r[6:11]]
    hunter = {(1, 0): "blademaster", (0, 1): "gunner"}.get((min(r[15], 1), min(r[16], 1)), "both")
    genders = "".join(g for g, ok in zip("mf", r[13:15]) if ok)
    resist = {k: struct.unpack_from("<b", r, 23 + i)[0] for i, k in enumerate(RESISTANCES)}
    rank = ("low" if r[103] + 1 <= 3 else "high" if r[103] + 1 <= 7 else "G") if s else "high" if r[112] else "low"
    levels = defense_levels(build_rows[r[106 + s]], r[105 + s], r[104])
    model = struct.unpack_from("<H", r, 11)[0]
    price = struct.unpack_from("<I", r, 17)[0]
    pieces = []
    for p, part in enumerate(PARTS):
        if not has[p]:
            continue
        skills = tuple(GenSkill(tree, points) for tree, points in
                       (struct.unpack_from("<Hb", r, 28 + 15 * p + 3 * j) for j in range(5)) if tree)
        pieces.append(GenArmorPiece(
            index, part, {lang: texts[lang][SERIES_NAMES * index + p] for lang in texts},
            {lang: texts[lang][SERIES_NAMES * index + 5 + p] for lang in texts}, rank, hunter, genders, model,
            levels[0], levels[-1], r[104], resist, r[107 + s + p], skills, r[103] + 1, price))
    return GenArmorSeries(index, struct.unpack_from("<H", r, 4)[0], rank, hunter, genders, model, r[103] + 1, price,
                          r[104], levels, tuple(pieces), tuple(r[115 + s:126 + s]))


@dataclass(frozen=True)
class GenArmorSet:
    """A blademaster series and its gunner twin (the Smithy's rows serve both) with the recipes of the pair."""
    blademaster: GenArmorSeries | None
    gunner: GenArmorSeries | None
    create: dict = field(compare=False, hash=False)      # part -> GenRecipe (one per piece, both hunters)
    upgrade: dict = field(compare=False, hash=False)     # level -> GenRecipe (the whole series, a step per level)

    @property
    def series(self) -> tuple[GenArmorSeries, ...]:
        return tuple(s for s in (self.blademaster, self.gunner) if s)


# ----- skills ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class GenSkillTree:
    id: int
    names: dict = field(compare=False, hash=False)
    descriptions: dict = field(compare=False, hash=False)
    effects: dict = field(compare=False, hash=False)      # points (SKILL_POINTS) -> {"skill", "names", "descriptions"}


def parse_skill_tree(index: int, r: bytes, types: Mapping[str, Sequence[str]], skills: Mapping[str,
    Sequence[str]]) -> GenSkillTree:
    """A `skillTypeData` record (19 bytes): u16 id, u16, u8, then seven u16 skill ids for SKILL_POINTS (0: none)."""
    effects = {}
    for points, skill in zip(SKILL_POINTS, struct.unpack_from("<7H", r, 5)):
        if skill:
            effects[points] = {"skill": skill, "names": {lang: skills[lang][2 * skill] for lang in skills},
                               "descriptions": {lang: skills[lang][2 * skill + 1] for lang in skills}}
    return GenSkillTree(index, {lang: types[lang][2 * index] for lang in types},
                        {lang: types[lang][2 * index + 1] for lang in types}, effects)


# ----- Felyne gear ----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class GenFelyneArmor:
    """A Felyne head and body piece (one record)."""
    id: int
    names: dict = field(compare=False, hash=False)           # language -> (head, body)
    descriptions: dict = field(compare=False, hash=False)
    model: int
    rarity: int
    price: int
    head_defense: int
    body_defense: int
    head_resist: dict = field(compare=False, hash=False)     # RESISTANCES -> s8
    body_resist: dict = field(compare=False, hash=False)
    head_recipe: tuple[GenMaterial, ...]
    body_recipe: tuple[GenMaterial, ...]


@dataclass(frozen=True)
class GenFelyneWeapon:
    id: int
    names: dict = field(compare=False, hash=False)
    descriptions: dict = field(compare=False, hash=False)
    model: int
    damage_kind: str             # "blunt" or "cutting"
    element: str | None
    kind: str                    # FELYNE_TYPES
    attack: int
    affinity: int
    element_value: int
    boomerang_attack: int
    boomerang_affinity: int
    boomerang_element_value: int
    rarity: int
    price: int
    recipe: tuple[GenMaterial, ...]


def parse_felyne_armor(index: int, r: bytes, texts: Mapping[str, Sequence[str]],
                       head: tuple[GenMaterial, ...], body: tuple[GenMaterial, ...]) -> GenFelyneArmor:
    """An `otArmorData` record (30 bytes): +6 model, +7 rarity - 1, +8 u32 price, +14 head defense, +16 head
    resistances, +21 body defense, +23 body resistances; texts: 4 per piece (head name, body name, head description,
    body one)."""
    return GenFelyneArmor(
        index, {lang: (texts[lang][4 * index], texts[lang][4 * index + 1]) for lang in texts},
        {lang: (texts[lang][4 * index + 2], texts[lang][4 * index + 3]) for lang in texts}, r[6], r[7] + 1,
        struct.unpack_from("<I", r, 8)[0], r[14], r[21], dict(zip(RESISTANCES, struct.unpack_from("<5b", r, 16))),
        dict(zip(RESISTANCES, struct.unpack_from("<5b", r, 23))), head, body)


def parse_felyne_weapon(index: int, r: bytes, texts: Mapping[str, Sequence[str]],
                        recipe: tuple[GenMaterial, ...]) -> GenFelyneWeapon:
    """An `otWeaponData` record (31 bytes): +4 u16 model, +6 blunt, +8 element, +9 type, +10 u16 attack, +12 affinity,
    +13 element value, +15 u16 boomerang attack, +17 / +18 its affinity and element value, +22 rarity - 1, +25 u32
    price."""
    return GenFelyneWeapon(
        index, {lang: texts[lang][2 * index] for lang in texts}, {lang: texts[lang][2 * index + 1] for lang in texts},
        struct.unpack_from("<H", r, 4)[0], "blunt" if r[6] else "cutting", FELYNE_ELEMENTS.get(r[8], str(r[8])),
        FELYNE_TYPES.get(r[9], str(r[9])), struct.unpack_from("<H", r, 10)[0], struct.unpack_from("<b", r, 12)[0],
        r[13], struct.unpack_from("<H", r, 15)[0], struct.unpack_from("<b", r, 17)[0], r[18], r[22] + 1,
        struct.unpack_from("<I", r, 25)[0], recipe)


# ----- the game -------------------------------------------------------------------------------------------------

class GenGame:
    """MHGen's (or XX's) tables, recipes and texts read from its romfs `romfs` (anything with `read(path)`:
    exefs.romfs.RomFS), each archive on first use. `fmt`: its `SourceFormat` (found from the romfs by default).
    `names`: for a game with no Western text (XX), the names block `game_names.load_names` gives (the file's by
    default)."""

    def __init__(self, romfs, fmt: SourceFormat | None = None, names: Mapping[str, dict] | None = None):
        self.romfs = romfs
        self.fmt = fmt or detect_format(romfs)
        self._archives: dict[str, dict[str, bytes]] = {}
        self._messages: dict[str, dict[str, list[str]]] = {}
        self._names = names

    @property
    def names(self) -> Mapping[str, dict]:
        """XX's Western names by kind of record and id (`game_names`); empty for a game that has its own."""
        if self._names is None:
            self._names = {} if self.fmt.western_text else game_names.load_names()
        return self._names

    def _archive(self, path: str) -> dict[str, bytes]:
        if path not in self._archives:
            self._archives[path] = {e.name: e.data for e in parse_arc(self.romfs.read(path)).entries}
        return self._archives[path]

    def table(self, name: str) -> bytes:
        """A resident table, e.g. `table("itemData")`."""
        return self._archive(self.fmt.resident)[f"table\\{name}"]

    def records(self, name: str, size: int) -> list[bytes]:
        return table_records(self.table(name), size)

    def recipe_table(self, name: str) -> bytes:
        """A table of the blacksmith archive."""
        return self._archive(self.fmt.blacksmith)[f"table\\{name}"]

    def messages(self, table: str) -> dict[str, list[str]]:
        """The messages of resident table `table` (`itemData`) in every language. XX has only Japanese text: every
        language gets it, and the names block's strings go over it."""
        if self.fmt.western_text:
            return {lang: gmd_strings(self._archive(LANG_RESIDENT.format(lang=lang))[f"{lang}\\table\\{table}_{lang}"])
                    for lang in LANGUAGES}
        japanese = gmd_strings(self.romfs.read(f"table/{table}_jpn.gmd"))
        texts = {lang: list(japanese) for lang in LANGUAGES}
        self._put_names(table, texts)
        return texts

    def _put_names(self, table: str, texts: dict[str, list[str]]) -> None:
        """The names block's strings of `table` over `texts` ({lang: messages}, edited in place)."""
        for kind, name in game_names.TABLES.items():
            if name == table:
                for record, entry in self.names.get(kind, {}).items():
                    game_names.apply(kind, record, entry, texts)
        if table.startswith("weapon") and table.endswith("MsgData"):
            for line, entry in self.names.get("weapons", {}).get(table[6:8], {}).items():
                game_names.apply("weapons", line, entry, texts, self.message_numbers("eng", table)[line])

    def message_numbers(self, lang: str, table: str) -> tuple[int, ...]:
        """A weapon class's un-suffixed `weaponNNMsgData`: the message number of each line (XX: the same for every
        language, in the resident archive)."""
        if self.fmt.western_text:
            data = self._archive(LANG_RESIDENT.format(lang=lang))[f"{lang}\\table\\{table}"]
        else:
            data = self.table(table)
        count = struct.unpack_from("<I", data, 4)[0]
        return struct.unpack_from(f"<{count}I", data, 8)

    # items
    @cached_property
    def item_records(self) -> list[bytes]:
        return self.records("itemData", ITEM_SIZE)

    @cached_property
    def item_texts(self) -> dict[str, list[str]]:
        return self.messages("itemData")

    def item(self, index: int) -> GenItem:
        return parse_item(index, self.item_records[index], self.item_texts)

    def find_items(self, *, tokens: Sequence[str] = (), name: str | None = None) -> list[int]:
        """The ids of the items whose English name has any of `tokens`, or is `name` (all that are, ascending)."""
        names = self.item_texts["eng"]
        return [i for i in range(len(self.item_records))
                if (name is not None and names[2 * i] == name) or any(t in names[2 * i] for t in tokens)]

    def category(self, category: int) -> GenItemCategory:
        if self.fmt.western_text:
            names = {lang: gmd_strings(self._archive(LANG_VILLAGE.format(lang=lang))
                                       [f"{lang}\\table\\itemCategoryTypeData_{lang}"])[category] for lang in LANGUAGES}
        else:
            japanese = gmd_strings(self.romfs.read(XX_ITEM_CATEGORIES))[category]
            names = {lang: self.names.get("categories", {}).get(category, {}).get(lang, japanese)
                     for lang in LANGUAGES}
        return GenItemCategory(category, names, category_members(self.item_records, category))

    @cached_property
    def scrap_exchange(self) -> dict[int, tuple[tuple[int, int], ...]]:
        return parse_scrap_exchange(self.recipe_table("pieceCreateList"))

    # armor
    @cached_property
    def _series_records(self) -> list[bytes]:
        return self.records("armorSeriesData", self.fmt.series_size)

    @cached_property
    def _series_texts(self) -> dict[str, list[str]]:
        return self.messages("armorSeriesData")

    @cached_property
    def _build_rows(self) -> list[bytes]:
        return self.records("armorBuildData", BUILD_SIZE)

    def armor_series(self, index: int) -> GenArmorSeries:
        return parse_armor_series(index, self._series_records[index], self._build_rows, self._series_texts,
                                  self.fmt.series_shift)

    @cached_property
    def _armor_create(self) -> dict[tuple[int, int], dict[str, GenRecipe]]:
        out: dict[tuple[int, int], dict[str, GenRecipe]] = {}
        for p, part in enumerate(PARTS):
            for row, r in enumerate(table_records(self.recipe_table(f"armorCreateA0{p}"), ARMOR_CREATE_SIZE)):
                out.setdefault(struct.unpack_from("<HH", r, 0), {})[part] = armor_create(row, r)
        return out

    @cached_property
    def _armor_upgrade(self) -> dict[tuple[int, int], dict[int, GenRecipe]]:
        out: dict[tuple[int, int], dict[int, GenRecipe]] = {}
        for row, r in enumerate(table_records(self.recipe_table("armorProcessA00"), ARMOR_UPGRADE_SIZE)):
            recipe = armor_upgrade(row, r)
            out.setdefault(struct.unpack_from("<HH", r, 0), {})[recipe.level] = recipe
        return out

    def armor_set(self, blademaster: int, gunner: int) -> GenArmorSet:
        """The series pair (0: none) with the pair's recipes."""
        key = (blademaster, gunner)
        return GenArmorSet(self.armor_series(blademaster) if blademaster else None,
                           self.armor_series(gunner) if gunner else None,
                           dict(self._armor_create.get(key, {})), dict(sorted(self._armor_upgrade.get(key,
                               {}).items())))

    # weapons
    def weapon_line(self, nn: str, index: int) -> WeaponLine:
        """Line `index` of class `nn` ("00") with its levels and recipes."""
        xx = not self.fmt.western_text
        kind = self.fmt.kinds[nn]
        base = parse_weapon_base(kind, index, self.records(f"weapon{nn}BaseData", kind.base_size)[index])
        levels = sorted((parse_level_record(kind, r) for r in self.records(f"weapon{nn}LevelData", kind.level_size)[1:]
                         if r[4] == index), key=lambda lr: lr["level"])
        create = next(((row, r) for row, r in enumerate(table_records(self.recipe_table(f"weaponCreateW{nn}"),
                                                                       self.fmt.weapon_create_size))
                       if create_line(r, xx) == index and create_kind(r, xx) == 1), None)
        process = {}
        for row, r in enumerate(table_records(self.recipe_table(f"weaponProcessW{nn}"), WEAPON_UPGRADE_SIZE)):
            line, level = struct.unpack_from("<HH", r, 0)
            if line == index:
                process[level] = (row, r)
        numbers = {lang: self.message_numbers(lang, f"weapon{nn}MsgData")[index] for lang in LANGUAGES}
        strings = self.fmt.line_strings
        texts = self.messages(f"weapon{nn}MsgData")
        text = lambda k: {lang: texts[lang][strings * numbers[lang] + k] for lang in LANGUAGES}  # noqa: E731
        shots = self._shot_rows(nn)
        for lr in levels:
            cd = lr["class_data"]
            if nn == "04":
                cd["squat_shots"] = tuple({"ammo_index": shots[i][0], "item": AMMO_ITEMS.get(shots[i][0]),
                    "capacity": shots[i][1]}
                                          for i in cd["shot_indexes"] if i)
            elif nn == "06":
                cd["rapid_shots"] = tuple({"ammo_index": shots[i][0], "item": AMMO_ITEMS.get(shots[i][0]),
                    "capacity": shots[i][1],
                                           "multiplier_percent": shots[i][2], "wait_id": shots[i][3] + 1}
                                          for i in cd["shot_indexes"] if i)
        best = (text(4), text(5)) if xx else (None, None)
        return build_line(kind, base, levels, self._sharpness, create, process, text(0), text(1), text(2), text(3),
                          *best)

    @cached_property
    def _sharpness(self) -> list[tuple[int, ...]]:
        return sharpness_rows(self.table("kireajiData"), self.fmt.sharpness_columns)

    def _shot_rows(self, nn: str) -> list[tuple[int, ...]]:
        if nn == "04":
            return [struct.unpack("<BB", r) for r in self.records("squatshotData", 2)]
        if nn == "06":
            return [struct.unpack("<BBBB", r) for r in self.records("rapidshotData", 4)]
        return []

    def find_weapon_line(self, nn: str, name: str) -> int | None:
        """The line of class `nn` whose English name is `name`, None if there is none."""
        kind = self.fmt.kinds[nn]
        numbers = self.message_numbers("eng", f"weapon{nn}MsgData")
        texts = self.messages(f"weapon{nn}MsgData")["eng"]
        for index in range(len(self.records(f"weapon{nn}BaseData", kind.base_size))):
            if texts[self.fmt.line_strings * numbers[index]] == name:
                return index
        return None

    # skills
    def skill_tree(self, index: int) -> GenSkillTree:
        return parse_skill_tree(index, self.records("skillTypeData", SKILL_TREE_SIZE)[index], self._tree_texts,
                                self._skill_texts)

    @cached_property
    def _tree_texts(self) -> dict[str, list[str]]:
        return self.messages("skillTypeData")

    @cached_property
    def _skill_texts(self) -> dict[str, list[str]]:
        return self.messages("skillData")

    # Felyne
    @cached_property
    def _felyne_armor_texts(self) -> dict[str, list[str]]:
        return self.messages("otArmorData")

    @cached_property
    def _felyne_weapon_texts(self) -> dict[str, list[str]]:
        return self.messages("otWeaponData")

    @cached_property
    def _felyne_armor_recipes(self) -> dict[int, bytes]:
        return {struct.unpack_from("<I", r, 0)[0]: r
                for r in table_records(self.recipe_table("otArmorCreate"), FELYNE_CREATE_SIZE)}

    @cached_property
    def _felyne_weapon_recipes(self) -> dict[int, bytes]:
        return {struct.unpack_from("<I", r, 0)[0]: r
                for r in table_records(self.recipe_table("otWeaponCreate"), FELYNE_CREATE_SIZE)}

    def felyne_armor(self, index: int) -> GenFelyneArmor:
        row = self._felyne_armor_recipes.get(index)
        head = felyne_create(row, 12, 3) if row else ()
        body = felyne_create(row, 24, 3) if row else ()
        return parse_felyne_armor(index, self.records("otArmorData", self.fmt.felyne_armor_size)[index],
            self._felyne_armor_texts,
                                  head, body)

    def felyne_weapon(self, index: int) -> GenFelyneWeapon:
        row = self._felyne_weapon_recipes.get(index)
        return parse_felyne_weapon(index, self.records("otWeaponData", FELYNE_WEAPON_SIZE)[index],
                                   self._felyne_weapon_texts, felyne_create(row, 12, 6) if row else ())

    def felyne_pieces_of(self, tokens: Sequence[str], own_items: Sequence[int],
                         also: Sequence[int] = ()) -> tuple[list[int], list[int]]:
        """The Felyne armor and weapon ids of a monster: named with any of `tokens` (head, body or weapon), or made
        only of the monster's own items `own_items` and `also` (his drops; generic Hyper scraps and Bubblefoam are
        always allowed), at least one of them own: the S versions have other names (Mizutsune's "F Crimson
        Parasol")."""
        own = set(own_items)
        names = self.item_texts["eng"]
        generic = {i for i in range(len(self.item_records)) if names[2 * i] in ("Hyper Scrap", "Hyper Scrap+",
            "Bubblefoam",
                                                                                  "Bubblefoam+")}

        def made_of_own(row: bytes | None) -> bool:
            items = {m.item for m in felyne_create(row, 12, 6)} if row else set()
            return bool(items & own) and items <= own | generic | set(also)

        armor_names = self._felyne_armor_texts["eng"]
        weapon_names = self._felyne_weapon_texts["eng"]
        armor = [i for i in range(1, len(armor_names) // 4)
                 if made_of_own(self._felyne_armor_recipes.get(i))
                 or any(t in armor_names[4 * i] or t in armor_names[4 * i + 1] for t in tokens)]
        weapons = [i for i in range(1, len(weapon_names) // 2)
                   if made_of_own(self._felyne_weapon_recipes.get(i)) or any(t in weapon_names[2 * i] for t in tokens)]
        return armor, weapons


class GameSet:
    """The games a run reads ported gear from, by the `source` of a monster's record: MH Generations' ("gen", the
    monsters ported first) and MH XX's ("xx", Great Maccao on). Either may be missing; `of` gives None then."""

    def __init__(self, gen: GenGame | None = None, xx: GenGame | None = None):
        self.games = {"gen": gen, "xx": xx}

    def of(self, source: str) -> GenGame | None:
        if source not in self.games:
            raise ValueError(f"no such source game: {source!r}")
        return self.games[source]

    @classmethod
    def wrap(cls, game: "GenGame | GameSet | None") -> "GameSet":
        """`game` as a set: a bare game is the one of its own format (Generations' or XX's), None has none."""
        if isinstance(game, GameSet):
            return game
        return cls(**{game.fmt.key: game}) if game is not None else cls()


# ----- the ported monsters --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class MonsterSpec:
    """Which of MHGen's (or XX's) gear is a monster's (game/data/curated/mhgen_monsters.json). A monster found in XX has
    its `xx` part: XX has no Western names to find his items and Felyne pieces by, so it lists their ids."""
    key: str
    name: str
    armor: tuple[tuple[int, int], ...]          # (blademaster series, gunner series) pairs
    weapons: dict = field(compare=False, hash=False)   # class nn ("00") -> (line, its English name)
    item_tokens: tuple[str, ...]                # English name parts of his own materials
    drops: tuple[str, ...]                      # English names of the items he drops
    felyne_tokens: tuple[str, ...]
    source: str = "gen"                         # the game it is read from: "gen" or "xx"
    item_ids: tuple[int, ...] = ()              # XX: his own items, the items he drops and his Felyne pieces by id
    drop_ids: tuple[int, ...] = ()
    felyne_armor_ids: tuple[int, ...] = ()
    felyne_weapon_ids: tuple[int, ...] = ()


def load_monster_specs(path: Path = MONSTERS_FILE, source: str = "gen") -> dict[str, MonsterSpec]:
    """The curated monsters by key, as read from game `source` ("gen": all; "xx": the ones with an `xx` part)."""
    data = json.loads(path.read_text(encoding="utf-8"))["monsters"]
    if source == "gen":
        return {key: MonsterSpec(key, m["name"], tuple((a, b) for a, b in m["armor"]),
                                 {nn: (line, name) for nn, (line, name) in m["weapons"].items()},
                                 tuple(m["item_tokens"]), tuple(m["drops"]), tuple(m["felyne_tokens"]))
                for key, m in data.items() if "armor" in m}      # a monster only XX has (Valstrax) has just `xx`
    return {key: MonsterSpec(key, m["name"], tuple((a, b) for a, b in m["xx"]["armor"]),
                             {nn: (line, name) for nn, (line, name) in m["xx"]["weapons"].items()}, (), (), (),
                             "xx", tuple(m["xx"]["items"]), tuple(m["xx"]["drops"]), tuple(m["xx"]["felyne_armor"]),
                             tuple(m["xx"]["felyne_weapons"]))
            for key, m in data.items() if "xx" in m}


@dataclass
class MonsterGear:
    """What one ported monster brings from MHGen. `items` has every item of his recipes, drops and own materials."""
    spec: MonsterSpec
    armor: tuple[GenArmorSet, ...]
    weapons: tuple[WeaponLine, ...]
    felyne_armor: tuple[GenFelyneArmor, ...]
    felyne_weapons: tuple[GenFelyneWeapon, ...]
    own_items: tuple[int, ...]                  # every item named after him (materials, scraps, Hyper versions)
    drop_items: tuple[int, ...]                 # the curated drops, in order
    items: dict[int, GenItem]
    categories: dict[int, GenItemCategory]      # the categories his upgrade recipes ask points of
    scrap_exchange: dict[int, tuple[tuple[int, int],
        ...]]    # scrap item -> (source item, points) of the scraps he uses
    skill_trees: dict[int, GenSkillTree]        # the trees of his armor

    def recipes(self):
        """Every recipe of his gear, with what it makes: ("armor", series, part or level, recipe), ("weapon", name,
        level, recipe)."""
        for pair in self.armor:
            for part, recipe in pair.create.items():
                yield "armor create", (pair.blademaster or pair.gunner).index, part, recipe
            for level, recipe in pair.upgrade.items():
                yield "armor upgrade", (pair.blademaster or pair.gunner).index, level, recipe
        for line in self.weapons:
            for level in line.levels:
                if level.recipe:
                    yield "weapon", line.names["eng"], level.level, level.recipe
            for level in line.g_levels:
                if level.recipe:
                    yield "weapon", line.names["eng"], level.level, level.recipe
            if line.upgrade_to_first:
                yield "weapon", line.names["eng"], 1, line.upgrade_to_first


def read_monster_gear(game: GenGame, key: str, specs: Mapping[str, MonsterSpec] | None = None, *,
                      check_names: bool = True) -> MonsterGear:
    """The gear of ported monster `key` from `game` (its spec is the one of the game's source: MH Generations' or XX's).
    Raises ValueError if a curated weapon line is not the named one (not the game the curation was made on);
    `check_names` False leaves that out (research/porting/xx_names.py reads XX before its names block has the names)."""
    spec = (specs or load_monster_specs(source=game.fmt.key))[key]
    armor = tuple(game.armor_set(a, b) for a, b in spec.armor)
    weapons = []
    for nn, (line, name) in spec.weapons.items():
        weapon = game.weapon_line(nn, line)
        if check_names and weapon.names["eng"] != name:
            raise ValueError(f"{spec.name}: weapon {nn} line {line} is {weapon.names['eng']!r}, not {name!r}")
        weapons.append(weapon)
    if spec.source == "xx":
        own, drops = spec.item_ids, list(spec.drop_ids)
        felyne_armor, felyne_weapons = spec.felyne_armor_ids, spec.felyne_weapon_ids
    else:
        own = tuple(game.find_items(tokens=spec.item_tokens))
        drops = []
        for name in spec.drops:
            ids = game.find_items(name=name)
            if not ids:
                raise ValueError(f"{spec.name}: no item named {name!r}")
            drops.append(ids[0])
        scraps = [i for i in own if "Scrap" in game.item_texts["eng"][2 * i]]
        felyne_armor, felyne_weapons = game.felyne_pieces_of(spec.felyne_tokens, scraps, drops)
    gear = MonsterGear(spec, armor, tuple(weapons), tuple(game.felyne_armor(i) for i in felyne_armor),
                       tuple(game.felyne_weapon(i) for i in felyne_weapons), own, tuple(drops), {}, {}, {}, {})
    used = set(own) | set(drops)
    for _, _, _, recipe in gear.recipes():
        used.update(m.item for m in recipe.materials)
        if recipe.category:
            gear.categories[recipe.category] = game.category(recipe.category)
    for felyne in (*gear.felyne_armor, *gear.felyne_weapons):
        for recipe in ((felyne.head_recipe, felyne.body_recipe) if isinstance(felyne,
            GenFelyneArmor) else (felyne.recipe,)):
            used.update(m.item for m in recipe)
    gear.scrap_exchange = {scrap: game.scrap_exchange[scrap] for scrap in sorted(used) if scrap in game.scrap_exchange}
    for rows in gear.scrap_exchange.values():
        used.update(source for source, _ in rows)
    for category in gear.categories.values():
        used.update(item for item, _ in category.members)
    gear.items = {i: game.item(i) for i in sorted(used)}
    trees = {skill.tree for pair in armor for series in pair.series for piece in series.pieces
             for skill in piece.skills}
    gear.skill_trees = {t: game.skill_tree(t) for t in sorted(trees)}
    return gear
