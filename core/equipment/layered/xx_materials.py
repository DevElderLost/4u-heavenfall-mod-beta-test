"""The rare materials of MH XX's monsters that MH4U lacks, brought into MH4U as new items for the Layered Gear prices
(curated/xx_materials.json).

A look of MH XX of a monster MH4U lacks (Lagiacrus, Astalos, Redhelm Arzuros) costs that monster's rarest material
of the look's rank, by MH4U's rule (prices.pick_two: when it is common, his next pick too; the units by its XX chance,
prices.units_for), read from XX's own reward lists (mhgen/gear_rewards.py: carves, shiny drops, part breaks, capture,
quest rewards):

* **A monster's materials** are the items of his lists whose XX item category bears his species' name (XX groups a
  species' parts in categories named after it: "Lagiacrus", "Ceanataur" for Shogun Ceanataur's, "Arzuros" for Redhelm
  Arzuros'): never a bone, an ore, dung, honey, a ticket, a coin or a charm, and never another species' part he drops
  (Shogun Ceanataur's Black Pearl is Hermitaur's).
* **A deviant** asks only the parts he alone drops (Boltreaver Astalos' Electric Barb); with none, his base species'.
* **One item per monster and rank** where he has one (two when the first is common); a look of a rank with none asks
  the next rank's, as the other XX looks (prices.rank_order). Only what a look asks is kept (`needed_picks`,
  `trim_picks`): a rank no look reaches has none, so no item is defined and traded for nothing. The file's `asks` says
  what each monster and rank asks, with each item's best percent there.

The items take ids from `first_id` (curated; far past the ported monsters' items, so their blocks never mix): item
`slot` is id `first_id + slot`, and slots are only ever appended (an id a save holds never changes). Two more items
come with them, Foreign Scrap and Foreign Scrap+ (`ForeignScrap`, the file's "foreign_scraps": slots 96 and 97, the
Felyne rows of XX and the Meownster Hunters' expeditions ask or bring them); the picking never takes their slots. An
item MH4U already has by name (a Wyporium material: Lagiacrus Sapphire, Spongy Hide) is MH4U's (`mh4u`), not a new one.
A new item is never deleted once released: one no pick asks any more is `retired` (its record, names, icon and prices
stay, so a save holding it still reads it; no trade, no look asks it), and the file is refused when a slot of
`xx_released_slots.json` is neither an item, a retired item nor a scrap. The items' records (names and descriptions in
the five languages, rarity, prices, carry limit, icon) are committed in `xx_item_records.json`, written from XX's dump
by the build tool, so a run defines the same items with XX's game or without it (the web installer never has it), and
with Layered Gear on or off (a save keeps the items it got while it was on).
`tools/build/build_xx_materials.py` reads both the XX ROM and MH Generations Ultimate's English texts and writes the
picks into the curated file, keeping every slot it already has.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path

from core.equipment.layered.prices import pick_two, rank_order, units_for
from core.game.data.paths import CURATED_DIR

CURATED_PATH = CURATED_DIR / "xx_materials.json"
RECORDS_PATH = CURATED_DIR / "xx_item_records.json"       # the item table record and texts of each new item
RELEASED_PATH = CURATED_DIR / "xx_released_slots.json"    # the slots a public release defined: never to vanish
RANKS = ("low", "high", "G")
LIST_KINDS = ("carve", "cut", "second cut", "shiny", "capture", "break", "reward")
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")


class MaterialsError(ValueError):
    pass


@dataclass(frozen=True)
class XxMonster:
    """A monster of MH XX that MH4U lacks: his name (MHGU's English), the `em` numbers his lists are under (two for a
    monster of two forms: Ahtal-Ka), his variant (4: a deviant) and, for a deviant, his base species' name."""
    name: str
    ems: tuple[int, ...]
    variant: int = 0
    base: str | None = None
    categories: tuple[str, ...] = ()     # XX item categories of his parts besides those named after him
    not_asked: tuple[str, ...] = ()      # items of his never asked (inorganic, or a small monster's too), by name
    ported: str | None = None            # the key of his port (a ported monster or his deviant): his items join a run
    #                                      only when that monster is not in it (`Materials.without_ported`)
    ranks: tuple[str, ...] = RANKS       # the ranks his looks ask a material at (Alatreon has no low look)
    sets: tuple[str, ...] = ()           # armor sets (group names) that are a deviant's: Hellblade, Soulseer


