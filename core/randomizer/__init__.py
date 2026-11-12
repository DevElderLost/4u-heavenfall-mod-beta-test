"""Quest randomization logic, independent of file formats and user interface.

Its names load their modules on first use (`__getattr__`), so a module that only imports a submodule of this package
(the equipment catalog, say) loads no part of the randomizer."""

_SETTINGS = ("ArmorSkillMode", "DuplicateMode", "FrenzyChance", "Frequency", "HudScale", "ModelMode",
             "PalicoModelMode", "ProgressionMode", "RewardSource", "Settings", "StatMode", "StructureMode",
             "SubQuestMode", "TextMode")
_WHERE = {
    **{name: "core.app.settings" for name in _SETTINGS},
    "RandomizerContext": "core.randomizer.quest_randomizer", "randomize_quest": "core.randomizer.quest_randomizer",
    "RandomizationError": "core.randomizer.quest_randomizer",
    "pool_data": "core.randomizer.randomize_all", "randomize_quests": "core.randomizer.randomize_all",
    "QuestReport": "core.randomizer.report", "unrandomized_quests": "core.randomizer.report",
    "write_spoiler_json": "core.randomizer.report", "write_spoiler_text": "core.randomizer.report",
    "validate_quest": "core.randomizer.validation",
}

__all__ = sorted(_WHERE)


def __getattr__(name: str):
    if name in _WHERE:
        import importlib
        return getattr(importlib.import_module(_WHERE[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
