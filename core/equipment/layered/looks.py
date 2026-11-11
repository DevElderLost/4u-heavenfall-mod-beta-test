"""The looks of layered equipment: every armor and weapon model of the game, grouped, ordered and named.

An armor look is a pair of model numbers (male, female) and the parts it exists for: pieces sharing the pair
form one look, whatever their rank (the S, X... versions of a set often keep the model of the first one). A
piece made for one gender only (model 0 for the other) is merged with its counterpart: the same name first
(Varia Suit), then the same model number (Helios / Selene). Pieces without any model (earrings) are left
out. A weapon look is a model id of one weapon class (for bows and bowguns the record's +0x00).

Looks are grouped by set name (armor) or by weapon family (the monster of the materials,
randomizer/equipment/models.py), groups from the lowest rank, and named from the game's own names in each
language.

The structure comes from the clean executable and is kept in game/data/generated/layered_looks.json
(tools/build/build_layered_looks.py), so a run never depends on equipment the randomizer changed. The hand-made
game/data/curated/layered_looks.json adds names, groups and further looks.
"""

import json
import os
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from functools import cache

from core.game.data.paths import CURATED_DIR, GENERATED_DIR
from core.equipment.layered.forge_rule import ALWAYS, ForgeRules, conditions_list
from core.equipment.tables.layout import PALICO_TABLES, WEAPON_CLASSES
from core.randomizer.equipment.catalog import rank_of

GENERATED_PATH = GENERATED_DIR / "layered_looks.json"
CURATED_PATH = CURATED_DIR / "layered_looks.json"
# Display order of the armor parts (the game's armor category menu), and their order in layered_state
# (equipment type - 1: body, arms, waist, legs, head).
NAME_PARTS = ("head", "body", "arms", "waist", "legs")
STATE_PARTS = ("body", "arms", "waist", "legs", "head")
# Weapon classes in layered_state order (equipment type - 7).
STATE_WEAPONS = tuple(wc.key for wc in sorted(WEAPON_CLASSES, key=lambda wc: wc.recipe_type))
RANGED = frozenset(wc.key for wc in WEAPON_CLASSES if wc.ranged)
BLADEMASTER, GUNNER = 0x04, 0x08  # armor record flags (byte 4)
HUNTER_ORDER = {"blademaster": 0, "gunner": 1, "both": 2}
# An armor value of layered_state that is no model: the part is drawn as the game draws armor id 0, the hunter's own
# body, arms and legs, no waist and no helm (layered_selector.c NO_ARMOR; the whole-sets lists write it for a part the
# set lacks). Past every model of the tables (ARMOR_IDS, equipment_pack.py) and not 0xFFFF, which the loader skips.
NO_ARMOR = 0xFFFE
# The curated look "Nothing" (layered_looks.json `nothing`), after MH4U's own: NO_ARMOR on every part, for both genders,
# low rank, always offered; free by its curated recipe. The first armor row under every filter (look_order.py).
NOTHING_KEY = "nothing"
# The Felyne pieces the game's code goes by the id of, per part: a whole suit, a model group hidden, a colour, joints.
CASE_PIECES = {"head": (0x8B,), "body": (0x42, 0x43, 0x9F, 0xA7, 0xA9, 0xAB, 0xAC), "weapon": (0x48, 0xAC)}
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")  # the RomFS language folders
# Words that join a set name to the piece's noun ("Casco de Ludroth", "Mail of Rage", "Grèves en lingot").
CONNECTORS = frozenset({"de", "del", "della", "dello", "di", "du", "des", "en", "of", "la", "le", "da", "in", "der",
                        "die", "das", "von", "el", "il", "lo"})


@dataclass(frozen=True)
class ArmorPiece:
    part: str
    index: int           # id in its table and name list
    name: str
    male: int            # model numbers; 0 = none for that gender
    female: int
    rarity: int          # 1-10
    hunter: int          # record flags & 0x0C: BLADEMASTER, GUNNER (heads have both)
    craftable: bool      # has a create recipe
    gender: int = 3      # record flags & 3: 1 male, 2 female


@dataclass(frozen=True)
class WeaponPiece:
    weapon: str          # weapon class key
    index: int
    name: str
    model: int
    rarity: int
    family: str          # group of the weapon's line


