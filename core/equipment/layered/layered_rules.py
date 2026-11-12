"""The block layered_rules: when each look of the forge-style screens appears, and what it costs.

A rule is a list of conditions, one per record of the catalogs of `layered_data` (MH4U's armor looks and XX's, the
weapon looks of each class in both, and the Felyne rows), in the same order. The lists are shared: a rule is the word
index of its list in `conds`. A look appears when its rank is open (the header's `unlock` lists, curated
`rank_unlocks`: `rank_unlock_words`) and any condition of its list holds (layered_forge.c; forge_rule.py says how a
condition reads the save):

* a look of MH4U: the forge's rule, generated from the game's tables (`Look.forge`);
* a relic of MH4U (relic_prices.relic_keys): its forge rule alone, the bits of the pieces wearing it the hunter has had
  once; on the Relics screens, which list every relic of the ranks open, it says the relic is bought already;
* a Felyne row of the game's own gear: the forge's rule of every piece wearing that number (`FelyneRow.forge`);
* a look of XX with a record in the price table (xx_prices.py): the record's conditions;
* a look of XX without a record, a Felyne row of XX, any other look without a rule of its own: always, until the curated
  data gives it a list of its own (`recipes`), and then any item of the list; a list that names an item this game lacks
  (an unknown id or name, or a new item of a monster not in the run) never appears. A list of its own replaces the
  record's conditions;
* a look a ported monster's gear wears (Mizutsune, Glavenus, Alatreon, Great Maccao), joined by model: the forge rule of
  that gear, as the game's tables have it in this run (its recipe's first material when gated, its parents' bits), in
  place of "always" (not for a Felyne row of the game's own, which keeps its own rule). A look of the same monster that
  no piece of his wears (Hellblade is Glavenus', Soulseer Mizutsune's; the sets of his the port does not use) appears
  when his looks of the same rank do: the union of their ported rules, else the next ranks'
  (xx_prices.equivalent_forge).
  A run without the monster has no such piece: his looks keep their record's "always".

What a look costs is its recipe (`RECIPE`), the materials of the price table (prices.py; xx_prices.py for XX), up to
two, and its zenny: its original forge price mapped into the range of its kind and listed rank (zenny.py, curated
`recipes.zenny`; the originals: `_originals`). A look no piece of which has a recipe (a relic) costs exactly what its
counterpart costs in the run, curated recipes and all, over every other rule; without one, what the dearest look of its
monster (or of any of its family) costs at its listed rank, of its kind or, when they have none, of the other kind, or
the relic's own curated price when they have none of its rank; a relic of no monster, of monsters without a look or of
a counterpart the run lacks, its rank's tier of the relic table with its zenny raised (relic_prices.py, curated
`layered_relics.json`: by its rarity in `tables`); "Nothing" is free: no material and
no zenny, and the screen shows it as bought. A look of XX without a record, and a Felyne
row of XX, cost zenny only. A record with `ported` names the item of a ported monster (ported_prices.py): the material
is that item when the monster is in the run (`ported`, with `item_ids`), else the record's own materials (for a look of
XX his XX materials, new items of a run without him, as any XX monster's look: gameplay/wyporium; an MH4U look keeps its
recipe). The curated `recipes` of a look (`armor`, `weapons`, `felyne`) replace its
recipe and, with a `price`, its zenny. Each catalog has a u16 recipe index and a u32 zenny parallel to its rules.

Relics are offered once per model (xx_prices.relic_offers): `relic_trim` says which parts of a free look stay, and which
looks are dropped; a dropped look has the empty rule, and a trimmed one is written with the parts that stay
(layered_equipment.py). The order entry of every relic kept has ORDER_RELIC (look_order.py): the Relics screens list
those alone, the others every look but them.

The block (little-endian; offsets from its start): the header (`HEADER`), the rules of the armor looks (u16 each), those
of each class' weapons, the recipe indexes in the same order, the Felyne rows (`ROW`), their rules and recipe indexes,
the zenny of every look in the same order (u32 each; armor, weapons, Felyne rows), the lists' order (look_order.py:
u16 entries, positions over both catalogs; armor, each class' weapons, Felyne rows), the owned bit of each armor look
(u16, parallel to the rules; `armor_bits`: a model, never a place), the messages of the entry's Relics line and its
help, `conds` (u16 words: a list ends with 0; 0xFFFF alone is "always"; bit 15 clear: an item in bits 0-12, bit 14
male only, bit 13 female only; bit 15 set: a gear bit)
and the recipes (`RECIPE`, the materials, each list once; the first is the empty one). The first list of
`conds` is empty (never).
"""

import struct
from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from core.equipment.layered.felyne_looks import GAME_MH4U, NO_LOOKS, FelyneLooks, FelyneRow, felyne_rows
from core.equipment.layered.forge_rule import ALWAYS_WORD, ForgeRules, condition_word
from core.equipment.layered.look_order import ORDER_POSITION, ORDER_RELIC, list_facts, run_orders
from core.equipment.layered.looks import NOTHING_KEY, STATE_WEAPONS, Looks, load_curated, load_looks
from core.equipment.layered.prices import load_prices, shown_ranks
from core.equipment.layered.relic_prices import (
    load_relic_table, no_monster_cost, relic_keys, relic_price, relic_rarity,
)
from core.equipment.layered.texts import FORGE_KEYS, felyne_row_base, message_id
from core.equipment.layered.xx_prices import equivalent_forge, relic_offers
from core.equipment.layered.zenny import RANKS, ZENNY_KINDS, ZennyScale, scaled_zenny
from core.equipment.mhgen.felyne_pack import FELYNE_IDS
from core.equipment.tables.layout import ARMOR_PARTS, WEAPON_CLASSES
from core.game.executable.code_space import CodeSpaceError

RULES_MAGIC = 0x454C5552          # "RULE"
CATALOGS = 2                      # MH4U's, XX's
CLASSES = len(STATE_WEAPONS)
MAX_MATERIALS = 2                 # a recipe of the curated data or the price table: the rows of the box that show
RECIPE_SLOTS = 4                  # the game's recipe record has four, and the game's box reads that many
# magic; armor rules (2), weapon rules (2 x 14), armor recipe indexes (2), weapon recipe indexes (2 x 14); Felyne rows,
# Felyne rules, Felyne recipe indexes, conds, recipes; counts: armor (2), weapons (2 x 14), Felyne rows, recipes, cond
# words, a spare; the zone in the game's data (offset; MH4U armor, XX armor, each class' weapons (14), Felyne; size);
# the messages of FORGE_KEYS; what opens the high rank and the G rank (`rank_unlock_words`); the zenny of the armor
# looks (2), of each class' weapons (2 x 14) and of the Felyne rows (u32 each, parallel to the rules); the screens'
# order of the armor looks, of each class' weapons (14) and of the Felyne rows (look_order.py: u16 entries, both
# catalogs); the owned bit of each armor look (2: u16 each, parallel to the rules; `armor_bits`); where the zone's
# format byte is in it and its value; the messages of the entry's Relics line and of its help (RELIC_KEYS)
UNLOCK_ROOM = 4                   # entries per rank (0 ends a list)
UNLOCK_FLAG = 0x8000              # an entry with this bit is a story flag (the other bits), else a quest id
UNLOCK_OPEN = 0xFFFF              # an entry that always holds: the rank opens at once (layered_by_rank off)
RANK_UNLOCKS = ("high", "g")      # the curated lists: what opens rank 2, rank 3
HEADER = struct.Struct(f"<I{CATALOGS}I{CATALOGS * CLASSES}I{CATALOGS}I{CATALOGS * CLASSES}I5I"
                       f"{CATALOGS}H{CATALOGS * CLASSES}H4H"
                       f"I{CATALOGS + CLASSES + 2}H{len(FORGE_KEYS)}H"
                       f"{len(RANK_UNLOCKS) * UNLOCK_ROOM}H"
                       f"{CATALOGS}I{CATALOGS * CLASSES}II"
                       f"I{CLASSES}II"
                       f"{CATALOGS}I2H2H")