@dataclass(frozen=True)
class XxMaterial:
    """One item: its slot (a new item, id `first_id + slot`) or MH4U's id (`mh4u`: MH4U has it), XX's item id,
    English name, and the monster and rank it is the material of (`also`: other (monster, rank) that ask it); where it
    drops in XX (`found`: list kind, percent) and how a player gets it in MH4U (`obtain`: {"trade": the MH4U item
    handed over, "give": its name}, the Wyporium's trade, tools/build/build_wyporium.py; empty until decided)."""
    slot: int | None
    mh4u: int | None
    mhgen: int
    name: str
    monster: str
    rank: str
    found: tuple[str, int]
    also: tuple[tuple[str, str], ...] = ()
    obtain: str | Mapping = ""


@dataclass(frozen=True)
class ForeignScrap:
    """An item of the mod no monster drops (curated "foreign_scraps"): its slot (id `first_id + slot`), names and
    descriptions in the five languages, and the numbers of its item table record."""
    slot: int
    names: Mapping[str, str]
    descriptions: Mapping[str, str]
    rarity: int
    sell: int
    buy: int
    carry: int
    shape: int
    colour: int


@dataclass(frozen=True)
class Materials:
    first_id: int
    monsters: dict[str, XxMonster]
    items: tuple[XxMaterial, ...]
    # (monster, rank) -> the items its looks ask, in order: (item id, its best percent there)
    picks: dict[tuple[str, str], tuple[tuple[int, int], ...]] = field(default_factory=dict)
    scraps: tuple[ForeignScrap, ...] = ()      # Foreign Scrap and Foreign Scrap+: in every run that has these materials
    expedition: Mapping[str, object] = field(default_factory=dict)   # what each Meownster Hunters level adds
    retired: tuple[XxMaterial, ...] = ()       # released items no pick asks: defined, never traded or asked
    # XX item id -> {"names", "descriptions", rarity, sell, buy, carry, shape, colour} of each defined item
    # (xx_item_records.json); empty where an item's record is read from XX's game instead
    records: Mapping[int, Mapping] = field(default_factory=dict)

    def id(self, item: XxMaterial) -> int:
        return item.mh4u if item.mh4u is not None else self.first_id + item.slot

    def scrap_ids(self) -> dict[str, int]:
        """The English name of each foreign scrap -> its item id."""
        return {scrap.names["eng"]: self.first_id + scrap.slot for scrap in self.scraps}

    @property
    def ported_keys(self) -> set[str]:
        """The keys of the ported monsters whose looks these materials stand in for when the monster is absent."""
        return {m.ported for m in self.monsters.values() if m.ported}

    def of_set(self, group: str) -> str | None:
        """The monster whose `sets` hold the armor set called `group` (a deviant's: Hellblade, Soulseer), or None."""
        return next((name for name, monster in self.monsters.items() if group in monster.sets), None)

    def without_ported(self, present: Iterable[str]) -> "Materials":
        """The materials of a run whose ported monsters are `present` (their keys): the items of a monster whose port
        is present are left out (his gear brings his own items); a run without him keeps them. The picks stay, for the
        prices."""
        present = set(present)
        items = tuple(item for item in self.items if self.monsters[item.monster].ported not in present)
        return replace(self, items=items)

    def item(self, item_id: int) -> XxMaterial:
        return next(item for item in self.items if self.id(item) == item_id)

    @property
    def new(self) -> tuple[XxMaterial, ...]:
        """The items MH4U lacks, which a run adds."""
        return tuple(item for item in self.items if item.slot is not None)

    @property
    def defined(self) -> tuple[XxMaterial, ...]:
        """The items a run defines in the item table: the new ones and the retired."""
        return self.new + self.retired

    def material(self, monster: str, rank: int) -> tuple[int, int] | None:
        """(item id, the rank (1-3) it was found at) a look of `monster` at `rank` asks: his item of the first rank of
        `rank_order` that has one; a deviant with none at all, his base's. None: the monster has no item."""
        found = self._asks(monster, rank)
        return None if found is None else (found[0][0][0], found[1])

    def materials(self, monster: str, rank: int, rules: Mapping, trade_of: Mapping[int, tuple[int, int]] | None = None,
                  chance: Callable[[int, int], int | None] | None = None
                  ) -> tuple[list[tuple[XxMaterial, int]], int] | None:
        """([(item, units)], the rank (1-3) they were found at) a look of `monster` at `rank` asks (`material`'s rank),
        each item's units by its XX percent there (prices.units_for). None: the monster has no item. A material with a
        trade (`trade_of`: item id -> (the MH4U item its trade takes, the rank of the trade), `traded_materials`)
        follows the Wyporium rule of MH4U's own: its units by the best chance (`chance(item, rank)`) of the item its
        trade takes at the look's rank, else that item's first rank, and the rank returned is not below the trade's.
        A new item keeps XX's rule (its units by its XX percent) when the item its trade takes is in the same units
        band at the trade's rank (wyporium_data.handed_over picks it so); only one with no such item takes the
        Wyporium rule."""
        found = self._asks(monster, rank)
        if found is None:
            return None
        picks, at = found
        if not trade_of or chance is None:
            return [(self.item(item), units_for(percent, rules)) for item, percent in picks], at
        at = max([at, *(trade_of[item][1] for item, _ in picks if item in trade_of)])
        out = []
        for item, percent in picks:
            got = None
            if item in trade_of:
                give, trade_at = trade_of[item]
                same = chance(give, trade_at)
                if self.item(item).slot is None or same is None or units_for(same, rules) != units_for(percent, rules):
                    got = chance(give, max(rank, at))
            out.append((self.item(item), units_for(percent if got is None else got, rules)))
        return out, at

    def _asks(self, monster: str, rank: int) -> tuple[tuple[tuple[int, int], ...], int] | None:
        for name in (monster, self.monsters[monster].base) if monster in self.monsters else ():
            if name is None:
                continue
            for at in rank_order(rank):
                found = self.picks.get((name, RANKS[at - 1]))
                if found:
                    return found, at
        return None