@dataclass(frozen=True)
class ArmorLook:
    key: str             # "<male>-<female>"
    male: int
    female: int
    parts: tuple[str, ...]                                     # in NAME_PARTS order
    pieces: dict = field(compare=False, hash=False)            # part -> (piece,) or (male's, female's) naming it
    rank: int            # 1 low, 2 high, 3 G
    hunter: str          # "blademaster", "gunner" or "both"
    group: str
    whole: bool          # offered as a whole set (two parts or more)
    members: tuple = field(default=(), compare=False, hash=False)      # every piece wearing it: (part, id)
    forge: tuple | None = field(default=None, compare=False, hash=False)    # when the forge offers it (forge_rule)


@dataclass(frozen=True)
class WeaponLook:
    key: str             # "<class>-<model>"
    model: int
    weapon: int          # the weapon whose name it shows (name list index); -1 = a curated name
    rank: int
    group: str
    number: int = 0      # from 2 on: the look shares its weapon's name with earlier ones (relic weapons)
    names: dict = field(default_factory=dict, compare=False, hash=False)  # curated names by language
    members: tuple = field(default=(), compare=False, hash=False)      # every weapon wearing it (ids of its class)
    forge: tuple | None = field(default=None, compare=False, hash=False)    # when the forge offers it (forge_rule)


# ----- names -------------------------------------------------------------------------------------------------

# A word of a piece name: split at spaces and hyphens, and inside German compounds the game wrote without them
# ("RathianArmschienenEX" -> Rathian, Armschienen, EX).
WORD = re.compile(r"[^\s\-]+?(?=[A-ZÄÖÜ][a-zäöüß]|(?<=[a-zäöüß])[A-Z]|[\s\-]|$)")
ELISION = re.compile(r"^(?:d|l|dell|dall|nell|all|sull|qu)'", re.I)


def _words(name: str) -> list[re.Match]:
    return list(WORD.finditer(name))


def _same(a: str, b: str) -> bool:
    """The same word, maybe with another ending ("voraz" / "voraces", "ardito" / "ardita") or abbreviated by
    the game ("argent." / "argentato")."""
    x, y = a.lower(), b.lower()
    if x == y:
        return True
    if x.endswith(".") or y.endswith("."):
        short, long = (x, y) if x.endswith(".") else (y, x)
        return len(short) > 2 and long.rstrip(".").startswith(short[:-1])
    prefix = len(os.path.commonprefix([x, y]))
    return prefix >= 4 and prefix >= min(len(x), len(y)) - 2


def _significant(words: list[str]) -> bool:
    return any(len(word) >= 3 for word in words) or len("".join(words)) >= 2


def _capital(name: str) -> str:
    return name[:1].upper() + name[1:]


def common_name(names: Iterable[str]) -> str:
    """The name a set's pieces share: the words of the first name found in every other one, in its order and
    without the joining words at the ends ("Rathalos Helm", "Rathalos Mail" -> "Rathalos"; "Casco voraz",
    "Brazales voraces" -> "Voraz"; "Rathian-Helm EX", "RathianArmschienenEX" -> "Rathian EX"), else their common
    beginning ("Dragonhead", "Dragonhide" -> "Dragon"). One name is kept whole."""
    names = list(dict.fromkeys(name.strip() for name in names))
    if len(names) == 1:
        return names[0]
    first, others = _words(names[0]), [[m.group() for m in _words(name)] for name in names[1:]]
    kept = []
    for match in first:
        variants = [next((w for w in words if _same(match.group(), w)), None) for words in others]
        if all(variants):
            word = match.group()
            if word.endswith("."):  # cut by the game: the longest whole form
                word = max((w for w in variants if not w.endswith(".")), key=len, default=word)
            kept.append((match, word))
    low, high = 0, len(kept)
    while low < high and kept[low][1].lower() in CONNECTORS:
        low += 1
    while high > low and kept[high - 1][1].lower() in CONNECTORS:
        high -= 1
    chosen = kept[low:high]
    words = [word for _, word in chosen]
    if words and ELISION.match(words[0]):
        words[0] = ELISION.sub("", words[0])
    if _significant(words):
        # Words next to each other in the first name keep the hyphen or space between them ("Kut-Ku").
        text = words[0]
        for (before, _), (match, _), word in zip(chosen, chosen[1:], words[1:]):
            gap = names[0][before.end():match.start()]
            text += (gap if gap in (" ", "-") else " ") + word
        return _capital(text)
    start = os.path.commonprefix(names).rstrip(" -'")
    if len(start) >= 3:
        return _capital(start)
    return names[0]


