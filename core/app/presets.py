"""The GUI's presets: what a new run fixes without a widget and which fields are the installer's options
(`game/data/curated/gui_presets.json`), and every widget's starting value (`game/data/curated/gui_defaults.json`, a
settings file with only the widgets' fields).

No GUI imports, so the Qt pages and the tests share it. The `Settings` dataclass defaults never change (the checksum
of the games made before depends on them): a preset is a dict of `Settings` fields that is merged over them.

Fix mode never uses any of this: a loaded game keeps its own values (seed, quest rerolls, every option it was made
with), and the presets never carry `seed`, `quest_reroll`, `quest_rerolls` or `free_cutscene_monsters`.
"""

import json
from dataclasses import fields, replace
from functools import lru_cache

from core.app.settings import Settings
from core.game.data.paths import CURATED_DIR

PRESETS_PATH = CURATED_DIR / "gui_presets.json"
DEFAULTS_PATH = PRESETS_PATH.with_name("gui_defaults.json")
KINDS = ("install", "randomizer")


@lru_cache(maxsize=1)
def load_presets() -> dict:
    """Both files' content (gui_defaults.json under "defaults"), checked: every key is a `Settings` field, every
    value parses, every installer option has a default and no field is in two places. Cached."""
    data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    data["defaults"] = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    names = {f.name for f in fields(Settings)}
    data.setdefault("in_game", [])
    missing = set(data["install"]["options"]) - set(data["defaults"])
    if missing:
        raise ValueError(f"gui_defaults.json: no value for the installer options {sorted(missing)}")
    if not set(data["in_game"]) <= set(data["install"]["options"]):
        raise ValueError("gui_presets.json: an option of the START menu's page (in_game) is no installer option")
    for name, bounds in data["ranges"].items():
        if name not in names or len(bounds) != 2 or bounds[0] > bounds[1]:
            raise ValueError(f"gui_presets.json, ranges: {name}")
    for name, step in data.setdefault("steps", {}).items():
        if name not in data["ranges"] or step < 1:
            raise ValueError(f"gui_presets.json, steps: {name}")
    parts = _sections(data)
    for name, values in parts.items():
        unknown = set(values) - names
        if unknown:
            raise ValueError(f"gui_presets.json / gui_defaults.json, {name}: not Settings fields: {sorted(unknown)}")
        Settings.from_dict(values)  # an unknown enum value raises here
    for source, targets in data["install"]["links"].items():
        if source not in data["install"]["options"] or not set(targets) <= names:
            raise ValueError(f"gui_presets.json, install.links: {source}")
    for kind in (("common", "install_fixed", "install_options"),
                 ("common", "randomizer_fixed", "randomizer_defaults", "install_options")):
        seen: dict[str, str] = {}
        for name in kind:
            for key in parts[name]:
                if key in seen:
                    raise ValueError(f"gui_presets.json / gui_defaults.json: {key} is in {seen[key]} and {name}")
                seen[key] = name
    _check_modules(data["install"].get("modules", {}), data["install"]["options"], names)
    return data


def _check_modules(layout: dict, options: list[str], names: set[str]) -> None:
    """An edition's modules hold every installer option once, each under a switch of its own (a bool installer option,
    the first name); the other names are Settings fields or rows of the START menu's page only."""
    if not layout:
        return
    from core.interface.mod_settings.mod_options import page_only_options
    bools = {f.name for f in fields(Settings) if f.type in (bool, "bool")}
    listed = [name for members in layout.values() for name in members]
    for key, members in layout.items():
        if not members or members[0] not in bools or members[0] not in options:
            raise ValueError(f"gui_presets.json, install.modules: {key} starts with no switch")
    unknown = set(listed) - names - set(page_only_options())
    doubled = {name for name in listed if listed.count(name) > 1}
    left_out = set(options) - set(listed)
    if unknown or doubled or left_out:
        raise ValueError(f"gui_presets.json, install.modules: unknown {sorted(unknown)}, twice {sorted(doubled)}, "
                         f"in no module {sorted(left_out)}")


def _sections(data: dict) -> dict[str, dict]:
    defaults, options, in_game = data["defaults"], data["install"]["options"], data["in_game"]
    return {"common": data["fixed"], "install_fixed": data["install"]["fixed"],
            "install_options": {k: defaults[k] for k in options}, "in_game": {k: defaults[k] for k in in_game},
            "randomizer_fixed": data["randomizer"]["fixed"],
            "randomizer_defaults": {k: v for k, v in defaults.items() if k not in options}}


