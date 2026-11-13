"""The ported monsters' equipment as curated (game/data/curated/ported_equipment.json): the monsters' items per rank,
armor sets, weapon rules,
Felyne pieces, carve and reward maps. Nothing here is game data except the G rank items of MH Generations Ultimate
(web knowledge: names, rarity, prices, icons), which the file carries
itself.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from core.equipment.tables.item_data import FIRST_NEW_ID
from core.equipment.new_gear.new_texts import tidy_names
from core.game.data.paths import CURATED_DIR, GENERATED_DIR

if TYPE_CHECKING:
    from core.game.data.gamedata import ItemInfo

CURATED_FILE = CURATED_DIR / "ported_equipment.json"
RANKS = ("low", "high", "G")
PARTS = ("head", "body", "arms", "waist", "legs")
HUNTERS = ("blademaster", "gunner")
FELYNE_KINDS = ("weapon", "head", "body")
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
MAX_ITEM_SLOTS = 367            # the ported monsters' slots end below xx_materials.json's first id, 0x791 + 367
SCRAP_SHAPE = 49                # MH Generations' icon shape of a scrap
MAX_SCRAP_PERCENT = 30
# The monsters in the order their gear takes ids: a monster's weapons, armor and Felyne pieces take the fixed block of
# ids after the blocks of the monsters before it (blocks.py), so an id never depends on which monsters are on. Only
# ever append (with a block in blocks.BLOCKS).
ORDER = ("mizutsune", "alatreon", "great_maccao", "glavenus", "valstrax", "astalos",
         "boltreaver", "hellblade", "soulseer")     # the Deviants


class CuratedError(ValueError):
    pass


@dataclass(frozen=True)
class ItemSpec:
    """One item of a monster. `mhgen`: MH Generations' item id (XX's for a record whose source is xx; its name `name`
    is checked when reading; the numbers
    come from the game, the fields given here replace them); `mh4u`: an item the game has; neither: the numbers are
    here (the G rank items)."""
    key: str
    rank: str
    mhgen: int | None = None
    mh4u: int | None = None
    name: str | None = None
    names: Mapping[str, str] | None = None
    rarity: int | None = None
    sell: int | None = None
    buy: int | None = None
    carry: int | None = None
    shape: int | None = None
    colour: int | None = None
    description: str | None = None
    shared: bool = False        # a game-wide item he drops (the Wyvern Tears of his shiny drop), not a material of his
    # the key of the monster whose item this is (a Deviant's recipes and drops ask his base's G materials): the item is
    # that record's item of the same key, not a new one; `name` is its English name; always `shared`
    of: str | None = None

    @property
    def is_new(self) -> bool:
        return self.mh4u is None and self.of is None

    @property
    def is_scrap(self) -> bool:
        """A Smithy scrap (MHGen icon shape 49; English "Scrap", "Scrap+", "Heavy Scrap"): never carved, only a quest
        reward (step 4)."""
        english = (self.names or {}).get("eng") or self.name or ""
        return self.shape == SCRAP_SHAPE or "scrap" in english.lower()


@dataclass(frozen=True)
class ArmorSetSpec:
    """The five pieces of one rank and hunter style. Per piece, in PARTS order: `slots`, and each skill's points."""
    rank: str
    hunter: str
    rarity: int
    defense: tuple[int, int]               # base (level 1) and maximum
    resist: tuple[int, int, int, int, int]  # fire, water, thunder, dragon, ice (MH4U's order)
    slots: tuple[int, ...]
    skills: Mapping[str, tuple[int, ...]]   # MH4U skill tree name -> points per piece
    price: int


STEP_LABEL = re.compile(r"[LG][1-9][0-9]?")