def _look_halves(look: ArmorLook, names: Mapping[str, Mapping[int, str]]) -> list[str]:
    """The base names of a look in one language: the common name of its pieces, one per half of a merged look
    whose halves have different names ("Helios", "Selene")."""
    halves = []
    for half in range(max(len(look.pieces[part]) for part in look.parts)):
        pieces = [(part, look.pieces[part][half]) for part in look.parts if half < len(look.pieces[part])]
        halves.append(common_name(names[part][index] for part, index in pieces))
    return list(dict.fromkeys(halves))


def abbreviate(name: str, room: int) -> str:
    """`name` in `room` characters, its longest words cut as the game does ("Parabraccia" -> "Parabr.")."""
    words = name.split(" ")
    while len(" ".join(words)) > room:
        long = [i for i, word in enumerate(words) if len(word) > 5 and not word.endswith(".")]
        if not long:
            return " ".join(words)[:room].rstrip()
        i = max(long, key=lambda i: len(words[i]))
        excess = len(" ".join(words)) - room
        words[i] = words[i][:max(4, len(words[i]) - excess - 1)] + "."
    return " ".join(words)


def fit_label(base: str, tail: str, max_line: int | None, halves: list[str] | None = None, room: int = 0) -> str:
    """"base tail" in `max_line` characters: a merged base keeps its first half, then words are cut, to leave
    `room` characters for the tail (at least its own: looks of one base get the same cut)."""
    room = max(room, len(tail))
    if max_line is None or len(base) + 1 + room <= max_line:
        return f"{base} {tail}"
    if halves and len(halves) > 1:
        base = halves[0]
    return f"{abbreviate(base, max_line - room - 1)} {tail}"


def armor_labels(looks: list[ArmorLook], names: Mapping[str, Mapping[int, str]], ranks: tuple[str, str, str],
                 hunters: Mapping[str, str], overrides: Mapping[str, str] | None = None,
                 max_line: int | None = None) -> list[str]:
    """The name shown for each look in one language: base name and rank ("Rathalos LR"), plus the hunter type
    when a blademaster and a gunner look would share it ("Rathalos LR Blade"), plus a number when looks
    still share it ("Kirin LR 2"); at most `max_line` characters (fit_label). `names`: part -> piece index ->
    name; `overrides`: look key -> base name."""
    overrides = overrides or {}
    bases = []
    for look in looks:
        halves = [overrides[look.key]] if overrides.get(look.key) else _look_halves(look, names)
        bases.append(("/".join(halves), halves))
    plain = [f"{base} {ranks[look.rank - 1]}" for (base, _), look in zip(bases, looks)]
    kinds: dict[str, set[str]] = defaultdict(set)
    for label, look in zip(plain, looks):
        kinds[label].add(look.hunter)
    tails = [f"{ranks[look.rank - 1]} {hunters[look.hunter]}" if len(kinds[label]) > 1 and look.hunter in hunters
             else ranks[look.rank - 1] for label, look in zip(plain, looks)]
    rooms: dict[str, int] = defaultdict(int)
    for (base, _), tail in zip(bases, tails):
        rooms[base] = max(rooms[base], len(tail))
    labels = [fit_label(base, tail, max_line, halves, rooms[base]) for (base, halves), tail in zip(bases, tails)]
    seen: dict[str, int] = defaultdict(int)
    numbers = []
    for label in labels:
        seen[label] += 1
        numbers.append(seen[label])
    return [label if number == 1 else fit_label(base, f"{tail} {number}", max_line, halves, rooms[base])
            for label, number, (base, halves), tail in zip(labels, numbers, bases, tails)]


# ----- armor -------------------------------------------------------------------------------------------------

def _naming_order(piece: ArmorPiece) -> tuple:
    """Craftable pieces name a look first, from the lowest rarity; arena copies have rarity 1."""
    return not piece.craftable, piece.rarity if piece.craftable or piece.rarity > 1 else 11, piece.index


def _rank(pieces: list[ArmorPiece]) -> int:
    craftable = [p.rarity for p in pieces if p.craftable]
    real = [p.rarity for p in pieces if p.rarity > 1]
    return rank_of(min(craftable or real or [1]))


def _representatives(pieces: list[ArmorPiece]) -> dict[str, ArmorPiece]:
    by_part: dict[str, list[ArmorPiece]] = defaultdict(list)
    for piece in pieces:
        by_part[piece.part].append(piece)
    return {part: min(by_part[part], key=_naming_order) for part in NAME_PARTS if part in by_part}