def _monster(name: str, raw: Mapping) -> XxMonster:
    ranks = tuple(raw.get("ranks", RANKS))
    if not ranks or set(ranks) - set(RANKS):
        raise MaterialsError(f"xx_materials: {name}: ranks are some of {RANKS}")
    return XxMonster(name, tuple(raw["em"]), raw.get("variant", 0), raw.get("base"), tuple(raw.get("categories", ())),
                     tuple(raw.get("not_asked", ())), raw.get("ported"), ranks, tuple(raw.get("sets", ())))


def parse(data: Mapping, released: Mapping | None = None, records: Mapping | None = None) -> Materials:
    """The curated file's content as `Materials`; MaterialsError on a slot used twice, an unknown monster or rank, or
    `asks` naming an item the file lacks. Without `asks`, each item is asked alone by its monster and rank (and
    `also`), at its `found` percent. `released`: xx_released_slots.json's content: a slot it holds that the file no
    longer defines is refused. `records`: xx_item_records.json's content: a defined item without a record is
    refused."""
    first = int(data["first_id"], 0) if isinstance(data["first_id"], str) else data["first_id"]
    monsters = {name: _monster(name, raw) for name, raw in data["monsters"].items()}
    items, picks, slots = [], {}, set()
    retired = []
    for raw in data["items"]:
        if raw.get("retired"):
            if raw.get("slot") is None or raw["slot"] in slots:
                raise MaterialsError(f"xx_materials: retired {raw.get('name')}: its slot is missing or used twice")
            slots.add(raw["slot"])
            retired.append(XxMaterial(raw["slot"], None, raw["mhgen"], raw["name"], "", "", ("", 0)))
            continue
        item = XxMaterial(raw.get("slot"), raw.get("mh4u"), raw["mhgen"], raw["name"], raw["monster"], raw["rank"],
                          (raw["found"][0], raw["found"][1]), tuple(tuple(x) for x in raw.get("also", ())),
                          raw.get("obtain", ""))
        if (item.slot is None) == (item.mh4u is None):
            raise MaterialsError(f"xx_materials: {item.name} needs a slot or MH4U's id, not both")
        if item.slot in slots:
            raise MaterialsError(f"xx_materials: slot {item.slot} is used twice")
        if item.slot is not None:
            slots.add(item.slot)
        for monster, rank in ((item.monster, item.rank), *item.also):
            if monster not in monsters or rank not in RANKS:
                raise MaterialsError(f"xx_materials: {item.name}: {monster!r} {rank!r} is no monster and rank of "
                                     "the file")
            picks[monster, rank] = ((item.mh4u if item.mh4u is not None else first + item.slot, item.found[1]),)
        items.append(item)
    for monster in monsters.values():
        if monster.base is not None and monster.base not in monsters:
            raise MaterialsError(f"xx_materials: {monster.name}'s base {monster.base!r} is not in the file")
    if "asks" in data:
        by_xx = {item.mhgen: item.mh4u if item.mh4u is not None else first + item.slot for item in items}
        picks = {}
        for monster, ranks in data["asks"].items():
            for rank, asked in ranks.items():
                if monster not in monsters or rank not in RANKS or any(xx not in by_xx for xx, _ in asked):
                    raise MaterialsError(f"xx_materials: asks {monster!r} {rank!r}: no such monster, rank or item")
                picks[monster, rank] = tuple((by_xx[xx], percent) for xx, percent in asked)
    scraps, expedition = _foreign_scraps(data.get("foreign_scraps", {}), slots)
    if released is not None:
        gone = sorted(int(slot) for slot in released["slots"] if int(slot) not in slots)
        if gone:
            names = ", ".join(f"{slot} ({released['slots'][str(slot)]})" for slot in gone)
            raise MaterialsError(f"xx_materials: released slot(s) {names} vanished: an item is never deleted, keep it "
                                 "as retired")
    found = {int(xx): record for xx, record in (records or {}).get("items", {}).items()}
    if records is not None:
        lacking = [item.name for item in (*items, *retired) if item.slot is not None and item.mhgen not in found]
        if lacking:
            raise MaterialsError(f"xx_materials: no record in xx_item_records.json for {', '.join(lacking)}")
    return Materials(first, monsters, tuple(items), picks, scraps, expedition, tuple(retired), found)