@dataclass(frozen=True)
class WeaponShape:
    """The steps of each weapon line a monster keeps, modelled on the lines of a reference monster of MH4U: `keep` maps
    a weapon class key (or "default") to the
    labels of the steps that are made, `L1` ... the levels of MH Generations and `G1` ... MHGU's G steps, in the line's
    order. A step a line does not keep is retired: it keeps its id, record and name (a save's weapon stays the weapon it
    was) but nothing forges it and nothing upgrades into it. `reference` ({"name": "White Fatalis", "item_prefix": "Old
    Fatalis"}) names the monster whose weapons the shape copies: the weapons asking an item that starts with the
    prefix."""
    reference: Mapping[str, str]
    keep: Mapping[str, tuple[str, ...]]

    def kept(self, cls: str) -> tuple[str, ...]:
        """The labels of the steps `cls`'s line keeps."""
        return self.keep.get(cls) or self.keep["default"]


@dataclass(frozen=True)
class WeaponRules:
    """The weapon standard's curated parts."""
    rarities: Mapping[str, tuple[int, ...]]   # rank -> the rarity of its n-th weapon in a line (the last one repeats)
    # rank -> {an item's English name -> that rank's version of it}: a rank's first weapon that the original game cannot
    # create is forged from level I's create recipe with every material moved to the rank (`items.ItemBook.promote`)
    promote: Mapping[str, Mapping[str, str]]
    # an item of MH Generations' or MHGU's weapon recipes -> the item the weapons ask instead (an MH4U item name, one of
    # his own as "@key"), before the monster's `substitutes`: the Hyper items become his high rank materials, MHGU's
    # foreign ones his own G materials of the same kind
    substitutes: Mapping[str, str | None]
    overrides: tuple[Mapping, ...]            # {"class", "line", "level", <stat>: value} replacing a number
    shape: WeaponShape | None = None          # the steps of each line that are made (None: every step)


@dataclass(frozen=True)
class FelyneSpec:
    rarities: Mapping[str, int]
    armor: tuple[Mapping, ...]                # {"mhgen": id, "rank": ...}
    weapons: tuple[Mapping, ...]
    model: int | None                         # MH Generations' Felyne model of the set (None: no MHGen pieces)
    # Pieces with no MH Generations counterpart (Alatreon's set), each {"kind": weapon | head | body, "rank",
    # "template": the name of the MH4U Felyne piece whose model and pose bytes it copies, "element" (a weapon),
    # "names",
    # "descriptions" (five languages) and "recipe" ("3 Heavy Alatreon Scrap, 2 Alatreon Talon")}
    pieces: tuple[Mapping, ...] = ()


