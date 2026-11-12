"""Damage Numbers: a number over the monster at each hit. The executable's side:
the hooks (damage_numbers_stub.s), the code (damage_numbers.c), its data and its state; the game files' side is
layout.py. The option is the START menu's (Mod Settings > Other > Damage Numbers: on or off, all damage, the
style, the size, the duration; core/interface/mod_settings), so every mod with that page carries it and a character's
choice acts at once.

These functions change, in the update's executable (canonical):

- FUN_00af52a0 (sMhMain::frame): its `ldr r0, [r4, #0x2bc]` after every system's move and before the render
  (FRAME_HOOK) goes through the stub, which runs the numbers' frame first;
- FUN_00be9c64 (a hit on a monster): its only call of FUN_00921f74, which adds the hit's final damage to the monster's
  damage of the frame (HIT_CALL), goes through the stub, which hands the difference it made to the code;
- FUN_00920104 (the monster's damage step): its call of FUN_009178e8, the blast (BLAST_CALL), and its two calls of
  FUN_0093ba30 that take a poison tick (POISON_CALL) and the mount's finish (MOUNT_CALL) off the monster's health;
- FUN_00c1017c (the quest's layouts' loader): its `mov r4, #0` right after the stage map's load (LOAD_HOOK) loads our
  layout too, and FUN_00c0f110 (frees the GUI layouts): its `mov r10, r1` (FREE_HOOK) frees it. The target face takes
  the instructions next to them (interface/hud/code_patch.py LOADER_HOOK, FREE_HOOK), so both can be in a mod.
Update's executable only; the version maps carry it to the base games.
"""

import json
import struct
from pathlib import Path
from typing import Any

from core.game.data.paths import CURATED_DIR
from core.game.executable.blocks import DAMAGE_NUMBERS_DATA_SIZE, GAME_SYMBOLS
from core.game.executable.code_space import BASE_ADDRESS, Layout, bl_target, load_layout
from core.game.files.gui.lyt import name_hash
from core.interface.damage_numbers.layout import EFFECTS, GROUP, atlas

TUNING_FILE = CURATED_DIR / "damage_numbers.json"
STUB, CODE, DATA, STATE = "damage_numbers_stub", "damage_numbers_code", "damage_numbers_data", "damage_numbers_state"
OPTIONS = ("damage_numbers", "damage_numbers_other", "damage_numbers_style", "damage_numbers_size",
           "damage_numbers_duration")
STYLES = ("wilds", "rise", "classic")   # the style option's values in order (curated mod_settings.json)
KINDS = ("hit", "poison", "blast", "mount", "other")    # damage_numbers.c KIND_*
MARKS = ("star", "star_core", "slash", "slash_core", "mark")    # the atlas' effects

# The hooks. (address, the word the game has, or the function the `bl` calls)
FRAME_HOOK, FRAME_WORD = 0xAF554C, bytes.fromhex("bc0294e5")   # FUN_00af52a0: ldr r0, [r4, #0x2bc]
HIT_CALL = 0xBEBE78             # FUN_00be9c64: bl FUN_00921f74 (monster_hit_damage)
BLAST_CALL = 0x920334           # FUN_00920104: bl FUN_009178e8 (blast_damage)
POISON_CALL = 0x9209F8          # FUN_00920104: bl FUN_0093ba30 (enemy_vital_add), the poison tick
MOUNT_CALL = 0x9211FC           # FUN_00920104: bl FUN_0093ba30, the mount's finish
LOAD_HOOK, LOAD_WORD = 0xC10434, bytes.fromhex("0040a0e3")    # FUN_00c1017c: mov r4, #0 (after the stage map)
FREE_HOOK, FREE_WORD = 0xC0F118, bytes.fromhex("01a0a0e1")    # FUN_00c0f110: mov r10, r1
WORDS = ((FRAME_HOOK, FRAME_WORD, "dmg_frame_hook"), (LOAD_HOOK, LOAD_WORD, "dmg_loader"),
         (FREE_HOOK, FREE_WORD, "dmg_free"))
CALLS = ((HIT_CALL, "monster_hit_damage", "dmg_hit_hook"), (BLAST_CALL, "blast_damage", "dmg_blast_hook"),
         (POISON_CALL, "enemy_vital_add", "dmg_poison_hook"), (MOUNT_CALL, "enemy_vital_add", "dmg_mount_hook"))


class DamageNumbersError(ValueError):
    """The curated tuning is not what the code can hold."""


def _value(raw: dict, key: str) -> Any:
    entry = raw.get(key)
    if not isinstance(entry, dict) or "value" not in entry or not isinstance(entry.get("description"), str):
        raise DamageNumbersError(f"damage_numbers.json: {key} must be {{\"value\": ..., \"description\": ...}}")
    return entry["value"]


