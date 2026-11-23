"""The extra songs' volumes: Monster Hunter World's tracks (music/mhw/music.py) and the
theme of every ported monster (monsters/porting/product.py, spec.theme_volume_key), in percent in VOLUMES_FILE. The
developer's levels, edited by hand, never a player option."""

from __future__ import annotations

import json
import math
from pathlib import Path

# At the checkout's top, to edit by hand: {song: percent}, keys starting with "_" are notes
VOLUMES_FILE = Path(__file__).resolve().parents[3] / "extra_ost_volumes.json"
MAX_PERCENT = 400


def volumes() -> dict[str, float]:
    """{song: percent} from VOLUMES_FILE."""
    return {k: v for k, v in json.loads(VOLUMES_FILE.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def percent_db(percent: float) -> float:
    """A volume in percent (100: the game's full level) as the queue's offset in dB (strq.volume)."""
    if not 0 < percent <= MAX_PERCENT:
        raise ValueError(f"{VOLUMES_FILE.name}: {percent} % is not in (0, {MAX_PERCENT}]")
    return 20 * math.log10(percent / 100)