@dataclass(frozen=True)
class MonsterRecord:
    key: str
    slot: int                                 # his first item slot (item id 0x791 + slot)
    host: str
    items: tuple[ItemSpec, ...]
    # an item MH4U lacks -> an MH4U item name, "@key" (one of his own) or None (dropped)
    substitutes: Mapping[str, str | None]
    armor_names: Mapping[str, tuple[int, int]]   # rank -> MH Generations' (blademaster, gunner) series
    armor_sets: tuple[ArmorSetSpec, ...]
    armor_recipes: Mapping[str, Mapping[str, str]]   # rank -> part -> "2 Name*, 3 Name" (MHGU's G rank armor)
    weapons: WeaponRules
    felyne: FelyneSpec | None
    carve_map: Mapping[str, tuple[tuple[str, int], ...]]    # host item name -> (his item key, weight)
    carve_extra: tuple[tuple[str, str, int], ...]           # (rank, item key, percent) added to every carve list
    reward_map: Mapping[str, tuple[tuple[str, int], ...]]   # quest reward items replaced (beside carve_map)
    reward_quests: str                                      # "own": the quests of the monster
    # rank -> (his item key, percent) of the tail carve list, replacing the host's mapped one (MHGen's tail rates);
    # empty: the host's mapped list
    carve_tail: Mapping[str, tuple[tuple[str, int], ...]] = field(default_factory=dict)
    # rank -> (his item key, percent) of the body carve list, replacing the host's mapped one (MHGU's rates, for a host
    # whose materials repeat in two ranks); empty: the host's mapped list
    carve_body: Mapping[str, tuple[tuple[str, int], ...]] = field(default_factory=dict)
    # (rank, scrap key, percent) added to the ordinary reward tables of his quests of that rank that hold his materials:
    # scraps are rewards, never carves
    reward_scraps: tuple[tuple[str, str, int], ...] = ()
    # rank -> (his item key, percent, quantity) of the capture reward table (flag 0x4) of box A that his quests of that
    # rank get when they have none (XX's `bui` capture list; rows add up to 100). Empty: the quests keep theirs.
    reward_capture: Mapping[str, tuple[tuple[str, int, int], ...]] = field(default_factory=dict)
    # English name of an item, weapon, armor or Felyne piece as the plan makes it -> {language: name} replacing the
    # name in those languages (abbreviations that fit the box)
    names: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    # One entry per reward bit (0-7) of his part breaks (his DTP records' third byte, XX's fourth): {"low": rows,
    # "high": rows, "G": rows} with rows of (his item key, percent, quantity) adding up to 100, {"host": n} for his
    # host's reward bit n with his materials mapped as the carves are, or None for a bit nothing breaks
    # (equipment/ported_gear/breaks.py). Empty: his host's.
    breaks: tuple[Mapping[str, tuple[tuple[str, int, int], ...] | int] | None, ...] = ()
    # His shiny drop (the sparkle that falls off a hit monster, equipment/ported_gear/shiny.py): {"low": rows, "high":
    # rows, "G": rows} with rows of (his item key, percent) adding up to 100, or {"host": True} for his host's list with
    # his materials mapped as the carves are. None: no list of his own (a monster whose host has none drops nothing).
    shiny: Mapping[str, tuple[tuple[str, int], ...] | bool] | None = None
    # his item key -> the key of the same material one rank down, for a host with no low rank (Deviljho): his low rank
    # carve lists are the high ones filled in, and their rows (and a low rank quest's rewards) take the lower versions
    carve_low: Mapping[str, str] = field(default_factory=dict)
    # The small monsters his own call brings (curated/monster_rules.json `called_small`): their id -> {rank: (his item
    # key, percent)} of the carve list of each rank, adding up to 100
    carve_called: Mapping[int, Mapping[str, tuple[tuple[str, int], ...]]] = field(default_factory=dict)
    # The game his gear is read from: "gen" (MH Generations, the monsters ported first) or "xx" (MH XX, the one the
    # player has: Great Maccao on). Every `mhgen` id of his record, armor series pair and Felyne piece is that game's.
    source: str = "gen"

    def renamed(self, names: Mapping[str, str], kind: str) -> dict[str, str]:
        """`names` (a piece's name per language) fitted to the box of its `kind` ("item", "weapon", "armor", "felyne";
        equipment/new_gear/new_texts.tidy_names), then with this record's replacements for its English name (the name as
        the plan makes it, before the fitting)."""
        return {**tidy_names(names, kind), **self.names.get(names["eng"], {})}

    def item(self, key: str) -> ItemSpec:
        for item in self.items:
            if item.key == key:
                return item
        raise CuratedError(f"{self.key}: no item {key!r}")

    def sets(self, rank: str, hunter: str) -> ArmorSetSpec:
        for spec in self.armor_sets:
            if spec.rank == rank and spec.hunter == hunter:
                return spec
        raise CuratedError(f"{self.key}: no {rank} {hunter} armor set")

    @property
    def ranks(self) -> tuple[str, ...]:
        return tuple(r for r in RANKS if any(s.rank == r for s in self.armor_sets))


def _items(key: str, records: list[dict]) -> tuple[ItemSpec, ...]:
    out = []
    for record in records:
        known = set(ItemSpec.__dataclass_fields__)
        if set(record) - known:
            raise CuratedError(f"{key}: item {record.get('key')}: unknown fields {sorted(set(record) - known)}")
        if record["rank"] not in RANKS:
            raise CuratedError(f"{key}: item {record['key']}: rank {record['rank']!r}")
        out.append(ItemSpec(**record))
    keys = [i.key for i in out]
    if len(set(keys)) != len(keys):
        raise CuratedError(f"{key}: an item key twice")
    return tuple(out)


