"""Two small tables of the knowledge base, read without loading all of it (`load_game_data` also builds the monsters,
the maps and the routes): MH4U's item names and the stars of each Gathering Hall quest. Code that only needs these two
(the Wyporium's trades, layered equipment's rules) uses them, so it loads none of the rest."""

import json
from functools import cache

from core.game.data.paths import CURATED_DIR, GENERATED_DIR


@cache
def item_names() -> dict[int, str]:
    """MH4U's items by id (generated/items.json): the names `load_game_data().items` holds."""
    data = json.loads((GENERATED_DIR / "items.json").read_text(encoding="utf-8"))
    return {int(key): info["name"] for key, info in data.items()}


@cache
def quest_ranks() -> dict[int, int]:
    """Quest id -> its rank (1-3 low, 4-7 high, 8-10 G1-G3; curated/quest_rules.json), as `QuestInfo.rank`."""
    data = json.loads((CURATED_DIR / "quest_rules.json").read_text(encoding="utf-8"))
    return {int(key): info["rank"] for key, info in data["quests"].items()}
