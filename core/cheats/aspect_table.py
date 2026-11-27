"""The aspect ratios the emulator's picture can have, read from the curated aspect_ratio.json. On their own so that the
settings can read them without the patch (cheats/aspect_ratio.py)."""

import json
from dataclasses import dataclass
from pathlib import Path

from core.game.data.paths import CURATED_DIR

SETTINGS_FILE = CURATED_DIR / "aspect_ratio.json"
OFF = "off"                 # the option's value without hooks; no ratio can have this name
GAME_WIDTH, GAME_HEIGHT = 400, 240      # the game's frame, the ratio that changes nothing


class AspectTableError(ValueError):
    """The curated aspect_ratio.json is not what the mod can use."""


@dataclass(frozen=True)
class Ratio:
    name: str
    width: int
    height: int

    def factors(self) -> tuple[float, float, float]:
        """What the frame's shape asks of the game: the multiplier of a 3D view's aspect (ratio / 5:3), and the width
        and the height of the 2D interface's units (one of them is 1: the interface fits inside, undistorted)."""
        view = self.width * GAME_HEIGHT / (self.height * GAME_WIDTH)
        return view, max(1.0, view), max(1.0, 1.0 / view)


def interface_size(name: str) -> tuple[float, float]:
    """The width and the height of the interface's units (Ratio.factors) of the option's value `name`: 1, 1 for OFF."""
    for ratio in load_ratios():
        if ratio.name == name:
            return ratio.factors()[1:]
    return 1.0, 1.0


# The list in the game has the frame's own shape first: the option's OFF
GAME_RATIO = Ratio("5:3", 5, 3)


def menu_ratios() -> tuple[Ratio, ...]:
    """The rows of the list in the game (interface/mod_settings), in its order: the byte a character saves counts on it.
    """
    return GAME_RATIO, *load_ratios()


def ratio_text(ratio: Ratio) -> str:
    """The key of the ratio's name in the menu's texts (curated mod_settings.json)."""
    return "aspect_" + ratio.name.replace(":", "_")


def _ratio(entry: object, taken: tuple[str, ...]) -> Ratio:
    """A ratio of the curated file: a name of its own (not one of `taken`, never OFF) and whole sides above 0."""
    entry = entry if isinstance(entry, dict) else {}
    name, width, height = (entry.get(key) for key in ("name", "width", "height"))
    if not isinstance(name, str) or not name or name == OFF or name in taken:
        raise AspectTableError(f"aspect_ratio.json: {name!r} cannot name a ratio: each has a name of its own, "
                               f"never {OFF!r}")
    if not all(isinstance(side, int) and not isinstance(side, bool) and side > 0 for side in (width, height)):
        raise AspectTableError(f"aspect_ratio.json: {name}: width and height must be whole numbers above 0")
    return Ratio(name, width, height)


def load_ratios(path: Path = SETTINGS_FILE) -> tuple[Ratio, ...]:
    """The curated ratios, in the program's order. Refuses no ratios, a name repeated or named OFF, and a width or
    height that is not a whole number above 0."""
    raw = json.loads(Path(path).read_text(encoding="utf-8")).get("ratios")
    entries = raw.get("value") if isinstance(raw, dict) else None
    if not isinstance(entries, list) or not entries:
        raise AspectTableError("aspect_ratio.json: ratios must list at least one ratio")
    ratios: list[Ratio] = []
    for entry in entries:
        ratios.append(_ratio(entry, tuple(ratio.name for ratio in ratios)))
    return tuple(ratios)


def cheat_ratio(path: Path = SETTINGS_FILE) -> Ratio:
    """The ratio of the Cheats group's row (curated `cheat_ratio`; aspect_ratio.py CHEAT_ROW): in no list. Refuses a
    file without it, and a name the list (or the game's own shape) already has."""
    raw = json.loads(Path(path).read_text(encoding="utf-8")).get("cheat_ratio")
    if not isinstance(raw, dict) or "value" not in raw:
        raise AspectTableError("aspect_ratio.json: cheat_ratio must name the Cheats group's ratio")
    taken = (GAME_RATIO.name, *(ratio.name for ratio in load_ratios(path)))
    return _ratio(raw["value"], taken)
