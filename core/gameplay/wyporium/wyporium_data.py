"""The Wyporium's data: what MH XX's materials trade for, and the rare materials exchange.

* **Trades of XX's materials.** Every new item of curated/xx_materials.json (and MH4U's own XX materials) trades 1 for 1
  for an item of an MH4U monster, rare for rare, common for common. Which monster: `counterpart` (what the game's own
  trades of that XX monster ask at that rank, else the nearest rank's, else the curated table); which item: `handed`
  (the counterpart's usable items at the rank the trade opens, `trade_rank`: the one in the same units band as the
  material's XX chance whose best chance is closest to it, else the closest overall).
* **The rare materials exchange.** `rare_exchange`: the rare items of every large monster of MH4U and the ported ones,
  each with its owners and the pool of items that pay it.

Everything curated (the pairs nothing decides, the unlock quests, the units, the rare percent) is
curated/wyporium.json; the rules are the layered prices' (core/equipment/layered/prices.py).
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import cache, cached_property

from core.equipment.layered.prices import (
    DROPS_PATH, ITEM_DROPS_PATH, ITEM_MONSTERS_PATH, Families, home_rank, load_curated_prices, load_trades,
    monster_families, units_for,
)
from core.equipment.layered.xx_materials import (  # noqa: F401  (trade_rank: the one place that decides it)
    RANKS, Materials, XxMaterial, load_materials, trade_rank,
)
from core.game.data.paths import CURATED_DIR, GENERATED_DIR

CURATED_PATH = CURATED_DIR / "wyporium.json"
RARE_EXCHANGE_PATH = GENERATED_DIR / "rare_exchange.json"
GAME, NEAREST, CURATED = "game trade", "nearest rank", "curated"


class WyporiumError(ValueError):
    pass


@cache
def load_curated() -> dict:
    return json.loads(CURATED_PATH.read_text(encoding="utf-8"))


def unlock_quest_id(rank: str) -> int:
    """The quest (id) that opens the game's first trades of `rank` (low, high, G), curated `unlock_quest`."""
    entry = load_curated()["unlock_quest"][rank]
    if entry["quest_id"] is None:
        raise WyporiumError(f"curated/wyporium.json: unlock_quest {rank} has no quest_id")
    return entry["quest_id"]


@cache
def load_rare_exchange() -> dict:
    return json.loads(RARE_EXCHANGE_PATH.read_text(encoding="utf-8"))


# ----- the monsters ------------------------------------------------------------------------------------------------

def merge_apex(families: Families, data) -> Families:
    """`families` with every Apex form counted as its base: his drop lists join the base's (best chance per item) and he
    is no monster of his own any more."""
    own = {m: {r: dict(items) for r, items in lists.items()} for m, lists in families.own.items()}
    droppers = {item: set(who) for item, who in families.droppers.items()}
    for monster in [m for m in own if data.monsters[m].is_apex]:
        parent = data.monsters[monster].material_parent
        for rank, items in own.pop(monster).items():
            into = own.setdefault(parent, {}).setdefault(rank, {})
            for item, percent in items.items():
                into[item] = max(into.get(item, 0), percent)
        for who in droppers.values():
            if monster in who:
                who.discard(monster)
                who.add(parent)
    return replace(families, own=own, droppers=droppers)


