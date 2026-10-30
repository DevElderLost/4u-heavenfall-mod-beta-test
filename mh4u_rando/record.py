"""The record of a run, saved with its settings in settings_<seed>.json: randomizer version, fix revision, the
checksum of what the game plays and the history of fixes (mh4u_rando/fix.py).

The checksum covers the quests and the equipment tables. Two friends playing the same seed compare its short
code ("A1B2-C3D4"): equal codes mean the same quests, the same equipment and the same settings to fix them
later. Left out: the options each player chooses for themselves (`PERSONAL_FIELDS`) and the quest board
pictures, which depend on the new monster icons being in the mod (the update may be missing on one PC).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__
from .settings import Settings

if TYPE_CHECKING:
    from .mib import Quest

RECORD_KEY = "run"


@dataclass(frozen=True)
class Checksum:
    quests: str     # sha256 of the quest files, quest board pictures left out
    equipment: str  # sha256 of the equipment tables; "" when the equipment is not randomized (retail tables)
    code: str       # short code to compare by eye, "XXXX-XXXX"


@dataclass
class Revision:
    """One entry of the fix history."""
    revision: int
    date: str
    code: str
    changes: list[str] = field(default_factory=list)


@dataclass
class RunRecord:
    version: str = __version__  # randomizer version that made the run (for messages; the checksum is the proof)
    revision: int = 0           # 0: the original run; +1 per fix
    checksum: Checksum | None = None
    history: list[Revision] = field(default_factory=list)

    def to_dict(self) -> dict:
        values = {"version": self.version, "revision": self.revision}
        if self.checksum:
            values.update(checksum=self.checksum.code, quests_sha=self.checksum.quests,
                          equipment_sha=self.checksum.equipment)
        values["history"] = [vars(entry) for entry in self.history]
        return values

    @classmethod
    def from_dict(cls, values: dict) -> "RunRecord":
        checksum = None
        if values.get("checksum") and "quests_sha" in values:
            checksum = Checksum(str(values["quests_sha"]), str(values.get("equipment_sha", "")),
                                str(values["checksum"]))
        history = [Revision(int(entry["revision"]), str(entry.get("date", "")), str(entry.get("code", "")),
                            [str(change) for change in entry.get("changes", [])])
                   for entry in values.get("history", [])]
        return cls(str(values.get("version", "")), int(values.get("revision", 0)), checksum, history)


def quests_digest(quests: dict[str, Quest]) -> str:
    from .mib import write_mib
    digest = hashlib.sha256()
    for name in sorted(quests):
        quest = quests[name]
        pictures = quest.pictures
        quest.pictures = [0] * len(pictures)
        try:
            data = write_mib(quest)
        finally:
            quest.pictures = pictures
        digest.update(name.encode("utf-8") + len(data).to_bytes(4, "little") + data)
    return digest.hexdigest()


def compute_checksum(quests: dict[str, Quest], equipment_code: bytes | None, settings: Settings) -> Checksum:
    """`equipment_code`: the executable after randomize_equipment, None if the equipment is not randomized."""
    from .equipment import tables_digest
    quests_sha = quests_digest(quests)
    equipment_sha = tables_digest(equipment_code) if equipment_code is not None else ""
    combined = json.dumps({"quests": quests_sha, "equipment": equipment_sha, "settings": settings.checksum_dict()},
                          sort_keys=True)
    short = hashlib.sha256(combined.encode("utf-8")).hexdigest().upper()
    return Checksum(quests_sha, equipment_sha, f"{short[:4]}-{short[4:8]}")


def save_run(path: Path, settings: Settings, record: RunRecord) -> None:
    values = settings.to_dict()
    values[RECORD_KEY] = record.to_dict()
    Path(path).write_text(json.dumps(values, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_run(path: Path) -> tuple[Settings, RunRecord | None]:
    """The settings of a settings_<seed>.json (or any preset) and its record, None if it has none (presets and
    runs made before 0.2.0)."""
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    record = values.get(RECORD_KEY)
    return Settings.from_dict(values), RunRecord.from_dict(record) if isinstance(record, dict) else None
