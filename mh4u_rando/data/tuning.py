"""Tunable parameters of the randomizer (curated/tuning.json).

Every arbitrary probability lives in that file with its description, so it
can be changed without touching code: `tuning("equipment", "progressive_sigma")`.
"""

import json
from functools import cache
from pathlib import Path

TUNING_PATH = Path(__file__).resolve().parent / "curated" / "tuning.json"


@cache
def load_tuning(path: Path = TUNING_PATH) -> dict[str, dict[str, object]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    values: dict[str, dict[str, object]] = {}
    for section, entries in raw.items():
        if section == "description":
            continue
        values[section] = {}
        for name, entry in entries.items():
            if set(entry) != {"value", "description"} or not entry["description"]:
                raise ValueError(f"tuning {section}.{name}: needs a value and a description")
            values[section][name] = entry["value"]
    return values


def tuning(section: str, name: str):
    return load_tuning()[section][name]


def weights(section: str, name: str) -> dict[int, float]:
    """A {"number": weight} parameter with integer keys."""
    return {int(k): float(v) for k, v in tuning(section, name).items()}