@dataclass
class Context:
    """What the rules read: MH4U monsters (`families`, Apex counted as the base), the curated prices' rules, the game's
    trades, XX's materials and the curated Wyporium file."""
    data: object
    families: Families
    rules: dict
    trades: Mapping[str, dict]
    materials: Materials
    curated: dict

    @cached_property
    def appearances(self) -> dict[int, set[int]]:
        """Monster -> the ranks (1-3) Kiranico's per-item data (item_monsters.json) has him at, an Apex form counted as
        its base: the ranks he really appears at (the executable's drop lists also hold ranks with no quest)."""
        aliases = load_curated_prices().get("kiranico_names", {})
        ids = {name.lower(): m for m, name in self.families.names.items()}
        out: dict[int, set[int]] = defaultdict(set)
        if not ITEM_MONSTERS_PATH.is_file():
            return out
        for record in json.loads(ITEM_MONSTERS_PATH.read_text(encoding="utf-8")).values():
            for name, rank, _ in record["monsters"] or []:
                monster = ids.get(aliases.get(name, name).lower())
                if monster is not None:
                    if self.data.monsters[monster].is_apex:
                        monster = self.data.monsters[monster].material_parent
                    out[monster].add({"low": 1, "high": 2, "g": 3}[rank])
        return out

    @cached_property
    def _names(self) -> dict[str, int]:
        return {name.lower(): m for m, name in self.families.names.items() if m in self.families.own}

    def by_name(self) -> dict[str, int]:
        return self._names

    def name(self, monster: int) -> str:
        return self.families.names[monster]

    def monster(self, name: str) -> int:
        try:
            return self.by_name()[name.lower()]
        except KeyError:
            raise WyporiumError(f"wyporium: {name!r} is no large monster of MH4U with drops") from None

    def item_name(self, item: int) -> str:
        return self.data.items[item].name

    def usable(self, monster: int, rank: int) -> dict[int, int]:
        """The monster's usable items at `rank` (1-3) whose home rank is not above it -> their best chance there."""
        found = self.families.usable_at(monster, rank, self.rules["max_families"])
        return {item: percent for item, percent in found.items()
                if (home_rank(self.families, monster, item) or 9) <= rank}


def load_context(data=None) -> Context:
    from core.game.data import load_game_data
    data = data or load_game_data()
    curated = load_curated_prices()
    drops = json.loads(DROPS_PATH.read_text(encoding="utf-8"))
    item_monsters = json.loads(ITEM_MONSTERS_PATH.read_text(encoding="utf-8")) if ITEM_MONSTERS_PATH.is_file() else None
    item_drops = json.loads(ITEM_DROPS_PATH.read_text(encoding="utf-8"))
    trades = load_trades()
    families = monster_families(data, drops, item_monsters, curated.get("kiranico_names", {}), item_drops,
                                curated.get("not_asked"), curated["unobtainable"], trades)
    return Context(data, merge_apex(families, data), curated["rules"], trades, load_materials(), load_curated())


# ----- which monster a trade is of -----------------------------------------------------------------------------------

def _aliases(materials: Materials) -> dict[str, str]:
    """Words a Wyporium item's name may carry for an XX monster -> the monster: his whole name, and for a base species
    each of its words that no other monster's name holds (Ceanataur for Shogun Ceanataur, Lao-Shan, Ludroth)."""
    names = list(materials.monsters)
    out = {name.lower(): name for name in names}
    bases = [name for name in names if materials.monsters[name].base is None]
    for name in bases:
        for word in name.split():
            if sum(word.lower() in other.lower().split() for other in bases) == 1:
                out.setdefault(word.lower(), name)
    return out


def trade_monsters(materials: Materials, trades: Mapping[str, dict],
                   by_item_name: Mapping[str, str] | None = None) -> dict[int, str]:
    """The game's Wyporium item (received, id) -> the XX monster of `materials` it is a material of: the item MH4U has
    with an XX material (`mh4u`), the monster the curated `trade_items` names for its name, else the longest alias
    whole-word in its name ("S.Barioth" is no Barioth)."""
    aliases = _aliases(materials)
    known = {item.mh4u: item.monster for item in materials.items if item.mh4u is not None}
    out = {}
    for key, trade in trades.items():
        if int(key) in known:
            out[int(key)] = known[int(key)]
            continue
        if trade["name"] in (by_item_name or {}):
            out[int(key)] = by_item_name[trade["name"]]
            continue
        found = [(len(word), monster) for word, monster in aliases.items()
                 if re.search(rf"(?<![\w.]){re.escape(word)}(?![\w])", trade["name"], re.IGNORECASE)]
        if found:
            out[int(key)] = max(found)[1]
    return out


