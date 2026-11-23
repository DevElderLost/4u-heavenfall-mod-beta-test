"""Item marks' lists and look (curated/item_marks.json): which items are rare, which are
upgrades and of what level, and the numbers the stars and the halo are drawn with.

Items are named in English; a name stands for every id that bears it: the game's own (generated/items.json), the
ported monsters' new items (ids from 0x791, interface of `equipment/ported_gear/curated.py`) and XX's rare materials
(from 0x900, `equipment/layered/xx_materials.py`), so a material defined twice (a ported monster's and XX's stand-in for
it) is marked under both. The two equipment modules are imported only when asked for: an edition without the ported
monsters resolves the rest.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from core.game.data.lookups import item_names
from core.game.data.paths import CURATED_DIR

TUNING_FILE = CURATED_DIR / "item_marks.json"
LEVELS = (1, 2)
ICON_SIZES = ("16", "24")
ENTRIES = ("rare", "upgrades", "star_size", "star_inset", "back_shift", "back_lift", "gold", "white", "glow",
           "halo_size", "halo_alpha", "cycle_seconds", "twinkle_places", "twinkle_sizes", "twinkle_life", "reserve")
STAR_COLOURS = ("gold", "white")    # the entries a value of Mod Settings' Star Colour may name (its `setting`)


class ItemMarksError(ValueError):
    pass


@dataclass(frozen=True)
class Upgrade:
    item: str
    base: str
    level: int


@dataclass(frozen=True)
class Marks:
    rare: tuple[str, ...]
    upgrades: tuple[Upgrade, ...]
    look: dict


def _rgb(value) -> bool:
    return isinstance(value, list) and len(value) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in value)


def _number(value, low: float, high: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high


def _check_look(look: dict) -> None:
    sizes = look["star_size"]
    if not isinstance(sizes, dict) or sorted(sizes) != list(ICON_SIZES) or \
            not all(isinstance(v, int) and 3 <= v <= 16 for v in sizes.values()):
        raise ItemMarksError("item_marks.json: star_size maps \"16\" and \"24\" to a side of 3-16 px")
    for key, low, high in (("star_inset", 0, 8), ("back_shift", 0, 1), ("back_lift", 0, 8), ("halo_size", 8, 32),
                           ("cycle_seconds", 0.2, 10), ("twinkle_life", 0.05, 1)):
        if not _number(look[key], low, high):
            raise ItemMarksError(f"item_marks.json: {key} is a number in [{low}, {high}]")
    for cell, side in sizes.items():
        width, height = stars_box(look, cell)
        if look["star_inset"] + max(width, height) > int(cell):
            raise ItemMarksError(f"item_marks.json: two stars of {side} px (star_inset, back_shift, back_lift) "
                                 f"leave a {cell}-px icon's square")
    for key in ("gold", "white", "glow"):
        if not _rgb(look[key]):
            raise ItemMarksError(f"item_marks.json: {key} is an RGB colour")
    alpha = look["halo_alpha"]
    if not (isinstance(alpha, list) and len(alpha) == 2 and all(_number(a, 0, 1) for a in alpha)
            and alpha[0] <= alpha[1]):
        raise ItemMarksError("item_marks.json: halo_alpha is [low, high] in [0, 1]")
    places = look["twinkle_places"]
    if not (isinstance(places, list) and places and all(isinstance(p, list) and len(p) == 2 and
                                                        all(_number(v, -8, 24) for v in p) for p in places)):
        raise ItemMarksError("item_marks.json: twinkle_places are [x, y] pairs")
    twinkles = look["twinkle_sizes"]
    if not (isinstance(twinkles, list) and twinkles and all(isinstance(s, int) and 3 <= s <= 16 for s in twinkles)):
        raise ItemMarksError("item_marks.json: twinkle_sizes are sides of 3-16 px")
    reserve = look["reserve"]
    if not (isinstance(reserve, dict) and sorted(reserve) == ["panes", "sprites"] and
            all(isinstance(v, int) and 0 <= v <= 8192 for v in reserve.values())):
        raise ItemMarksError("item_marks.json: reserve is {\"panes\": n, \"sprites\": n}, 0-8192 each")


def load_marks(path: Path = TUNING_FILE) -> Marks:
    """The curated lists and look, checked: every entry present as {"value", "description"}; levels 1 or 2, a level-2
    item's base a level-1 upgrade, no item both an upgrade and a base of level 1, nothing both rare and an upgrade."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    values = {}
    for key in ENTRIES:
        entry = raw.get(key)
        if not isinstance(entry, dict) or "value" not in entry or not isinstance(entry.get("description"), str):
            raise ItemMarksError(f"item_marks.json: {key} must be {{\"value\": ..., \"description\": ...}}")
        values[key] = entry["value"]
    rare = values.pop("rare")
    if not isinstance(rare, list) or not all(isinstance(name, str) and name for name in rare):
        raise ItemMarksError("item_marks.json: rare is a list of item names")
    upgrades = []
    for entry in values.pop("upgrades"):
        if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) for key in ("item", "base")):
            raise ItemMarksError("item_marks.json: an upgrade is {\"item\", \"base\", \"level\"}")
        if entry.get("level") not in LEVELS:
            raise ItemMarksError(f"item_marks.json: {entry['item']}: level is 1 or 2")
        upgrades.append(Upgrade(entry["item"], entry["base"], entry["level"]))
    level = {u.item: u.level for u in upgrades}
    for u in upgrades:
        if u.level == 1 and u.base in level:
            raise ItemMarksError(f"item_marks.json: {u.base} is both an upgrade and the base of a level 1 upgrade")
        if u.level == 2 and level.get(u.base) != 1:
            raise ItemMarksError(f"item_marks.json: {u.item}: a level 2 item's base must be a level 1 upgrade")
    both = sorted(set(rare) & set(level))
    if both:
        raise ItemMarksError(f"item_marks.json: rare and an upgrade: {', '.join(both)}")
    _check_look(values)
    return Marks(tuple(rare), tuple(upgrades), values)