def _base(pieces: list[ArmorPiece]) -> str:
    return common_name(piece.name for piece in _representatives(pieces).values())


def build_armor_looks(pieces: Iterable[ArmorPiece],
                      model_files: Mapping[str, Mapping[str, set[int]]] | None = None) -> list[ArmorLook]:
    """Every armor look, in list order. `model_files`: part -> "m" / "f" -> model numbers that have a file
    (pl_m_helmNNN...); without it every model is kept."""
    pairs: dict[tuple[int, int], list[ArmorPiece]] = defaultdict(list)
    for piece in pieces:
        male, female = piece.male, piece.female
        if model_files is not None:
            files = model_files.get(piece.part, {})
            male = male if male in files.get("m", ()) else 0
            female = female if female in files.get("f", ()) else 0
        if male or female:
            pairs[(male, female)].append(replace(piece, male=male, female=female))

    # Pieces made for one gender: merged with the same piece of the other (same name), then with the model
    # number's other half.
    halves = []
    males = sorted(key for key in pairs if not key[1])
    females = sorted(key for key in pairs if not key[0])
    by_name: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for key in females:
        by_name[_base(pairs[key])].append(key)
    for key in list(males):
        match = by_name.get(_base(pairs[key]))
        if match:
            other = match.pop(0)
            halves.append((key, other))
            males.remove(key)
            females.remove(other)
    for key in list(males):
        if (0, key[0]) in females:
            halves.append((key, (0, key[0])))
            males.remove(key)
            females.remove((0, key[0]))
    merged = {key: (pairs[key], []) for key in pairs if key[0] and key[1]}
    merged.update({key: (pairs[key], []) for key in (*males, *females)})
    merged.update({(m[0], f[1]): (pairs[m], pairs[f]) for m, f in halves})

    looks = []
    for (male, female), (first, second) in merged.items():
        everything = first + second
        reps = [_representatives(first), _representatives(second)] if second else [_representatives(first)]
        parts = tuple(part for part in NAME_PARTS if any(part in rep for rep in reps))
        named = {part: tuple(rep[part].index for rep in reps if part in rep) for part in parts}
        bits = 0
        for piece in everything:
            if piece.part != "head" or len(parts) == 1:
                bits |= piece.hunter
        hunter = {BLADEMASTER: "blademaster", GUNNER: "gunner"}.get(bits & (BLADEMASTER | GUNNER), "both")
        group = "/".join(dict.fromkeys(_base(half) for half in ((first, second) if second else (first,))))
        looks.append(ArmorLook(f"{male}-{female}", male, female, parts, named, _rank(everything), hunter, group,
                               len(parts) >= 2, tuple(sorted((piece.part, piece.index) for piece in everything))))
    return order_armor(looks)


def _first_index(look: ArmorLook) -> int:
    part = next(part for part in ("body", "head", "arms", "waist", "legs") if part in look.parts)
    return look.pieces[part][0]


def order_armor(looks: list[ArmorLook]) -> list[ArmorLook]:
    """Groups from the lowest rank (then table order), and in a group by rank, blademaster before gunner."""
    group_order: dict[str, tuple] = {}
    for look in looks:
        key = (look.rank, _first_index(look))
        group_order[look.group] = min(group_order.get(look.group, key), key)
    return sorted(looks, key=lambda look: (group_order[look.group], look.group, look.rank,
                                           HUNTER_ORDER[look.hunter], _first_index(look), look.male, look.female))


# ----- weapons -----------------------------------------------------------------------------------------------