# ----- the counterpart ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Counterpart:
    """The MH4U monster whose items an XX monster's materials of `rank` trade for, `source`: `GAME` (the game's trades
    of that XX monster at that rank ask his items), `NEAREST` (those of the nearest rank, `from_rank`) or `CURATED`."""
    monster: int
    source: str
    from_rank: int


def _ranks_near(rank: int) -> list[int]:
    """The other ranks, nearest first, the lower one first."""
    return sorted((r for r in (1, 2, 3) if r != rank), key=lambda r: (abs(r - rank), r))


def _owners(ctx: Context, item: int, rank: int) -> list[int]:
    return sorted(m for m, lists in ctx.families.own.items() if item in lists.get(rank - 1, {}))


def _family_pick(ctx: Context, gives: list[tuple[int, int]], rank: int) -> int | None:
    """The MH4U monster the items `gives` ((item, trade rank)) belong to at `rank`: the family most of them belong to (a
    tie: the one whose name starts most of the items' names), inside it the base when it drops any, else the member
    dropping most."""
    families = ctx.families
    votes: Counter = Counter()
    named: Counter = Counter()
    members: dict[int, Counter] = defaultdict(Counter)
    for item, _ in gives:
        owners = _owners(ctx, item, rank) or _owners(ctx, item, 1) or _owners(ctx, item, 2) or _owners(ctx, item, 3)
        for family in {families.root[m] for m in owners}:
            votes[family] += 1
            if ctx.item_name(item).lower().startswith(families.names[family].lower().split()[0]):
                named[family] += 1
        for m in owners:
            members[families.root[m]][m] += 1
    if not votes:
        return None
    family = min(votes, key=lambda f: (-votes[f], -named[f], f))
    return family if family in members[family] else min(members[family], key=lambda m: (-members[family][m], m))


def game_gives(ctx: Context) -> dict[str, dict[int, list[tuple[int, int]]]]:
    """XX monster -> trade rank (1-3) -> [(item the game's trades take, its rank)], the trades of that monster."""
    out: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for item, monster in trade_monsters(ctx.materials, ctx.trades, ctx.curated.get("trade_items")).items():
        trade = ctx.trades[str(item)]
        out[monster][trade["rank"]].append((trade["give"], trade["rank"]))
    return out


def _curated_pair(ctx: Context, monster: str, rank: int) -> int | None:
    entry = ctx.curated["counterparts"].get(monster)
    if entry is None:
        return None
    return ctx.monster(entry.get(RANKS[rank - 1], entry["monster"]))


def counterpart(ctx: Context, monster: str, rank: int) -> Counterpart:
    """The counterpart of the XX monster `monster` at `rank` (1-3): what the game's trades of that monster ask at that
    rank, else the nearest rank's (lower first), else the curated table's; a deviant takes his base's counterpart's
    variant when it drops at the rank (`variants`: curated, else the lowest id), else the base."""
    info = ctx.materials.monsters[monster]
    if info.base is not None:
        base = counterpart(ctx, info.base, rank)
        family = ctx.families.root[base.monster]
        variants = sorted(m for m in ctx.families.own
                          if ctx.families.root[m] == family and m != base.monster and ctx.usable(m, rank))
        chosen = ctx.curated.get("variants", {}).get(monster)
        pick = ctx.by_name().get(chosen.lower()) if chosen else None
        if pick not in variants:
            pick = variants[0] if variants else None
        return replace(base, monster=pick) if pick is not None else base
    gives = game_gives(ctx).get(monster, {})
    for at in (rank, *_ranks_near(rank)):
        if gives.get(at):
            found = _family_pick(ctx, gives[at], at)
            # a monster with nothing of the rank to give (Brute Tigrex low) is replaced by his base
            for candidate in (found, ctx.families.root.get(found)):
                if candidate is not None and ctx.usable(candidate, rank):
                    return Counterpart(candidate, GAME if at == rank and candidate == found else NEAREST, at)
    pair = _curated_pair(ctx, monster, rank)
    if pair is None or not ctx.usable(pair, rank) or rank not in ctx.appearances.get(pair, ()):
        raise WyporiumError(f"wyporium: no counterpart for {monster} at rank {rank}: add one that drops and appears "
                            "there (Kiranico's ranks) to curated/wyporium.json")
    return Counterpart(pair, CURATED, rank)


