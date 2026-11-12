"""MH XX's looks for layered equipment: the armor series and
weapons of MH XX whose models the pack brings (pack_run.py), named from the curated names file.

XX's armor series (table\\armorSeriesData of arc/resident.arc, 127 bytes each) give one model id for all their pieces
and both genders; they have no high rank flag, the rank is read from the rarity (low 1-3, high 4-7, G 8 and up).
A weapon (table\\weaponNNBaseData) gives its model at +4 and its rarity at +11. XX has only Japanese text: the names
in the five languages are in `looks_names.json` (research/porting/xx_names.py copies them once from MH Generations
Ultimate's text, where the tables are XX's byte for byte; the 14 series and 4 weapons MHGU names DUMMY keep
Generations' names). A series or weapon with no names there gives no look: the file holds the records of the looks
in the pack, and turning on more looks is writing their names (`xx_names.py --looks --all`).

A set look is the models of one or more series' pieces: a piece the pack brought is at its pack id (both
genders), a piece identical to a model of MH4U or to an earlier pack model keeps that model, a piece neither is
left out. Only series with a piece the pack brought give a look, and the per-part lists show only those pieces,
each model once. A weapon look is a pack weapon model, named after its first weapon (lowest rarity).
"""

import json
import struct
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.files.arc import parse_arc
from core.equipment.layered.looks import (
    LANGUAGES, NAME_PARTS, STATE_WEAPONS, ArmorLook, WeaponLook, common_name, order_armor,
)
from core.equipment.mhgen.equipment_pack import ARMOR_PARTS, CLASS_FOLDERS, WEAPON_FOLDERS, PackModel

RESIDENT = "arc/resident.arc"
NAMES_FILE = CURATED_DIR / "looks_names.json"
SERIES_TABLE = "table\\armorSeriesData"
WEAPON_TABLE = "table\\weapon{nn}BaseData"
TABLE_HEADER = 8          # the tables: a version (float) and a u32 count
SERIES_RECORD = 127
SERIES_PARTS = 6          # u8 per part (ARMOR_PARTS order): the series has that piece
SERIES_MODEL = 11         # u16, every piece's model, both genders
SERIES_GENDERS = 13       # u8 male may wear it, u8 female may
SERIES_HUNTERS = 15       # u8 blademaster, u8 gunner
SERIES_RARITY = 103       # rarity - 1
SERIES_PRICE = 17         # u32, what forging each of its pieces costs
SERIES_PIECES = 5         # the names of a series in the names file: one per piece (ARMOR_PARTS order)
SERIES_COLOURS = 114      # the pieces' default colour, per gender (male, then female): kind, row, entry (3 bytes)
COLOUR_ENTRY, COLOUR_ROW = 0, 1  # kind 0: the palette's entry; kind 1: COLOUR_ROWS_TABLE's row (an entry per piece)
PALETTE_TABLE = "table\\equipBaseColorData"   # the default colours (RGB): a piece's colour fresh from the forge
COLOUR_ROWS_TABLE = "table\\ArmorColorData"   # rows of a palette entry per piece (ARMOR_PARTS order)
NO_COLOUR = 0xFF          # a piece whose default colour is not known
WEAPON_MODEL = 4          # u16
WEAPON_RARITY = 11        # rarity - 1
WEAPON_PRICE = 12         # u32, what forging the line costs (its level 1; gear_weapons.level_price)
LOW_RANK_RARITY, HIGH_RANK_RARITY = 3, 7   # the rarities of low rank (1-3) and high rank (4-7); above: G
# The pack's armor parts and weapon classes -> the randomizer's (equipment/tables/layout.py).
PART_KEYS = dict(zip(ARMOR_PARTS, NAME_PARTS))
CLASS_KEYS = {WEAPON_FOLDERS[folder]: key for key, folder in CLASS_FOLDERS.items()}
HUNTERS = {(1, 0): "blademaster", (0, 1): "gunner"}


def rank_of(rarity: int) -> int:
    """The rank of a series or weapon of this rarity: 1 low, 2 high, 3 G (XX has no rank flag)."""
    return 1 if rarity <= LOW_RANK_RARITY else 2 if rarity <= HIGH_RANK_RARITY else 3


