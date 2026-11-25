"""The options a player changes during play (blocks `mod_options_stub`, `mod_options_data`, `mod_raw_table`, variable
`mod_options_state`, and the unit mod_options.c of `mod_settings_code`).

Each option has a list of values (curated mod_settings.json, `options`) and half a byte of the character's save zone
(option_half; the zone counts only with the magic and the mod's version). A
character with no choice, and the title screen, take the default the mod is installed with: the Settings field of the
same name, what the player chose in the installer (it starts at gui_defaults.json's). An option with a `default` of its
own in the curated file is the page's only: it has no Settings field, every edition's mod has it, and that value is its
default. The code reads every option once a frame (mod_options.c `mod_frame`).
These functions change, in the update's executable (canonical):

- FUN_00af52a0, the application's update: its call of FUN_00644320 (FRAME_CALL) goes through the stub, which runs
  mod_frame first;
- FUN_002bc258, the bloom and depth of field pass: its first instruction (BLOOM_FILTER) goes through the stub, which
  returns at once while the option is on;
- FUN_00bff28c and FUN_00c06a14, the camera's resets: the loads of the field of view (FOV_SITES) take the mod's value;
- FUN_00533e6c, FUN_005348a8 and FUN_00535480, the multiplayer node's waits (NET_SITES): the numbers come from the mod;
- FUN_0026e33c and FUN_0027335c, which load the weapon classes' table of display multipliers (RAW_SITES): its base
  address is the game's table or one of 100s;
- FUN_00bfd028, the camera's turn by the buttons (the PC port's `sMhCamera::turnByInput`): its load of the cap on how
  long a turn has been held, and so of the turn's top speed (CAMERA_CAP, 10.0), takes the mod's value;
- FUN_009ec82c, which opens an item box's menu: its store of the box's kind (BOX_KIND; 0 the house's, 1 the
  Gathering Hall's) makes every box the house's, and its store of the menu's count of lines (BOX_LINES; 7 at home, 4
  at the Hall's box) keeps Change Appearance only where its screen's layout is loaded (mod_options.c mod_box_count),
  so Manage Equipment, Equipment Sets and Change Appearance are at every box, drawn: every town area's stage list
  loads the layout too (box_appearance.py);
- FUN_00b0b0ac and FUN_00b0a658, which load a Honed weapon's glow and put it on the weapon's models: their reads of
  the weapon's honing (HONING_SITES) see none while the option is No;
- FUN_002b58e8, the poll of the game's keyboard: through a gate to the system keyboard (system_keyboard);
- the calls of hold A, fast text, fast gathering, the lock-on's D-pad filter, the death camera skip (FUN_00c006f4's
  call of a camera sequence's frame), the modern camera (FUN_00b3cc64's question "is the C-stick tilted", the
  cameras' calls of FUN_00bfd028) and the intro skip (FUN_002951fc's call of a touch bar button's frame) go through
  a gate (the modules' own patches, `gated`), which makes the game's call when the option is off.

The game's per-frame writes (3D, the frame rate, the camera) are mod_frame's. Update's executable only; the version maps
carry it to the base games.
"""

import json
import struct
from collections.abc import Collection
from enum import Enum
from pathlib import Path
from typing import Any

from core.game.data.paths import CURATED_DIR
from core.game.executable.blocks import MOD_OPTIONS_DATA_SIZE, MOD_RAW_TABLE_SIZE
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout
from core.interface.mod_settings.mod_texts import message_indices

SETTINGS_FILE = CURATED_DIR / "mod_settings.json"
STUB, DATA, RAW_TABLE = "mod_options_stub", "mod_options_data", "mod_raw_table"
VARIABLES = ("mod_options_state", "option_list_state")