def build_weapon_looks(pieces: Iterable[WeaponPiece],
                       model_files: Mapping[str, set[int]] | None = None) -> dict[str, list[WeaponLook]]:
    """Weapon class -> its looks (distinct model ids), families from the lowest rarity, in a family by the
    first weapon wearing each model. Weapons sharing a name (relic weapons: one name, several models, each
    without a recipe line) join the family of the first, follow it and are numbered from 2. `model_files`:
    class -> model numbers with a file."""
    firsts: dict[str, dict[int, WeaponPiece]] = defaultdict(dict)
    members: dict[tuple[str, int], list[int]] = defaultdict(list)
    for piece in pieces:
        if not piece.model:
            continue
        if model_files is not None and piece.model not in model_files.get(piece.weapon, ()):
            continue
        members[piece.weapon, piece.model].append(piece.index)
        current = firsts[piece.weapon].get(piece.model)
        if current is None or (piece.rarity, piece.index) < (current.rarity, current.index):
            firsts[piece.weapon][piece.model] = piece
    result = {}
    for key in STATE_WEAPONS:
        chosen = list(firsts.get(key, {}).values())
        name_first: dict[str, WeaponPiece] = {}
        for piece in sorted(chosen, key=lambda p: (p.rarity, p.index)):
            name_first.setdefault(piece.name, piece)
        chosen = [replace(p, family=name_first[p.name].family) for p in chosen]
        family_order: dict[str, tuple] = {}
        for piece in chosen:
            family_order[piece.family] = min(family_order.get(piece.family, (99, 0)), (piece.rarity, piece.index))

        chosen.sort(key=lambda p, firsts=name_first, families=family_order: (
            families[p.family], p.family, firsts[p.name].rarity, firsts[p.name].index, p.rarity, p.index))
        seen: dict[str, int] = defaultdict(int)
        result[key] = []
        for p in chosen:
            seen[p.name] += 1
            result[key].append(WeaponLook(f"{key}-{p.model}", p.model, p.index, rank_of(p.rarity), p.family,
                                          seen[p.name] if seen[p.name] > 1 else 0,
                                          members=tuple(sorted(members[key, p.model]))))
    return result


# ----- from the game -----------------------------------------------------------------------------------------

def game_pieces(tables, data) -> tuple[list[ArmorPiece], list[WeaponPiece]]:
    """Every real armor piece and weapon of the (clean) equipment tables, with English names and families."""
    from core.randomizer.equipment.catalog import build_catalog
    from core.randomizer.equipment.models import weapon_families
    catalog = build_catalog(tables)
    armor = [ArmorPiece(part, p.index, p.name, p.original["model_m"], p.original["model_f"], p.rarity,
                        p.record.data[4] & (BLADEMASTER | GUNNER), p.create is not None, p.record.data[4] & 3)
             for part, group in catalog.armor.items() for p in group.values()]
    weapons = []
    for key in catalog.weapons:
        for family, members in weapon_families(catalog, key, data).items():
            name = f"{family[0]}:{family[1]}"
            weapons += [WeaponPiece(key, p.index, p.name, _weapon_model(key, p), p.rarity, name) for p in members]
    return armor, weapons


def _weapon_model(key: str, piece) -> int:
    """The model id the game draws: a bow's or bowgun's is its record's +0x00 (RangedWeapon "model", +0x02, is
    another field)."""
    return int.from_bytes(piece.record.data[:2], "little") if key in RANGED else piece.original["model"]


def looks_to_json(armor: list[ArmorLook], weapons: dict[str, list[WeaponLook]]) -> dict:
    """One record per look; the models are in the key ("<male>-<female>"), the parts in `pieces`, the forge's
    conditions (forge_rule) in `forge`."""
    return {
        "armor": [{"key": look.key, "rank": look.rank, "hunter": look.hunter, "group": look.group,
                   "pieces": {part: list(look.pieces[part]) for part in look.parts},
                   **({"forge": list(look.forge)} if look.forge else {})} for look in armor],
        "weapons": {key: [{"model": look.model, "weapon": look.weapon, "rank": look.rank, "group": look.group,
                           **({"number": look.number} if look.number else {}),
                           **({"forge": list(look.forge)} if look.forge else {})}
                          for look in looks] for key, looks in weapons.items()},
    }


def with_forge(armor: list[ArmorLook], weapons: dict[str, list[WeaponLook]], tables) -> tuple[list, dict]:
    """The looks with the forge's rule of MH4U (forge_rule) for `tables`, the game's clean equipment tables."""
    rules = ForgeRules(tables)
    armor = [replace(look, forge=conditions_list(c for part, index in look.members
                                                 for c in rules.armor(part, index))) for look in armor]
    weapons = {key: [replace(look, forge=conditions_list(c for index in look.members
                                                         for c in rules.weapon(key, index))) for look in looks]
               for key, looks in weapons.items()}
    return armor, weapons


