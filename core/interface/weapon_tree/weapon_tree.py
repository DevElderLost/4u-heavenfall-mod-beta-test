"""The Smithy's weapon tree (option smithy_view): the executable's side. The code
(weapon_tree.c), its data block (struct wt_data: the curated weapon_tree.json and the panes' name hashes of panes.py)
and its state; the game files' side (the panes, the words) is tree_layout.py.

The patch, on the update's executable (the version maps carry it to the base games):

* word 7 of the Smithy's state jump table (FUN_009ad59c, 0x9AD668), which the game never sets and points at the switch's
  end, runs weapon_tree_smithy_update: weapon_tree_update every frame of state 7;
* the `b 0x9ADC1C` of state 2's A on a weapon class (0x9ADCCC, after the class is stored) goes to weapon_tree_entry,
  which builds the tree and sets state 7 when it has a row; the forge's own entry runs on in every case;
* FUN_009bb1ac's first call (0x9BB1B4, the Smithy's end, also when it is closed by force) goes through
  weapon_tree_smithy_end, which hides the tree's groups first;
* Upgrade's `bl FUN_00a02048` on a box weapon (0x9BDC70) goes to weapon_tree_upgrade: the tree on that copy, or the
  game's list;
* the START menu's row Smithy View (`gated`) puts a gate in front of the two entries: with List the weapon class's
  branch goes to the forge's entry and Upgrade makes its own call, as the game does;
* places the blocks weapon_tree and weapon_tree_data, and reserves the variable weapon_tree_state.
"""

import json
import struct
from collections.abc import Mapping

from core.game.data.paths import CURATED_DIR
from core.game.executable.blocks import WEAPON_TREE_DATA_SIZE, WEAPON_TREE_STATE_SIZE
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, branch_word, load_layout
from core.game.files.gui.lyt import name_hash
from core.interface.weapon_tree import node_marks, panes
from core.interface.weapon_tree.tree_texts import CAPS_SOURCES, CHOICE, MAKESHOP_FILE, MESSAGE_BASE, message_index

CODE, DATA, STATE = "weapon_tree", "weapon_tree_data", "weapon_tree_state"
SETTINGS_PATH = CURATED_DIR / "weapon_tree.json"

# FUN_009ad59c, the Smithy: its state jump table (12 words; state 7's is the switch's end, as no code sets state 7) and
# state 2's A on a weapon class, `b 0x9ADC1C` once the class is stored (1)
SMITHY_STATES = 0x9AD668
TREE_STATE = 7
SMITHY_DONE = 0x9AE280
ENTRY = 0x9ADCCC
FORGE_JOIN = 0x9ADC1C
# FUN_009bb1ac, the Smithy's end (also when it is closed by force): its first call, bl FUN_0027ff58 (the stats panels
# released), goes through weapon_tree_smithy_end, which closes the tree first
SMITHY_END = 0x9BB1B4
PANELS_RELEASE = 0x27FF58
# FUN_009bdb58, Upgrade (the Smithy's state 8): A on a box weapon calls FUN_00a02048 for its upgrades; the call goes
# through weapon_tree_upgrade, which opens the tree on that copy instead when it takes it
UPGRADE_PICK = 0x9BDC70
UPGRADE_LIST = 0xA02048

# struct wt_data (weapon_tree.h)
MAGIC = 0x31525457                   # "WTR1"
DATA_HEAD = 260
CORNERS = 8 * len(node_marks.ELEMENTS)   # the head's last bytes: element_uv, each element icon's (u, v)
# the colours the code tints with (the layout's `fill` and `cost` are not)
COLOURS = ("band", "band_alt", "plate", "plate_lit", "plate_owned", "link", "link_lit", "worn", "cursor", "key_bar",
           "hint", "count", "arrow", "unpayable", "forge", "choice_on", "choice_off", "element", "element_hidden",
           "box", "price", "price_short")
REVEALS = ("all", "discovered")
STYLES = ("bracket", "frame")
HOLD_STEPS = 4
PULSE_KEYS = 3                       # the "NEW" marks' clip: its keys (frame, brightness); the last frame, its length
PULSE_STEPS = 4                      # struct wt_state.pulse: the clip's time in quarter frames, in a byte
BRIGHTNESS_MAX = 2.0                 # the GUI engine keeps a pane's brightness in 0 .. 2 (FUN_00ae7ed0, property 0x0C)
NAME_FILES = 27                     # LswordName: the first class's weapon names among the common files
# struct wt_state: its head, then 6 bytes for each id of a class (the game's most, 247, and the new weapons' room)
MAX_IDS = 336
STATE_HEAD = 94
WEAPON_SIZE = 6


