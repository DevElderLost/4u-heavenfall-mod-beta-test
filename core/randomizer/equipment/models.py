"""Equipment models (looks).

Only models already used by real pieces of the same weapon class / armor part
are assigned, so every model file exists. Armor looks are numbers: a number's
male and female models (some sets are split, a male-only piece Gloaming and a
female-only twin Adamance share it) form one look, and a piece only takes a
look that has a model for every gender it originally had; a gender without a
model stays without one.

Weapons, FAMILIES: a family is a weapon line, keyed by the monster that
provides most of its materials; lines made of ore or bone inherit the family
of the weapon they are upgraded from. A family's models are ordered by rarity,
and each family takes the models of another one (never its own) with about as
many models, at the same relative position, so the first weapon of a line gets
the most basic look.

Armor, FAMILIES: a family is a set (pieces sharing a model number); a whole
set takes the look of another set that has every one of its parts.

"Use each model once" turns the random choice of a family (or model) into a
permutation, so every look is used and none is repeated while possible. In CHAOTIC armor a source is a number plus
the genders its piece needs, so a female-only piece of a split set draws its look apart from its male twin.

Extra models (ExtraModels: MH Generations' pack) are
looks no piece has: CHAOTIC draws from them too; in FAMILIES an extra armor set
is one more set a set can take, and weapons keep to the game's models.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.app.settings import ModelMode, Settings

if TYPE_CHECKING:       # the knowledge base is only named in annotations: a run that shuffles no models never loads it
    from core.game.data import GameData
from core.randomizer.equipment.catalog import Catalog, Piece


@dataclass(frozen=True)
class ExtraModels:
    """Models the run adds to the game, by weapon class key and armor part key (equipment/tables/layout.py)."""
    weapons: dict[str, tuple[int, ...]] = field(default_factory=dict)    # class -> model ids
    armor: dict[str, dict[str, int]] = field(default_factory=dict)       # part -> {set name: model id (both genders)}


def _choose_targets(sources: list, targets: list, once: bool, rng: random.Random) -> dict:
    if not targets:
        return {}
    if once:
        shuffled = targets[:]
        rng.shuffle(shuffled)
        mapping, pending = {}, list(sources)
        rng.shuffle(pending)
        while pending:
            batch, pending = pending[:len(shuffled)], pending[len(shuffled):]
            mapping.update(zip(batch, shuffled))
            rng.shuffle(shuffled)
        return mapping
    return {source: rng.choice(targets) for source in sources}


# ----- weapons -------------------------------------------------------------------------------------------

def _monster_by_item(data: GameData) -> dict[int, list[int]]:
    owners: dict[int, list[int]] = defaultdict(list)
    for monster in data.monsters.values():
        for item in monster.material_ids:
            owners[item].append(monster.monster_id)
    return owners


def _main_monster(piece: Piece, owners: dict[int, list[int]]) -> int | None:
    scores: dict[int, float] = defaultdict(float)
    for item, _ in piece.original_materials:
        for monster in owners.get(item, ()):
            scores[monster] += 1 / len(owners[item])
    return min(scores, key=lambda m: (-scores[m], m)) if scores else None


def weapon_families(catalog: Catalog, key: str, data: GameData) -> dict[object, list[Piece]]:
    """Family id -> weapons, for the weapons of one class that have a model."""
    weapons = catalog.weapons[key]
    owners = _monster_by_item(data)
    family: dict[int, object] = {}

    def resolve(piece: Piece, seen=()) -> object:
        if piece.index in family:
            return family[piece.index]
        monster = _main_monster(piece, owners)
        if monster is not None:
            result = ("monster", monster)
        elif piece.parent is not None and piece.parent not in seen:
            result = resolve(weapons[piece.parent], seen + (piece.index,))
        else:
            result = ("line", piece.index)
        family[piece.index] = result
        return result

    groups: dict[object, list[Piece]] = defaultdict(list)
    for piece in weapons.values():
        if piece.original["model"]:
            groups[resolve(piece)].append(piece)
    return dict(groups)


def _model_sequence(pieces: list[Piece]) -> list[int]:
    first_seen: dict[int, tuple] = {}
    for piece in pieces:
        order = (piece.rarity, piece.original["attack"], piece.index)
        model = piece.original["model"]
        first_seen[model] = min(first_seen.get(model, order), order)
    return sorted(first_seen, key=first_seen.get)


MIN_FAMILY_GROUP = 4  # families that can swap models with each other; with fewer the choice barely depends on the seed


def _size_groups(ids: list, sequences: dict) -> list[list]:
    """Families grouped by model count. A group of fewer than MIN_FAMILY_GROUP families joins the next smaller
    group (the smallest joins the next larger one): the longest lines, such as the ore and bone lines the game
    starts with, are often alone with their count and would otherwise only get their own models."""
    groups: dict[int, list] = defaultdict(list)
    for fid in ids:
        groups[len(sequences[fid])].append(fid)
    merged: list[list] = []
    for size in sorted(groups):
        if merged and (len(groups[size]) < MIN_FAMILY_GROUP or len(merged[-1]) < MIN_FAMILY_GROUP):
            merged[-1] = merged[-1] + groups[size]
        else:
            merged.append(groups[size])
    return merged


def _pair_families(ids: list, sequences: dict, once: bool, rng: random.Random) -> dict:
    """Each family takes the models of another family with about as many models, so lines keep their
    progression. A family only keeps its own models when it is the only one."""
    mapping = {}
    for group in _size_groups(ids, sequences):
        if len(group) == 1:
            mapping[group[0]] = group[0]
        elif once:
            # A random cycle: every family of the group is taken once and none keeps its own models.
            order = group[:]
            rng.shuffle(order)
            mapping.update(zip(order, order[1:] + order[:1]))
        else:
            for fid in group:
                mapping[fid] = rng.choice([other for other in group if other != fid])
    return mapping


def _same_position(position: int, length: int, target: list[int]) -> int:
    ratio = position / (length - 1) if length > 1 else 0.5
    return target[round(ratio * (len(target) - 1))]


def randomize_weapon_models(catalog: Catalog, settings: Settings, data: GameData, rng: random.Random,
                            extra: ExtraModels | None = None) -> None:
    once = settings.models_use_each_once
    extra = extra or ExtraModels()
    for key, weapons in catalog.weapons.items():
        pieces = [p for p in weapons.values() if p.original["model"]]
        if settings.model_mode is ModelMode.CHAOTIC:
            models = sorted({p.original["model"] for p in pieces})
            targets = models + sorted(extra.weapons.get(key, ()))
            if once:
                mapping = _choose_targets(models, targets, True, rng)
                for piece in pieces:
                    piece.record["model"] = mapping[piece.original["model"]]
            else:
                for piece in pieces:
                    piece.record["model"] = rng.choice(targets)
            continue
        families = weapon_families(catalog, key, data)
        sequences = {fid: _model_sequence(members) for fid, members in families.items()}
        mapping = _pair_families(sorted(families, key=str), sequences, once, rng)
        for fid, members in families.items():
            own, target = sequences[fid], sequences[mapping[fid]]
            for piece in members:
                position = own.index(piece.original["model"])
                piece.record["model"] = _same_position(position, len(own), target)


# ----- armor ---------------------------------------------------------------------------------------------

def armor_number(values: dict) -> int:
    """The model number of an armor piece (the set it belongs to): its male model, or its female one when it is
    female-only."""
    return values["model_m"] or values["model_f"]


def _genders(models: tuple[int, int]) -> tuple[bool, bool]:
    """Which genders have a model: what a piece needs (its original models) or what a look offers."""
    return bool(models[0]), bool(models[1])


def _fits(look: tuple[int, int], need: tuple[bool, bool]) -> bool:
    return (bool(look[0]) or not need[0]) and (bool(look[1]) or not need[1])


def _looks(pieces: list[Piece]) -> dict[int, tuple[int, int]]:
    """Model number -> (male, female) models. A split set (Gloaming male-only, Adamance female-only) shares one
    number, so its look merges the models of every piece."""
    looks: dict[int, list[int]] = {}
    for piece in pieces:
        look = looks.setdefault(armor_number(piece.original), [0, 0])
        for gender, name in enumerate(("model_m", "model_f")):
            look[gender] = look[gender] or piece.original[name]
    return {number: (male, female) for number, (male, female) in looks.items()}


def _choose_covering(sources: list, targets: list, looks: dict, rng: random.Random) -> dict:
    """CHAOTIC with `once`: sources are (number, needed genders), more of them than looks. A look shows the model of a
    gender only through a source that needs that gender, so each source, the most demanding first, takes the fitting
    look with most models still unseen (a tie: the one left with fewest unseen), and every model gets shown while
    possible; once all are seen the draw is among the looks that fit."""
    unseen = {t: [bool(looks[t][0]), bool(looks[t][1])] for t in targets}
    order = sources[:]
    rng.shuffle(order)
    order.sort(key=lambda s: -sum(s[1]))
    mapping = {}
    for source in order:
        need = source[1]
        fitting = [t for t in targets if _fits(looks[t], need)]

        scores = {}
        for t in fitting:
            gain = sum(1 for g in (0, 1) if need[g] and unseen[t][g])
            scores[t] = (gain, -(sum(unseen[t]) - gain))
        best = max(scores.values())
        mapping[source] = target = rng.choice([t for t in fitting if scores[t] == best])
        for g in (0, 1):
            unseen[target][g] = unseen[target][g] and not need[g]
    return mapping


def _choose_sets(sets: list[int], targets: list, looks: dict[str, dict], once: bool, rng: random.Random) -> dict:
    """FAMILIES: set number -> the set (a number or an extra set's name) it wears in every part. A target must have
    a look, with every gender the source's look has, in each part the source has; a set never takes itself while
    another fits. Sets are taken the most demanding first (most parts and genders), in a random order within the
    same demand, so whole sets are not spent on a lone helm; with `once`, each target is used once while one that
    fits is left."""
    needs = {s: tuple((key, _genders(part[s])) for key, part in looks.items() if s in part) for s in sets}
    fitting: dict[tuple, list] = {}   # by need: most sets need the same five parts for both genders

    def fit(need: tuple) -> list:
        if need not in fitting:
            fitting[need] = [t for t in targets
                             if all(t in looks[key] and _fits(looks[key][t], genders) for key, genders in need)]
        return fitting[need]

    order = sets[:]
    rng.shuffle(order)
    order.sort(key=lambda s: -sum(sum(genders) for _, genders in needs[s]))
    mapping, free = {}, set(targets)
    for source in order:
        others = [t for t in fit(needs[source]) if t != source] or [source]
        unused = [t for t in others if t in free]
        mapping[source] = target = rng.choice(unused if once and unused else others)
        free.discard(target)
    return mapping


def randomize_armor_models(catalog: Catalog, settings: Settings, rng: random.Random,
                           extra: ExtraModels | None = None) -> None:
    once = settings.models_use_each_once
    extra = extra or ExtraModels()
    parts = {key: [p for p in pieces.values() if armor_number(p.original)] for key, pieces in catalog.armor.items()}
    looks = {key: _looks(pieces) for key, pieces in parts.items()}
    added = {key: sorted(extra.armor.get(key, {})) for key in parts}  # extra set names, keys of `looks` too
    for key, names in added.items():
        looks[key].update((name, (extra.armor[key][name],) * 2) for name in names)
    if settings.model_mode is ModelMode.FAMILIES:
        sets = sorted({model for key in parts for model in looks[key] if model not in added[key]})
        extra_sets = sorted({name for names in added.values() for name in names})
        set_mapping = _choose_sets(sets, sets + extra_sets, looks, once, rng)
    for key, pieces in parts.items():
        models = sorted(m for m in looks[key] if m not in added[key])
        targets = models + added[key]
        fitting: dict[tuple[bool, bool], list] = {}
        if settings.model_mode is ModelMode.FAMILIES:
            mapping = {m: set_mapping[m] for m in models}
        elif once:
            # CHAOTIC, once: a source is a number plus the genders its piece needs, so a female-only piece of a split
            # set is not tied to its male twin's look (nor Sailor, female-only alone, to itself).
            sources = sorted({(armor_number(p.original), _genders((p.original["model_m"], p.original["model_f"])))
                              for p in pieces})
            mapping = _choose_covering(sources, targets, looks[key], rng)
        else:
            mapping = None
        for piece in pieces:
            original = piece.original
            need = _genders((original["model_m"], original["model_f"]))
            if mapping is None:  # CHAOTIC: each piece draws among the looks that have the models it needs
                if need not in fitting:
                    fitting[need] = [t for t in targets if _fits(looks[key][t], need)]
                target = rng.choice(fitting[need])
            elif settings.model_mode is ModelMode.FAMILIES:
                target = mapping[armor_number(original)]
            else:
                target = mapping[armor_number(original), need]
            male, female = looks[key][target]
            piece.record["model_m"] = male if original["model_m"] else 0
            piece.record["model_f"] = female if original["model_f"] else 0