def _weights(table: Mapping[str, list]) -> dict[str, tuple[tuple[str, int], ...]]:
    return {name: tuple((k, int(w)) for k, w in rows) for name, rows in table.items()}


def _break_bit(bit: dict | None) -> dict | None:
    """One reward bit of the file's "breaks": rows as (key, percent, quantity) tuples, a quantity of 1 left out."""
    if bit is None or "host" in bit:
        return None if bit is None else dict(bit)
    return {rank: tuple((k, int(p), int(q[0]) if q else 1) for k, p, *q in rows) for rank, rows in bit.items()}


def _shiny(entry: dict | None) -> dict | None:
    """The file's "shiny": rows as (key, percent) tuples, or {"host": true}."""
    if not entry or "host" in entry:
        return dict(entry) if entry else None
    return {rank: tuple((k, int(p)) for k, p in rows) for rank, rows in entry.items()}


def _monster(key: str, m: dict) -> MonsterRecord:
    armor = m["armor"]
    sets = tuple(ArmorSetSpec(s["rank"], s["hunter"], s["rarity"], tuple(s["defense"]), tuple(s["resist"]),
                              tuple(s["slots"]), {n: tuple(v) for n, v in s["skills"].items()}, s["price"])
                 for s in armor["sets"])
    w = m["weapons"]
    shape = w.get("shape")
    rules = WeaponRules({rank: tuple(r) for rank, r in w["rarities"].items()},
                        {rank: dict(by_name) for rank, by_name in w.get("promote", {}).items()},
                        dict(w.get("substitutes", {})), tuple(w.get("overrides", ())),
                        WeaponShape(dict(shape.get("reference", {})),
                                    {cls: tuple(labels) for cls, labels in shape["keep"].items()}) if shape else None)
    f = m.get("felyne")
    felyne = FelyneSpec(f["rarities"], tuple(f.get("armor", ())), tuple(f.get("weapons", ())), f.get("model"),
                        tuple(f.get("pieces", ()))) if f else None
    carves, rewards = m["carves"], m["rewards"]
    record = MonsterRecord(
        key, m["slot"], m["host"], _items(key, m["items"]), dict(m["substitutes"]),
        {rank: tuple(pair) for rank, pair in armor["names"].items()}, sets, armor.get("recipes", {}), rules, felyne,
        _weights(carves["map"]), tuple((r, k, int(p)) for r, k, p in carves["extra"]), _weights(rewards["map"]),
        rewards["quests"],
        carve_tail={rank: tuple((k, int(p)) for k, p in rows) for rank, rows in carves.get("tail", {}).items()},
        carve_body={rank: tuple((k, int(p)) for k, p in rows) for rank, rows in carves.get("body", {}).items()},
        reward_scraps=tuple((r, k, int(p)) for r, k, p in rewards.get("scraps", ())),
        reward_capture={rank: tuple((k, int(p), int(q)) for k, p, q in rows)
                        for rank, rows in rewards.get("capture", {}).items()},
        names={eng: dict(by_lang) for eng, by_lang in m.get("names", {}).items()},
        breaks=tuple(_break_bit(bit) for bit in m.get("breaks", ())), shiny=_shiny(m.get("shiny")),
        carve_low=dict(carves.get("low", {})), source=m.get("source", "gen"),
        carve_called={int(monster): {rank: tuple((k, int(p)) for k, p in rows) for rank, rows in by_rank.items()}
                      for monster, by_rank in carves.get("called", {}).items()})
    check(record)
    return record


