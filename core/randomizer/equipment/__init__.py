"""Equipment randomizer: recipes, statistics and models, applied to the executable's tables (randomize.py).

Its names load `randomize` on first use (`__getattr__`), so the equipment catalog and the model lists, which layered
equipment reads too, load none of the randomizer."""

_NAMES = ("EquipmentReport", "EquipmentResult", "ExtraModels", "randomize_equipment", "write_equipment_json",
          "write_equipment_text")

__all__ = list(_NAMES)


def __getattr__(name: str):
    if name in _NAMES:
        from core.randomizer.equipment import randomize
        return getattr(randomize, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