# ----- the items handed over -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Handed:
    """What one XX material trades for: the material, its rank (1-3), its chance in XX, the counterpart, the item handed
    over and its best chance at that rank. `game`: the game's own trade (an MH4U item shared with XX)."""
    item: XxMaterial
    rank: int
    percent: int
    counterpart: Counterpart | None
    give: int
    give_percent: int
    game: bool = False
    kept: bool = False     # the item handed over is in the units band of the material's XX chance (XX's rule holds)


def chances(ctx: Context, monster: int, rank: int) -> dict[int, int]:
    """The items `monster` may be asked at `rank` -> their best chance in any large monster's lists at that rank (the
    chance the price rule reads, `Families.best_chance`)."""
    return {item: ctx.families.best_chance(item, rank) or percent
            for item, percent in ctx.usable(monster, rank).items()}


def closest(candidates: Mapping[int, int], target: int, rare_percent: int, rarity: Mapping[int, int],
            taken: set[int]) -> int | None:
    """The item of `candidates` (item -> chance) whose chance is closest to `target`, on its side of `rare_percent`
    (rare for rare, common for common) when any is; ties: the rarer item, then the lower id. `taken`: items not to
    give."""
    free = {item: percent for item, percent in candidates.items() if item not in taken}
    same = {item: percent for item, percent in free.items() if (percent <= rare_percent) == (target <= rare_percent)}
    pool = same or free
    return min(pool, key=lambda item: (abs(pool[item] - target), -rarity.get(item, 0), item), default=None)


def handed_over(ctx: Context) -> list[Handed]:
    """One `Handed` per material of the file, in the file's order: the game's own trade for MH4U's items, the closest
    item of the counterpart for a new one (different for the materials of one monster and rank)."""
    out: list[Handed] = []
    taken: dict[tuple[str, int], set[int]] = defaultdict(set)
    items = list(ctx.materials.items)
    for item in items:                       # the game's trades first: a new item never repeats them
        if item.mh4u is not None:
            trade = ctx.trades[str(item.mh4u)]
            taken[item.monster, trade["rank"]].add(trade["give"])
    rare = ctx.rules["rare_percent"]
    for item in items:
        if item.mh4u is not None:
            trade = ctx.trades[str(item.mh4u)]
            owner = _family_pick(ctx, [(trade["give"], trade["rank"])], trade["rank"])
            out.append(Handed(item, trade["rank"], item.found[1],
                              None if owner is None else Counterpart(owner, GAME, trade["rank"]), trade["give"],
                              ctx.families.best_chance(trade["give"], trade["rank"]) or 0, True))
    new = sorted((i for i in items if i.slot is not None),
                 key=lambda i: (list(ctx.materials.monsters).index(i.monster), RANKS.index(trade_rank(i)),
                                i.found[1], i.slot))
    groups: dict[tuple[str, int], list[XxMaterial]] = defaultdict(list)
    for item in new:
        groups[item.monster, RANKS.index(trade_rank(item)) + 1].append(item)
    for (monster, rank), members in groups.items():
        cp = counterpart(ctx, monster, rank)
        found = chances(ctx, cp.monster, rank)
        # the item handed over keeps XX's units (same band) where one is free; the scarcest bands choose first
        band = {i.slot: {g for g, p in found.items() if units_for(p, ctx.rules) == units_for(i.found[1], ctx.rules)}
                for i in members}
        for item in sorted(members, key=lambda i: (len(band[i.slot] - taken[monster, rank]) or 99, i.found[1], i.slot)):
            inside = {g: found[g] for g in band[item.slot]}
            give = closest(inside, item.found[1], rare, ctx.families.rarity, taken[monster, rank])
            kept = give is not None
            if give is None:
                give = closest(found, item.found[1], rare, ctx.families.rarity, taken[monster, rank])
            if give is None:
                raise WyporiumError(f"wyporium: {item.name}: {ctx.name(cp.monster)} has no item to give at rank {rank}")
            taken[monster, rank].add(give)
            out.append(Handed(item, rank, item.found[1], cp, give, found[give], False, kept))
    order = {id(item): n for n, item in enumerate(items)}
    return sorted(out, key=lambda h: order[id(h.item)])