def check(record: MonsterRecord) -> None:
    """Raise CuratedError for a record the integration could not use."""
    keys = {i.key for i in record.items}
    if record.source not in ("gen", "xx"):
        raise CuratedError(f"{record.key}: source {record.source!r} (gen or xx)")
    if not 0 <= record.slot < MAX_ITEM_SLOTS:
        raise CuratedError(f"{record.key}: item slot {record.slot}")
    for item in record.items:
        sources = [item.mhgen is not None, item.mh4u is not None, item.names is not None, item.of is not None]
        if sum(sources) != 1:
            raise CuratedError(f"{record.key}: item {item.key} needs one of mhgen, mh4u, names or of")
        if item.of is not None and not (item.name and item.shared and item.of != record.key):
            raise CuratedError(f"{record.key}: item {item.key} is another monster's: it needs his key in `of`, its "
                               "English `name` and `shared`")
        if item.names is not None:
            missing = {"rarity", "sell", "buy", "carry", "shape", "colour"} - {
                n for n in ("rarity", "sell", "buy", "carry", "shape", "colour") if getattr(item, n) is not None}
            if missing or "eng" not in item.names:
                raise CuratedError(f"{record.key}: item {item.key} lacks {sorted(missing) or 'its English name'}")
    for spec in record.armor_sets:
        if spec.rank not in RANKS or spec.hunter not in HUNTERS:
            raise CuratedError(f"{record.key}: armor set {spec.rank} {spec.hunter}")
        if len(spec.slots) != 5 or any(len(v) != 5 for v in spec.skills.values()) or len(spec.skills) > 5:
            raise CuratedError(f"{record.key}: armor set {spec.rank} {spec.hunter}: five pieces, at most five skills")
    for table in (record.carve_map, record.reward_map):
        for name, rows in table.items():
            for target, weight in rows:
                if target not in keys or weight < 1:
                    raise CuratedError(f"{record.key}: {name} -> {target!r}")
    for rank, key, percent in record.carve_extra:
        if key not in keys or rank not in RANKS or not 1 <= percent <= 50:
            raise CuratedError(f"{record.key}: extra carve {rank} {key} {percent}")
    # Scraps are never carved, only quest rewards (a standing rule for every ported monster)
    scraps = {i.key for i in record.items if i.is_scrap}
    carved = {t for rows in record.carve_map.values() for t, _ in rows} | {k for _, k, _ in record.carve_extra} | {
        k for rows in (*record.carve_tail.values(), *record.carve_body.values()) for k, _ in rows}
    if carved & scraps:
        raise CuratedError(f"{record.key}: scraps {sorted(carved & scraps)} in a carve list: scraps are quest rewards")
    for key, lower in record.carve_low.items():
        if key not in keys or lower not in keys or key in scraps or lower in scraps:
            raise CuratedError(f"{record.key}: carves.low {key!r} -> {lower!r}: two of his materials, no scrap")
    check_breaks(record, keys, scraps)
    check_shiny(record, keys, scraps)
    for what, lists in (("tail", record.carve_tail), ("body", record.carve_body)):
        for rank, rows in lists.items():
            if rank not in RANKS or not rows or sum(p for _, p in rows) != 100 or any(k not in keys or p < 1
                                                                                      for k, p in rows):
                raise CuratedError(f"{record.key}: {what} carve of rank {rank!r}: his items, adding up to 100")
    for monster, lists in record.carve_called.items():
        if set(lists) != set(RANKS):
            raise CuratedError(f"{record.key}: the carves of monster {monster} need the ranks {list(RANKS)}")
        for rank, rows in lists.items():
            if not rows or sum(p for _, p in rows) != 100 or any(k not in keys or k in scraps or p < 1
                                                                 for k, p in rows):
                raise CuratedError(f"{record.key}: carve of monster {monster} at rank {rank!r}: his items, no scrap, "
                                   "adding up to 100")
    for rank, key, percent in record.reward_scraps:
        if key not in scraps or rank not in RANKS or not 1 <= percent <= MAX_SCRAP_PERCENT:
            raise CuratedError(f"{record.key}: scrap reward {rank} {key} {percent}: a scrap of his, 1-"
                               f"{MAX_SCRAP_PERCENT} percent")
    for rank, rows in record.reward_capture.items():
        if rank not in RANKS or not rows or sum(p for _, p, _ in rows) != 100 or any(
                k not in keys or p < 1 or not 1 <= q <= 0xFFFF for k, p, q in rows):
            raise CuratedError(f"{record.key}: capture reward of rank {rank!r}: his items, adding up to 100")
    unrewarded = scraps - {k for _, k, _ in record.reward_scraps}
    if unrewarded:
        raise CuratedError(f"{record.key}: scraps {sorted(unrewarded)} are in no quest reward (rewards.scraps)")
    for name, target in record.substitutes.items():
        if isinstance(target, str) and target.startswith("@") and target[1:] not in keys:
            raise CuratedError(f"{record.key}: {name} -> {target}")
    for eng, by_lang in record.names.items():
        if not by_lang or set(by_lang) - {"eng", "fre", "ger", "ita", "spa"} or not all(by_lang.values()):
            raise CuratedError(f"{record.key}: names of {eng!r}: {by_lang}")
    if record.felyne:
        for piece in record.felyne.pieces:
            if piece.get("kind") not in FELYNE_KINDS or piece.get("rank") not in record.felyne.rarities:
                raise CuratedError(f"{record.key}: Felyne piece {piece.get('kind')!r} of rank {piece.get('rank')!r}")
            if set(piece.get("names", ())) != set(LANGUAGES) or set(piece.get("descriptions", ())) != set(LANGUAGES):
                raise CuratedError(f"{record.key}: Felyne piece {piece['kind']}: names and descriptions in "
                                   f"{', '.join(LANGUAGES)}")
            if not piece.get("template") or not piece.get("recipe"):
                raise CuratedError(f"{record.key}: Felyne piece {piece['kind']} needs a template and a recipe")
    check_weapons(record)
    for rank in record.armor_recipes:
        if rank not in RANKS:
            raise CuratedError(f"{record.key}: recipes of rank {rank!r}")
    ranks = {s.rank for s in record.armor_sets}
    for rank in ranks:
        if rank not in record.armor_names and rank not in record.armor_recipes:
            raise CuratedError(f"{record.key}: {rank} armor has neither an MH Generations series nor recipes")


