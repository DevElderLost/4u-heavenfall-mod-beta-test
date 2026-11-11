"""Texts of layered equipment: the messages added to the Smithy's text file, E_makeshop, in every language.

The Smithy's menu shows messages of msg\\lobby\\E_makeshop_<lang> (lobby message file 6; it has 147 messages in
every language). The screens' own texts and the names of the armor looks are appended to it, at fixed
indices (UI_KEYS, then one per armor look in list order) that the executable patch uses
(core/equipment/layered/layered_equipment.py). Weapon looks show the game's weapon names, already in memory, except
the numbered ones (a name several looks share: "Bone Staff 2") and those of the curated file, appended after
the armor look names. With MH XX's looks (equipment/mhgen/looks.py), their set names and weapon names follow
(gen_set_base), and then the names of the Felynes' rows (felyne_row_base).
Every copy of the file is changed (core_lobby, core_arena and core_result), and the facility menu's layout (ui401, in
the same ARCs) gets the screens' panes (menu_layout.py).
"""

from collections import defaultdict
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from core.game.files.arc import parse_arc, write_arc
from core.game.files.text.lmd import LMD_TYPE_HASH, parse_lmd, write_lmd
from core.interface.hud.build import GameFiles
from core.equipment.layered.menu_layout import add_forge_screen
from core.equipment.layered.looks import (
    NAME_PARTS, NOTHING_KEY, STATE_WEAPONS, Looks, WeaponLook, abbreviate, armor_labels, common_name, fit_label,
    load_curated, load_looks,
)

if TYPE_CHECKING:
    from core.equipment.layered.felyne_looks import FelyneLooks
    from core.equipment.mhgen.looks import GenLooks

LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
MAKESHOP_ARCS = ("core_lobby.arc", "core_arena.arc", "core_result.arc")
MAKESHOP_FILE = 6        # E_makeshop among the lobby's message files (table at 0xF007E4)
MESSAGE_BASE = 147       # the game's own messages in E_makeshop
# The words of the forge-style screens (layered_rules.py gives their messages to the screens' code).
FORGE_KEYS = ("rank_low", "rank_high", "rank_g", "game_mh4u", "game_gen", "game_all", "armor", "help_weapons",
              "help_armor", "help_felyne", "help_row", "help_filter")
# help_row_weapons: the weapons' key bar, which has no Y (layered_equipment.py gives its message to struct data);
# dye_keys, select_key: the colour window's key bar and the word on SELECT's key (menu_layout.py, struct fg_dye);
# relics, help_relics: the entry's Relics line and its help (layered_rules.py gives their messages to the screens' code)
UI_KEYS = ("entry", "entry_help", "weapons", "blank", "felynes", "felyne_none", "felyne_choose", *FORGE_KEYS,
           "help_row_weapons", "counter", "dye_keys", "select_key", "relics", "help_relics")
COUNTER = None  # the "counter" message: only the text renderer's string slot 0 (Lmd.add_number_message), no text
SET_BASE = MESSAGE_BASE + len(UI_KEYS)  # the name of armor look i is message SET_BASE + i
NAME_FILES = {"head": "HeadName", "body": "BodyName", "arms": "ArmName", "waist": "WaistName", "legs": "LegName"}
FELYNE_NAME_FILES = {"head": "OtHelmName", "body": "OtArmorName", "weapon": "OtWeaponName"}
# The weapon name lists of core_common (common message files 27-40, in equipment type order).
WEAPON_NAME_FILES = {
    "great_sword": "LswordName", "sword_and_shield": "SwordName", "hammer": "HammerName", "lance": "LanceName",
    "light_bowgun": "LightName", "heavy_bowgun": "HeavyName", "long_sword": "Lsword2Name", "switch_axe": "AxeName",
    "gunlance": "Lance2Name", "bow": "BowName", "dual_blades": "WswordName", "hunting_horn": "Hammer2Name",
    "insect_glaive": "RodName", "charge_blade": "GaxeName",
}
MAX_LINE = 20            # characters of a menu line (ui401's text pane is 120 pixels at font 11)


class LayeredTextError(ValueError):
    pass


def message_id(key: str) -> int:
    return MESSAGE_BASE + UI_KEYS.index(key)


def _texts(common_arc: bytes) -> dict[str, bytes]:
    return {entry.name.split("\\")[-1]: entry.data for entry in parse_arc(common_arc).entries
            if entry.type_hash == LMD_TYPE_HASH}


def piece_names(common_arc: bytes, lang: str) -> dict[str, dict[int, str]]:
    """Part -> armor piece index -> name, from a language's core_common.arc."""
    texts = _texts(common_arc)
    return {part: dict(enumerate(parse_lmd(texts[f"{NAME_FILES[part]}_{lang}"]).strings)) for part in NAME_PARTS}


