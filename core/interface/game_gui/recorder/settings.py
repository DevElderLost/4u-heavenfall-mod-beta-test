"""The recorder's numbers (retries, timeouts, stability and blink windows), from
game/data/curated/game_gui/recorder.json."""

import json
from dataclasses import dataclass, fields
from pathlib import Path

from core.interface.game_gui.config import ARRANGEMENT_DIR as CURATED

SETTINGS = CURATED / "recorder.json"
COVERAGE = CURATED / "coverage.json"


@dataclass(frozen=True)
class RecorderSettings:
    frame_marks_variable: str       # the code space's variable holding the two u32 frame counters (started, done)
    copy_timeout_s: float           # how long one turn looks for a quiet window to copy in before giving up
    retry_sleep_s: float            # wait between two reads of the counters while looking for the window (0: none)
    tick_spin_s: float              # how long the probe check reads the counters in a row before it answers "not yet"
    window_measure_s: float         # a quiet window is measured (for the log) at most this long; 0 never measures
    no_pause_rest_s: float          # a window that finds no pause long enough for a copy rests this long
    copy_interval_s: float          # time between copies of one emulator window
    tick_window_s: float            # how long the counters may stay still before the recording probe counts as missing
    reconnect_interval_s: float     # time between looks for emulators and games
    rediscover_attempts: int        # copies in a row that may find the GUI moved before a turn is given up
    merge_gap: int                  # bytes between two copied pages below which one read takes both
    max_slots: int                  # a manager's group list longer than this is a misread
    max_panes_per_group: int        # a group's tree larger than this is a misread (a loop)
    stable_s: float                 # a screen (set of shown groups) is kept once it holds this long
    blink_window_s: float           # the window in which a group's shown changes are counted
    blink_toggles: int              # shown changes in that window that make a group blink (left out of signatures)
    max_variants: int               # variants kept per screen
    history_s: float                # how long checked copies are kept (compressed) to pair with the Ctrl+P pictures
    pair_max_age_s: float           # a picture pairs with a snapshot at most this much older
    picture_settle_s: float         # a new picture is read once its file is this old (the emulator still writing)
    picture_poll_s: float           # time between looks into the screenshot folder
    layout_language: str            # the layouts' language folder that names the groups (spa: the Spanish game's)


def load_settings(path: Path = SETTINGS, **overrides) -> RecorderSettings:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    names = {f.name for f in fields(RecorderSettings)}
    missing, unknown = names - set(data), set(data) - names
    if missing or unknown:
        raise ValueError(f"{path}: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return RecorderSettings(**{**data, **overrides})
