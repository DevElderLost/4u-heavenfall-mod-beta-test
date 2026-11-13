"""Better Camera (code: modern_camera): the C-stick turns the camera and the aims analogically: in every direction, its
speed following the tilt, speeding up and slowing down smoothly (option modern_camera, a list of the START menu's Mod
Settings only, on by default, with Max Speed and Acceleration beside it).
The D-pad and the circle pad keep the game's turns.

These functions change, in the update's executable (canonical):

- FUN_00b3cc64 (the hunter's camera buttons from the D-pad and the C-stick): its call of the hunter's vtable + 0x98
  (STICK_CALL, `blx r2`: "is the C-stick tilted") goes to the block's `modern_camera_stick`, which answers what the
  vtable's function answers (the C-stick sets the game's buttons for every reader) and, when the game takes the C-stick
  for the camera (not while a gunner looks through the scope), keeps the stick's direction and length for it;
- FUN_00c009ac (the quest camera), FUN_00bfe11c and FUN_00c01608 (the special cameras): their call of FUN_00bfd028
  (sMhCamera::turnByInput, TURN_CALLS) goes to `modern_camera_turn`, which makes that call with the C-stick's buttons
  hidden and then turns the camera's angles by the kept stick (modern_camera.c);
- FUN_00b2041c (the hunter's aim, AIM_FRAME its stack's layout): its reads of the commands over the shoulder and the
  Bow's (AIM_COMMANDS, `ldr r0, [r2, #0x3e4]`) go to `aim_commands_hook`, which takes out the C-stick's command and
  turns the aim by the stick; its test of the scope's C-stick bits (AIM_SCOPE_TEST, `tst r0, #0x3c`) to
  `aim_scope_hook`, which hides them and turns the aim by the stick; its calls of FUN_00b1ea04 (AIM_VIEW_CALLS, the
  pitch's angle the aim shows, the bowguns' and the Bow's) to `modern_aim_view`, which makes it from the whole pitch.
Through the START menu's gates (`gated`: interface/mod_settings/mod_options_stub.s) each makes the game's own call while
the option is off. The tuning is curated modern_camera.json (the block modern_camera_data).

Update's executable only; the version maps carry it to the base games.
"""

import json
import struct
from pathlib import Path
from typing import Any

from core.game.data.paths import CURATED_DIR
from core.game.executable.blocks import MODERN_CAMERA_DATA_SIZE
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout

BLOCK, DATA, STATE = "modern_camera", "modern_camera_data", "modern_camera_state"
TUNING_FILE = CURATED_DIR / "modern_camera.json"
OPTION = "modern_camera"
SPEED_OPTION = "modern_camera_speed"            # Max Speed: its value (a float) multiplies every top speed
ACCELERATION_OPTION = "modern_camera_acceleration"   # Acceleration: its value divides every time constant

# The hooks
STICK_CALL = 0xB3CD80           # FUN_00b3cc64: blx r2 (the hunter's vtable + 0x98, "is the C-stick tilted")
STICK_WORD = bytes.fromhex("32ff2fe1")
TURN_BY_INPUT = 0xBFD028        # FUN_00bfd028 (sMhCamera::turnByInput)
TURN_CALLS = (
    0xBFE338,                   # FUN_00bfe11c (a special camera, its input at sMhCamera + 0xFC0): bl FUN_00bfd028
    0xC00AC0,                   # FUN_00c009ac (the quest camera, its input at sMhCamera + 0xE80)
    0xC01654,                   # FUN_00c01608 (a special camera, + 0xFC0; it reads the call's result)
)
# FUN_00b2041c(hunter, motion, mode, turn), the hunter's aim. Its prologue fixes the stack the hooks read (its yaw at
# sp + 0x18, mode and turn at sp + 0x5C, + 0x60): stmdb sp!, {r0-r11, lr}; vpush {d8-d10}; sub sp, sp, #0x3c
AIM_FRAME = ((0xB2041C, bytes.fromhex("ff4f2de9")), (0xB20428, bytes.fromhex("068b2ded")),
             (0xB2042C, bytes.fromhex("3cd04de2")))