# The options' numbers: mod_options.c's enum, and the offsets mod_options_stub.s reads (.equ OPT_*)
OPTION_IDS = {
    "cheat_3d_mode": 0, "cheat_no_bloom_dof": 1, "cheat_fps": 2, "cheat_fov": 3, "cheat_net_fix": 4,
    "cheat_raw_unbloat": 5, "touchless_target": 6, "hold_a": 7, "fast_text": 8,
    "camera_speed": 10, "box_equipment": 11, "system_keyboard": 12, "skip_death_camera": 13, "damage_numbers": 14,
    "damage_numbers_other": 15, "damage_numbers_style": 16, "damage_numbers_size": 17, "damage_numbers_duration": 18,
    "modern_camera": 19,
    "horn_songs": 20,
    "skip_monster_intro": 21,
    "modern_camera_speed": 22, "modern_camera_acceleration": 23,
    "horn_songs_colour": 24,
    "camera_distance": 25,
    "smithy_view": 26,
    "layered_looks": 27,
    # The Cheats group's rows:
    # only a mod built with `cheats_enabled` has them, each kept per character and off at first
    "fast_gathering": 28, "cheat_interruptible_flex": 29, "cheat_whetstone_cancel": 30, "cheat_skip_quest_end": 31,
    "cheat_rewards_no_limit": 32, "cheat_capture_guru": 33, "cheat_autotracker": 34,
    "world_sharpness": 35,
    "upgrade_stars": 36, "rare_rewards": 37, "upgrade_stars_colour": 38,
    "honing_glow": 39,
    "town_map": 40,
    # More of the Cheats group: the extra aspect ratio (cheats/aspect_ratio.c) and the damage multipliers
    # (cheats/damage_multipliers/)
    "cheat_aspect_18_9": 41, "cheat_damage_dealt": 42, "cheat_damage_taken": 43,
}
# The rows of a feature the installer chooses, which mean nothing without it: the row, the feature's Settings field
# (or property)
FEATURE_ROWS = {"layered_looks": "layered_equipment",  # Layered Gear's switch (equipment/layered/layered_switch.c)
                # the town minimap's start (interface/single_screen/executable/single_screen_minimap_hall.c)
                "town_map": "single_screen",
                # the extra aspect ratio needs the aspect ratio's hooks (Settings.aspect_on: the installer's switch)
                "cheat_aspect_18_9": "aspect_on"}
CHEATS_ALLOWED = "cheats_allowed"   # the gate's variable (mod_options.c struct cheats_allowed)
GATE_SIZE = 12                  # struct cheats_gate: two words of gated options, the retry's frames, a pad
MAX_OPTIONS = 52                # the room (mod_options.c MOD_OPTIONS; mod_options_state.values): zone bytes 10-35
MAX_VALUES = 15                 # a list of values (two pages): a value's place + 1 fits half a byte
PAYLOAD_WORDS = 2               # what a value writes or hands to a hook
VALUE_POOL = 256                # the values of all the options together (mod_options.c MOD_POOL); the first is none
ZONE_FIRST_BYTE = 10            # the options' first byte of the save zone (9: the ratio; the wheel's: 6-7, 37-47)
ZONE_BYTES = 48                 # the zone's size (curated mod_settings.json)
OPTION_SIZE = 4                 # struct mod_option: count, default place, first value in the pool, half byte
HEADER_SIZE = 16
NO_MULTIPLIER = 100             # a weapon class's display multiplier in percent: 100 shows the true attack
CLASS_MULTIPLIERS = 16          # the table's words