RARITY_RANGE = {"low": (1, 3), "high": (4, 7), "G": (8, 10)}     # the rarities of each rank (catalog.rank_of)


def check_weapons(record: MonsterRecord) -> None:
    """Raise CuratedError for weapon rules the integration could not use: a rarity ladder per rank, inside the rank's
    rarities and not falling; a promotion map only for the ranks a line can start in above level I."""
    rules = record.weapons
    if not rules.rarities or set(rules.rarities) - set(RANKS):
        raise CuratedError(f"{record.key}: weapon rarities per rank {RANKS}, not {sorted(rules.rarities)}")
    for rank, ladder in rules.rarities.items():
        low, high = RARITY_RANGE[rank]
        if not ladder or any(not low <= r <= high for r in ladder) or list(ladder) != sorted(ladder):
            raise CuratedError(f"{record.key}: {rank} weapon rarities {list(ladder)}: not falling, in {low}-{high}")
    for rank, by_name in rules.promote.items():
        if rank not in ("high", "G") or not all(isinstance(k, str) and isinstance(v, str) for k, v in by_name.items()):
            raise CuratedError(f"{record.key}: weapon promotion of rank {rank!r}")
    keys = {i.key for i in record.items}
    for name, target in rules.substitutes.items():
        if isinstance(target, str) and target.startswith("@") and target[1:] not in keys:
            raise CuratedError(f"{record.key}: weapons.substitutes {name} -> {target}")
    if rules.shape is not None:
        check_shape(record.key, rules.shape)


def step_order(label: str) -> tuple[int, int]:
    """Where a step label stands in a line: the levels of MH Generations (`L3`) before the G steps (`G1`)."""
    return (label[0] == "G", int(label[1:]))