def load_tuning(path: Path = TUNING_FILE) -> dict:
    """The curated tuning, checked: every key as its value; refuses a style or a mark the code does not have, more
    marks than a slot has sprites for, a colour that is not four bytes."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    keys = ("weak_hitzone", "colours", "digit_height", "frame_seconds", "pop", "rise", "fade_from", "stack", "edge",
            "monster_lift", "group", "shared_health_species", "styles")
    tuning = {key: _value(raw, key) for key in keys}
    colours = [*tuning["colours"].values()] + [e["colour"] for s in tuning["styles"].values() for e in s["effects"]]
    if set(tuning["colours"]) != {"white", "gold", "grey"} or any(
            len(c) != 4 or not all(0 <= x <= 255 for x in c) for c in colours):
        raise DamageNumbersError("damage_numbers.json: colours are white, gold and grey; every colour, a mark's too, "
                                 "is four bytes (RGBA)")
    if set(tuning["styles"]) != set(STYLES):
        raise DamageNumbersError(f"damage_numbers.json: styles must be {', '.join(STYLES)}")
    for style, entry in tuning["styles"].items():
        effects = entry["effects"]
        if len(effects) > EFFECTS or any(effect["mark"] not in MARKS for effect in effects):
            raise DamageNumbersError(f"damage_numbers.json: {style}: at most {EFFECTS} marks, of {', '.join(MARKS)}")
    if len(tuning["shared_health_species"]) > 4 or not 0 < tuning["fade_from"] < 1:
        raise DamageNumbersError("damage_numbers.json: at most 4 shared health species; fade_from between 0 and 1")
    return tuning


def _rgba(colour) -> int:
    return struct.unpack("<I", bytes(colour))[0]


def _cell(rect, size) -> tuple[float, float, float, float]:
    x, y, w, h = rect
    return x / size[0], y / size[1], w / size[0], h / size[1]


def data_block(tuning: dict | None = None) -> bytes:
    """The block damage_numbers_data (damage_numbers.c struct dmg_data)."""
    from core.interface.mod_settings.mod_options import OPTION_IDS
    tuning = tuning or load_tuning()
    art = atlas()
    size = art["size"]
    data = struct.pack("<4I", name_hash(GROUP), INDEX, tuning["group"]["layer"], tuning["group"]["priority"])
    data += struct.pack("<5I", *(OPTION_IDS[key] for key in OPTIONS))
    data += struct.pack("<i3I", tuning["weak_hitzone"],
                        *(_rgba(tuning["colours"][c]) for c in ("white", "gold", "grey")))
    pop, stack = tuning["pop"], tuning["stack"]
    data += struct.pack("<9fI2f", tuning["digit_height"], tuning["frame_seconds"], pop["seconds"], pop["scale"],
                        tuning["rise"], tuning["fade_from"], stack["radius"], stack["seconds"], stack["step"],
                        stack["max"], tuning["edge"], tuning["monster_lift"])
    shared = list(tuning["shared_health_species"]) + [0] * (4 - len(tuning["shared_health_species"]))
    data += struct.pack("<4B", *shared)
    for style in STYLES:
        entry, digits = tuning["styles"][style], art["styles"][style]["digits"]
        data += b"".join(struct.pack("<4f", *_cell(rect, size)) for rect in digits)
        cell_w, cell_h = digits[0][2], digits[0][3]
        data += struct.pack("<4f", cell_w / cell_h, 1.0, entry["advance"] * cell_w / cell_h, entry["weak_scale"])
        data += struct.pack("<I", len(entry["effects"]))
        for effect in entry["effects"] + [None] * (EFFECTS - len(entry["effects"])):
            if effect is None:
                data += bytes(48)
                continue
            data += struct.pack("<4f", *_cell(art["effects"][effect["mark"]], size))
            data += struct.pack("<7fI", *effect["anchor"], *effect["offset"], *effect["size"], effect["grow"],
                                _rgba(effect["colour"]))
    if len(data) != DAMAGE_NUMBERS_DATA_SIZE:
        raise DamageNumbersError(f"damage_numbers_data holds {DAMAGE_NUMBERS_DATA_SIZE} bytes, made {len(data)}")
    return data


INDEX = 0x5D0   # the group's slot in the GUI manager: free in every scene (the game: 20-721, 1526-1535; the target
                # face: 0x5C0-0x5C2); damage_numbers_stub.s INDEX


def _word(code: bytes | bytearray, at: int) -> bytes:
    return bytes(code[at - BASE_ADDRESS:at - BASE_ADDRESS + 4])


def supports_damage_numbers(code: bytes) -> bool:
    """`code` (the update's executable, canonical, not patched yet) has every instruction the hooks replace."""
    return (all(_word(code, site) == word for site, word, _ in WORDS)
            and all(bl_target(code, site) == GAME_SYMBOLS[callee] for site, callee, _ in CALLS))


def patch_damage_numbers(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (the update's executable) with Damage Numbers' blocks, its state and its hooks. Refuses an executable
    where a site is not the game's instruction."""
    layout = layout or load_layout()
    out = bytearray(code)
    for name in (STUB, CODE):
        layout.place(out, name)
    layout.place(out, DATA, data_block())
    layout.reserve(out, STATE)
    at = lambda label: layout.symbol(STUB, label)  # noqa: E731
    for site, word, label in WORDS:
        layout.hook(out, site, at(label), original=word)
    for site, callee, label in CALLS:
        layout.hook(out, site, at(label), calls=GAME_SYMBOLS[callee])
    return bytes(out)


__all__ = ["CALLS", "INDEX", "KINDS", "WORDS", "OPTIONS", "STYLES", "data_block", "load_tuning",
           "patch_damage_numbers", "supports_damage_numbers"]
