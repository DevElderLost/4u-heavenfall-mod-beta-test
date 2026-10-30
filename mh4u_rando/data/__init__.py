"""Game knowledge base: monsters, maps, items, quests and the rules that govern them.

Its names load `gamedata` (and through it the monster routes and the ported monsters' specs) on first use, so a
module that only imports `data.paths` or `data.tuning` loads none of it."""

__all__ = [
    "GEAR_CRAFTING_CATEGORIES", "LANGUAGES", "AreaInfo", "DropList", "GameData", "GameDataError", "ItemCategory",
    "ItemInfo", "LowTierGuarantee", "MapCategory", "MapInfo", "MonsterGrammar", "MonsterInfo", "PartGrammar",
    "QuestCategory", "QuestInfo", "SupplyRule", "load_game_data",
]


def __getattr__(name: str):
    if name in __all__:
        from . import gamedata
        return getattr(gamedata, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