def item_ids_by_name(ported: bool = True) -> dict[str, tuple[int, ...]]:
    """Every item name -> its ids, sorted: the game's items, XX's rare materials and, with `ported`, the ported
    monsters' items."""
    ids: dict[str, set[int]] = defaultdict(set)
    for item_id, name in item_names().items():
        ids[name].add(item_id)
    from core.equipment.layered.xx_materials import load_materials
    materials = load_materials()
    for item in materials.items + materials.retired:
        ids[item.name].add(materials.id(item))
    for name, item_id in materials.scrap_ids().items():
        ids[name].add(item_id)
    if ported:
        from core.equipment.ported_gear.curated import item_ids, load_curated
        for record in load_curated().values():
            record_ids = item_ids(record)
            for item in record.items:
                ids[item.name].add(record_ids[item.key])
    return {name: tuple(sorted(found)) for name, found in ids.items()}


def rare_ids(marks: Marks, ported: bool = True) -> tuple[int, ...]:
    """The rare items' ids, sorted (a name without an id in this edition is left out)."""
    ids = item_ids_by_name(ported)
    return tuple(sorted({i for name in marks.rare for i in ids.get(name, ())}))


def upgrade_levels(marks: Marks, ported: bool = True) -> dict[int, int]:
    """Each upgrade's id -> its number of stars, by id."""
    ids = item_ids_by_name(ported)
    levels = {i: u.level for u in marks.upgrades for i in ids.get(u.item, ())}
    return dict(sorted(levels.items()))


def back_shift(look: dict, cell: str) -> int:
    """Two stars: the back one's shift to the right in pixels on a `cell`-px icon ("16" or "24")."""
    return round(look["back_shift"] * look["star_size"][cell])


def stars_box(look: dict, cell: str) -> tuple[int, int]:
    """The width and height in pixels of two stars on a `cell`-px icon (one star's box is its side): the back one
    back_shift to the right and back_lift higher than the front one."""
    side = look["star_size"][cell]
    return side + back_shift(look, cell), side + look["back_lift"]


def star_colours(marks: Marks, settings: list[str]) -> list[list[int]]:
    """The upgrade stars' RGB for each value of Mod Settings' Star Colour, in its values' order: `settings` are the
    values' settings, each one of STAR_COLOURS."""
    unknown = [s for s in settings if s not in STAR_COLOURS]
    if unknown:
        raise ItemMarksError(f"Star Colour's values name no star colour ({', '.join(STAR_COLOURS)}): {unknown}")
    return [marks.look[s] for s in settings]


__all__ = ["ENTRIES", "ICON_SIZES", "ItemMarksError", "LEVELS", "Marks", "STAR_COLOURS", "TUNING_FILE", "Upgrade",
           "back_shift", "item_ids_by_name", "load_marks", "rare_ids", "star_colours", "stars_box", "upgrade_levels"]
