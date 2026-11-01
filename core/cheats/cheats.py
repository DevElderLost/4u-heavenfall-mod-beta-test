"""Cheats (options cheat_3d_mode, cheat_no_bloom_dof, cheat_fps, cheat_fov, cheat_net_fix, and the debug cheat
cheat_insta_kill): the players' Gateway / Citra cheat codes for the update (1.1), as executable
patches.

Static ones overwrite a word of the game: the bloom filter's first instruction (a `bx lr`), the three camera field
of view floats, and the three constants of the multiplayer node's waits. The ones the game rewrites (3D, frame rate,
the camera's field of view) are written every frame by the block `cheats` (cheats/cheats.s), which the
application's update calls first of all: for each entry of its table, when the object a variable holds exists, a
value goes at an offset of it. Insta kill sends two calls of the hunter's attack to the block `insta_kill`
(cheats/insta_kill.c), which multiplies and caps the weapon's attack. Every setting at its neutral value leaves the
executable as it was. Update's executable (the canonical one) only; carried to the base games by the version maps.
"""

import struct
from typing import Any

from core.app.presets import field_range
from core.game.data.tuning import tuning
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout

# Static sites: (address, the word the game has, the word the cheat writes).
BLOOM_FILTER = 0x2BC258        # FUN_002bc258(filter, pass), a slot of the bloom filter's vtable (0xE5E824)
BLOOM_ORIGINAL = 0xE92D4FF0    # push {r4-r11, lr}
BLOOM_RETURN = 0xE12FFF1E      # bx lr: the filter draws nothing

# The camera's field of view, in degrees: FUN_00c06a14 stores it at camera + 0x90 (0xC06DE8), and the reset of sCamera
# FUN_00bff28c (0xBFF664, and 0xBFF668 for the camera mode of state 8 / 1) loads it. Original: 50.0 (58.0 for the last).
FOV_SITES = ((0xC06DE8, 0x42480000), (0xBFF664, 0x42480000), (0xBFF668, 0x42680000))
GAME_FOV = 50                  # the game's own: cheat_fov at this value writes nothing

# The multiplayer node (UdsNode) waits: a frame counter that gives up at 120, and the polls of the node's state byte
# (10) after Participate and RegisterGathering. Original, cheat.
NET_SITES = ((0x533F40, 0xE3520078, 0xE3520EFA),    # cmp r2, #120    -> cmp r2, #4000
             (0x534B54, 0xE3A0000A, 0xE3A00FFA),    # mov r0, #10     -> mov r0, #1000
             (0x5356DC, 0xE3A0000A, 0xE3A00FFA))

# Per-frame: the application's update (FUN_00af52a0) calls the engine's timing update first (a bl, hooked)
FRAME_CALL = 0xAF52E4
FRAME_UPDATE = 0x644320

# The objects the block writes into, in the order of the block's `globals` table; the offsets and values written.
GLOBALS = ("gx_main", "game_main", "camera_control")
GX, MAIN, CAMERA = range(len(GLOBALS))
MAX_ENTRIES = 4                # the block's table (an end mark follows)
DISPLAY_MODE_OFFSET = 0x6BA8   # MtGX's object: the display mode word (the twin of +0x6BA4)
# 3D off, dithering off or on: 0x010F036E and 0x011F036E (written as bytes: as numbers they sit in the game's address
# range and tools/build/build_version_maps.py would take them for addresses)
DITHER_OFF_WORD = struct.unpack("<I", bytes.fromhex("6E030F01"))[0]
DITHER_ON_WORD = struct.unpack("<I", bytes.fromhex("6E031F01"))[0]
FRAME_RATE_OFFSET = 0x30       # the main object: the frame rate the limiter aims at
FOV_OFFSET = 0xED0             # sCamera + 0xE40 (the camera) + 0x90 (its field of view)

# Insta kill: FUN_002f8f34(table, hunter, stat, flag), a stat of the hunter's equipment (6: the weapon's attack), and
# the two calls that ask it for the attack: the hunter's attack in a hit (FUN_00b1ea88) and in the equipment's status
# screen (FUN_00af8b80). Both go to the block `insta_kill`, which calls it and multiplies the value.
HUNTER_GEAR_STAT = 0x2F8F34
ATTACK_CALLS = (0xB1EAC8, 0xAF8BB0)
INSTA_KILL, INSTA_KILL_DATA = "insta_kill", "insta_kill_data"

_DITHER_WORDS = {"dither_off": DITHER_OFF_WORD, "dither_on": DITHER_ON_WORD}


def float_bits(value: int | float) -> int:
    """The IEEE single of `value` (an angle, a frame rate), as the game keeps it."""
    return struct.unpack("<I", struct.pack("<f", value))[0]