def check_shape(key: str, shape: WeaponShape) -> None:
    """Raise CuratedError for a weapon shape the plan could not use: a `default`, only weapon classes beside it, and for
    each a non-empty list of well-formed, distinct labels in the line's order."""
    from core.equipment.tables.layout import WEAPON_CLASSES
    classes = {wc.key for wc in WEAPON_CLASSES}
    if "default" not in shape.keep or set(shape.keep) - classes - {"default"}:
        raise CuratedError(f"{key}: weapons.shape.keep needs a default and weapon class keys, not {sorted(shape.keep)}")
    for cls, labels in shape.keep.items():
        if not labels or not all(STEP_LABEL.fullmatch(label) for label in labels) or list(labels) != sorted(
                set(labels), key=step_order):
            raise CuratedError(f"{key}: weapons.shape.keep.{cls} {list(labels)}: steps as L1 ... (levels) and G1 ... "
                               "(G steps), each once, in the line's order")
    if shape.reference and not (shape.reference.get("name") and shape.reference.get("item_prefix")):
        raise CuratedError(f"{key}: weapons.shape.reference needs a name and the item_prefix of the monster's items")


MAX_BREAK_BITS = 8              # equipment/tables/item_data.BREAK_BITS
MAX_BREAK_ROWS = 8              # equipment/new_gear/new_breaks.MAX_ROWS


def check_breaks(record: MonsterRecord, keys: set[str], scraps: set[str]) -> None:
    """Raise CuratedError for a "breaks" entry the integration could not use: at most eight reward bits; per bit the
    three ranks, each 1-8 rows of his items adding up to 100 (a quantity of 1-4) and none of his scraps (scraps are
    quest rewards only), or the host's bit number."""
    if len(record.breaks) > MAX_BREAK_BITS:
        raise CuratedError(f"{record.key}: {len(record.breaks)} break reward bits (at most {MAX_BREAK_BITS})")
    for bit, entry in enumerate(record.breaks):
        if entry is None:
            continue
        if "host" in entry:
            if set(entry) != {"host"} or not isinstance(entry["host"], int) or not 0 <= entry["host"] < MAX_BREAK_BITS:
                raise CuratedError(f"{record.key}: break bit {bit}: \"host\" is a bit number 0-7 and nothing else")
            continue
        if set(entry) != set(RANKS):
            raise CuratedError(f"{record.key}: break bit {bit} needs the ranks {RANKS}, not {sorted(entry)}")
        for rank, rows in entry.items():
            where = f"{record.key}: break bit {bit}, rank {rank}"
            if not 1 <= len(rows) <= MAX_BREAK_ROWS:
                raise CuratedError(f"{where}: 1-{MAX_BREAK_ROWS} rows, not {len(rows)}")
            if sum(percent for _, percent, _ in rows) != 100:
                raise CuratedError(f"{where}: the rows add up to {sum(percent for _, percent, _ in rows)}, not 100")
            for key, percent, qty in rows:
                if key not in keys or percent < 1 or not 1 <= qty <= 4:
                    raise CuratedError(f"{where}: {key!r} x{qty} at {percent} %")
                if key in scraps:
                    raise CuratedError(f"{where}: {key!r} is a scrap: scraps are quest rewards only")


MAX_SHINY_ROWS = 7              # the longest list of the game's pointer array


def check_shiny(record: MonsterRecord, keys: set[str], scraps: set[str]) -> None:
    """Raise CuratedError for a "shiny" entry the integration could not use: the host's list (`{"host": True}` and
    nothing else) or the three ranks, each 1-7 rows of his items adding up to 100 and none of his scraps (scraps are
    quest rewards only)."""
    entry = record.shiny
    if entry is None:
        return
    if "host" in entry:
        if entry != {"host": True}:
            raise CuratedError(f"{record.key}: shiny drop: \"host\" is true and nothing else")
        return
    if set(entry) != set(RANKS):
        raise CuratedError(f"{record.key}: shiny drop needs the ranks {RANKS}, not {sorted(entry)}")
    for rank, rows in entry.items():
        where = f"{record.key}: shiny drop, rank {rank}"
        if not 1 <= len(rows) <= MAX_SHINY_ROWS:
            raise CuratedError(f"{where}: 1-{MAX_SHINY_ROWS} rows, not {len(rows)}")
        if sum(percent for _, percent in rows) != 100:
            raise CuratedError(f"{where}: the rows add up to {sum(percent for _, percent in rows)}, not 100")
        for key, percent in rows:
            if key not in keys or percent < 1:
                raise CuratedError(f"{where}: {key!r} at {percent} %")
            if key in scraps:
                raise CuratedError(f"{where}: {key!r} is a scrap: scraps are quest rewards only")


