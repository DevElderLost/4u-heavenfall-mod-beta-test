"""The options a player changes during play (blocks `mod_options_stub`, `mod_options_data`, `mod_raw_table`, variable
`mod_options_state`, and the unit mod_options.c of `mod_settings_code`).

Each option has a list of values (curated mod_settings.json, `options`) and a byte of the character's save zone. A
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
  at the Hall's box) takes the option's count at a box away from home, so Manage Equipment and Equipment Sets are at
  every box, drawn, and Change Appearance stays at the house's;
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
    "cheat_raw_unbloat": 5, "touchless_target": 6, "hold_a": 7, "fast_text": 8, "fast_gathering": 9,
    "camera_speed": 10, "box_equipment": 11, "system_keyboard": 12, "skip_death_camera": 13, "damage_numbers": 14,
    "damage_numbers_other": 15, "damage_numbers_style": 16, "damage_numbers_size": 17, "damage_numbers_duration": 18,
    "modern_camera": 19,
    "horn_songs": 20,
    "skip_monster_intro": 21,
    "modern_camera_speed": 22, "modern_camera_acceleration": 23,
}
MAX_OPTIONS = 24                # the data block's room (mod_options.c MOD_OPTIONS; mod_options_state.values has 24)
MAX_VALUES = 16                 # a list of values: two pages
PAYLOAD_WORDS = 2               # what a value writes or hands to a hook
ZONE_FIRST_BYTE = 10            # option n's byte of the save zone is this + n (0 to 8: the item wheel's, 9: the ratio)
ZONE_BYTES = 48                 # the zone's size (curated mod_settings.json)
OPTION_SIZE = 4 + 2 * MAX_VALUES + 4 * PAYLOAD_WORDS * MAX_VALUES
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
BOX_KIND = (0x9EC870, 0xE5C46002)                       # FUN_009ec82c: strb r6, [r4, #0x2] (the box's kind)
BOX_LINES = (0x9EC8A4, 0xE5C4100A)                      # FUN_009ec82c: strb r1, [r4, #0xa] (the menu's lines)
CLASS_TABLE = 0xED24A0
CLASS_WORDS = (480, 140, 520, 230, 150, 130, 130, 330, 540, 230, 120, 140, 520, 310, 360, 170)


class ModOptionsError(ValueError):
    """The curated options are not what the code can hold."""


def _words(code: bytes | bytearray, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def load_options(path: Path = SETTINGS_FILE) -> list[dict]:
    """The curated options: {"key", "name", "help", "title", "values": [{"name", "setting", "payload": [u32, u32]}]},
    and "default" for an option of the page only, in the order of the file (the title is the name, for a row without
    one of its own). Refuses an option the code has no number for, a repeated one, a list of values that is empty or
    longer than MAX_VALUES, a value with more than PAYLOAD_WORDS numbers or both kinds of them, a default that is not
    one of its values' settings, and a text that is no menu text."""
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
        if "default" in entry:
            if not any(_same(value["setting"], entry["default"]) for value in values):
                raise ModOptionsError(f"mod_settings.json: {key}: its default is none of its values' settings")
            option["default"] = entry["default"]
        options.append(option)
    return options


def _same(a: Any, b: Any) -> bool:
    return a == b and type(a) is type(b)


def page_only_options(path: Path = SETTINGS_FILE) -> list[str]:
    """The options of the START menu's page only: a `default` of their own in the curated file, no Settings field and
    no installer choice; every edition's mod has them."""
    return [option["key"] for option in load_options(path) if "default" in option]


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