RELIC_KEYS = ("relics", "help_relics")
ROW = struct.Struct("<2H3Bx")         # a Felyne row: number, message, parts mask (LOOK_PARTS order), rank, game
RECIPE = struct.Struct(f"<{2 * RECIPE_SLOTS}H")        # 4 x (item, quantity): what the game's box reads
MAX_ZENNY = 999_999               # a look's zenny: a u32 of the block, at most the price row's six digits
#                                   (kit_number_text)
# Where a look is: kind (KIND_ARMOR, KIND_WEAPON, KIND_FELYNE), its catalog, its weapon class (else 0), its position
KIND_ARMOR, KIND_WEAPON, KIND_FELYNE = 0, 2, 3
OVERRIDE_SECTIONS = {"armor": KIND_ARMOR, "weapons": KIND_WEAPON, "felyne": KIND_FELYNE}
XX_FELYNE_RANKS = ("low", "high", "G")           # the keys of recipes.xx_felyne_materials: ranks 1, 2, 3
ZENNY_KIND = {KIND_ARMOR: "armor", KIND_WEAPON: "weapons", KIND_FELYNE: "felyne"}   # recipes.zenny's kind of each

# The owned bits: bytes of the game's data kept per
# character, from data + ZONE_AT up to Mod Settings' zone at data + 0x124E0. Every bit is a model number, so a build
# that orders its catalogs otherwise reads what an earlier one bought. The zones, by offset in it and room in bytes:
# MH4U's armor looks by model (`armor_bits`: the male's, the female's for a look with none, NOTHING_BIT for "Nothing";
# MH4U's highest is 582), XX's by their series' model (mhgen.looks.series_model; XX_SERIES_MODELS is one past XX's
# highest, 747, so every set XX has fits), weapons by model in a table per class of ZONE_WEAPON_MODELS bits
# (STATE_WEAPONS' order: the class' highest model in both catalogs and a margin, in whole bytes; a model is a byte, so
# 256 is the most), Felynes by model number. What follows the Felynes is free but the last byte, the zone's format
# (ZONE_FORMAT_AT): ZONE_FORMAT is written there with every purchase; 0 says no look was ever bought by a build that
# writes it (a new character, or one of the builds that kept armor by catalog place, none of them released). The
# builder checks every look fits its zone and has a bit of its own.
ZONE_AT = 0x12288
ZONE_SIZE = 600
ZONE_WEAPON_MODELS = {"great_sword": 224, "sword_and_shield": 256, "hammer": 216, "lance": 208, "light_bowgun": 176,
                      "heavy_bowgun": 168, "long_sword": 216, "switch_axe": 184, "gunlance": 192, "bow": 192,
                      "dual_blades": 208, "hunting_horn": 184, "insect_glaive": 144, "charge_blade": 136}