def _foreign_scraps(raw: Mapping, taken: set[int]) -> tuple[tuple[ForeignScrap, ...], dict]:
    """The curated "foreign_scraps": the items (their slots must not be a material's or each other's) and the item each
    level of the Meownster Hunters adds (by English name, one of the items)."""
    scraps = []
    for item in raw.get("items", ()):
        if item["slot"] in taken:
            raise MaterialsError(f"xx_materials: foreign scrap slot {item['slot']} is used twice")
        taken.add(item["slot"])
        for field_name in ("names", "descriptions"):
            if set(item[field_name]) != set(LANGUAGES):
                raise MaterialsError(f"xx_materials: foreign scrap {item['names'].get('eng')}: {field_name} are "
                                     f"given in {', '.join(LANGUAGES)}")
        scraps.append(ForeignScrap(item["slot"], item["names"], item["descriptions"], item["rarity"], item["sell"],
                                   item["buy"], item["carry"], item["shape"], item["colour"]))
    expedition = dict(raw.get("expedition", {}))
    named = {scrap.names["eng"] for scrap in scraps}
    for level in ("low", "high"):
        if expedition and expedition.get(level) not in named:
            raise MaterialsError(f"xx_materials: expedition {level}: {expedition.get(level)!r} is no foreign scrap")
    return tuple(scraps), expedition


@cache
def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_materials(path: Path = CURATED_PATH, released: Path | None = RELEASED_PATH,
                   records: Path | None = RECORDS_PATH) -> Materials:
    """The curated file as `Materials`, checked against the released slots and holding the items' records (pass None
    to skip either)."""
    return parse(_read(path), _read(released) if released else None, _read(records) if records else None)


def released_slots(materials: Materials) -> dict[str, str]:
    """Slot -> English name of every item and scrap `materials` defines: the content of `xx_released_slots.json`
    (written by `tools/build/build_xx_materials.py --freeze` when a release goes public)."""
    names = {item.slot: item.name for item in materials.defined}
    names.update({scrap.slot: scrap.names["eng"] for scrap in materials.scraps})
    return {str(slot): names[slot] for slot in sorted(names)}


def item_records(materials: Materials, game, previous: Mapping | None = None) -> dict:
    """xx_item_records.json's content: for each defined item (by XX item id) its names and descriptions in the five
    languages and the numbers of its item table record, read from `game` (gear_data.GenGame of XX's ROM). A record
    `previous` already holds is kept as it is (an item never changes once released)."""
    out = dict((previous or {}).get("items", {}))
    for item in materials.defined:
        if str(item.mhgen) in out:
            continue
        found = game.item(item.mhgen)
        if found.name != item.name:
            raise MaterialsError(f"xx_materials: XX's item {item.mhgen} is {found.name!r}, not {item.name!r}")
        out[str(item.mhgen)] = {
            "names": {lang: found.names.get(lang) or found.names["eng"] for lang in LANGUAGES},
            "descriptions": {lang: found.descriptions.get(lang) or found.descriptions.get("eng", "")
                             for lang in LANGUAGES},
            "rarity": found.rarity, "sell": found.sell, "buy": found.buy, "carry": found.carry_max,
            "shape": found.icon_shape, "colour": found.icon_color}
    return {"items": dict(sorted(out.items(), key=lambda kv: int(kv[0])))}