def weapon_names(common_arc: bytes, lang: str) -> dict[str, dict[int, str]]:
    """Weapon class -> weapon index -> name (the message a weapon row shows), from a language's core_common.arc."""
    texts = _texts(common_arc)
    names = {}
    for key in STATE_WEAPONS:
        lmd = parse_lmd(texts[f"{WEAPON_NAME_FILES[key]}_{lang}"])
        names[key] = {i: lmd.message(i).strip() for i in range(lmd.message_count)}
    return names


def look_names(looks: Looks, lang: str, names: Mapping[str, Mapping[int, str]]) -> list[str]:
    """The menu line of every armor look in one language; "Nothing" (looks.NOTHING_KEY) is its word alone, being of
    every rank."""
    curated = load_curated()
    overrides = {key: value[lang] for key, value in looks.names.items() if lang in value}
    labels = armor_labels(looks.armor, names, tuple(curated["ranks"][lang]), curated["hunters"][lang], overrides,
                          max_line=MAX_LINE)
    labels = [overrides[look.key] if look.key == NOTHING_KEY else label for look, label in zip(looks.armor, labels)]
    return [label[:1].upper() + label[1:] for label in labels]


def custom_weapons(looks: Looks) -> list[WeaponLook]:
    """The weapon looks whose line is an added message, in data order: named by the curated file (looks of
    other games) or numbered (their weapon's name is shared)."""
    return [look for key in STATE_WEAPONS for look in looks.weapons[key] if look.weapon < 0 or look.number]


def weapon_name_messages(looks: Looks) -> list[int]:
    """The message of each of custom_weapons: after the armor look names."""
    first = SET_BASE + len(looks.armor)
    return [first + i for i in range(len(custom_weapons(looks)))]


def weapon_label(key: str, look: WeaponLook, lang: str, names: Mapping[str, Mapping[int, str]]) -> str:
    """The line of a weapon look of class `key` in one language. `names`: weapon_names."""
    if look.weapon < 0:
        return look.names.get(lang) or look.names["eng"]
    name = names[key][look.weapon]
    return fit_label(name, str(look.number), MAX_LINE) if look.number else name


def gen_set_base(looks: Looks) -> int:
    """The message of Generations set i is gen_set_base + i, after the MH4U looks' messages; the Generations
    weapons' follow the sets (data order: STATE_WEAPONS, then each class's looks)."""
    return SET_BASE + len(looks.armor) + len(custom_weapons(looks))


def gen_set_labels(gen: "GenLooks", lang: str) -> list[str]:
    """The menu line of every Generations set in one language, named as the MH4U looks (armor_labels)."""
    curated = load_curated()
    labels = armor_labels([s.look for s in gen.sets], gen.piece_names(lang), tuple(curated["ranks"][lang]),
                          curated["hunters"][lang], max_line=MAX_LINE)
    return [label[:1].upper() + label[1:] for label in labels]


def felyne_row_base(looks: Looks, gen: "GenLooks | None") -> int:
    """The message of the first Felyne row's name, after every other look's."""
    if gen is None:
        return gen_set_base(looks)
    return gen_set_base(looks) + len(gen.sets) + sum(len(gen.weapons[key]) for key in STATE_WEAPONS)


def felyne_piece_names(common_arc: bytes, lang: str) -> dict[str, dict[int, str]]:
    """Part -> Felyne piece -> name, from a language's core_common.arc."""
    texts = _texts(common_arc)
    return {part: dict(enumerate(parse_lmd(texts[f"{name}_{lang}"]).strings))
            for part, name in FELYNE_NAME_FILES.items()}


def felyne_row_labels(felynes: "FelyneLooks", lang: str,
                      names: Mapping[str, Mapping[int, str]] | None = None) -> list[str]:
    """The lines of the Felyne rows (felyne_looks.felyne_rows) in one language: the armor pieces' common name, else
    the weapon's, cut to MAX_LINE and numbered where two rows share a line (numbered_labels). The game's own rows read
    theirs in `names` (felyne_piece_names); MH XX's bring them."""
    from core.equipment.layered.felyne_looks import felyne_rows

    def own(row) -> str:
        armor = [part for part in ("head", "body") if part in row.pieces] or ["weapon"]
        return common_name(names[part][row.pieces[part]] for part in armor)

    return numbered_labels([own(row) if row.pieces else row.names.get(lang) or row.names["eng"]
                            for row in felyne_rows(felynes)])