def options_data(settings: Any, available: set[str] | frozenset[str] | list[str], path: Path = SETTINGS_FILE) -> bytes:
    """The block `mod_options_data` (struct mod_options_data in mod_options.c): the save zone's place, magic and
    version, the value list's texts, and per option (MAX_OPTIONS of them, in the order of OPTION_IDS) its count of
    values (0: the mod does not have it), the default place, its byte of the zone, the name of each value, and what
    each value writes (PAYLOAD_WORDS words)."""
    from core.interface.mod_settings.mod_settings import load_zone

    zone, known = load_zone(path), message_indices()
    data = struct.pack("<I4sH3H", zone["offset"], zone["magic"], zone["version"], known["option_help"],
                       known["aspect_row"], known["aspect_marked"])
    by_id = {OPTION_IDS[option["key"]]: option for option in load_options(path) if option["key"] in available}
    for number in range(MAX_OPTIONS):
        option = by_id.get(number)
        if option is None:
            data += bytes(OPTION_SIZE)
            continue
        values = option["values"]
        names = [known[value["name"]] for value in values] + [0] * (MAX_VALUES - len(values))
        payload = [word for value in values for word in value["payload"]] + [0] * (
            PAYLOAD_WORDS * (MAX_VALUES - len(values)))
        data += struct.pack("<4B", len(values), default_value(option, settings), ZONE_FIRST_BYTE + number, 0)
        data += struct.pack(f"<{MAX_VALUES}H", *names) + struct.pack(f"<{PAYLOAD_WORDS * MAX_VALUES}I", *payload)
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
    if key == "box_equipment":
        return _static_ok(code, (BOX_KIND, BOX_LINES))
    from core.interface.system_keyboard.system_keyboard import supports_system_keyboard
    from core.gameplay.death_camera_skip.death_camera_skip import supports_death_camera_skip
    from core.gameplay.modern_camera.modern_camera import supports_modern_camera
    from core.gameplay.intro_skip.intro_skip import supports_intro_skip
    from core.interface.damage_numbers.damage_numbers import OPTIONS, supports_damage_numbers
    if key in OPTIONS:
        return supports_damage_numbers(code)
    if key == "horn_songs":
        from core.interface.horn_songs.horn_songs import supports_horn_songs
        return supports_horn_songs(code)
    checks = {"touchless_target": supports_target_switch, "hold_a": supports_hold_a, "fast_text": supports_fast_text,
              "fast_gathering": supports_fast_gathering, "system_keyboard": supports_system_keyboard,
              "skip_death_camera": supports_death_camera_skip, "modern_camera": supports_modern_camera,
              "modern_camera_speed": supports_modern_camera, "modern_camera_acceleration": supports_modern_camera,
              "skip_monster_intro": supports_intro_skip}
    return checks[key](code) if key in checks else True


def supports_mod_options(code: bytes) -> bool:
    """The application's update calls the timing update where the update's executable has the call, and the START
    menu has the words the page replaces."""
    from core.interface.mod_settings.mod_settings import supports_mod_settings
    return bl_target(code, FRAME_CALL) == FRAME_UPDATE and supports_mod_settings(code)


def available_options(code: bytes, settings: Any, console: bool = False) -> list[str]:
    """The options the player's game can change during play, in the order of OPTION_IDS: the edition's
    (gui_presets.json, `in_game`) and the page's own (page_only_options), the ones a 3DS can use when `console`, and
    those whose hooks the executable has."""
    from core.app.presets import in_game_fields
    from core.app.settings import EMULATOR_ONLY
    wanted = [key for key in (*in_game_fields(), *page_only_options()) if not (console and key in EMULATOR_ONLY)]
    return sorted((key for key in wanted if supports_option(code, key)), key=OPTION_IDS.__getitem__)


def patch_mod_options(code: bytes, settings: Any, available: list[str], layout: Layout | None = None,
                      aspect: bool = False) -> bytes:
    """`code` (the update's executable) with the START menu's page for `available` options, each frame's read of them,
    and the hooks of those that need one. The Settings field of an option is its installed default. `aspect`: the
    aspect ratio's switch is on, so its row is in the page. Refuses an executable where a site is not the game's
    word."""
    from core.interface.mod_settings.mod_settings import load_settings, patch_mod_settings
    if not supports_mod_options(code):
        raise CodeSpaceError("the options' sites are not the update's words: already patched or another game")
    layout = layout or load_layout()
    table = load_settings(available=available, aspect=aspect)
    out = bytearray(patch_mod_settings(code, layout, table, bool(getattr(settings, "single_screen", False))))
    layout.place(out, STUB)
    layout.place(out, DATA, options_data(settings, available))
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
    if "box_equipment" in available:
        layout.hook(out, BOX_KIND[0], at("mod_box_kind"), original=word(BOX_KIND[1]))
        layout.hook(out, BOX_LINES[0], at("mod_box_lines"), original=word(BOX_LINES[1]), link=False)
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
    return bytes(out)


__all__ = ["OPTION_IDS", "available_options", "default_value", "load_options", "options_data", "page_only_options",
           "patch_mod_options", "raw_table", "supports_mod_options", "supports_option"]