# The hooks. (address, the word the game has)
FRAME_CALL, FRAME_UPDATE = 0xAF52E4, 0x644320   # FUN_00af52a0: bl FUN_00644320
BLOOM_FILTER, BLOOM_ORIGINAL = 0x2BC258, 0xE92D4FF0     # FUN_002bc258: push {r4-r11, lr}
FOV_RESET = ((0xBFF440, 0x1D9F0A87), (0xBFF444, 0x0D9F0A87))   # FUN_00bff28c: vldrne s0, [pc, ..]; vldreq s0, [pc, ..]
FOV_OTHER = (0xC06C88, 0xEDDF1A56)                      # FUN_00c06a14: vldr s3, [pc, #0x158]
NET_WAITS = (0x533F40, 0xE3520078)                      # FUN_00533e6c: cmp r2, #120
NET_POLLS = ((0x534B54, 0xE3A0000A), (0x5356DC, 0xE3A0000A))   # FUN_005348a8, FUN_00535480: mov r0, #10
RAW_SITES = ((0x26E390, 0xE59F0020), (0x273368, 0xE59F201C))   # FUN_0026e33c, FUN_0027335c: ldr r0/r2, [pc, ..]
CAMERA_CAP = (0xBFD16C, 0xED9F0A72)                     # FUN_00bfd028: vldr s0, [pc, #0x1c8] (10.0, at 0xBFD33C)
# The camera's distance from the hunter (camera + 0xEB8): its three loads of a literal, each replaced by a jump to its
# stub in CAMERA_DISTANCE_STUBS
CAMERA_DISTANCE = ((0xBFFF78, 0xED9F1A2A),      # FUN_00bfff70: vldr s2, [pc, #0xa8] (490.0, the resting distance)
                   (0xC056DC, 0xEDDF0A09),      # FUN_00c056d4: vldr s1, [pc, #0x24] (630.0, an event's zoom-out)
                   (0xC00AA4, 0xED9F0AAB))      # FUN_00c009ac: vldr s0, [pc, #0x2ac] (300.0, a state of the hunter)
CAMERA_DISTANCE_STUBS = ("mod_camera_rest", "mod_camera_event", "mod_camera_state")
BOX_KIND = (0x9EC870, 0xE5C46002)                       # FUN_009ec82c: strb r6, [r4, #0x2] (the box's kind)
BOX_LINES = (0x9EC8A4, 0xE5C4100A)                      # FUN_009ec82c: strb r1, [r4, #0xa] (the menu's lines)
# The two reads of a weapon's honing (its reference's halfword +0x12, bits 14-15) that give it its glow, each replaced
# by a call of mod_honing_glow
HONING_SITES = ((0xB0B0E0, 0xE1A00720),     # FUN_00b0b0ac: lsr r0, r0, #14 (which glow to load)
                (0xB0A680, 0xE1B00720))     # FUN_00b0a658: lsrs r0, r0, #14 (put it on the weapon's models)
CLASS_TABLE = 0xED24A0
CLASS_WORDS = (480, 140, 520, 230, 150, 130, 130, 330, 540, 230, 120, 140, 520, 310, 360, 170)


class ModOptionsError(ValueError):
    """The curated options are not what the code can hold."""