def traded_materials(materials: Materials, trades: Mapping[str, dict]) -> dict[int, tuple[int, int]]:
    """Item id -> (the MH4U item its trade takes, the rank (1-3) of the trade) of every material of `materials` that has
    a Wyporium trade: MH4U's own by the game's trade (`trades`: wyporium_trades.json's "trades"), a new item by its
    `obtain` (the material's rank is the trade's)."""
    out = {}
    for item in materials.items:
        if item.mh4u is not None:
            if str(item.mh4u) in trades:
                out[item.mh4u] = (trades[str(item.mh4u)]["give"], trades[str(item.mh4u)]["rank"])
        elif isinstance(item.obtain, Mapping) and "trade" in item.obtain:
            out[materials.id(item)] = (item.obtain["trade"], RANKS.index(trade_rank(item)) + 1)
    return out


def trade_rank(item: XxMaterial) -> str:
    """The rank name (low, high, G) a new item's trade opens at: the lowest rank whose looks ask it, its own or an
    `also` rank below, so that no look is offered before (or after) it can be paid."""
    return min((item.rank, *(rank for _, rank in item.also)), key=RANKS.index)


# ----- what XX says of its items ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class XxItems:
    """XX's items as the picking and the looks' owners read them: English names and item categories' names (MHGU's,
    whose tables are XX's), rarity, and who drops each (item -> the (em, variant) whose reward lists hold it)."""
    names: Mapping[int, str]
    categories: Mapping[int, str]
    rarity: Mapping[int, int]
    droppers: Mapping[int, frozenset[tuple[int, int]]]


CATEGORY_TABLE = "itemCategoryTypeData"


def read_xx_items(romfs, mhgu: Path) -> XxItems:
    """`XxItems` of MH XX's `romfs` (game.executable.romfs.RomFS of its ROM) and MH Generations Ultimate's extracted
    files `mhgu` (local.ini mhgu_romfs); every monster with a `hagi` file counts for the droppers."""
    from core.equipment.layered.xx_monsters import english_item_names
    from core.equipment.mhgen.gear_data import GenGame, item_category
    from core.equipment.mhgen.gear_rewards import RewardFiles, read_monster_rewards
    from core.game.files.text.gmd import gmd_strings
    names = english_item_names(mhgu)
    category_names = gmd_strings((mhgu / "eng" / "table" / f"{CATEGORY_TABLE}_eng.gmd").read_bytes())
    records = GenGame(romfs).item_records
    files = RewardFiles(romfs)
    hagi = re.compile(r"hagi_s\d_em(?P<em>\d{3})_(?P<variant>\d{2})$")
    droppers: dict[int, set[tuple[int, int]]] = {}
    for em, variant in sorted({(int(m["em"]), int(m["variant"])) for name in files.result()
                               if (m := hagi.search(name))}):
        for rank in rank_lists([read_monster_rewards(files, em, variant)]).ranks:
            for item in rank:
                droppers.setdefault(item, set()).add((em, variant))
    categories = {i: category_names[item_category(r)] if item_category(r) else "" for i, r in enumerate(records)}
    return XxItems(names, categories, {i: r[5] + 1 for i, r in enumerate(records)},
                   {i: frozenset(d) for i, d in droppers.items()})


def only_his(monster: XxMonster, droppers: Mapping[int, frozenset[tuple[int, int]]]) -> set[int]:
    """The items only `monster` (his `em` numbers at his variant) drops."""
    his = {(em, monster.variant) for em in monster.ems}
    return {item for item, who in droppers.items() if who <= his}


def owner(items: Mapping[int, int], xx: XxItems, materials: Materials, common: set[int], share: float,
          lead: float) -> str | None:
    """The monster of `materials` a look whose recipes ask `items` (XX item -> units) is of, like XX's weapon vote
    (xx_monsters.weapon_monster): the species whose parts (by item category, `usable`'s rule) hold `share` of the
    units of the items that are not `common`, the second species at most `lead` of its units; a deviant of that species
    when an item only he drops is asked (Redhelm Ragehair). A ported monster (`ported`) owns none: his looks are the
    ported ones'. None: no monster of the file."""
    species = [m for m in materials.monsters.values() if m.base is None and m.ported is None]
    units: Counter = Counter()
    total = 0
    for item, quantity in items.items():
        if item in common:
            continue
        total += quantity
        category = xx.categories.get(item, "")
        found = next((m.name for m in species if of_species(m.name, category) or category in m.categories), None)
        if found is not None:
            units[found] += quantity
    if not units or not total:
        return None
    (top, count), *rest = units.most_common()
    if count < share * total or (rest and rest[0][1] > lead * count):
        return None
    for deviant in (m for m in materials.monsters.values() if m.base == top):
        if set(items) & only_his(deviant, xx.droppers):
            return deviant.name
    return top