def obtain_field(handed: Handed, ctx: Context) -> dict:
    """The `obtain` of the curated item: {"trade": MH4U's id of the item handed over, "give": its name}."""
    return {"trade": handed.give, "give": ctx.item_name(handed.give)}


# ----- the rare materials exchange -------------------------------------------------------------------------------

def rare_items(found: Mapping[int, int], home: Mapping[int, int], rank: int, rare_percent: int,
               rarity: Mapping[int, int]) -> list[int]:
    """The rare items of one monster at `rank` among `found` (item -> best chance there), `home` item -> home rank: his
    rarest item with home `rank` (rule 3's exception when none has it: the rarest that drops there), and the items with
    home `rank` and a chance up to `rare_percent`."""
    def key(item):
        return found[item], -rarity.get(item, 0), item
    here = [item for item in found if home.get(item) == rank]
    first = min(here or found, key=key, default=None)
    if first is None:
        return []
    return sorted({first, *(item for item in here if found[item] <= rare_percent)})


def _mh4u_candidates(ctx: Context) -> dict[tuple[int, int], dict]:
    """(monster, rank) -> {"found", "home", "rare": [items]} of every monster with usable items at the rank."""
    rare = ctx.curated["rare_percent"]
    out = {}
    for monster in sorted(ctx.families.own):
        for rank in (1, 2, 3):
            found = ctx.families.usable_at(monster, rank, ctx.rules["max_families"])
            if not found:
                continue
            home = {item: home_rank(ctx.families, monster, item) for item in found}
            out[monster, rank] = {"found": found, "home": home,
                                  "rare": rare_items(found, home, rank, rare, ctx.families.rarity)}
    return out