def _words(code: bytes | bytearray, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def option_half(number: int) -> int:
    """The save zone's half byte of option `number`: byte half // 2, its low half for an even number and its high half
    for an odd one, holding the value's place + 1 (0: no choice yet)."""
    return 2 * ZONE_FIRST_BYTE + number


def load_options(path: Path = SETTINGS_FILE) -> list[dict]:
    """The curated options: {"key", "name", "help", "title", "values": [{"name", "setting", "payload": [u32, u32]}]},
    and "default" for an option of the page only, in the order of the file (the title is the name, for a row without
    one of its own). Refuses an option the code has no number for, a repeated one, a list of values that is empty or
    longer than MAX_VALUES, more values in all than the pool holds, a value with more than PAYLOAD_WORDS numbers or
    both kinds of them, a default that is not one of its values' settings, and a text that is no menu text."""
    raw = json.loads(Path(path).read_text(encoding="utf-8")).get("options")
    entries = raw.get("value") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise ModOptionsError("mod_settings.json: options must be {\"value\": [options], \"description\": ...}")
    known, seen, options = message_indices(), set(), []
    for entry in entries:
        key = entry.get("key")
        if key not in OPTION_IDS or key in seen:
            raise ModOptionsError(f"mod_settings.json: option {key!r} is unknown or repeated (OPTION_IDS)")
        seen.add(key)
        values = entry.get("values")
        if not isinstance(values, list) or not 1 <= len(values) <= MAX_VALUES:
            raise ModOptionsError(f"mod_settings.json: {key} must have 1 to {MAX_VALUES} values")
        title = entry.get("title", entry.get("name"))
        for text in (entry.get("name"), entry.get("help"), title, *(value.get("name") for value in values)):
            if text not in known:
                raise ModOptionsError(f"mod_settings.json: {key}: no menu text {text!r}")
        option = {"key": key, "name": entry["name"], "help": entry["help"], "title": title,
                  "values": [{"name": value["name"], "setting": value["setting"], "payload": _payload(key, value)}
                             for value in values]}
        if entry.get("cheat"):
            if "default" not in entry:
                raise ModOptionsError(f"mod_settings.json: {key} is a cheat: it needs a default of its own")
            option["cheat"] = True
        if "default" in entry:
            if not any(_same(value["setting"], entry["default"]) for value in values):
                raise ModOptionsError(f"mod_settings.json: {key}: its default is none of its values' settings")
            option["default"] = entry["default"]
        options.append(option)
    if 1 + sum(len(option["values"]) for option in options) > VALUE_POOL:
        raise ModOptionsError(f"mod_settings.json: the options have more values than the pool holds ({VALUE_POOL - 1})")
    return options


def _same(a: Any, b: Any) -> bool:
    return a == b and type(a) is type(b)


def page_only_options(path: Path = SETTINGS_FILE) -> list[str]:
    """The options of the START menu's page only: a `default` of their own in the curated file, no Settings field and
    no installer choice; every edition's mod has them, but for the cheats (`cheat_options`)."""
    return [option["key"] for option in load_options(path) if "default" in option and not option.get("cheat")]


def cheat_options(path: Path = SETTINGS_FILE) -> list[str]:
    """The rows of the Cheats group (`cheat`: true in the curated file): page-only options that only a mod built with
    `cheats_enabled` has, each off at first."""
    return [option["key"] for option in load_options(path) if option.get("cheat")]


def _payload(key: str, value: dict) -> list[int]:
    if "words" in value and "floats" in value:
        raise ModOptionsError(f"mod_settings.json: {key}: a value has words or floats, not both")
    if "floats" in value:
        words = [struct.unpack("<I", struct.pack("<f", number))[0] for number in value["floats"]]
    else:
        words = [int(number) for number in value.get("words", [])]
    if len(words) > PAYLOAD_WORDS or any(not 0 <= word < 1 << 32 for word in words):
        raise ModOptionsError(f"mod_settings.json: {key}: at most {PAYLOAD_WORDS} numbers of 32 bits per value")
    return words + [0] * (PAYLOAD_WORDS - len(words))


def _setting(settings: Any, key: str) -> Any:
    value = getattr(settings, key)
    return value.value if isinstance(value, Enum) else value


def default_value(option: dict, settings: Any) -> int:
    """The place in the option's values of `settings`' value for it (the installed default), or of its own `default`
    for an option of the page only: the value whose `setting` is it, else for a number the nearest, else the first (the
    game's own)."""
    wanted = option["default"] if "default" in option else _setting(settings, option["key"])
    choices = [value["setting"] for value in option["values"]]
    for place, choice in enumerate(choices):
        if _same(choice, wanted):
            return place
    if isinstance(wanted, int) and not isinstance(wanted, bool):
        numbers = [(abs(choice - wanted), place) for place, choice in enumerate(choices)
                   if isinstance(choice, int) and not isinstance(choice, bool)]
        if numbers:
            return min(numbers)[1]
    return 0


def cheats_retry(path: Path = SETTINGS_FILE) -> int:
    """The frames between two reads of the cheats' flag that got no answer (curated `cheats_gate`, `retry_frames`)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8")).get("cheats_gate")
    frames = raw.get("value", {}).get("retry_frames") if isinstance(raw, dict) else None
    if not isinstance(frames, int) or isinstance(frames, bool) or not 1 <= frames <= 0xFFFF:
        raise ModOptionsError("mod_settings.json: cheats_gate must be {\"value\": {\"retry_frames\": 1 to 65535}}")
    return frames


def gate_data(gated: Collection[str] = (), path: Path = SETTINGS_FILE) -> bytes:
    """struct cheats_gate (mod_options.c), the tail of `mod_options_data`: a bit per option of `gated`, the options that
    are 0 while the launcher's flag has not allowed the cheats, and the frames between two reads of the flag (curated
    `cheats_gate`); all zeros without one (every mod but a 3DS title's: the flag is never read)."""
    if not gated:
        return bytes(GATE_SIZE)
    mask = 0
    for key in gated:
        mask |= 1 << OPTION_IDS[key]
    return struct.pack("<2I2H", mask & 0xFFFFFFFF, mask >> 32, cheats_retry(path), 0)


def options_data(settings: Any, available: set[str] | frozenset[str] | list[str], path: Path = SETTINGS_FILE,
                 gated: Collection[str] = ()) -> bytes:
    """The block `mod_options_data` (struct mod_options_data in mod_options.c): the save zone's place, magic and
    version, the value list's texts, per option (MAX_OPTIONS of them, in the order of OPTION_IDS) its count of values
    (0: the mod does not have it), the default place, its first value in the pool and its half byte of the zone
    (option_half), then the pool: each value's name and what it writes (PAYLOAD_WORDS words), the options' values one
    after another from the second; the first is none (no name, zeros), which an option the mod lacks points at; last
    the Cheats group's gate (gate_data of `gated`, options of `available`)."""
    from core.interface.mod_settings.mod_settings import load_zone

    zone, known = load_zone(path), message_indices()
    data = struct.pack("<I4sH3H", zone["offset"], zone["magic"], zone["version"], known["option_help"],
                       known["aspect_row"], known["aspect_marked"])
    by_id = {OPTION_IDS[option["key"]]: option for option in load_options(path) if option["key"] in available}
    names, payload = [0], [0] * PAYLOAD_WORDS
    for number in range(MAX_OPTIONS):
        option = by_id.get(number)
        if option is None:
            data += struct.pack("<4B", 0, 0, 0, option_half(number))
            continue
        values = option["values"]
        data += struct.pack("<4B", len(values), default_value(option, settings), len(names), option_half(number))
        names += [known[value["name"]] for value in values]
        payload += [word for value in values for word in value["payload"]]
    names += [0] * (VALUE_POOL - len(names))
    payload += [0] * (PAYLOAD_WORDS * VALUE_POOL - len(payload))
    data += struct.pack(f"<{VALUE_POOL}H", *names) + struct.pack(f"<{PAYLOAD_WORDS * VALUE_POOL}I", *payload)
    if set(gated) - set(available):
        raise ModOptionsError(f"gated options the mod does not have: {sorted(set(gated) - set(available))}")
    data += gate_data(gated, path)
    if len(data) != MOD_OPTIONS_DATA_SIZE:
        raise ModOptionsError(f"mod_options_data holds {MOD_OPTIONS_DATA_SIZE} bytes, the options make {len(data)}")
    return data


def raw_table() -> bytes:
    """The block `mod_raw_table`: the weapon classes' multipliers, all 100."""
    data = struct.pack(f"<{CLASS_MULTIPLIERS}I", *[NO_MULTIPLIER] * CLASS_MULTIPLIERS)
    assert len(data) == MOD_RAW_TABLE_SIZE
    return data


def _static_ok(code: bytes, sites: tuple[tuple[int, int], ...]) -> bool:
    return all(_words(code, at) == word for at, word in sites)


def supports_option(code: bytes, key: str) -> bool:
    """`code` has what the option's hooks replace (the update's executable, canonical, not patched yet)."""
    from core.gameplay.fast_gathering.fast_gathering import supports_fast_gathering
    from core.gameplay.hold_a.hold_a import supports_hold_a
    from core.interface.fast_text.fast_text import supports_fast_text
    from core.interface.hud.code_patch import supports_target_switch
    if key == "cheat_no_bloom_dof":
        return _words(code, BLOOM_FILTER) == BLOOM_ORIGINAL
    if key == "cheat_fov":
        return _static_ok(code, (*FOV_RESET, FOV_OTHER))
    if key == "cheat_net_fix":
        return _static_ok(code, (NET_WAITS, *NET_POLLS))
    if key == "cheat_raw_unbloat":
        return _static_ok(code, RAW_SITES) and all(
            _words(code, CLASS_TABLE + 4 * place) == word for place, word in enumerate(CLASS_WORDS))
    if key == "camera_speed":
        return _static_ok(code, (CAMERA_CAP,))
    if key == "camera_distance":
        return _static_ok(code, CAMERA_DISTANCE)
    if key == "box_equipment":
        return _static_ok(code, (BOX_KIND, BOX_LINES))
    if key == "honing_glow":
        return _static_ok(code, HONING_SITES)
    from core.interface.system_keyboard.system_keyboard import supports_system_keyboard
    from core.gameplay.death_camera_skip.death_camera_skip import supports_death_camera_skip
    from core.gameplay.modern_camera.modern_camera import supports_modern_camera
    from core.gameplay.intro_skip.intro_skip import supports_intro_skip
    from core.interface.damage_numbers.damage_numbers import OPTIONS, supports_damage_numbers
    if key in OPTIONS:
        return supports_damage_numbers(code)
    cheat = _cheat_supports().get(key)
    if cheat is not None:
        return cheat(code)
    if key == "smithy_view":
        from core.interface.weapon_tree.weapon_tree import supports_weapon_tree
        return supports_weapon_tree(code)
    if key in ("horn_songs", "horn_songs_colour"):
        from core.interface.horn_songs.horn_songs import supports_horn_songs
        return supports_horn_songs(code)
    if key == "layered_looks":
        from core.equipment.layered.layered_equipment import supports_layered_equipment
        return supports_layered_equipment(code)
    if key == "world_sharpness":
        from core.interface.world_sharpness.world_sharpness import supports_world_sharpness
        return supports_world_sharpness(code)
    if key in ("upgrade_stars", "rare_rewards", "upgrade_stars_colour"):
        from core.interface.item_marks.item_marks import supports_item_marks
        return supports_item_marks(code)
    checks = {"touchless_target": supports_target_switch, "hold_a": supports_hold_a, "fast_text": supports_fast_text,
              "fast_gathering": supports_fast_gathering, "system_keyboard": supports_system_keyboard,
              "skip_death_camera": supports_death_camera_skip, "modern_camera": supports_modern_camera,
              "modern_camera_speed": supports_modern_camera, "modern_camera_acceleration": supports_modern_camera,
              "skip_monster_intro": supports_intro_skip}
    return checks[key](code) if key in checks else True


def _cheat_supports() -> dict[str, Any]:
    """The check of each cheat's hooks (core/cheats/), by the option key of its row. The modules import this one for
    the number of rows, so they are loaded when asked for."""
    from core.cheats.action_cancel.action_cancel import FLEX_OPTION, WHETSTONE_OPTION, supports_action_cancel
    from core.cheats.aspect_ratio import CHEAT_ROW as ASPECT_ROW, supports_aspect_ratio
    from core.cheats.damage_multipliers.damage_multipliers import (
        CHEATS as DAMAGE_MULTIPLIERS, supports_damage_multipliers,
    )
    from core.cheats.map_skills.map_skills import CHEATS as MAP_SKILLS, supports_map_skills
    from core.cheats.quest_timers.quest_timers import CHEATS as QUEST_TIMERS, supports_quest_timers
    return {**dict.fromkeys((FLEX_OPTION, WHETSTONE_OPTION), supports_action_cancel),
            **dict.fromkeys(MAP_SKILLS, supports_map_skills), **dict.fromkeys(QUEST_TIMERS, supports_quest_timers),
            **dict.fromkeys(DAMAGE_MULTIPLIERS, supports_damage_multipliers),
            ASPECT_ROW: lambda code: supports_aspect_ratio(code, menu=False)}


def supports_mod_options(code: bytes) -> bool:
    """The application's update calls the timing update where the update's executable has the call, and the START
    menu has the words the page replaces."""
    from core.interface.mod_settings.mod_settings import supports_mod_settings
    return bl_target(code, FRAME_CALL) == FRAME_UPDATE and supports_mod_settings(code)


def available_options(code: bytes, settings: Any, console: bool = False, cheats_gate: bool = False) -> list[str]:
    """The options the player's game can change during play, in the order of OPTION_IDS: the edition's
    (gui_presets.json, `in_game`) and the page's own (page_only_options), the ones a 3DS can use when `console`, those
    of a feature the run has (FEATURE_ROWS) and those whose hooks the executable has. The Cheats group's only with the
    settings' `cheats_enabled`, or with `cheats_gate` (a 3DS title: the group always there, behind the launcher's flag,
    patch_mod_options)."""
    from core.app.presets import in_game_fields
    from core.app.settings import EMULATOR_ONLY
    with_cheats = cheats_gate or getattr(settings, "cheats_enabled", False)
    cheats = cheat_options() if with_cheats else []     # the Cheats group: only with them
    wanted = [key for key in (*in_game_fields(), *page_only_options(), *cheats)
              if not (console and key in EMULATOR_ONLY)
              and (key not in FEATURE_ROWS or getattr(settings, FEATURE_ROWS[key]))]
    return sorted((key for key in wanted if supports_option(code, key)), key=OPTION_IDS.__getitem__)


def patch_mod_options(code: bytes, settings: Any, available: list[str], layout: Layout | None = None,
                      aspect: bool = False, wheel: bool = False, cheats_gate: bool = False) -> bytes:
    """`code` (the update's executable) with the START menu's page for `available` options, each frame's read of them,
    and the hooks of those that need one. The Settings field of an option is its installed default. `aspect`: the
    aspect ratio's switch is on, so its row is in the page; `wheel`: the mod has the item wheel, so its Radial Menu
    row is (interface/radial_menu/radial_menu.py patches the wheel and its screens' data). With the box's option a
    run also gives every town area Change Appearance's layout (box_appearance.py: the lobby's ARC and, after the
    single-screen mode's patches, the stage lists).
    `cheats_gate` (a 3DS title): the Cheats group's rows of `available` and
    their hooks are there, but the page leaves the group out and their options are 0 until the launcher's flag file
    allows them, which the game reads once a launch through Heavenfall Beta's sidecars (save/beta_sidecar.c
    beta_cheats_flag: the run must also patch_beta_sidecar). Without it a mod is exactly as before: the group shows
    and acts when `available` has its rows. Refuses an executable where a site is not the game's word."""
    from core.interface.mod_settings.mod_settings import load_settings, patch_mod_settings
    if not supports_mod_options(code):
        raise CodeSpaceError("the options' sites are not the update's words: already patched or another game")
    layout = layout or load_layout()
    gated = [key for key in available if key in cheat_options()] if cheats_gate else []
    table = load_settings(available=available, aspect=aspect, wheel=wheel, gated=gated)
    out = bytearray(patch_mod_settings(code, layout, table, bool(getattr(settings, "single_screen", False))))
    layout.place(out, STUB)
    layout.place(out, DATA, options_data(settings, available, gated=gated))
    if gated:
        layout.reserve(out, CHEATS_ALLOWED)
    layout.place(out, RAW_TABLE, raw_table())
    layout.hook(out, FRAME_CALL, STUB, calls=FRAME_UPDATE)
    word = lambda value: value.to_bytes(4, "little")  # noqa: E731
    at = lambda label: layout.symbol(STUB, label)  # noqa: E731
    if "cheat_no_bloom_dof" in available:
        layout.hook(out, BLOOM_FILTER, at("mod_bloom"), original=word(BLOOM_ORIGINAL), link=False)
    if "cheat_fov" in available:
        layout.hook(out, FOV_RESET[0][0], at("mod_fov_reset"), original=word(FOV_RESET[0][1]), link=False)
        layout.hook(out, FOV_OTHER[0], at("mod_fov_other"), original=word(FOV_OTHER[1]), link=False)
    if "cheat_net_fix" in available:
        layout.hook(out, NET_WAITS[0], at("mod_net_waits"), original=word(NET_WAITS[1]), link=False)
        for (site, original), label in zip(NET_POLLS, ("mod_net_polls_a", "mod_net_polls_b")):
            layout.hook(out, site, at(label), original=word(original), link=False)
    if "cheat_raw_unbloat" in available:
        for (site, original), label in zip(RAW_SITES, ("mod_raw_a", "mod_raw_b")):
            layout.hook(out, site, at(label), original=word(original), link=False)
    if "camera_speed" in available:
        layout.hook(out, CAMERA_CAP[0], at("mod_camera_cap"), original=word(CAMERA_CAP[1]), link=False)
    if "camera_distance" in available:
        for (site, original), label in zip(CAMERA_DISTANCE, CAMERA_DISTANCE_STUBS):
            layout.hook(out, site, at(label), original=word(original), link=False)
    if "box_equipment" in available:
        layout.hook(out, BOX_KIND[0], at("mod_box_kind"), original=word(BOX_KIND[1]))
        layout.hook(out, BOX_LINES[0], at("mod_box_lines"), original=word(BOX_LINES[1]), link=False)
    if "honing_glow" in available:
        for site, original in HONING_SITES:
            layout.hook(out, site, at("mod_honing_glow"), original=word(original))
    from core.gameplay.fast_gathering.fast_gathering import patch_fast_gathering
    from core.gameplay.hold_a.hold_a import patch_hold_a
    from core.interface.fast_text.fast_text import patch_fast_text
    from core.interface.system_keyboard.system_keyboard import patch_system_keyboard
    from core.gameplay.death_camera_skip.death_camera_skip import patch_death_camera_skip
    from core.gameplay.modern_camera.modern_camera import patch_modern_camera
    from core.gameplay.intro_skip.intro_skip import patch_intro_skip
    for key, patch in (("hold_a", patch_hold_a), ("fast_text", patch_fast_text),
                       ("fast_gathering", patch_fast_gathering), ("system_keyboard", patch_system_keyboard),
                       ("skip_death_camera", patch_death_camera_skip), ("modern_camera", patch_modern_camera),
                       ("skip_monster_intro", patch_intro_skip)):
        if key in available:
            out = bytearray(patch(bytes(out), layout, gated=True))
    return patch_cheats_options(bytes(out), available, layout)


def patch_cheats_options(code: bytes, available: list[str], layout: Layout) -> bytes:
    """`code` with the hooks of the Cheats group's rows in `available` (a mod without `cheats_enabled` has none of them
    there): each cheat reads its row's number in OPTION_IDS (core/cheats/gates.py). The extra aspect ratio's row has
    no hook here: the aspect ratio's code reads it (cheats/aspect_ratio.py CHEAT_ROW)."""
    from core.cheats.action_cancel.action_cancel import FLEX_OPTION, NO_OPTION, WHETSTONE_OPTION, patch_action_cancel
    from core.cheats.damage_multipliers.damage_multipliers import patch_damage_multipliers
    from core.cheats.map_skills.map_skills import patch_map_skills
    from core.cheats.quest_timers.quest_timers import patch_quest_timers
    chosen = {key: OPTION_IDS[key] for key in available if key in OPTION_IDS}
    out = patch_map_skills(patch_quest_timers(code, chosen, layout), chosen, layout)
    out = patch_damage_multipliers(out, chosen, layout)
    if FLEX_OPTION in chosen or WHETSTONE_OPTION in chosen:
        out = patch_action_cancel(out, layout, (chosen.get(FLEX_OPTION, NO_OPTION),
                                                chosen.get(WHETSTONE_OPTION, NO_OPTION)))
    return out


__all__ = ["OPTION_IDS", "available_options", "cheat_options", "cheats_retry", "default_value", "gate_data",
           "load_options", "option_half", "options_data", "page_only_options", "patch_cheats_options",
           "patch_mod_options", "raw_table", "supports_mod_options", "supports_option"]