def gen_weapon_labels(looks: list[WeaponLook], lang: str) -> list[str]:
    """The lines of one class's Generations weapon looks: MHGen's names (numbered_labels)."""
    return numbered_labels([look.names.get(lang) or look.names["eng"] for look in looks])


def numbered_labels(names: list[str]) -> list[str]:
    """`names` cut to MAX_LINE (abbreviate), from the second line alike on numbered as relic weapons are."""
    seen: dict[str, int] = defaultdict(int)
    labels = []
    for name in names:
        label = abbreviate(name, MAX_LINE)
        seen[label] += 1
        labels.append(label if seen[label] == 1 else fit_label(name, str(seen[label]), MAX_LINE))
    return labels


def layered_messages(looks: Looks, lang: str, names: Mapping[str, Mapping[int, str]],
                     weapons: Mapping[str, Mapping[int, str]], gen: "GenLooks | None" = None,
                     felynes: "FelyneLooks | None" = None,
                     felyne_names: Mapping[str, Mapping[int, str]] | None = None) -> list[str | None]:
    """Every message added to E_makeshop in one language, in index order from MESSAGE_BASE (COUNTER: the
    counter's slot). `names`: piece_names; `weapons`: weapon_names; `gen`: Generations' looks, if any; `felynes`:
    the Felynes', if any, and `felyne_names` (felyne_piece_names) for the game's own rows."""
    ui = load_curated()["ui"]
    custom = [weapon_label(key, look, lang, weapons) for key in STATE_WEAPONS for look in looks.weapons[key]
              if look.weapon < 0 or look.number]
    ui_messages = [COUNTER if key == "counter" else ui[key][lang] for key in UI_KEYS]
    messages = ui_messages + look_names(looks, lang, names) + custom
    if gen is not None:
        messages += gen_set_labels(gen, lang)
        messages += [label for key in STATE_WEAPONS for label in gen_weapon_labels(gen.weapons[key], lang)]
    if felynes is not None:
        messages += felyne_row_labels(felynes, lang, felyne_names)
    return messages


def add_messages(arc: bytes, lang: str, messages: list[str | None]) -> bytes:
    """`arc` with `messages` appended to its E_makeshop (COUNTER: a message of the string slot)."""
    parsed = parse_arc(arc)
    name = f"{lang}\\msg\\lobby\\E_makeshop_{lang}"
    entry = next((e for e in parsed.entries if e.name == name and e.type_hash == LMD_TYPE_HASH), None)
    if entry is None:
        raise LayeredTextError(f"no {name} in the ARC")
    lmd = parse_lmd(entry.data)
    if lmd.message_count != MESSAGE_BASE:
        raise LayeredTextError(f"{name} has {lmd.message_count} messages, not the game's {MESSAGE_BASE}")
    for text in messages:
        if text is COUNTER:
            lmd.add_number_message()
        else:
            lmd.add_message(text)
    entry.data = write_lmd(lmd)
    return write_arc(parsed)


def layered_text_files(rom: GameFiles, files: Mapping[str, bytes] | None = None,
                       looks: Looks | None = None, gen: "GenLooks | None" = None,
                       felynes: "FelyneLooks | None" = None) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of every copy of E_makeshop, for the 5 languages. An ARC already in `files` (the HUD, the
    icons) gets the messages on top of that version; the others start from the base game's (`rom`), whose core_common
    gives
    the names. The ARC's ui401 gets the screens' panes (menu_layout.py). `gen`: XX's looks, whose names follow, and then
    `felynes`', the Felynes' rows."""
    files = files or {}
    looks = looks or load_looks()
    for lang in LANGUAGES:
        common = files.get(f"{lang}/data/core_common.arc") or rom.read(f"{lang}/data/core_common.arc")
        title = files.get(f"{lang}/data/core_title.arc") or rom.read(f"{lang}/data/core_title.arc")
        messages = layered_messages(looks, lang, piece_names(common, lang), weapon_names(common, lang), gen, felynes,
                                    felyne_piece_names(common, lang) if felynes is not None and felynes.game else None)
        for arc_name in MAKESHOP_ARCS:
            path = f"{lang}/data/{arc_name}"
            raw = files.get(path) or rom.read(path)
            yield path, add_forge_screen(add_messages(raw, lang, messages), lang, common, title)


def layered_text_paths(mod_dir: Path) -> list[Path]:
    """Every file the option can leave in a mod folder."""
    return [Path(mod_dir) / "romfs" / lang / "data" / name for lang in LANGUAGES for name in MAKESHOP_ARCS]


def remove_layered_text_files(mod_dir: Path) -> None:
    for path in layered_text_paths(mod_dir):
        path.unlink(missing_ok=True)