def rare_exchange(ctx: Context, ported: Mapping | None = None) -> dict:
    """What generated/rare_exchange.json holds: `rare_percent`, `units` (by rank), `rows` (one per rare item and rank)
    and `no_pool` (the rare items nothing could pay, left out). MH4U's monsters (`item` an id)
    come first, then `ported` (the ported monsters by key, ported_prices.ported_monsters; None: none), whose rows name
    items by English name and carry `ported`. A pool is the usable items with home rank R of any owner, minus the rare
    items and of the curated `abundant` ones (items a monster sheds in quantity); with none (a monster whose items of
    that rank are all rare) any usable item of the rank of an owner. A row is sorted by its owner monster (the family
    root of its lowest-id owner: a monster and his variants together), then rank, then item id; a row whose item is a
    scrap (the item's category; a ported monster's scrap by his curated rewards) has `scrap`, and costs `scrap_units`.
    The ported monsters' rows follow in the order of `ported`."""
    from core.equipment.layered.ported_prices import usable as ported_usable
    from core.game.data.gamedata import ItemCategory     # the knowledge base: the generator's, not a run's
    candidates = _mh4u_candidates(ctx)
    excluded = set(ctx.curated["excluded"])
    abundant = {entry["item"] for entry in ctx.curated["abundant"]}
    rare_set = {item for c in candidates.values() for item in c["rare"]} | excluded
    scrap = ItemCategory.SCRAP
    rows: list[dict] = []
    no_pool: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for (_, rank), c in candidates.items():
        for item in c["rare"]:
            if (item, rank) in seen or item in excluded:
                continue
            seen.add((item, rank))
            owners = _owners(ctx, item, rank)
            here: set[int] = set()
            anywhere: set[int] = set()
            for owner in owners:
                got = candidates.get((owner, rank))
                if got:
                    here |= {i for i in got["found"] if got["home"][i] == rank}
                    anywhere |= set(got["found"])
            row = {"item": item, "name": ctx.item_name(item), "rank": rank, "owners": [ctx.name(m) for m in owners]}
            if ctx.data.items[item].category == scrap:
                row["scrap"] = True
            barred = rare_set | abundant
            pool = sorted((here - barred) or (anywhere - barred))
            (rows if pool else no_pool).append({**row, **({"pool": pool} if pool else {})})
    root = ctx.families.root
    rows.sort(key=lambda r: (root[min(ctx.monster(o) for o in r["owners"])], r["rank"], r["item"]))
    rare_names = {r["name"] for r in rows} | {r["name"] for r in no_pool}
    abundant_names = {entry["name"] for entry in ctx.curated["abundant"]}
    for key, monster in (ported or {}).items():
        for rank in (1, 2, 3):
            found = ported_usable(monster, ctx.families, rank, ctx.rules["max_families"])
            if not found:
                continue
            home = {item: monster.home.get(item) or next((r for r in (1, 2, 3) if item in monster.lists[r - 1]), None)
                    for item in found}
            if rank not in home.values():
                continue            # rows only at the ranks his items belong to (the exception below is MH4U's)
            names = {item: monster.english[item] for item in found}
            rare = rare_items(found, home, rank, ctx.curated["rare_percent"], monster.rarity)
            barred = {names[i] for i in rare} | rare_names | abundant_names
            for item in rare:
                pool = sorted(({names[i] for i in found if home[i] == rank} - barred)
                              or ({names[i] for i in found} - barred))
                row = {"item": names[item], "name": names[item], "ported": key, "rank": rank, "owners": [key]}
                if item in monster.scraps:
                    row["scrap"] = True
                (rows if pool else no_pool).append({**row, **({"pool": pool} if pool else {})})
    return {"description": "The rare materials exchange (core/gameplay/wyporium/wyporium_data.py; "
                           "): one row per rare item and rank: its owners and the "
                           "items that "
                           "pay it ('no_pool': rare items nothing could pay, left out). Written by "
                           "tools/build/build_wyporium.py.",
            "rare_percent": ctx.curated["rare_percent"], "units": ctx.curated["units"],
            "scrap_units": ctx.curated["scrap_units"], "rows": rows,
            "no_pool": no_pool}


# ----- the doc ------------------------------------------------------------------------------------------------------

TRADES_MARKS = ("<!-- trades: written by tools/build/build_wyporium.py -->", "<!-- end of trades -->")
EXCHANGE_MARKS = ("<!-- exchange: written by tools/build/build_wyporium.py -->", "<!-- end of exchange -->")
RANK_LABELS = {1: "low", 2: "high", 3: "G"}


def counterparts_table(ctx: Context, handed: list[Handed]) -> str:
    """The counterpart of every XX monster at every rank where he has a material, and where it comes from."""
    order = {name: n for n, name in enumerate(ctx.materials.monsters)}
    seen: dict[tuple[str, int], Counterpart | None] = {}
    for h in handed:
        if (h.item.monster, h.rank) not in seen or (seen[h.item.monster, h.rank] is None and not h.game):
            seen[h.item.monster, h.rank] = None if h.game else h.counterpart
    for (monster, rank), cp in list(seen.items()):
        if cp is None:
            seen[monster, rank] = counterpart(ctx, monster, rank)
    rows = ["| XX monster | Rank | Counterpart | Where it comes from |", "|---|---|---|---|"]
    for (monster, rank), cp in sorted(seen.items(), key=lambda kv: (order[kv[0][0]], kv[0][1])):
        why = cp.source + (f" ({RANK_LABELS[cp.from_rank]})" if cp.source == NEAREST else "")
        if cp.source == CURATED:
            base = ctx.materials.monsters[monster].base or monster
            why += f": {ctx.curated['counterparts'][base]['why']}"
        rows.append(f"| {monster} | {RANK_LABELS[rank]} | {ctx.name(cp.monster)} | {why} |")
    return "\n".join(rows)