# ----- picking them (tools/build/build_xx_materials.py) ------------------------------------------------------------

@dataclass(frozen=True)
class Lists:
    """A monster's reward lists by rank (low, high, G): item -> (best percent, the list kind that gives it)."""
    ranks: tuple[dict[int, tuple[int, str]], ...]

    def at(self, rank: int) -> dict[int, int]:
        """Item -> best percent at `rank` (1-3)."""
        return {item: found[0] for item, found in self.ranks[rank - 1].items()}

    def home(self, item: int) -> int | None:
        """The first rank (1-3) whose lists hold `item`."""
        return next((rank for rank in (1, 2, 3) if item in self.ranks[rank - 1]), None)


def rank_lists(rewards: Iterable) -> Lists:
    """`Lists` of one monster from his `gear_rewards.RankRewards` of each rank (low, high, G), any number of forms
    (Ahtal-Ka's two) joined: an item's best percent over every list of the rank."""
    ranks: list[dict[int, tuple[int, str]]] = [{}, {}, {}]
    for by_rank in rewards:
        for r, rank in enumerate(RANKS):
            got = by_rank[rank]
            rows = [("carve", got.body), ("cut", got.cut), ("second cut", got.second_cut), ("shiny", got.shiny),
                    ("capture", got.capture), *(("break", rows) for rows in got.breaks.values()),
                    ("reward", got.quest)]
            for kind, drops in rows:
                for drop in drops:
                    if drop.item and drop.percent and drop.percent > ranks[r].get(drop.item, (0, ""))[0]:
                        ranks[r][drop.item] = (drop.percent, kind)
    return Lists(tuple(ranks))


def of_species(name: str, category: str) -> bool:
    """An item of the XX category named `category` is a part of the monster called `name`: the category's name is
    a whole-word part of his ("Ceanataur" in "Rustrazor Ceanataur")."""
    return bool(category) and re.search(rf"(?<![\w-]){re.escape(category)}(?![\w-])", name, re.IGNORECASE) is not None


def usable(monster: XxMonster, lists: Lists, categories: Mapping[int, str],
           only_his: set[int] | None = None, names: Mapping[int, str] | None = None) -> set[int]:
    """The items of `lists` the monster may ask: parts of his species (`categories`: item -> its XX category's English
    name) but those his `not_asked` names (`names`: item -> English name); a deviant only those he alone drops
    (`only_his`)."""
    items = {item for rank in lists.ranks for item in rank if (names or {}).get(item) not in monster.not_asked}
    out = {item for item in items if of_species(monster.name, categories.get(item, ""))
           or categories.get(item) in monster.categories}
    return out & only_his if monster.base is not None and only_his is not None else out


def pick(monster: XxMonster, lists: Lists, categories: Mapping[int, str], rarity: Mapping[int, int],
         rare_percent: int, only_his: set[int] | None = None, names: Mapping[int, str] | None = None,
         mh4u_rank: Mapping[int, int] | None = None) -> dict[str, list[int]]:
    """Rank name -> the items the monster's looks of that rank ask (prices.pick_two over his usable items: the rarest,
    and the next one when it is common); a rank where he has none is left out. `mh4u_rank`: an XX item MH4U has -> the
    rank it first drops at in MH4U; it is not asked below that rank (a low player could not pay it)."""
    allowed = usable(monster, lists, categories, only_his, names)
    mh4u_rank = mh4u_rank or {}
    out = {}
    for rank in (1, 2, 3):
        if RANKS[rank - 1] not in monster.ranks:
            continue
        found = {item: percent for item, percent in lists.at(rank).items()
                 if item in allowed and mh4u_rank.get(item, 0) <= rank}
        if found:
            home = {item: lists.home(item) for item in found}
            out[RANKS[rank - 1]] = pick_two(found, home, rank, rare_percent, rarity,
                                            {item: lists.at(at)[item] for item, at in home.items()})
    return out


