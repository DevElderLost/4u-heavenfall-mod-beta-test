"""The looks of XX's catalog the same as an earlier look, taken out of the run (generated/layered_alike.json, made by
equipment/layered/alike.py): an armor look the same for both sexes
and a weapon look are removed; an armor look the same for one sex loses that sex's models and stays for the other. The
pack's models no look wears any more leave the plan, so their files are neither made nor written, and their entries
leave the executable's tables. A hunter or another player wearing a look removed wears the real gear there (the
screens' known_armor / known_weapon: a model no look of the run has)."""

from collections.abc import Mapping
from dataclasses import replace

from core.equipment.layered.looks import SEXES, STATE_WEAPONS, load_alike
from core.equipment.mhgen.equipment_pack import CLASS_FOLDERS, WEAPON_FOLDERS
from core.equipment.mhgen.looks import PART_KEYS, GenLooks

SLOTS = {part: slot for slot, part in PART_KEYS.items()}          # NAME_PARTS part -> the pack's armor slot
CLASS_SLOTS = {key: WEAPON_FOLDERS[CLASS_FOLDERS[key]] for key in STATE_WEAPONS}


def removed(alike: Mapping) -> tuple[dict[str, frozenset[int]], dict[str, frozenset[str]]]:
    """From layered_alike.json: armor look key -> the sexes (0 male, 1 female) it is the same for, and weapon class ->
    the keys of its looks the same as an earlier one."""
    armor = {key: frozenset(SEXES.index(sex) for sex in sexes) for key, sexes in alike.get("hidden", {}).items()}
    weapons = {key: frozenset(kind.get("hidden", {})) for key, kind in alike.get("weapons", {}).items()}
    return armor, weapons


def without_repeats(gen: GenLooks, alike: Mapping | None = None) -> GenLooks:
    """`gen` without the looks the same as an earlier one (`alike`, default: the generated file): a set the same for
    both sexes and a weapon left out, a set the same for one sex with that sex's models 0 (the screens list it for the
    other sex alone). Keys of `alike` that are not `gen`'s (MH4U's looks, another pack's) change nothing."""
    armor, weapons = removed(load_alike() if alike is None else alike)
    sets = []
    for s in gen.sets:
        sexes = armor.get(s.look.key, frozenset())
        if len(sexes) == len(SEXES):
            continue
        if sexes:
            sex = next(iter(sexes))
            s = replace(s, models={part: tuple(0 if i == sex else model for i, model in enumerate(pair))
                                   for part, pair in s.models.items()})
        sets.append(s)
    kept_weapons = {key: [look for look in looks if look.key not in weapons.get(key, ())]
                    for key, looks in gen.weapons.items()}
    return replace(gen, sets=sets, weapons=kept_weapons)


def pack_models(gen: GenLooks) -> set[tuple[str, int]]:
    """The (pack slot, model) every look of `gen` wears, either sex."""
    worn = {(SLOTS[part], model) for s in gen.sets for part, pair in s.models.items() for model in pair if model}
    worn |= {(CLASS_SLOTS[key], look.model) for key, looks in gen.weapons.items() for look in looks}
    return worn


def pack_without_repeats(prepared, alike: Mapping | None = None):
    """`prepared` (pack_run.PreparedPack) for a run: its looks without the repeats (without_repeats), its plan without
    the models only those looks wore (and their preview copies), and its executable's needs without their entries."""
    full = prepared.gen_looks()
    kept = without_repeats(full, alike)
    gone = pack_models(full) - pack_models(kept)
    plan = tuple(p for p in prepared.plan if (p.slot, p.model) not in gone)
    displays = tuple(d for d in prepared.displays if (d.slot, d.worn) not in gone)
    gone |= {(d.slot, d.preview) for d in prepared.displays if d not in displays}
    weapons = {(slot, model) for slot, model in gone if slot in CLASS_SLOTS.values()}
    armor = {(slot, model) for slot, model in gone if slot in SLOTS.values()}
    helms = {model for slot, model in armor if slot == SLOTS["head"]}
    needs = prepared.needs
    needs = replace(needs,
                    donors={k: v for k, v in needs.donors.items() if k not in weapons},
                    effects={k: v for k, v in needs.effects.items() if k not in weapons},
                    hair={k: v for k, v in needs.hair.items() if k[1] not in helms},
                    hair_shown={k: v for k, v in needs.hair_shown.items() if k[1] not in helms},
                    cloth={k: v for k, v in needs.cloth.items() if k[1:] not in armor},
                    armor_sounds={k: v for k, v in needs.armor_sounds.items() if k[1:] not in armor})
    return replace(prepared, plan=plan, needs=needs, displays=displays,
                   kept_looks=replace(kept, preview_models={key: model for key, model in kept.preview_models.items()
                                                            if (CLASS_SLOTS[key[0]], model) not in gone}))
