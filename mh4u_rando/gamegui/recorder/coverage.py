"""Which screens are still to record, from the optional
`data/curated/game_gui/coverage.json`:

    {"screens": [{"id": "07", "name": "Cantina", "groups": ["ui???_..."], "any": ["..."], "without": ["..."]}]}

A screen counts as recorded when some recorded signature holds every group of `groups`, at least one of `any` (when
given) and none of `without` (root group labels, `#1` for a second instance). An entry names `groups`, `any` or both.
Its English name comes from names_en.json's `coverage`, beside it."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import ENGLISH_NAMES, load_english_names
from .settings import COVERAGE


@dataclass(frozen=True)
class CoverageScreen:
    id: str
    name: str
    groups: tuple[str, ...]
    without: tuple[str, ...] = field(default=())
    any: tuple[str, ...] = field(default=())
    name_en: str = ""

    def told_by(self, groups: set[str]) -> bool:
        return (set(self.groups) <= groups and not set(self.without) & groups
                and (not self.any or bool(set(self.any) & groups)))


def load_coverage(path: Path = COVERAGE) -> list[CoverageScreen]:
    """The screens to record; none when the file does not exist."""
    path = Path(path)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    english = load_english_names(path.parent / ENGLISH_NAMES)["coverage"]
    out = []
    for screen in data["screens"]:
        if not screen.get("groups") and not screen.get("any"):
            raise ValueError(f"{path}: screen {screen.get('id')!r} names no group")
        out.append(CoverageScreen(str(screen["id"]), screen["name"], tuple(screen.get("groups", ())),
                                  tuple(screen.get("without", ())), tuple(screen.get("any", ())),
                                  english.get(str(screen["id"]), "")))
    return out


def missing(screens: list[CoverageScreen], signatures: list[set[str]]) -> list[CoverageScreen]:
    return [screen for screen in screens if not any(screen.told_by(groups) for groups in signatures)]