MONSTER_RULE = "monster:"      # a recipe item's curated replacement by a monster's material (xx_prices._replaced)


def needed_picks(xx_monsters: Mapping, replace_items: Mapping[str, str], monsters: Mapping[str, XxMonster],
                 of_set: Callable[[str], str | None] = lambda group: None) -> dict[tuple[str, int], int]:
    """(monster, rank 1-3) -> how many of his picks there a look asks (2: all, 1: the first only), from
    generated/layered_xx_monsters.json (`xx_monsters`): a look of no monster MH4U has (its recipe's `xx_monster`) asks
    all, a recipe item replaced by his material ("monster:M" in `replace_items`) the first, a ported monster's look
    (his XX materials in a run without him; a deviant's set, `of_set`) all."""
    out: dict[tuple[str, int], int] = {}

    def need(name: str, rank: int, count: int) -> None:
        out[name, rank] = max(out.get((name, rank), 0), count)

    for kind in ("armor", "weapons"):
        for look in xx_monsters.get(kind, {}).values():
            if look["monster"] in monsters and monsters[look["monster"]].ported:
                need(of_set(look.get("name", "")) or look["monster"], look["rank"], 2)
        for look in xx_monsters.get("recipes", {}).get(kind, {}).values():
            if look.get("xx_monster"):
                need(look["xx_monster"], look["rank"], 2)
                continue
            for name, _ in look["materials"]:
                rule = replace_items.get(name, "")
                if rule.startswith(MONSTER_RULE) and rule[len(MONSTER_RULE):] in monsters:
                    need(rule[len(MONSTER_RULE):], look["rank"], 1)
    return out


def trim_picks(picks: Mapping[str, Mapping[str, Sequence[int]]], monsters: Mapping[str, XxMonster],
               needed: Mapping[tuple[str, int], int]) -> dict[str, dict[str, list[int]]]:
    """`picks` (monster -> rank name -> items) cut to what the looks ask (`needed_picks`), each need resolved as
    `Materials._asks` does (the monster's first rank of `rank_order` with a pick, else his base's): a rank no look
    reaches is dropped, and a second item only a monster material's replacement reaches (the first only) too, so no
    new item is defined and traded that no look asks."""
    used: dict[tuple[str, int], int] = {}
    for (name, rank), count in needed.items():
        for candidate in (name, monsters[name].base if name in monsters else None):
            at = next((at for at in rank_order(rank) if picks.get(candidate, {}).get(RANKS[at - 1])), None) \
                if candidate else None
            if at is not None:
                used[candidate, at] = max(used.get((candidate, at), 0), count)
                break
    return {name: {RANKS[at - 1]: list(by_rank[RANKS[at - 1]])[:used[name, at]]
                   for at in (1, 2, 3) if (name, at) in used and RANKS[at - 1] in by_rank}
            for name, by_rank in picks.items()}


def materials_file(previous: Mapping, picks: Mapping[str, Mapping[str, Sequence[int]]], lists: Mapping[str, Lists],
                   names: Mapping[int, str], mh4u: Mapping[str, int] | None = None) -> dict:
    """The curated file with the `picks` (monster -> rank -> XX items, in order) made: `previous` (the file as it is)
    keeps every item and slot it has (their `obtain` too); a new item takes the next slot, one MH4U has (`mh4u`: lower
    case English name -> MH4U's id) its id, and an item two monsters or ranks ask is one item with `also`; one of
    no pick asks any more is dropped (a kept new item keeps its slot). `asks`: monster -> rank -> [[XX item, its
    best percent there]], what `picks` gives. An item with a slot that no pick asks any more is kept as `retired` (an id
    a save holds stays defined; the released slots check refuses its loss); a retired one a pick asks again is revived
    in its slot."""
    mh4u = mh4u or {}
    items = [dict(raw) for raw in previous.get("items", ())]
    by_xx = {raw["mhgen"]: raw for raw in items}
    used = [raw["slot"] for raw in items if "slot" in raw]
    used += [raw["slot"] for raw in previous.get("foreign_scraps", {}).get("items", ())]
    next_slot = max(used, default=-1) + 1
    asks: dict[str, dict[str, list[list[int]]]] = {}
    for monster in previous["monsters"]:
        for rank in RANKS:
            for item in picks.get(monster, {}).get(rank, ()):
                percent, kind = lists[monster].ranks[RANKS.index(rank)][item]
                asks.setdefault(monster, {}).setdefault(rank, []).append([item, percent])
                raw = by_xx.get(item)
                if raw is not None and raw.get("retired"):
                    where = {"slot": raw["slot"]}
                    items.remove(raw)
                    raw = None
                else:
                    where = ({"mh4u": mh4u[names[item].lower()]} if names[item].lower() in mh4u
                             else {"slot": next_slot})
                if raw is None:
                    raw = {**where, "mhgen": item, "name": names[item], "monster": monster, "rank": rank,
                           "found": [kind, percent], "obtain": ""}
                    items.append(raw)
                    by_xx[item] = raw
                    next_slot += "slot" in where and where["slot"] == next_slot
                elif (raw["monster"], raw["rank"]) != (monster, rank) and [monster, rank] not in raw.get("also", []):
                    raw.setdefault("also", []).append([monster, rank])
    asked = {item for ranks in asks.values() for found in ranks.values() for item, _ in found}
    items = [raw if raw["mhgen"] in asked or raw.get("retired") else retire(raw) for raw in items]
    items = [raw for raw in items if raw is not None]
    return {**{key: value for key, value in previous.items() if key != "asks"}, "items": items, "asks": asks}