XX_SERIES_MODELS = 748
NOTHING_BIT = 0                   # model 0 is no armor: no look of MH4U wears it
ZONE_ROOM = {"armor_mh4u": 80, "armor_xx": (XX_SERIES_MODELS + 7) // 8, "felyne": (FELYNE_IDS + 7) // 8}
ZONE_ARMOR_MH4U = 0x000
ZONE_ARMOR_XX = ZONE_ARMOR_MH4U + ZONE_ROOM["armor_mh4u"]
ZONE_WEAPONS = ZONE_ARMOR_XX + ZONE_ROOM["armor_xx"]
ZONE_FELYNE = ZONE_WEAPONS + sum(ZONE_WEAPON_MODELS.values()) // 8
ZONE_FORMAT_AT = ZONE_SIZE - 1
ZONE_FORMAT = 1                   # armor by model (this layout); a later layout writes another value
assert tuple(ZONE_WEAPON_MODELS) == STATE_WEAPONS and all(n % 8 == 0 and n <= 256 for n in ZONE_WEAPON_MODELS.values())
assert ZONE_FELYNE + ZONE_ROOM["felyne"] <= ZONE_FORMAT_AT


def weapon_zone(key: str) -> int:
    """Where the table of the weapon class `key` starts in the zone."""
    at = ZONE_WEAPONS
    for other in STATE_WEAPONS[:STATE_WEAPONS.index(key)]:
        at += ZONE_WEAPON_MODELS[other] // 8
    return at


class LayeredRulesError(CodeSpaceError):
    pass


@dataclass
class Recipe:
    materials: tuple[tuple[int, int], ...]
    price: int


@dataclass
class Rules:
    """A block read back (read_rules): the lists as tuples of words."""
    armor: list[list[tuple[int, ...]]]                         # per catalog, per look
    weapons: list[list[list[tuple[int, ...]]]]                 # per catalog, per class, per look
    felyne: list[tuple[int, ...]]                              # per row
    rows: list[tuple[int, int, int, int, int]]                 # (number, message, parts, rank, game)
    recipes: list[Recipe]                                      # the materials lists (price 0: the zenny is a look's)
    armor_costs: list[list[Recipe]]                            # per catalog, per look: its materials and zenny
    weapon_costs: list[list[list[Recipe]]]                     # per catalog, per class, per look
    felyne_costs: list[Recipe]                                 # per row
    messages: dict[str, int] = field(default_factory=dict)     # FORGE_KEYS -> E_makeshop message
    zone: tuple[int, ...] = ()
    armor_order: list[int] = field(default_factory=list)       # the screens' order (look_order.py): u16 entries
    weapon_order: list[list[int]] = field(default_factory=list)   # per class
    felyne_order: list[int] = field(default_factory=list)
    unlocks: tuple[tuple[int, ...], ...] = ()                  # RANK_UNLOCKS' lists, UNLOCK_ROOM words each
    armor_bits: list[list[int]] = field(default_factory=list)  # per catalog, per look: its owned bit (armor_bits)
    zone_format: tuple[int, int] = (0, 0)                      # (ZONE_FORMAT_AT, ZONE_FORMAT)
    relic_messages: tuple[int, int] = (0, 0)                   # RELIC_KEYS -> E_makeshop message


def rank_unlock_words(unlocks: Mapping, by_rank: bool = True) -> list[int]:
    """The header's lists of what opens a rank (curated `rank_unlocks`; RANK_UNLOCKS' order, UNLOCK_ROOM words each, 0
    ends a list): a quest id opens it when cleared, {"flag": n} when story flag n is set (UNLOCK_FLAG | n). Every rank
    needs 1 to UNLOCK_ROOM entries: an empty list would never open it. `by_rank` False (option layered_by_rank off):
    each list is the one entry UNLOCK_OPEN, so every rank is open from the start (the lists are still checked)."""
    if set(unlocks) != set(RANK_UNLOCKS):
        raise LayeredRulesError(f"rank_unlocks: the ranks are {sorted(unlocks)}, not {sorted(RANK_UNLOCKS)}")
    words = []
    for rank in RANK_UNLOCKS:
        entries = list(unlocks[rank])
        if not 1 <= len(entries) <= UNLOCK_ROOM:
            raise LayeredRulesError(f"rank_unlocks {rank!r}: {len(entries)} entries, 1 to {UNLOCK_ROOM}")
        listed = []
        for entry in entries:
            if isinstance(entry, dict) and set(entry) == {"flag"} and type(entry["flag"]) is int \
                    and 0 < entry["flag"] < UNLOCK_FLAG:
                listed.append(UNLOCK_FLAG | entry["flag"])
            elif type(entry) is int and 0 < entry < UNLOCK_FLAG:
                listed.append(entry)
            else:
                raise LayeredRulesError(f"rank_unlocks {rank!r}: {entry!r} is neither a quest id nor "
                                        "{\"flag\": n} in range")
        words += listed + [0] * (UNLOCK_ROOM - len(listed))
    if not by_rank:
        return [UNLOCK_OPEN, *[0] * (UNLOCK_ROOM - 1)] * len(RANK_UNLOCKS)
    return words


def armor_bits(looks: Looks, gen) -> list[list[int]]:
    """The owned bit of each armor look, per catalog (MH4U's, XX's; parallel to the rules): a model, so that it does not
    depend on the catalog's order. MH4U: the male model, the female one for a look with no male model, NOTHING_BIT for
    "Nothing" (which needs none: it is free); XX: its series' model (GenSet.model)."""
    mh4u = [NOTHING_BIT if look.key == NOTHING_KEY else look.male or look.female for look in looks.armor]
    return [mh4u, [s.model for s in gen.sets] if gen is not None else []]


def check_zones(looks: Looks, gen, rows: list[FelyneRow]) -> None:
    """The looks must fit the zones of the owned bits: armor by model (armor_bits), each look of a catalog with a bit of
    its own; weapons by (class, model), Felynes by number."""
    names = ([look.key for look in looks.armor], [s.look.key for s in gen.sets] if gen is not None else [])
    rooms = (ZONE_ROOM["armor_mh4u"], ZONE_ROOM["armor_xx"])
    for keys, room, bits in zip(names, rooms, armor_bits(looks, gen)):
        owner: dict[int, str] = {}
        for key, bit in zip(keys, bits):
            if not 0 <= bit < room * 8:
                raise LayeredRulesError(f"{key}: its owned bit {bit} is past the {room * 8} of its zone")
            if bit in owner:
                raise LayeredRulesError(f"{key} and {owner[bit]} share the owned bit {bit}")
            owner[bit] = key
    catalogs = [looks.weapons] + ([gen.weapons] if gen is not None else [])
    for weapons in catalogs:
        for key in STATE_WEAPONS:
            for look in weapons[key]:
                if look.model >= ZONE_WEAPON_MODELS[key]:
                    raise LayeredRulesError(
                        f"{look.key}: model {look.model} is past the {ZONE_WEAPON_MODELS[key]} of {key}")
    for row in rows:
        if row.number >= FELYNE_IDS:
            raise LayeredRulesError(f"Felyne model {row.number} is past the {FELYNE_IDS} numbers")


# ----- items and recipes -----------------------------------------------------------------------------------

class Items:
    """The items a recipe may name: MH4U's by id or English name, the run's new ones by name. `ported`: the keys of the
    ported monsters in the run (None: every record with `ported` whose items resolve counts as his)."""

    def __init__(self, names: Mapping[int, str], new: Mapping[str, int] | None = None,
                 ported: Collection[str] | None = None):
        self.ported = None if ported is None else set(ported)
        self.valid = set(names)
        self.by_name: dict[str, int] = {}
        for item in sorted(names):
            self.by_name.setdefault(names[item].lower(), item)
        self.new = {name.lower(): item for name, item in (new or {}).items()}
        self.valid |= set(self.new.values())

    def resolve_new(self, name: str) -> int | None:
        """The id of the run's new item called `name` (a ported monster's: only when he is in the run), or None."""
        return self.new.get(name.lower())

    def resolve(self, ref) -> int | None:
        """The id `ref` (an id or an English name) stands for in this game, or None."""
        if isinstance(ref, bool):
            raise LayeredRulesError(f"item {ref!r}: an id or a name")
        if isinstance(ref, int):
            return ref if ref in self.valid else None
        if isinstance(ref, str):
            return self.by_name.get(ref.lower(), self.new.get(ref.lower()))
        raise LayeredRulesError(f"item {ref!r}: an id or a name")


def parse_recipe(raw, where: str) -> tuple[list, int | None]:
    """([(item reference, quantity)], price or None) of a curated recipe {"materials": [[item, quantity]...],
    "price": n}: up to MAX_MATERIALS materials, and no price means the look's zenny by kind and rank."""
    if not isinstance(raw, dict) or set(raw) - {"materials", "price"}:
        raise LayeredRulesError(f"recipes {where}: expected {{\"materials\": [[item, quantity], ...], \"price\": n}}")
    materials = raw.get("materials", [])
    if not isinstance(materials, list) or len(materials) > MAX_MATERIALS:
        raise LayeredRulesError(f"recipes {where}: at most {MAX_MATERIALS} materials")
    for entry in materials:
        if not (isinstance(entry, list) and len(entry) == 2 and isinstance(entry[1], int)
                and not isinstance(entry[1], bool) and 1 <= entry[1] <= 0xFFFF):
            raise LayeredRulesError(f"recipes {where}: a material is [item, quantity], got {entry!r}")
    price = raw.get("price")
    if price is not None and (not isinstance(price, int) or isinstance(price, bool) or not 0 <= price <= 0xFFFFFFFF):
        raise LayeredRulesError(f"recipes {where}: a price in zenny")
    return [(ref, qty) for ref, qty in materials], price


def _zenny_value(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xFFFFFFFF


def parse_zenny(recipes: Mapping) -> ZennyScale:
    """`recipes.zenny` of the curated data: for armor, weapons and Felyne, the range [min, max] of a look of rank 1, 2
    and 3; the `step` prices are rounded to; the `fallback` point of a range (0-1) a look with no original price costs
    (zenny.py)."""
    raw = recipes.get("zenny")
    if not isinstance(raw, dict) or set(raw) != {*ZENNY_KINDS, "step", "fallback"}:
        raise LayeredRulesError(f"recipes.zenny: a range per rank for each of {', '.join(ZENNY_KINDS)}, a step and a "
                                "fallback")
    for kind in ZENNY_KINDS:
        ranges = raw[kind]
        if not (isinstance(ranges, list) and len(ranges) == RANKS and all(
                isinstance(pair, list) and len(pair) == 2 and all(_zenny_value(v) for v in pair) and pair[0] <= pair[1]
                for pair in ranges)):
            raise LayeredRulesError(f"recipes.zenny.{kind}: three ranges [min, max] in zenny (low, high, G)")
    step, fallback = raw["step"], raw["fallback"]
    if not (_zenny_value(step) and step > 0):
        raise LayeredRulesError("recipes.zenny.step: a positive number of zenny")
    if not (isinstance(fallback, (int, float)) and not isinstance(fallback, bool) and 0 <= fallback <= 1):
        raise LayeredRulesError("recipes.zenny.fallback: a point of the range, 0 (its minimum) to 1 (its maximum)")
    return ZennyScale({kind: tuple(tuple(pair) for pair in raw[kind]) for kind in ZENNY_KINDS}, step, fallback)


def parse_xx_felyne(raw: Mapping, key: str = "xx_felyne_materials") -> dict[int, list]:
    """`recipes.xx_felyne_materials` of the curated data (or another such list, `key`): rank 1, 2, 3 -> [(item
    reference, quantity)], what a Felyne row of XX asks besides its zenny, from the keys low, high and G (a rank left
    out asks none)."""
    if set(raw) - set(XX_FELYNE_RANKS):
        raise LayeredRulesError(f"recipes.{key}: the ranks are {', '.join(XX_FELYNE_RANKS)}")
    return {XX_FELYNE_RANKS.index(rank) + 1: parse_recipe({"materials": materials}, f"{key}.{rank}")[0]
            for rank, materials in raw.items()}


@dataclass(frozen=True)
class Relics:
    """What the relic rule (xx_prices.relic_offers) does to the free looks of MH4U: the armor looks whose parts are
    cut down (look key -> the parts that stay), and the armor and weapon looks that are dropped."""
    armor: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    dropped_armor: frozenset[str] = frozenset()
    dropped_weapons: frozenset[str] = frozenset()


def relic_trim(looks: Looks, gen, prices: Mapping) -> Relics:
    """The free looks cut down or dropped so that each model is offered once: against MH4U's other looks, and XX's
    catalog's too when the run has it (`gen`)."""
    offered_armor, offered_weapons = relic_offers(looks, prices, None if getattr(gen, "empty", False) else gen)
    free = [look for look in looks.armor if prices["armor"].get(look.key, {}).get("rule") == "free"]
    trimmed = {look.key: offered_armor[look.key] for look in free
               if look.key in offered_armor and offered_armor[look.key] != look.parts}
    free_weapons = {look.key for by_class in looks.weapons.values() for look in by_class
                    if prices["weapons"].get(look.key, {}).get("rule") == "free"}
    return Relics(trimmed, frozenset(look.key for look in free if look.key not in offered_armor),
                  frozenset(free_weapons - set(offered_weapons)))


# ----- the rules ---------------------------------------------------------------------------------------------

class _Lists:
    """The condition lists, each once; a rule is a list's word index. List 0 is empty (never)."""

    def __init__(self):
        self.words = [0]
        self.index: dict[tuple[int, ...], int] = {(): 0}

    def add(self, words: tuple[int, ...]) -> int:
        if words not in self.index:
            self.index[words] = len(self.words)
            self.words += [*words, 0]
            if len(self.words) > 0xFFFF:
                raise LayeredRulesError("the condition lists are past 65,535 words")
        return self.index[words]


def _words(forge: tuple[str, ...] | None, record: tuple[str, ...] | None, own: tuple[int, ...] | None,
           extra: set[str], list_too: bool = True) -> tuple[int, ...]:
    """The condition words of a look. `forge`: its forge rule (None: it has none); `record`: the conditions of its price
    record (XX); `own`: the items of the list the curated data gives it (None: it has none; () a list naming an item
    this game lacks); `extra`: the conditions of the ported pieces wearing it. A look of MH4U goes by its forge rule
    (and the list, when a ported piece wears it and `list_too`); one with a ported piece by that piece's rule (and its
    list); one with a record by the record, or by its list; one with neither by its list, and always without one."""
    conditions = {condition_word(c) for c in extra}
    if forge is not None:
        conditions |= {condition_word(c) for c in forge}
        if extra and list_too:
            conditions |= set(own or ())
    elif own is not None:
        conditions |= set(own)
    elif not extra:
        conditions |= {condition_word(c) for c in record} if record is not None else {ALWAYS_WORD}
    return (ALWAYS_WORD,) if ALWAYS_WORD in conditions else tuple(sorted(conditions))


def _look_keys(looks: Looks, gen) -> dict[str, tuple[int, int, int, int]]:
    """Every look key -> (kind, catalog, class, position): what an override names."""
    keys = {look.key: (KIND_ARMOR, 0, 0, i) for i, look in enumerate(looks.armor)}
    if gen is not None:
        keys.update({s.look.key: (KIND_ARMOR, 1, 0, i) for i, s in enumerate(gen.sets)})
    for catalog, weapons in enumerate([looks.weapons] + ([gen.weapons] if gen is not None else [])):
        for c, key in enumerate(STATE_WEAPONS):
            keys.update({look.key: (KIND_WEAPON, catalog, c, i) for i, look in enumerate(weapons[key])})
    return keys


def _ported(tables, looks: Looks, gen, rows: list[FelyneRow]) -> dict[tuple, set[str]]:
    """The forge conditions of the ported monsters' gear (the new pieces of `tables`: ids past the game's counts), by
    the look they wear: ("armor", catalog, position), ("weapon", catalog, class index, position), ("felyne", row)."""
    from core.equipment.mhgen.equipment_pack import FALLBACK_MODEL     # the model a piece with none of its own wears
    from core.equipment.tables.layout import PALICO_TABLES
    found: dict[tuple, set[str]] = defaultdict(set)
    if tables is None:
        return found
    weapons = [(cls, i) for cls in WEAPON_CLASSES for i in range(cls.count, len(tables.weapons[cls.key]))]
    armor = [(part, i) for part in ARMOR_PARTS for i in range(part.count, len(tables.armor[part.key]))]
    palico = [(table, i) for table in PALICO_TABLES for i in range(table.count, len(tables.palico[table.key]))]
    if not (weapons or armor or palico):
        return found
    rules = ForgeRules(tables)
    catalogs = [looks.weapons] + ([gen.weapons] if gen is not None else [])
    for cls, i in weapons:
        model = tables.weapons[cls.key][i]["model"]
        if model and model != FALLBACK_MODEL:
            c = STATE_WEAPONS.index(cls.key)
            for catalog, by_class in enumerate(catalogs):
                for position, look in enumerate(by_class[cls.key]):
                    if look.model == model:
                        found["weapon", catalog, c, position] |= rules.weapon(cls.key, i)
    for part, i in armor:
        record = tables.armor[part.key][i]
        pair = record["model_m"], record["model_f"]
        if not any(pair) or pair == (FALLBACK_MODEL, FALLBACK_MODEL):
            continue
        conditions = rules.armor(part.key, i)
        for position, look in enumerate(looks.armor):
            if (look.male, look.female) == pair and part.key in look.parts:
                found["armor", 0, 0, position] |= conditions
        for position, s in enumerate(gen.sets if gen is not None else ()):
            if s.models.get(part.key) == pair:
                found["armor", 1, 0, position] |= conditions
    by_number = {row.number: position for position, row in enumerate(rows)}
    for table, i in palico:
        model = tables.palico[table.key][i]["model"]
        if model in by_number and model != FALLBACK_MODEL:
            found["felyne", 0, 0, by_number[model]] |= rules.palico(table.key, i)
    return found


def _base_cost(record: Mapping | None, rank: int, where: str,
               items: "Items") -> tuple[tuple[tuple[int, int], ...], int]:
    """(materials, the rank whose zenny it costs) of a look by the price table: a free look nothing, rank 0; a look with
    a record its materials; a look without one none (zenny only). A record with `ported` asks the ported monster's
    items instead when he is in the run (`items` has them). A material of `materials` given by English name (a rare
    material of XX's monsters, xx_materials.py; an XX recipe's, xx_prices.recipe_records) is a new item of the run:
    without it the look costs zenny only."""
    if record is not None and record.get("rule") == "free":
        return (), 0
    rank = max(rank, (record or {}).get("shown_rank", 0))       # a look moved up costs that rank's zenny
    resolved = [(item if isinstance(item, int) else items.resolve_new(item), int(quantity))
                for item, quantity in (record or {}).get("materials", ())]
    materials = tuple(resolved) if all(item is not None for item, _ in resolved) else ()
    here = items.ported is None or (record or {}).get("ported", {}).get("key") in items.ported
    ported = [(item if isinstance(item, int) else items.resolve_new(item), int(quantity)) for item, quantity in
              (record or {}).get("ported", {}).get("materials", ())] if here else []
    if ported and all(item for item, _ in ported):
        materials = tuple(ported)       # type: ignore[arg-type]
    if len(materials) > MAX_MATERIALS:
        raise LayeredRulesError(f"{where}: {len(materials)} materials in the price table, at most {MAX_MATERIALS}")
    if not 1 <= rank <= RANKS:
        raise LayeredRulesError(f"{where}: rank {rank}, not 1-3")
    return materials, rank


def _piece_price(records, piece: int, field: str = "price") -> int:
    """A piece's price in its table (0: no such piece, or a table of placeholders)."""
    record = records[piece] if 0 <= piece < len(records) else None
    return record[field] if record is not None else 0


def _originals(looks: Looks, gen, rows: list[FelyneRow], tables) -> dict[tuple, int]:
    """What forging each look's real gear cost in its own game (zenny.py), by its place (kind, catalog, class,
    position). MH4U's from the run's equipment tables (`tables`; None: unknown): an armor look the sum of the pieces
    naming its parts (the armor records hold half the price), a weapon look the weapon naming it, a Felyne row of MH4U
    the sum of its pieces. XX's from its catalog (GenLooks.prices) and, for a Felyne row of XX, its pieces'
    (FelyneRow.price)."""
    out: dict[tuple, int] = {}
    if tables is not None:
        for i, look in enumerate(looks.armor):
            out[KIND_ARMOR, 0, 0, i] = sum(2 * _piece_price(tables.armor[part], pieces[0], "price_half")
                                           for part, pieces in look.pieces.items() if pieces)
        for c, key in enumerate(STATE_WEAPONS):
            for i, look in enumerate(looks.weapons[key]):
                if look.weapon >= 0:
                    out[KIND_WEAPON, 0, c, i] = _piece_price(tables.weapons[key], look.weapon)
    for i, row in enumerate(rows):
        if row.game != GAME_MH4U:
            out[KIND_FELYNE, 0, 0, i] = row.price
        elif tables is not None:
            out[KIND_FELYNE, 0, 0, i] = sum(_piece_price(tables.palico[part], piece)
                                            for part, piece in row.pieces.items())
    if gen is not None:
        prices = getattr(gen, "prices", {})
        for i, s in enumerate(gen.sets):
            out[KIND_ARMOR, 1, 0, i] = prices.get(s.look.key, 0)
        for c, key in enumerate(STATE_WEAPONS):
            for i, look in enumerate(gen.weapons[key]):
                out[KIND_WEAPON, 1, c, i] = prices.get(look.key, 0)
    return out


def _inherited(ported: Mapping[tuple, set[str]], record_ported: Mapping[tuple, tuple[str, int]]
               ) -> dict[tuple, set[str]]:
    """The ported rules of the looks of a ported monster that no piece of his wears (Hellblade's, Soulseer's, the sets
    of his that his gear does not use): the union of the rules of his looks of the same rank that a piece wears, else of
    the next ranks' (xx_prices.equivalent_forge: an armor look takes his armor's; a weapon his class' weapons, else any
    class', else his armor's). `record_ported`: look position (kind, catalog, class, position) -> (his key, its
    rank)."""
    names = {KIND_ARMOR: "armor", KIND_WEAPON: "weapon"}
    armor, weapons = [], []
    for where, (key, rank) in record_ported.items():
        found = ported.get((names[where[0]], *where[1:]))
        if found:
            if where[0] == KIND_ARMOR:
                armor.append((rank, key, tuple(sorted(found))))
            else:
                weapons.append((STATE_WEAPONS[where[2]], rank, key, tuple(sorted(found))))
    out: dict[tuple, set[str]] = {}
    for where, (key, rank) in record_ported.items():
        at = (names[where[0]], *where[1:])
        if ported.get(at):
            continue
        cls = STATE_WEAPONS[where[2]] if where[0] == KIND_WEAPON else None
        forge = equivalent_forge(rank, key, armor, weapons, cls)
        if forge:
            out[at] = set(forge)
    return out


def _free(record: Mapping | None) -> bool:
    """A record of the price table no piece of which has a recipe: a relic's."""
    return record is not None and record.get("rule") == "free"


def _listed(look, table: Mapping) -> int:
    """The rank a look of MH4U is listed under: its own, or the higher one its record moves it to."""
    return max(look.rank, table.get(look.key, {}).get("shown_rank", 0))


def _relic_entries(entries: list[int], mh4u: list, keys: Collection[str]) -> list[int]:
    """An order array with ORDER_RELIC on the entries of the relics `keys` names (`mh4u`: the list's looks of MH4U,
    whose positions come first)."""
    return [entry | ORDER_RELIC if (entry & ORDER_POSITION) < len(mh4u) and mh4u[entry & ORDER_POSITION].key in keys
            else entry for entry in entries]


def layered_rules(looks: Looks | None = None, gen=None, felynes: FelyneLooks = NO_LOOKS, *, tables=None,
                  item_ids: Mapping[str, int] | None = None, curated: Mapping | None = None,
                  names: Mapping[int, str] | None = None, prices: Mapping | None = None,
                  relics: Relics | None = None, ported: Collection[str] | None = None, by_rank: bool = True) -> bytes:
    """The block layered_rules for the run's looks (`looks`, `gen` the pack's, `felynes`). `tables`: the run's
    equipment tables (EquipmentTables.read of the executable with the ported monsters' gear): their new pieces add
    their forge conditions. `item_ids`: the English names of the new items of the ported monsters in the run, with their
    ids. `curated`: the recipes (default: layered_looks.json); `names`: MH4U's items by id
    (default: lookups.item_names); `prices`: the price table (default: generated/layered_prices.json); `relics`: the
    free looks cut down or dropped (default: relic_trim); `ported`: the keys of the ported monsters in the run (None:
    every look with `ported` items that
    resolve counts as his); `by_rank`: the looks open by rank (`rank_unlocks`), False every rank from the start."""
    looks = looks or load_looks()
    curated = curated or load_curated()
    prices = prices if prices is not None else load_prices()
    if names is None:
        from core.game.data.lookups import item_names
        names = item_names()
    items = Items(names, item_ids, ported)
    rows = felyne_rows(felynes)
    check_zones(looks, gen, rows)
    relics = relics or relic_trim(looks, gen, prices)
    scale = parse_zenny(curated["recipes"])
    if "rank_unlocks" not in curated:
        raise LayeredRulesError("the curated data has no rank_unlocks")
    unlocks = rank_unlock_words(curated["rank_unlocks"], by_rank)

    # what each look costs: the price table's materials and the zenny of its original price (zenny.py), then the
    # curated recipes on top; the records of XX's looks
    xx = prices.get("xx", {})
    base: dict[tuple, tuple[tuple[tuple[int, int], ...], int]] = {}      # place -> (materials, its zenny's rank)
    record_forge: dict[tuple, tuple[str, ...]] = {}
    record_ported: dict[tuple, tuple[str, int]] = {}      # a look of a ported monster -> (his key, its rank)
    owners: dict[tuple, str] = {}         # a look of a monster, not a relic -> his name: what his relics cost

    def owner(where: tuple, record: Mapping | None):
        if record is not None and not _free(record) and record.get("monster"):
            owners[where] = record["monster"]
    for i, look in enumerate(looks.armor):
        record = prices["armor"].get(look.key)
        base[KIND_ARMOR, 0, 0, i] = _base_cost(record, look.rank, look.key, items)
        owner((KIND_ARMOR, 0, 0, i), record)
        if record is not None and "ported" in record:
            record_ported[KIND_ARMOR, 0, 0, i] = (record["ported"]["key"], look.rank)
    for i, s in enumerate(gen.sets if gen else ()):
        record = xx.get("armor", {}).get(s.look.key)
        base[KIND_ARMOR, 1, 0, i] = _base_cost(record, s.look.rank, s.look.key, items)
        owner((KIND_ARMOR, 1, 0, i), record)
        if record is not None:
            record_forge[KIND_ARMOR, 1, 0, i] = tuple(record["forge"])
            if "ported" in record:
                record_ported[KIND_ARMOR, 1, 0, i] = (record["ported"]["key"], record["rank"])
    for catalog, by_class in enumerate([looks.weapons] + ([gen.weapons] if gen else [])):
        table = prices["weapons"] if catalog == 0 else xx.get("weapons", {})
        for c, key in enumerate(STATE_WEAPONS):
            for i, look in enumerate(by_class[key]):
                record = table.get(look.key)
                base[KIND_WEAPON, catalog, c, i] = _base_cost(record, look.rank, look.key, items)
                owner((KIND_WEAPON, catalog, c, i), record)
                if catalog and record is not None:
                    record_forge[KIND_WEAPON, catalog, c, i] = tuple(record["forge"])
                    if "ported" in record:
                        record_ported[KIND_WEAPON, catalog, c, i] = (record["ported"]["key"], record["rank"])
    xx_felyne = parse_xx_felyne(curated["recipes"].get("xx_felyne_materials", {}))
    for i, row in enumerate(rows):
        record = prices["felyne"].get(str(row.number)) if row.game == GAME_MH4U else None
        base[KIND_FELYNE, 0, 0, i] = _base_cost(record, row.rank, f"Felyne model {row.number}", items)
        asked = [(items.resolve(ref), qty) for ref, qty in xx_felyne.get(row.rank, ())]
        if row.game != GAME_MH4U and asked and all(item for item, _ in asked):
            # a row of XX asks the foreign scraps of its rank besides its zenny (a run without them: zenny only)
            base[KIND_FELYNE, 0, 0, i] = (tuple(asked), base[KIND_FELYNE, 0, 0, i][1])    # type: ignore[arg-type]
    # a look that is not free and asks nothing (its recipe only an event's items or tickets, no recipe found, a ported
    # monster's item this run lacks) asks its listed rank's own: a Felyne row the foreign scraps when the run has XX's
    # Felyne rows (the expeditions bring the scraps only then), the rest the curated fallback (the rank's ore and
    # crystal)
    fallback = parse_xx_felyne(curated["recipes"].get("fallback_materials", {}), "fallback_materials")
    scraps = xx_felyne if any(row.game != GAME_MH4U for row in rows) else fallback
    for where, (materials, rank) in base.items():
        if rank and not materials:
            own = scraps if where[0] == KIND_FELYNE else fallback
            asked = [(items.resolve(ref), qty) for ref, qty in own.get(rank, ())]
            if asked and all(item for item, _ in asked):
                base[where] = (tuple(asked), rank)     # type: ignore[arg-type]
    originals = _originals(looks, gen, rows, tables)
    zenny = scaled_zenny(scale, {where: (ZENNY_KIND[where[0]], rank,
                                         rows[where[3]].game if where[0] == KIND_FELYNE else where[1],
                                         originals.get(where))
                                 for where, (_, rank) in base.items() if rank})
    cost = {where: (materials, zenny[where] if rank else 0) for where, (materials, rank) in base.items()}
    relics_kept = relic_keys(looks, prices, relics)

    # the curated recipes on top (a relic's after its own price below)
    keys = _look_keys(looks, gen)
    numbers = {row.number: position for position, row in enumerate(rows)}
    own_list: dict[tuple, tuple[int, ...]] = {}
    overrides: dict[tuple, tuple[tuple[tuple[int, int], ...], int | None]] = {}    # place -> (materials, own price)
    for section in OVERRIDE_SECTIONS:
        for key, raw in curated["recipes"].get(section, {}).items():
            materials, own_price = parse_recipe(raw, f"{section}.{key}")
            if section == "felyne":
                if not str(key).isdigit():
                    raise LayeredRulesError(f"recipes.felyne.{key}: the key is a Felyne model number")
                if int(key) not in numbers:
                    continue                  # a model this run lacks
                where = (KIND_FELYNE, 0, 0, numbers[int(key)])
            else:
                where = keys.get(key)
                if where is None:
                    continue                  # a look this run lacks (the pack's, when it is not in the run)
                if (where[0] == KIND_ARMOR) != (section == "armor"):
                    raise LayeredRulesError(f"recipes.{section}.{key}: that is not a look of {section}")
            resolved = [(items.resolve(ref), qty) for ref, qty in materials]
            overrides[where] = (tuple((item, qty) for item, qty in resolved if item), own_price)
            # the look's list: every item of the recipe, or none when one is not in this game; no material, no list
            if resolved:
                own_list[where] = tuple(sorted({item for item, _ in resolved if item})) \
                    if all(item for item, _ in resolved) else ()

    def override(where: tuple):
        materials, own_price = overrides[where]
        cost[where] = (materials, cost[where][1] if own_price is None else own_price)

    # every free look of MH4U is a relic, bought on the Relics screens (relic_prices.py): a relic costs its counterpart
    # as priced above, else the dearest look of its rank of its monster or family (of its kind, else of the other),
    # or its own price when they have none of its rank, else (none, no look, a counterpart the run lacks) its rank's
    # tier with more zenny; a dropped one is never listed
    relic_table = load_relic_table()
    relic_places = {(KIND_ARMOR, 0, 0, i): ("armor", look, None) for i, look in enumerate(looks.armor)
                    if _free(prices["armor"].get(look.key))}
    relic_places.update({(KIND_WEAPON, 0, c, i): ("weapons", look, key) for c, key in enumerate(STATE_WEAPONS)
                         for i, look in enumerate(looks.weapons[key]) if _free(prices["weapons"].get(look.key))})
    for where in overrides:
        if where not in relic_places:
            override(where)
    theirs: dict[str, dict[str, list]] = {"armor": defaultdict(list), "weapons": defaultdict(list)}
    for where, monster in owners.items():                         # kind -> monster -> (listed rank, cost) of his looks
        if cost[where] != ((), 0):                                # a look made free is no price to copy
            theirs["armor" if where[0] == KIND_ARMOR else "weapons"][monster].append((base[where][1], cost[where]))

    def final_cost(key: str):
        """A look's cost as priced above (a counterpart is never a relic), None when the run lacks it."""
        return cost[keys[key]] if key in keys else None
    from core.game.data.lookups import item_names
    game_items = Items(item_names())          # a rank gap's price names MH4U's items, whatever `names` holds
    for where, (kind, look, weapon_class) in relic_places.items():
        rank = _listed(look, prices[kind])
        cost[where] = relic_price(relic_table, scale, kind, look.key, rank, theirs, final_cost, game_items.resolve) \
            or no_monster_cost(relic_table, scale, kind, rank, relic_rarity(look, tables, weapon_class), items.resolve)
    for where in overrides:
        if where in relic_places:
            override(where)

    recipes: list[tuple[tuple[int, int], ...]] = [()]      # the materials, each list once; the empty one first
    index: dict[tuple, int] = {(): 0}

    def recipe_index(where: tuple) -> int:
        materials = cost[where][0]
        if materials not in index:
            index[materials] = len(recipes)
            recipes.append(materials)
        return index[materials]

    def zenny_of(where: tuple) -> int:
        price = cost[where][1]
        if price > MAX_ZENNY:
            raise LayeredRulesError(f"a look's price of {price} z, past the {MAX_ZENNY} the price row shows")
        return price
    ported = _ported(tables, looks, gen, rows)
    ported.update(_inherited(ported, record_ported))
    lists = _Lists()
    dropped = {KIND_ARMOR: relics.dropped_armor, KIND_WEAPON: relics.dropped_weapons}

    def rule(kind: str, where: tuple, forge, look_key: str | None = None) -> int:
        if look_key in dropped.get(where[0], ()):
            return lists.add(())
        if look_key in relics_kept:       # when the hunter had it: bought (no ported piece's rule, no list of its own)
            return lists.add(_words(forge or (), None, None, set()))
        extra = ported.get((kind, *where[1:]), set())
        return lists.add(_words(forge, record_forge.get(where), own_list.get(where), extra, kind != "felyne"))

    armor_n = [len(looks.armor), len(gen.sets) if gen else 0]
    armor_rules = [[rule("armor", (KIND_ARMOR, 0, 0, i), look.forge, look.key) for i, look in enumerate(looks.armor)],
                   [rule("armor", (KIND_ARMOR, 1, 0, i), None) for i in range(armor_n[1])]]
    by_catalog = [looks.weapons, gen.weapons if gen else {key: [] for key in STATE_WEAPONS}]
    weapon_rules = [[[rule("weapon", (KIND_WEAPON, catalog, c, i), look.forge, look.key if catalog == 0 else None)
                      for i, look in enumerate(by_class[key])] for c, key in enumerate(STATE_WEAPONS)]
                    for catalog, by_class in enumerate(by_catalog)]
    felyne_rules = [rule("felyne", (KIND_FELYNE, 0, 0, i), row.forge) for i, row in enumerate(rows)]
    armor_costs = [[recipe_index((KIND_ARMOR, c, 0, i)) for i in range(armor_n[c])] for c in range(CATALOGS)]
    weapon_costs = [[[recipe_index((KIND_WEAPON, catalog, c, i)) for i in range(len(by_class[key]))]
                     for c, key in enumerate(STATE_WEAPONS)] for catalog, by_class in enumerate(by_catalog)]
    felyne_costs = [recipe_index((KIND_FELYNE, 0, 0, i)) for i in range(len(rows))]
    armor_zenny = [[zenny_of((KIND_ARMOR, c, 0, i)) for i in range(armor_n[c])] for c in range(CATALOGS)]
    weapon_zenny = [[[zenny_of((KIND_WEAPON, catalog, c, i)) for i in range(len(by_class[key]))]
                     for c, key in enumerate(STATE_WEAPONS)] for catalog, by_class in enumerate(by_catalog)]
    felyne_zenny = [zenny_of((KIND_FELYNE, 0, 0, i)) for i in range(len(rows))]
    if len(recipes) > 0xFFFF:
        raise LayeredRulesError("too many recipes")
    # the screens' order of every list (look_order.py)
    sections = {"armor": KIND_ARMOR, "weapons": KIND_WEAPON, "felyne": KIND_FELYNE}
    orders = run_orders(list_facts(looks, gen, rows, prices, shown_ranks(prices),
                                   lambda section, *at: originals.get((sections[section], *at), 0)), curated)
    orders.armor = _relic_entries(orders.armor, looks.armor, relics_kept)
    orders.weapons = [_relic_entries(entries, looks.weapons[key], relics_kept)
                      for entries, key in zip(orders.weapons, STATE_WEAPONS)]

    # the block
    body = bytearray()
    base = HEADER.size

    def put(data: bytes, align: int = 4) -> int:
        body.extend(bytes(-(base + len(body)) % align))
        at = base + len(body)
        body.extend(data)
        return at

    def u16s(values) -> bytes:
        return struct.pack(f"<{len(values)}H", *values)

    def u32s(values) -> bytes:
        return struct.pack(f"<{len(values)}I", *values)

    armor_at = [put(u16s(rules_)) for rules_ in armor_rules]
    weapon_at = [put(u16s(rules_)) for catalog in weapon_rules for rules_ in catalog]
    armor_cost_at = [put(u16s(costs)) for costs in armor_costs]
    weapon_cost_at = [put(u16s(costs)) for catalog in weapon_costs for costs in catalog]
    first = felyne_row_base(looks, gen)
    rows_at = put(b"".join(ROW.pack(row.number, first + i, row.parts, row.rank, row.game)
                           for i, row in enumerate(rows)))
    felyne_at = put(u16s(felyne_rules))
    felyne_cost_at = put(u16s(felyne_costs))
    armor_zenny_at = [put(u32s(prices_)) for prices_ in armor_zenny]
    weapon_zenny_at = [put(u32s(prices_)) for catalog in weapon_zenny for prices_ in catalog]
    felyne_zenny_at = put(u32s(felyne_zenny))
    armor_order_at = put(u16s(orders.armor))
    weapon_order_at = [put(u16s(entries)) for entries in orders.weapons]
    felyne_order_at = put(u16s(orders.felyne))
    armor_bits_at = [put(u16s(bits)) for bits in armor_bits(looks, gen)]
    conds_at = put(u16s(lists.words))
    recipes_at = put(b"".join(RECIPE.pack(*(v for pair in (materials + ((0, 0),) * RECIPE_SLOTS)[:RECIPE_SLOTS]
                                            for v in pair)) for materials in recipes))
    counts = [len(r) for r in armor_rules] + [len(r) for catalog in weapon_rules for r in catalog]
    header = HEADER.pack(RULES_MAGIC, *armor_at, *weapon_at, *armor_cost_at, *weapon_cost_at, rows_at, felyne_at,
                         felyne_cost_at, conds_at, recipes_at,
                         *counts, len(rows), len(recipes), len(lists.words), 0,
                         ZONE_AT, ZONE_ARMOR_MH4U, ZONE_ARMOR_XX, *(weapon_zone(key) for key in STATE_WEAPONS),
                         ZONE_FELYNE, ZONE_SIZE,
                         *(message_id(key) for key in FORGE_KEYS), *unlocks,
                         *armor_zenny_at, *weapon_zenny_at, felyne_zenny_at,
                         armor_order_at, *weapon_order_at, felyne_order_at,
                         *armor_bits_at, ZONE_FORMAT_AT, ZONE_FORMAT, *(message_id(key) for key in RELIC_KEYS))
    return header + bytes(body) + bytes(-(len(header) + len(body)) % 4)


def read_rules(data: bytes) -> Rules:
    """The block's content (the inverse of layered_rules, for the tests and the screens' emulation)."""
    fields = HEADER.unpack_from(data)
    if fields[0] != RULES_MAGIC:
        raise LayeredRulesError("not a layered_rules block")
    at = iter(fields[1:])
    armor_at = [next(at) for _ in range(CATALOGS)]
    weapon_at = [next(at) for _ in range(CATALOGS * CLASSES)]
    armor_cost_at = [next(at) for _ in range(CATALOGS)]
    weapon_cost_at = [next(at) for _ in range(CATALOGS * CLASSES)]
    rows_at, felyne_at, felyne_cost_at, conds_at, recipes_at = (next(at) for _ in range(5))
    armor_n = [next(at) for _ in range(CATALOGS)]
    weapon_n = [next(at) for _ in range(CATALOGS * CLASSES)]
    rows_n, recipes_n, words_n, _spare = (next(at) for _ in range(4))
    zone = tuple(next(at) for _ in range(1 + CATALOGS + CLASSES + 2))
    messages = dict(zip(FORGE_KEYS, (next(at) for _ in FORGE_KEYS)))
    unlocks = tuple(tuple(next(at) for _ in range(UNLOCK_ROOM)) for _ in RANK_UNLOCKS)
    armor_zenny_at = [next(at) for _ in range(CATALOGS)]
    weapon_zenny_at = [next(at) for _ in range(CATALOGS * CLASSES)]
    felyne_zenny_at = next(at)
    armor_order_at = next(at)
    weapon_order_at = [next(at) for _ in range(CLASSES)]
    felyne_order_at = next(at)
    armor_bits_at = [next(at) for _ in range(CATALOGS)]
    zone_format = (next(at), next(at))
    relic_messages = (next(at), next(at))
    conds = struct.unpack_from(f"<{words_n}H", data, conds_at)

    def listed(rule: int) -> tuple[int, ...]:
        end = conds.index(0, rule)
        return tuple(conds[rule:end])

    def rules_of(offset: int, count: int) -> list[tuple[int, ...]]:
        return [listed(rule) for rule in struct.unpack_from(f"<{count}H", data, offset)]

    recipes = []
    for k in range(recipes_n):
        flat = RECIPE.unpack_from(data, recipes_at + k * RECIPE.size)
        recipes.append(Recipe(tuple((flat[i], flat[i + 1]) for i in range(0, 2 * RECIPE_SLOTS, 2) if flat[i]), 0))

    def costs_of(offset: int, zenny_at: int, count: int) -> list[Recipe]:
        return [Recipe(recipes[k].materials, price) for k, price in
                zip(struct.unpack_from(f"<{count}H", data, offset), struct.unpack_from(f"<{count}I", data, zenny_at))]

    return Rules(
        armor=[rules_of(armor_at[c], armor_n[c]) for c in range(CATALOGS)],
        weapons=[[rules_of(weapon_at[c * CLASSES + k], weapon_n[c * CLASSES + k]) for k in range(CLASSES)]
                 for c in range(CATALOGS)],
        felyne=rules_of(felyne_at, rows_n),
        rows=[ROW.unpack_from(data, rows_at + k * ROW.size) for k in range(rows_n)],
        recipes=recipes,
        armor_costs=[costs_of(armor_cost_at[c], armor_zenny_at[c], armor_n[c]) for c in range(CATALOGS)],
        weapon_costs=[[costs_of(weapon_cost_at[c * CLASSES + k], weapon_zenny_at[c * CLASSES + k],
                                weapon_n[c * CLASSES + k]) for k in range(CLASSES)] for c in range(CATALOGS)],
        felyne_costs=costs_of(felyne_cost_at, felyne_zenny_at, rows_n),
        messages=messages, zone=zone, unlocks=unlocks,
        armor_order=list(struct.unpack_from(f"<{sum(armor_n)}H", data, armor_order_at)),
        weapon_order=[list(struct.unpack_from(f"<{weapon_n[k] + weapon_n[CLASSES + k]}H", data, weapon_order_at[k]))
                      for k in range(CLASSES)],
        felyne_order=list(struct.unpack_from(f"<{rows_n}H", data, felyne_order_at)),
        armor_bits=[list(struct.unpack_from(f"<{armor_n[c]}H", data, armor_bits_at[c])) for c in range(CATALOGS)],
        zone_format=zone_format, relic_messages=relic_messages)