@dataclass(frozen=True)
class GenSeries:
    index: int
    model: int
    parts: tuple[str, ...]  # its pieces (ARMOR_PARTS)
    genders: str            # who may wear it: "mf", "m" or "f"
    hunter: str             # "blademaster", "gunner" or "both"
    rank: int               # 1 low, 2 high, 3 G
    rarity: int             # 1-11 (rank_of)
    names: dict = field(compare=False, hash=False)  # language -> piece names in ARMOR_PARTS order ("" for none)
    price: int = 0          # what forging one of its pieces costs (XX has one price per series)
    colours: tuple = ()     # (male, female): each piece's default colour (ARMOR_PARTS order), a palette entry; ()
                            # when the game has no colour tables


@dataclass(frozen=True)
class GenWeapon:
    cls: str                # the pack's class (WEAPON_FOLDERS' values)
    index: int
    model: int
    rarity: int
    names: dict = field(compare=False, hash=False)  # language -> name
    price: int = 0          # what forging the line costs (its level 1)


@dataclass(frozen=True)
class GenCatalog:
    """The real armor series and weapons that have names, with their names in every language."""
    series: tuple[GenSeries, ...]
    weapons: tuple[GenWeapon, ...]
    palette: tuple[int, ...] = ()   # the default colours (0xRRGGBB) the series' colours name

    def to_json(self) -> dict:
        return {"series": [[s.index, s.model, list(s.parts), s.genders, s.hunter, s.rank, s.rarity,
                            {lang: list(names) for lang, names in s.names.items()}, s.price,
                            [list(c) for c in s.colours]] for s in self.series],
                "weapons": [[w.cls, w.index, w.model, w.rarity, w.names, w.price] for w in self.weapons],
                "palette": list(self.palette)}

    @classmethod
    def from_json(cls, data: dict) -> "GenCatalog":
        series = tuple(GenSeries(i, model, tuple(parts), genders, hunter, rank, rarity,
                                 {lang: tuple(names) for lang, names in all_names.items()}, price,
                                 tuple(tuple(c) for c in colours))
                       for i, model, parts, genders, hunter, rank, rarity, all_names, price, colours
                       in data["series"])
        return cls(series, tuple(GenWeapon(*w) for w in data["weapons"]), tuple(data["palette"]))


def _records(data: bytes, size: int | None = None) -> list[bytes]:
    count = struct.unpack_from("<I", data, 4)[0]
    size = size or (len(data) - TABLE_HEADER) // count
    return [data[TABLE_HEADER + size * i:TABLE_HEADER + size * (i + 1)] for i in range(count)]