def build_felyne_rows(tables) -> list[dict]:
    """The game's own Felyne gear by model number: a number any piece with a forge rule wears (a piece with none has no
    way to appear: forge_rule.ForgeRules.palico). `pieces`: the part's first piece, by rarity and id, which names it;
    `rarity`: the lowest; `forge`: the rule of every piece wearing it; `cases`: its piece of CASE_PIECES, per part."""
    rules = ForgeRules(tables)
    found: dict[int, list[tuple[str, int, int, set[str]]]] = defaultdict(list)
    for table in PALICO_TABLES:
        for piece in range(table.count):
            conditions = rules.palico(table.key, piece)
            if conditions:
                record = tables.palico[table.key][piece]
                found[record["model"]].append((table.key, piece, record["rarity"], conditions))
    rows = []
    for number, pieces in sorted(found.items()):
        parts = {key: min((p for p in pieces if p[0] == key), key=lambda p: (p[2], p[1]))[1]
                 for key in ("head", "body", "weapon") if any(p[0] == key for p in pieces)}
        cases = {key: piece for key, piece, _, _ in pieces if piece in CASE_PIECES[key]}
        rows.append({"number": number, "rarity": min(p[2] for p in pieces), "pieces": parts,
                     "forge": list(conditions_list(c for p in pieces for c in p[3])),
                     **({"cases": cases} if cases else {})})
    return rows


def generated_looks(tables, data, model_files: Mapping | None = None) -> dict:
    """What game/data/generated/layered_looks.json holds for these (clean) tables."""
    armor, weapons = game_pieces(tables, data)
    return {**looks_to_json(*with_forge(build_armor_looks(armor, (model_files or {}).get("armor")),
                                        build_weapon_looks(weapons, (model_files or {}).get("weapons")), tables)),
            "felyne": build_felyne_rows(tables)}


# ----- loading -----------------------------------------------------------------------------------------------

@dataclass
class Looks:
    armor: list[ArmorLook]
    weapons: dict[str, list[WeaponLook]]          # class key -> looks, for every class of STATE_WEAPONS
    names: dict[str, dict[str, str]]              # look key -> language -> curated base name
    raw: dict                                     # the generated file


def _armor_from_json(record: dict) -> ArmorLook:
    male, female = map(int, record["key"].split("-"))
    parts = tuple(part for part in NAME_PARTS if part in record["pieces"])
    return ArmorLook(record["key"], male, female, parts,
                     {part: tuple(record["pieces"][part]) for part in parts}, record["rank"], record["hunter"],
                     record["group"], len(parts) >= 2, forge=tuple(record["forge"]) if "forge" in record else None)


@cache
def _read(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_curated() -> dict:
    return _read(CURATED_PATH)


def generated_felyne_rows() -> list[dict]:
    """The records of build_felyne_rows, from the generated file."""
    return _read(GENERATED_PATH)["felyne"]


def load_looks(curated: bool = True) -> Looks:
    """The look lists: the generated file, with the curated names, groups and extra looks."""
    raw = _read(GENERATED_PATH)
    extra = load_curated() if curated else {}
    groups = extra.get("groups", {})
    armor = [_armor_from_json(record) for record in raw["armor"]]
    armor += [_armor_from_json({**record, "pieces": {part: [] for part in record["parts"]}})
              for record in extra.get("extra_armor", [])]  # curated looks are named by "names"
    armor = [replace(look, group=groups[look.key]) if look.key in groups else look for look in armor]
    if groups or extra.get("extra_armor"):
        armor = order_armor(armor)
    weapons = {key: [WeaponLook(f"{key}-{r['model']}", r["model"], r["weapon"], r["rank"],
                                groups.get(f"{key}-{r['model']}", r["group"]), r.get("number", 0),
                                forge=tuple(r["forge"]) if "forge" in r else None)
                     for r in raw["weapons"][key]]
               for key in STATE_WEAPONS}
    for key, records in extra.get("extra_weapons", {}).items():
        weapons[key] += [WeaponLook(r["key"], r["model"], -1, r["rank"], r.get("group", r["key"]), names=r["names"])
                         for r in records]
    names = {key: dict(value) for key, value in extra.get("names", {}).items()}
    names.update({r["key"]: r["names"] for r in extra.get("extra_armor", [])})
    if extra.get("nothing"):
        armor.append(nothing_look())
        names[NOTHING_KEY] = dict(extra["nothing"]["names"])
    return Looks(armor, weapons, names, raw)


def nothing_look() -> ArmorLook:
    """The look "Nothing" (NOTHING_KEY): every part, NO_ARMOR for both genders."""
    return ArmorLook(NOTHING_KEY, NO_ARMOR, NO_ARMOR, NAME_PARTS, {part: () for part in NAME_PARTS}, 1, "both",
                     NOTHING_KEY, True, forge=(ALWAYS,))