def trades_table(ctx: Context, handed: list[Handed]) -> str:
    """The table of the trades of XX's materials: each material, the item handed over, both chances and whose units
    the looks ask (XX's: the item handed over is in the same band; else the item's, the Wyporium rule)."""

    def kind(h: Handed) -> str:
        return "game (the game's own trade)" if h.game else "same units" if h.kept else "the item's units"

    order = {name: n for n, name in enumerate(ctx.materials.monsters)}
    rows = ["| XX monster | Rank | Material (chance in XX) | Item handed over (best chance) | Counterpart | Units |",
            "|---|---|---|---|---|---|"]
    for h in sorted(handed, key=lambda h: (order[h.item.monster], h.rank, h.percent)):
        cp = ctx.name(h.counterpart.monster) if h.counterpart else "-"
        rows.append(f"| {h.item.monster} | {RANK_LABELS[h.rank]} | {h.item.name} ({h.percent} %) "
                    f"| {ctx.item_name(h.give)} ({h.give_percent} %) | {cp} | {kind(h)} |")
    return "\n".join(rows)


def rare_rank_mismatches(handed: list[Handed], rare_percent: int) -> list[Handed]:
    """The new trades that are not rare for rare or common for common (no item of that side was free)."""
    return [h for h in handed if not h.game and (h.percent <= rare_percent) != (h.give_percent <= rare_percent)]


def exchange_summary(exchange: Mapping) -> str:
    """The exchange's counts: rows by rank (MH4U's and each ported monster's), pools' sizes, empty pools."""
    rows = exchange["rows"]
    mh4u = [r for r in rows if "ported" not in r]
    lines = [f"{len(rows)} rare items: {len(mh4u)} of MH4U's monsters (" +
             ", ".join(f"{RANK_LABELS[r]} {sum(1 for x in mh4u if x['rank'] == r)}" for r in (1, 2, 3)) + ")"]
    for key in sorted({r["ported"] for r in rows if "ported" in r}):
        lines.append(f"{key}: " + ", ".join(
            f"{RANK_LABELS[r]} {sum(1 for x in rows if x.get('ported') == key and x['rank'] == r)}" for r in (1, 2, 3)))
    sizes = sorted(len(r["pool"]) for r in rows)
    left = exchange.get("no_pool", [])
    lines.append(f"pools: smallest {sizes[0]}, median {sizes[len(sizes) // 2]}, largest {sizes[-1]}; "
                 f"{len(left)} rare items left out, nothing pays them: "
                 + (", ".join(f"{r['name']} ({RANK_LABELS[r['rank']]})" for r in left) or "none"))
    return "\n".join(lines)


def _replace(doc: str, marks: tuple[str, str], text: str) -> str:
    start, end = doc.index(marks[0]) + len(marks[0]), doc.index(marks[1])
    return doc[:start] + "\n" + text + "\n" + doc[end:]


def with_tables(doc: str, ctx: Context, handed: list[Handed], exchange: Mapping) -> str:
    """with its generated parts rewritten between their markers."""
    mismatched = rare_rank_mismatches(handed, ctx.curated["rare_percent"])
    trades = (f"{sum(1 for h in handed if not h.game)} new trades and {sum(1 for h in handed if h.game)} of the game's "
              f"own (`game`).\n\n{counterparts_table(ctx, handed)}\n\n{trades_table(ctx, handed)}\n\n"
              f"Not rare for rare or common for common (no item of that side was free): "
              + (", ".join(f"{h.item.name}" for h in mismatched) or "none") + ".")
    doc = _replace(doc, TRADES_MARKS, trades)
    return _replace(doc, EXCHANGE_MARKS, exchange_summary(exchange).replace("\n", "\n\n"))