def section(name: str) -> dict:
    """One flat part of the file: common, install_fixed, install_options, in_game, randomizer_fixed,
    randomizer_defaults."""
    return dict(_sections(load_presets())[name])


def fixed_fields(kind: str) -> set[str]:
    """The fields a new run of `kind` ("install" | "randomizer") fixes: no widget anywhere."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    return set(section("common")) | set(section(f"{kind}_fixed"))


def in_game_fields() -> list[str]:
    """The options the START menu's Mod Settings page holds in this edition, in the file's order (gui_presets.json
    `in_game`). They are installer options too: the value installed is what a character with no choice gets."""
    return list(load_presets()["in_game"])


def install_links() -> dict[str, list[str]]:
    """Installer options that write other fields with the same value (Option.links)."""
    return {k: list(v) for k, v in load_presets()["install"]["links"].items()}


def modules() -> dict[str, list[str]]:
    """The edition's modules, in the Options page's order (gui_presets.json `install.modules`): each a switch (its first
    name) and what it turns on and off, Settings fields and rows of the START menu's page. Empty: an edition without
    modules, whose options are all on their own."""
    return {key: list(members) for key, members in load_presets()["install"].get("modules", {}).items()}


def module_off_fields(settings: Settings) -> set[str]:
    """Every name of the modules whose switch is off in `settings`: the run leaves them out of the game, and out of the
    START menu's page."""
    return {name for members in modules().values() if not getattr(settings, members[0]) for name in members}


def apply_modules(settings: Settings) -> Settings:
    """`settings` with each field of a module that is off at the Settings default, the game's own (the switch keeps its
    value). The Options page only greys those options out, so they keep the player's values for when the module is on
    again."""
    off = module_off_fields(settings) - {members[0] for members in modules().values()}
    defaults = Settings()
    names = {f.name for f in fields(Settings)}
    return replace(settings, **{name: getattr(defaults, name) for name in off if name in names})


def installer_fields() -> set[str]:
    """Every field an installer option writes (the options and what they link)."""
    return set(section("install_options")) | {t for ts in install_links().values() for t in ts}


def personal_defaults() -> dict:
    """The installer options' default values (hud_scale, touchless_target, skip_intro...); also the personal part of
    a randomizer run."""
    return section("install_options")


def field_range(field: str) -> tuple[int, int]:
    """The lowest and highest value a number option lets the player pick (gui_presets.json `ranges`)."""
    low, high = load_presets()["ranges"][field]
    return int(low), int(high)


def field_step(name: str) -> int:
    """How far apart a number field's values are (gui_presets.json `steps`; 1 unless it says otherwise): the values of
    its list in the game's menu."""
    return load_presets()["steps"].get(name, 1)


def legacy_choices() -> dict[str, list[str]]:
    """Per randomizer enum field, the values shown only while a loaded game has them (last in its choices)."""
    return {k: list(v) for k, v in load_presets()["randomizer"]["legacy_choices"].items()}


def randomizer_defaults() -> dict:
    """The randomizer widgets' default values (gui_defaults.json without the installer options)."""
    return section("randomizer_defaults")


def _expand(personal: dict) -> dict:
    unknown = set(personal) - set(section("install_options"))
    if unknown:
        raise ValueError(f"not installer options: {sorted(unknown)}")
    values = dict(personal)
    for source, targets in install_links().items():
        if source in personal:
            values.update({target: personal[source] for target in targets})
    if not values.get("cheat_aspect_allowed"):      # the list greys out without its switch, and keeps its value
        values["cheat_aspect_ratio"] = "off"
    return values


def install_settings(personal: dict) -> Settings:
    """The mod without the randomizer: the common and install fixed fields, the installer options as the player
    set them (`personal`, keys of `personal_defaults()`; a missing one keeps the Settings default) and their links.
    No seed."""
    return Settings.from_dict({**_expand(personal), **section("common"), **section("install_fixed")})


def randomizer_settings(chosen: dict, personal: dict, seed: str) -> Settings:
    """A randomizer run: the randomizer defaults, over them the player's widgets (`chosen`, keys of
    `randomizer_defaults()`), then the installer options (`personal`) and the fixed fields. A widget naming a fixed
    field or an unknown one raises ValueError."""
    defaults = randomizer_defaults()
    unknown = set(chosen) - set(defaults)
    if unknown:
        raise ValueError(f"not randomizer widgets: {sorted(unknown)}")
    return Settings.from_dict({**defaults, **chosen, **_expand(personal), **section("common"),
                               **section("randomizer_fixed"), "seed": seed})