AIM_COMMANDS = (
    0xB20570,                   # mode 0 (the bowguns) over the shoulder: ldr r0, [r2, #0x3e4]
    0xB207D8,                   # mode 3 (the Bow)
)
COMMANDS_WORD = bytes.fromhex("e40392e5")
AIM_SCOPE_TEST = 0xB20A74       # mode 0 through the scope: tst r0, #0x3c (the C-stick's direction bits)
SCOPE_TEST_WORD = bytes.fromhex("3c0010e3")
AIM_VIEW_CALLS = (
    0xB20E50,                   # mode 0: bl FUN_00b1ea04 (the pitch's angle, 45 degrees up and 30 down for 100 steps)
    0xB20D68,                   # mode 3 (the Bow: 60 degrees both ways)
)
AIM_PITCH_VIEW = 0xB1EA04

# Constants of the game's format, shared with modern_camera.c and its tests
UNITS_PER_TURN = 0x10000        # a u16 angle
TICKS_PER_SECOND = 60.0         # the camera's frame time (sMhCamera + 0xE2C) counts 1/60 s
PITCH_LIMIT = 0x3F00            # FUN_00bfd028's pitch limit, both ways
AIMS = ("shoulder", "scope", "bow")     # modern_camera.c enum aim
AIM_PITCH_SPAN = {"shoulder": 45.0, "scope": 45.0, "bow": 60.0}   # FUN_00b2041c: the degrees of 100 pitch steps up
AIM_RESPONSE = ("expo", "ramp_seconds")   # each aim's curve and ramp time, as the camera's
PITCH_STEPS_PER_SPAN = 100.0    # FUN_00b1ea04: the pitch in hundredths of its span


class ModernCameraError(ValueError):
    """The curated tuning is not what the code can hold."""


def _value(raw: dict, key: str) -> Any:
    entry = raw.get(key)
    if not isinstance(entry, dict) or "value" not in entry or not isinstance(entry.get("description"), str):
        raise ModernCameraError(f"modern_camera.json: {key} must be {{\"value\": ..., \"description\": ...}}")
    return entry["value"]


KEYS = ("dead_zone", "full_tilt", "expo", "yaw_degrees_per_second", "pitch_degrees_per_second", "ramp_seconds",
        "stop_degrees_per_second", "longest_frame_seconds", "direct", "aim_degrees_per_second",
        "aim_response")