class WeaponTreeError(ValueError):
    pass


def load_settings() -> dict:
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def _rgba(colour) -> int:
    values = list(colour) + [255] * (4 - len(colour))
    return struct.unpack("<I", bytes(values))[0]


def _byte(value: int, what: str) -> int:
    if not 0 <= value <= 0xFF:
        raise WeaponTreeError(f"{what} {value} does not fit a byte")
    return value


def element_corners(node: Mapping) -> bytes:
    """Each element icon's corner (u, v) in the marks' texture, as floats in node_marks.ELEMENTS' order: the code
    moves an element pane's region there, its size kept, so every icon must be the pane's size."""
    marks, pane = node["marks"], tuple(node["element"][2:])
    sizes = {name: tuple(marks[name]["size"]) for name in node_marks.ELEMENTS}
    if set(sizes.values()) != {pane}:
        raise WeaponTreeError(f"the element icons' sizes {sizes} are not the element pane's {pane}")
    return b"".join(struct.pack("<2f", *node_marks.region(marks, name)[:2]) for name in node_marks.ELEMENTS)


def pulse_keys(pulse: Mapping) -> bytes:
    """The "NEW" marks' clip (curated `new_pulse`) as struct wt_data.pulse: each key's frame and brightness, floats. The
    code joins the keys by straight lines and loops at the last key's frame; it keeps the time in a byte of quarter
    frames."""
    keys = [tuple(key) for key in pulse["keys"]]
    if len(keys) != PULSE_KEYS:
        raise WeaponTreeError(f"new_pulse has {len(keys)} keys, the code plays {PULSE_KEYS}")
    frames = [frame for frame, _ in keys]
    if frames[0] != 0 or any(b <= a for a, b in zip(frames, frames[1:])):
        raise WeaponTreeError(f"new_pulse's frames {frames} must start at 0 and grow")
    if PULSE_STEPS * frames[-1] > 0xFF:
        raise WeaponTreeError(f"new_pulse lasts {frames[-1]} frames, at most {0xFF // PULSE_STEPS}")
    if any(not 0 <= value <= BRIGHTNESS_MAX for _, value in keys):
        raise WeaponTreeError(f"new_pulse's brightness must stay within 0 .. {BRIGHTNESS_MAX}")
    return struct.pack(f"<{2 * PULSE_KEYS}f", *(value for key in keys for value in key))


def data_block(settings: Mapping | None = None, message_base: int = MESSAGE_BASE) -> bytes:
    """The block weapon_tree_data (weapon_tree.h struct wt_data). `message_base`: our first message of E_makeshop in
    the files written (tree_texts.message_base)."""
    settings = settings or load_settings()
    window, node, cursor = settings["window"], settings["node"], settings["cursor"]
    if not 0 < window["columns"] <= panes.MAX_COLUMNS or not 0 < window["rows"] <= panes.MAX_ROWS:
        raise WeaponTreeError(f"the window's {window['columns']} x {window['rows']} cells are more than the layout's "
                              f"{panes.MAX_COLUMNS} x {panes.MAX_ROWS}")
    hold = settings["hold"]
    if len(hold) > HOLD_STEPS:
        raise WeaponTreeError(f"{len(hold)} held steps, at most {HOLD_STEPS}")
    pack = _byte(settings["placing"]["pack"], "placing.pack")
    if not pack:
        raise WeaponTreeError("placing.pack must be at least 1")
    data = struct.pack("<I", MAGIC)
    data += bytes(_byte(settings["priority"][group], f"{group}'s priority") for group in panes.GROUPS)
    data += bytes((REVEALS.index(settings["reveal"]), window["columns"], window["rows"]))
    mix = settings["unpayable_mix"]
    if not 0 <= mix <= 100:
        raise WeaponTreeError(f"unpayable_mix {mix} is a percent")
    data += bytes((STYLES.index(cursor["style"]), pack, mix))
    data += struct.pack("<4H", *window["origin"], *window["pitch"])
    data += struct.pack("<2h2H", *node["icon"])
    (x0, y0), (x1, y1), width, height = cursor["bracket"]
    data += struct.pack("<4h2H", x0, y0, x1, y1, width, height)
    data += struct.pack("<2H", cursor["frame"]["pad"], cursor["frame"]["thickness"])
    data += pulse_keys(settings["new_pulse"])
    data += struct.pack(f"<{len(COLOURS)}I", *(_rgba(settings["colours"][name]) for name in COLOURS))
    steps = [value for step in hold for value in step] + [0] * (2 * (HOLD_STEPS - len(hold)))
    data += struct.pack(f"<{2 * HOLD_STEPS}H", *steps)
    data += struct.pack("<6H", message_index("count", message_base), message_index("hint_tree", message_base),
                        MAKESHOP_FILE, NAME_FILES, message_index(f"caps_{CAPS_SOURCES[0]:02x}", message_base),
                        message_index(CHOICE[0], message_base))
    data += element_corners(node)
    if len(data) != DATA_HEAD:
        raise WeaponTreeError(f"struct wt_data's head is {DATA_HEAD} bytes, made {len(data)}")
    names = panes.hash_names()
    data += struct.pack(f"<{len(names)}I", *(name_hash(name) for name in names))
    if len(data) != WEAPON_TREE_DATA_SIZE:
        raise WeaponTreeError(f"weapon_tree_data holds {WEAPON_TREE_DATA_SIZE} bytes, made {len(data)}")
    return data