def retire(raw: Mapping) -> dict | None:
    """The record of an item no pick asks any more: a new item (with a slot) becomes `retired`, which keeps its slot
    and name; one MH4U has needs no id of its own: None."""
    if "slot" not in raw:
        return None
    return {"slot": raw["slot"], "mhgen": raw["mhgen"], "name": raw["name"], "retired": True}


# ----- in a run -----------------------------------------------------------------------------------------------------

@dataclass
class Added:
    """What `add_materials` gives: the executable, the items (ported_gear.items.ItemBook) and their texts."""
    code: bytes
    book: object
    texts: object


def add_materials(code: bytes, xx_rom: Path | None, materials: Materials | None = None) -> Added:
    """`code` (the update's executable) with the new and the retired items of `materials` (default: the curated file),
    from the curated records (`xx_item_records.json`): the same items in a run with XX's game `xx_rom` or without it
    (None), for every run with no ported monster, Layered Gear on or off (with one, his gear adds them:
    ported_gear.build.build_gear's `materials`)."""
    from core.equipment.mhgen.gear_data import GameSet, GenGame
    from core.equipment.new_gear.new_items import patch_items
    from core.equipment.ported_gear.curated import mh4u_item_names
    from core.equipment.ported_gear.items import ItemBook, item_texts
    from core.game.executable.romfs import RomFS
    book = ItemBook([], GameSet(None, GenGame(RomFS(xx_rom))) if xx_rom else None, mh4u_item_names(),
                    materials=materials or load_materials())
    patched, _ = patch_items(code, book.slots(), None, book.slot_groups())
    return Added(patched, book, item_texts(book))


TABLE_START = "<!-- table: written by tools/build/build_xx_materials.py -->"
TABLE_END = "<!-- end of table -->"


def doc_table(materials: Materials) -> str:
    """The list of one row per item, by monster in the file's order and rank."""
    order = {name: n for n, name in enumerate(materials.monsters)}
    rows = ["| Id | Item | Monster | Rank | Found in XX | Also | Obtain |", "|---|---|---|---|---|---|---|"]
    for item in sorted(materials.items, key=lambda i: (order[i.monster], RANKS.index(i.rank))):
        where = f"{materials.id(item)} (0x{materials.id(item):X})" if item.mh4u is None else \
            f"MH4U's {item.mh4u}"
        also = ", ".join(f"{monster} {rank}" for monster, rank in item.also)
        obtain = f"Wyporium: {item.obtain['give']}" if isinstance(item.obtain, Mapping) else item.obtain
        rows.append(f"| {where} | {item.name} | {item.monster} | {item.rank} | {item.found[0]} {item.found[1]} % | "
                    f"{also} | {obtain} |")
    return "\n".join(rows)


def with_table(doc: str, materials: Materials) -> str:
    """The doc's text with its list rewritten between its markers."""
    start, end = doc.index(TABLE_START) + len(TABLE_START), doc.index(TABLE_END)
    return doc[:start] + "\n" + doc_table(materials) + "\n" + doc[end:]


def check_slots(items: Sequence[XxMaterial], first_id: int, last_id: int) -> None:
    """MaterialsError when an item's id is past `last_id` (item_data.LAST_NEW_ID)."""
    for item in items:
        if item.slot is not None and first_id + item.slot > last_id:
            raise MaterialsError(f"xx_materials: {item.name} would be item {first_id + item.slot}, past {last_id}")