@cache
def _names_of(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_names(path: Path | None = None) -> dict:
    """The names file: {"series": {index: {lang: [five piece names]}}, "weapons": {class: {index: {lang: name}}}}."""
    return _names_of(path or NAMES_FILE)


def read_catalog(xx, names: Mapping | None = None) -> GenCatalog:
    """The catalog of MH XX's romfs `xx` (a RomFS): series with a model, pieces and a wearer, weapons with a model,
    named by `names` (the names file's content by default). A record the names lack gives no look."""
    names = load_names() if names is None else names
    tables = {e.name: e.data for e in parse_arc(xx.read(RESIDENT)).entries}
    palette, rows = _palette(tables)
    series = []
    for index, record in enumerate(_records(tables[SERIES_TABLE], SERIES_RECORD)):
        model = struct.unpack_from("<H", record, SERIES_MODEL)[0]
        parts = tuple(part for i, part in enumerate(ARMOR_PARTS) if record[SERIES_PARTS + i])
        genders = "".join(g for g, allowed in zip("mf", record[SERIES_GENDERS:SERIES_GENDERS + 2]) if allowed)
        if not model or not parts or not genders or str(index) not in names["series"]:
            continue
        named = names["series"][str(index)]
        piece_names = {lang: tuple(named[lang][i] if part in parts else "" for i, part in enumerate(ARMOR_PARTS))
                       for lang in LANGUAGES}
        hunter = HUNTERS.get(tuple(min(b, 1) for b in record[SERIES_HUNTERS:SERIES_HUNTERS + 2]), "both")
        rarity = record[SERIES_RARITY] + 1
        series.append(GenSeries(index, model, parts, genders, hunter, rank_of(rarity), rarity, piece_names,
                                struct.unpack_from("<I", record, SERIES_PRICE)[0], _colours(record, rows, palette)))
    weapons = []
    for folder, cls in WEAPON_FOLDERS.items():
        table = WEAPON_TABLE.format(nn=folder[1:])
        if table not in tables:
            continue
        named = names["weapons"].get(cls, {})
        for index, record in enumerate(_records(tables[table])):
            model = struct.unpack_from("<H", record, WEAPON_MODEL)[0]
            if model and str(index) in named:
                weapons.append(GenWeapon(cls, index, model, record[WEAPON_RARITY] + 1, dict(named[str(index)]),
                                         struct.unpack_from("<I", record, WEAPON_PRICE)[0]))
    return GenCatalog(tuple(series), tuple(weapons), palette)


def _palette(tables: Mapping[str, bytes]) -> tuple[tuple[int, ...], list[bytes]]:
    """XX's default colours (0xRRGGBB) and its rows of per-piece entries; nothing when the game lacks either table."""
    if PALETTE_TABLE not in tables or COLOUR_ROWS_TABLE not in tables:
        return (), []
    palette = tuple(r << 16 | g << 8 | b for r, g, b in _records(tables[PALETTE_TABLE], 3))
    return palette, _records(tables[COLOUR_ROWS_TABLE], len(ARMOR_PARTS))


def _colours(record: bytes, rows: list[bytes], palette: tuple[int, ...]) -> tuple:
    """A series' default colour of each piece, per gender (male, female): palette entries in ARMOR_PARTS order, or
    NO_COLOUR (an unknown kind, a row past the table or an entry past the palette)."""
    if not palette:
        return ()
    genders = []
    unknown = (NO_COLOUR,) * len(ARMOR_PARTS)
    for gender in range(2):
        kind, row, entry = record[SERIES_COLOURS + 3 * gender:SERIES_COLOURS + 3 * gender + 3]
        if kind == COLOUR_ROW:
            entries = tuple(rows[row]) if row < len(rows) else unknown
        else:
            entries = (entry,) * len(ARMOR_PARTS) if kind == COLOUR_ENTRY else unknown
        genders.append(tuple(e if e < len(palette) else NO_COLOUR for e in entries))
    return tuple(genders)


# ----- the looks ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class GenSet:
    look: ArmorLook          # pieces: part -> the catalog positions of the series naming it (one per gender)
    models: dict = field(compare=False, hash=False)  # NAME_PARTS part -> (male, female) MH4U model ids
    listed: tuple[str, ...]  # the parts it shows in the per-part lists (NAME_PARTS order)
    model: int = 0           # its series' model in MH XX (series_model): the look's owned bit, whatever the order
    # NAME_PARTS part -> (male, female) default colour (0xRRGGBB) of the series naming it for that gender, None unknown
    colours: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass
class GenLooks:
    sets: list[GenSet]
    weapons: dict[str, list[WeaponLook]]  # STATE_WEAPONS key -> looks (names: language -> MHGen's name)
    catalog: GenCatalog
    prices: dict[str, int] = field(default_factory=dict)  # look key -> what forging its real gear costs in XX

    @property
    def empty(self) -> bool:
        return not self.sets and not any(self.weapons.values())

    def piece_names(self, lang: str) -> dict[str, dict[int, str]]:
        """Part (NAME_PARTS) -> catalog position -> piece name, what layered.looks.armor_labels names sets by."""
        return {key: {pos: s.names[lang][ARMOR_PARTS.index(part)] for pos, s in enumerate(self.catalog.series)}
                for part, key in PART_KEYS.items()}


def _naming_order(series: GenSeries) -> tuple:
    return series.rank, series.rarity, series.index


def series_model(series: Iterable[GenSeries], models: Mapping[str, tuple[int, int]],
                 ported: Mapping[tuple[str, int], int]) -> int:
    """The MH XX model of a set look made by `series` (wearing `models`, ARMOR_PARTS part -> (male, female)): the model
    of a series with a part the pack brought from that model, the lowest if several. Every series of a real set has the
    same model, and no two sets share one; a series
    whose parts are all copies of other models' (`same`) never decides it, so turning on more series keeps it."""
    series = list(series)
    own = [s.model for s in series if any(ported.get((part, s.model)) == male for part, (male, _) in models.items())]
    return min(own or [s.model for s in series])


def _set_colour(catalog: GenCatalog, position: int, female: int, part: str) -> int | None:
    """The default colour (0xRRGGBB) of the piece `part` (ARMOR_PARTS) of the series at `position` for a gender, or
    None when the catalog does not know it."""
    colours = catalog.series[position].colours
    entry = colours[female][ARMOR_PARTS.index(part)] if colours else NO_COLOUR
    return None if entry == NO_COLOUR else catalog.palette[entry]


def gen_looks(catalog: GenCatalog, plan: Iterable[PackModel],
              same: Mapping[tuple[str, int], tuple[int, ...]] | None = None) -> GenLooks:
    """The looks of the pack `plan`. `same`: (slot, MHGen model) -> the MH4U models ((male, female) for armor)
    identical to a model the pack left out."""
    plan, same = list(plan), same or {}
    ported = {(p.slot, p.source): p.model for p in plan}
    pack_models = defaultdict(set)
    for p in plan:
        pack_models[p.slot].add(p.model)
    by_models: dict[tuple, list[int]] = {}
    for position, series in enumerate(catalog.series):
        models = {}
        for part in series.parts:
            if (part, series.model) in ported:
                models[part] = (ported[(part, series.model)],) * 2
            elif (part, series.model) in same:
                models[part] = tuple(same[(part, series.model)])
        if any(male in pack_models[part] for part, (male, _) in models.items()):
            by_models.setdefault(tuple(models.items()), []).append(position)

    looks, models_of, prices, model_of, colours_of = [], {}, {}, {}, {}
    for key, positions in by_models.items():
        reps = [min((p for p in positions if gender in catalog.series[p].genders),
                    key=lambda p: _naming_order(catalog.series[p]), default=None) for gender in "mf"]
        halves = tuple(dict.fromkeys(p for p in reps if p is not None))
        models = {PART_KEYS[part]: pair for part, pair in key}
        parts = tuple(part for part in NAME_PARTS if part in models)
        hunters = {catalog.series[p].hunter for p in halves}
        group = "/".join(dict.fromkeys(
            common_name(name for name in catalog.series[p].names["eng"] if name) for p in halves))
        first = models[parts[0]]
        look = ArmorLook("gen-" + "-".join(f"{m}.{f}" for _, (m, f) in key), first[0], first[1], parts,
                         {part: halves for part in parts}, min(catalog.series[p].rank for p in positions),
                         hunters.pop() if len(hunters) == 1 else "both", group, len(parts) >= 2)
        looks.append(look)
        models_of[look.key] = models
        named = [halves[0] if rep is None else rep for rep in reps]   # the series naming it for each gender
        colours_of[look.key] = {PART_KEYS[part]: tuple(_set_colour(catalog, named[g], g, part) for g in range(2))
                                for part, _ in key}
        model_of[look.key] = series_model((catalog.series[p] for p in positions), dict(key), ported)
        # each piece the look offers at its series' price (the cheapest of the series that make it)
        prices[look.key] = len(parts) * min(catalog.series[p].price for p in halves)
    sets, seen = [], defaultdict(set)
    for look in order_armor(looks):
        models = models_of[look.key]
        listed = []
        for part, (male, female) in models.items():
            pack_part = ARMOR_PARTS[NAME_PARTS.index(part)]
            if male in pack_models[pack_part] and (male, female) not in seen[part]:
                seen[part].add((male, female))
                listed.append(part)
        sets.append(GenSet(look, models, tuple(listed), model_of[look.key], colours_of[look.key]))
    weapons, weapon_prices = _weapon_looks(catalog, plan)
    return GenLooks(sets, weapons, catalog, {**prices, **weapon_prices})


def _weapon_looks(catalog: GenCatalog, plan: list[PackModel]) -> tuple[dict[str, list[WeaponLook]], dict[str, int]]:
    """The weapon looks by class, and what forging each look's weapon (its first, of lowest rarity) costs."""
    looks: dict[str, list[WeaponLook]] = {key: [] for key in STATE_WEAPONS}
    prices = {}
    for cls, key in CLASS_KEYS.items():
        models = {p.source: p.model for p in plan if p.slot == cls}
        firsts: dict[int, GenWeapon] = {}
        for weapon in catalog.weapons:
            if weapon.cls == cls and weapon.model in models:
                current = firsts.get(weapon.model)
                if current is None or (weapon.rarity, weapon.index) < (current.rarity, current.index):
                    firsts[weapon.model] = weapon
        for weapon in sorted(firsts.values(), key=lambda w: (w.rarity, w.index)):
            model = models[weapon.model]
            looks[key].append(WeaponLook(f"{key}-gen{model}", model, -1, rank_of(weapon.rarity),
                                         f"rarity{weapon.rarity}", names=dict(weapon.names)))
            prices[looks[key][-1].key] = weapon.price
    return looks, prices