@cache
def load_curated(path: Path = CURATED_FILE) -> dict[str, MonsterRecord]:
    """The curated monsters by key (checked)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))["monsters"]
    return {key: _monster(key, m) for key, m in data.items()}


# ----- recipe strings ("2 Mizutsune Silkfin*, 5 Yukumo Stoutwood") -------------------------------------------------

_TERM = re.compile(r"^(?P<qty>\d+)\s+(?P<name>.+?)(?P<gate>\*)?$")


def parse_recipe(text: str) -> list[tuple[str, int, bool]]:
    """(item name, quantity, gated) of each term; a `*` marks the item that gates the recipe (the unlock item)."""
    out = []
    for term in text.split(","):
        match = _TERM.match(term.strip())
        if not match:
            raise CuratedError(f"recipe term {term.strip()!r}: \"<quantity> <item name>\" with an optional *")
        out.append((match["name"], int(match["qty"]), bool(match["gate"])))
    return out


def item_ids(record: MonsterRecord) -> dict[str, int]:
    """The id of each of the monster's items by key: MH4U's own, and the new ones at 0x791 + his first slot, in the
    order the file lists them. Needs nothing of the games, so the quest and reward code can use it."""
    out, slot = {}, record.slot
    for item in record.items:
        if item.of is not None:
            base = load_curated().get(item.of)
            if base is None or item.key not in item_ids(base):
                raise CuratedError(f"{record.key}: item {item.key} is {item.of}'s, who has no such item")
            out[item.key] = item_ids(base)[item.key]
        elif item.is_new:
            out[item.key] = FIRST_NEW_ID + slot
            slot += 1
        else:
            out[item.key] = item.mh4u
    return out


def material_ids(record: MonsterRecord) -> tuple[int, ...]:
    """The ids of his own materials (his knowledge base record's `material_ids`): `item_ids` less the shared items."""
    ids = item_ids(record)
    return tuple(ids[item.key] for item in record.items if not item.shared)


@cache
def mh4u_item_names() -> dict[int, str]:
    """MH4U's items by id (game/data/generated/items.json)."""
    data = json.loads((GENERATED_DIR / "items.json").read_text(encoding="utf-8"))
    return {int(k): v["name"] for k, v in data.items()}


@cache
def mh4u_item_rarities() -> dict[int, int]:
    """MH4U's item rarity by id (game/data/generated/item_categories.json): what the weapon forge metric weighs."""
    data = json.loads((GENERATED_DIR / "item_categories.json").read_text(encoding="utf-8"))
    return {int(k): v["rarity"] for k, v in data.items()}


def material_infos(key: str) -> dict[int, ItemInfo]:
    """The knowledge base's `ItemInfo` of the new items of monster `key` (by id), from the curated file alone: the
    rarity a rank gives (low 4, high 6, G 8) unless the record has one, so that the reward randomizer can hand them
    out (mizutsune_monster.with_him)."""
    from core.game.data.gamedata import ItemCategory, ItemInfo
    record = load_curated()[key]
    rarity = {"low": 4, "high": 6, "G": 8}
    ids = item_ids(record)
    out = {}
    for spec in record.items:
        if spec.is_new:
            name = (spec.names or {}).get("eng") or spec.name
            out[ids[spec.key]] = ItemInfo(ids[spec.key], name, True, ItemCategory.MONSTER_MATERIAL,
                                          spec.rarity or rarity[spec.rank], spec.carry or 99)
    return out