def check_fov(degrees: int) -> None:
    low, high = field_range("cheat_fov")
    if not low <= degrees <= high:
        raise ValueError(f"cheat_fov {degrees} is outside {low}-{high} degrees")


def wants_cheats(settings: Any) -> bool:
    """Some cheat is not at its neutral value."""
    return bool(settings.cheat_3d_mode.value != "off" or settings.cheat_no_bloom_dof
                or settings.cheat_fps.value != "off" or settings.cheat_net_fix or settings.cheat_fov != GAME_FOV
                or settings.cheat_insta_kill)


def cheat_entries(settings: Any) -> list[tuple[int, int, int]]:
    """The per-frame writes of `settings`: (index into GLOBALS, offset, value), in a fixed order."""
    entries = []
    if settings.cheat_3d_mode.value != "off":
        entries.append((GX, DISPLAY_MODE_OFFSET, _DITHER_WORDS[settings.cheat_3d_mode.value]))
    if settings.cheat_fps.value != "off":
        entries.append((MAIN, FRAME_RATE_OFFSET, float_bits(settings.cheat_fps.rate)))
    if settings.cheat_fov != GAME_FOV:
        check_fov(settings.cheat_fov)
        entries.append((CAMERA, FOV_OFFSET, float_bits(settings.cheat_fov)))
    return entries


def _word(code: bytes | bytearray, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def supports_cheats(code: bytes) -> bool:
    """True if every site holds the word the game has (a site in a hole of a game version holds a trap word)."""
    return (_word(code, BLOOM_FILTER) == BLOOM_ORIGINAL
            and all(_word(code, at) == original for at, original in FOV_SITES)
            and all(_word(code, at) == original for at, original, _ in NET_SITES)
            and bl_target(code, FRAME_CALL) == FRAME_UPDATE
            and all(bl_target(code, at) == HUNTER_GEAR_STAT for at in ATTACK_CALLS))


def runner_data(layout: Layout, entries: list[tuple[int, int, int]]) -> bytes:
    """The block `cheats` with `entries` in its table (the rest keep their end marks)."""
    if len(entries) > MAX_ENTRIES:
        raise ValueError(f"at most {MAX_ENTRIES} per-frame writes")
    block = layout.block("cheats")
    data = bytearray(block.data)
    at = layout.symbol("cheats", "entries") - block.address
    for i, entry in enumerate(entries):
        struct.pack_into("<3I", data, at + 12 * i, *entry)
    return bytes(data)


def insta_kill_data() -> bytes:
    """The block `insta_kill_data`: the attack's multiplier and cap (curated tuning.json, section cheats)."""
    multiplier, cap = tuning("cheats", "insta_kill_attack_multiplier"), tuning("cheats", "insta_kill_attack_cap")
    if not (isinstance(multiplier, int) and isinstance(cap, int) and multiplier > 0 and 0 < cap < 0x8000):
        raise ValueError("tuning.json cheats: insta_kill_attack_multiplier must be a whole number above 0 and "
                         "insta_kill_attack_cap one from 1 to 32767")
    return struct.pack("<2i", multiplier, cap)


def patch_cheats(code: bytes, settings: Any, layout: Layout | None = None) -> bytes:
    """`code` (the update's executable) with the cheats `settings` turns on; `code` itself when none is."""
    if not wants_cheats(settings):
        return code
    if not supports_cheats(code):
        raise CodeSpaceError("unexpected code at the cheats' sites: they need the update's executable")
    out = bytearray(code)
    if settings.cheat_no_bloom_dof:
        struct.pack_into("<I", out, BLOOM_FILTER - BASE_ADDRESS, BLOOM_RETURN)
    if settings.cheat_fov != GAME_FOV:
        check_fov(settings.cheat_fov)
        for at, _ in FOV_SITES:
            struct.pack_into("<I", out, at - BASE_ADDRESS, float_bits(settings.cheat_fov))
    if settings.cheat_net_fix:
        for at, _, patched in NET_SITES:
            struct.pack_into("<I", out, at - BASE_ADDRESS, patched)
    if settings.cheat_insta_kill:
        layout = layout or load_layout()
        layout.place(out, INSTA_KILL)
        layout.place(out, INSTA_KILL_DATA, insta_kill_data())
        for at in ATTACK_CALLS:
            layout.hook(out, at, INSTA_KILL, calls=HUNTER_GEAR_STAT)
    entries = cheat_entries(settings)
    if entries:
        layout = layout or load_layout()
        layout.place(out, "cheats", runner_data(layout, entries))
        layout.hook(out, FRAME_CALL, "cheats", calls=FRAME_UPDATE)
    return bytes(out)