def _word(code: bytes, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def supports_weapon_tree(code: bytes) -> bool:
    """`code` (the update's executable, canonical, not patched yet) has the Smithy's free state 7 and the entry's
    branch."""
    if len(code) < SMITHY_STATES + 4 * (TREE_STATE + 1) - BASE_ADDRESS:
        return False
    return (_word(code, SMITHY_STATES + 4 * TREE_STATE) == SMITHY_DONE
            and bytes(code[ENTRY - BASE_ADDRESS:ENTRY - BASE_ADDRESS + 4]) == branch_word(ENTRY, FORGE_JOIN)
            and bl_target(code, SMITHY_END) == PANELS_RELEASE and bl_target(code, UPGRADE_PICK) == UPGRADE_LIST)


def patch_weapon_tree(code: bytes, layout: Layout | None = None, message_base: int = MESSAGE_BASE,
                      settings: Mapping | None = None, gated: bool = False) -> bytes:
    """`code` with the weapon tree in the Smithy's Forge Weapons. `message_base`: our first message of E_makeshop in
    the files written (tree_texts.message_base). `gated`: the weapon class's branch and Upgrade's call go through the
    gates of the START menu's options (interface/mod_settings/mod_options_stub.s, Smithy View), which take the game's
    own lists while the option says List. Refuses an executable where a site is not the game's."""
    if not supports_weapon_tree(code):
        raise CodeSpaceError("unexpected code at the Smithy's states: the weapon tree needs the update's executable")
    if STATE_HEAD + WEAPON_SIZE * MAX_IDS != WEAPON_TREE_STATE_SIZE:
        raise WeaponTreeError("weapon_tree_state's size is not struct wt_state's")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, CODE)
    layout.place(out, DATA, data_block(settings, message_base))
    layout.reserve(out, STATE)
    struct.pack_into("<I", out, SMITHY_STATES + 4 * TREE_STATE - BASE_ADDRESS,
                     layout.symbol(CODE, "weapon_tree_smithy_update"))
    entry, upgrade = ((layout.symbol("mod_options_stub", gate) for gate in ("gate_smithy_view", "gate_smithy_upgrade"))
                      if gated else (layout.symbol(CODE, own) for own in ("weapon_tree_entry", "weapon_tree_upgrade")))
    layout.hook(out, ENTRY, entry, link=False, original=branch_word(ENTRY, FORGE_JOIN))
    layout.hook(out, SMITHY_END, layout.symbol(CODE, "weapon_tree_smithy_end"), calls=PANELS_RELEASE)
    layout.hook(out, UPGRADE_PICK, upgrade, calls=UPGRADE_LIST, link=False)
    return bytes(out)


__all__ = ["BRIGHTNESS_MAX", "CODE", "COLOURS", "CORNERS", "DATA", "DATA_HEAD", "ENTRY", "FORGE_JOIN", "MAGIC",
           "MAX_IDS", "NAME_FILES", "PANELS_RELEASE", "PULSE_KEYS", "PULSE_STEPS", "REVEALS", "SMITHY_DONE",
           "SMITHY_END", "SMITHY_STATES", "STATE", "STATE_HEAD", "STYLES", "TREE_STATE", "UPGRADE_LIST", "UPGRADE_PICK",
           "WEAPON_SIZE", "WeaponTreeError", "data_block", "element_corners", "load_settings", "patch_weapon_tree",
           "pulse_keys", "supports_weapon_tree"]