def load_tuning(path: Path = TUNING_FILE) -> dict:
    """The curated tuning, checked: every key as its value. Refuses lengths outside 0-1 or a full tilt not past the dead
    zone, a curve outside 0-1, a speed or time below zero and an aim
    without its yaw and pitch speeds above 0 or without its own curve (0-1) and times (not below 0)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    tuning = {key: _value(raw, key) for key in KEYS}
    if not 0 <= tuning["dead_zone"] < tuning["full_tilt"] <= 1 or not 0 <= tuning["expo"] <= 1:
        raise ModernCameraError("modern_camera.json: 0 <= dead_zone < full_tilt <= 1 and 0 <= expo <= 1")
    if any(not tuning[key] > 0 for key in ("yaw_degrees_per_second", "pitch_degrees_per_second",
                                           "longest_frame_seconds")) or \
            any(tuning[key] < 0 for key in ("ramp_seconds", "stop_degrees_per_second")):
        raise ModernCameraError("modern_camera.json: speeds and the longest frame above 0, times and the stop not "
                                "below 0")
    aims = tuning["aim_degrees_per_second"]
    if not isinstance(aims, dict) or set(aims) != set(AIMS) or \
            any(not isinstance(aims[aim], dict) or set(aims[aim]) != {"yaw", "pitch"} or
                any(not isinstance(speed, (int, float)) or not speed > 0 for speed in aims[aim].values())
                for aim in AIMS):
        raise ModernCameraError(f"modern_camera.json: aim_degrees_per_second needs a yaw and a pitch above 0 for each "
                                f"of {AIMS}")
    responses = tuning["aim_response"]
    if not isinstance(responses, dict) or set(responses) != set(AIMS) or \
            any(not isinstance(responses[aim], dict) or set(responses[aim]) != set(AIM_RESPONSE) or
                any(not isinstance(value, (int, float)) or value < 0 for value in responses[aim].values()) or
                not responses[aim]["expo"] <= 1 for aim in AIMS):
        raise ModernCameraError(f"modern_camera.json: aim_response needs {AIM_RESPONSE} for each of {AIMS} (the curve "
                                "0 to 1, the times not below 0)")
    return tuning


def _units(degrees_per_second: float) -> float:
    """Angle units per 1/60 s."""
    return degrees_per_second * UNITS_PER_TURN / 360.0 / TICKS_PER_SECOND


def _pitch_steps(degrees_per_second: float, aim: str) -> float:
    """The aim's pitch steps (FUN_00b1e684's, 100 to its span up) per 1/60 s."""
    return degrees_per_second * PITCH_STEPS_PER_SPAN / AIM_PITCH_SPAN[aim] / TICKS_PER_SECOND


def data_block(tuning: dict | None = None) -> bytes:
    """The block modern_camera_data (modern_camera.c struct modern_camera_data)."""
    from core.interface.mod_settings.mod_options import OPTION_IDS
    tuning = tuning or load_tuning()
    data = struct.pack("<9f3I", tuning["dead_zone"], tuning["full_tilt"], tuning["expo"],
                       _units(tuning["yaw_degrees_per_second"]), _units(tuning["pitch_degrees_per_second"]),
                       tuning["ramp_seconds"] * TICKS_PER_SECOND, tuning["ramp_seconds"] * TICKS_PER_SECOND,
                       _units(tuning["stop_degrees_per_second"]), tuning["longest_frame_seconds"] * TICKS_PER_SECOND,
                       int(bool(tuning["direct"])), OPTION_IDS[SPEED_OPTION], OPTION_IDS[ACCELERATION_OPTION])
    aims, responses = tuning["aim_degrees_per_second"], tuning["aim_response"]
    for aim in AIMS:
        response = responses[aim]
        data += struct.pack("<6f", _units(aims[aim]["yaw"]), _pitch_steps(aims[aim]["pitch"], aim),
                            _pitch_steps(tuning["stop_degrees_per_second"], aim), response["expo"],
                            response["ramp_seconds"] * TICKS_PER_SECOND,
                            response["ramp_seconds"] * TICKS_PER_SECOND)
    if len(data) != MODERN_CAMERA_DATA_SIZE:
        raise ModernCameraError(f"modern_camera_data holds {MODERN_CAMERA_DATA_SIZE} bytes, made {len(data)}")
    return data


def _word(code: bytes, at: int) -> bytes:
    return bytes(code[at - BASE_ADDRESS:at - BASE_ADDRESS + 4])


def supports_modern_camera(code: bytes) -> bool:
    """True if the C-stick's question, the three calls and the aim's prologue, instructions and call are where the
    update's executable has them (not patched)."""
    try:
        return _word(code, STICK_CALL) == STICK_WORD and \
            all(bl_target(code, at) == TURN_BY_INPUT for at in TURN_CALLS) and \
            all(_word(code, at) == word for at, word in AIM_FRAME) and \
            all(_word(code, at) == COMMANDS_WORD for at in AIM_COMMANDS) and \
            _word(code, AIM_SCOPE_TEST) == SCOPE_TEST_WORD and \
            all(bl_target(code, at) == AIM_PITCH_VIEW for at in AIM_VIEW_CALLS)
    except (struct.error, IndexError, ValueError):
        return False


def patch_modern_camera(code: bytes, layout: Layout | None = None, gated: bool = False) -> bytes:
    """`code` (the update's executable) where the C-stick turns the camera analogically. `gated`: the hooks go through
    the gates of the START menu's options (interface/mod_settings/mod_options_stub.s), which make the game's own calls
    while the option is off."""
    if not supports_modern_camera(code):
        raise CodeSpaceError(f"modern camera: the C-stick's call at {STICK_CALL:#x}, a call of FUN_00bfd028 or the "
                             "aim's FUN_00b2041c is not the update's (another executable, or already patched)")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, BLOCK)
    layout.place(out, DATA, data_block())
    layout.reserve(out, STATE)
    stub = "mod_options_stub"

    def entry(gate: str, block: str) -> int:
        return layout.symbol(stub, gate) if gated else layout.symbol(BLOCK, block)

    layout.hook(out, STICK_CALL, entry("gate_modern_stick", "modern_camera_stick"), original=STICK_WORD)
    for at in TURN_CALLS:
        layout.hook(out, at, entry("gate_modern_turn", "modern_camera_turn"), calls=TURN_BY_INPUT)
    for at in AIM_COMMANDS:
        layout.hook(out, at, entry("gate_aim_commands", "aim_commands_hook"), original=COMMANDS_WORD)
    layout.hook(out, AIM_SCOPE_TEST, entry("gate_aim_scope", "aim_scope_hook"), original=SCOPE_TEST_WORD)
    for at in AIM_VIEW_CALLS:
        layout.hook(out, at, entry("gate_aim_view", "modern_aim_view"), calls=AIM_PITCH_VIEW)
    return bytes(out)
