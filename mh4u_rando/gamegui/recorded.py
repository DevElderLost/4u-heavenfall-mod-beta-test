"""The recorded screens of every recording session under work/ui, each screen once:
what the gallery, the checker and the commands of tools/ui.py read.

A session's index names each screen by the root groups it showed, minus the groups the session measured to blink; a
session learns which groups blink as it runs, so its early signatures may still hold some, and two sessions blink
different groups. Two recordings are **the same screen** when their groups agree once the groups either session
measured to blink are left out (never on no group at all); the screen keeps the latest recording's groups less every
group a session of the screen measured to blink, and its signature is `signature_id` of them. The recorder's own
signatures stay findable (`RecordedScreen.aliases`), as requests name them.

Only the sessions of one GUI mode count (store.Session.gui_mode): the game's own by default, which the pictures and the
checker arrange; the screens recorded while single-screen mode arranged the GUI are apart."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from .recorder.store import signature_id


@dataclass
class Recording:
    """One session's entry for a screen."""
    session: str
    signature: str                  # the recorder's
    groups: frozenset[str]          # as recorded, the session's blinking groups left out
    snapshots: list[Path]           # the first snapshot, then the variants'
    last: float
    variants: int = 0


@dataclass
class RecordedScreen:
    signature: str
    groups: list[str]
    snapshot: Path                  # the latest recording's first snapshot
    session: str                    # the latest recording's session
    last: float
    variants: int = 0               # over every recording
    recordings: list[Recording] = field(default_factory=list)

    @property
    def sessions(self) -> list[str]:
        return sorted({r.session for r in self.recordings} or {self.session})

    @property
    def aliases(self) -> set[str]:
        """Every name the screen goes by: its signature and the recorder's of each recording."""
        return {self.signature} | {r.signature for r in self.recordings}

    @property
    def snapshots(self) -> list[Path]:
        return [path for r in self.recordings for path in r.snapshots] or [self.snapshot]


def _recordings(root: Path, gui_mode: str) -> tuple[list[Recording], dict[str, frozenset[str]]]:
    recordings: list[Recording] = []
    blinking: dict[str, frozenset[str]] = {}
    for index in sorted((Path(root) / "recordings").glob("*/index.json")):
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("gui_mode", "normal") != gui_mode:
            continue
        session = index.parent.name
        blink = frozenset(data.get("blinking", []))
        blinking[session] = blink
        for signature, entry in data.get("signatures", {}).items():
            if not entry.get("snapshots"):
                continue
            files = [index.parent / name for name in entry["snapshots"]]
            files += [index.parent / v["file"] for v in entry.get("variants", []) if v.get("file")]
            recordings.append(Recording(session, signature, frozenset(entry.get("groups", [])) - blink, files,
                                        float(entry.get("last", 0.0)), len(entry.get("variants", []))))
    return recordings, blinking


def recorded_screens(root: Path, gui_mode: str = "normal") -> list[RecordedScreen]:
    """Every screen recorded under `root` (work/ui) in `gui_mode`, once (above), by signature."""
    recordings, blinking = _recordings(root, gui_mode)
    parent = list(range(len(recordings)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, one in enumerate(recordings):
        for j in range(i):
            other = recordings[j]
            out = blinking[one.session] | blinking[other.session]
            if one.groups - out and one.groups - out == other.groups - out:
                parent[find(i)] = find(j)
    classes: dict[int, list[Recording]] = {}
    for i, recording in enumerate(recordings):
        classes.setdefault(find(i), []).append(recording)
    out: list[RecordedScreen] = []
    for members in classes.values():
        latest = max(members, key=lambda r: r.last)
        groups = latest.groups - frozenset().union(*(blinking[r.session] for r in members)) or latest.groups
        out.append(RecordedScreen(signature_id(groups), sorted(groups), latest.snapshots[0], latest.session,
                                  latest.last, sum(r.variants for r in members), members))
    return sorted(out, key=lambda s: s.signature)


def find_recorded(screens: list[RecordedScreen], name: str) -> list[RecordedScreen]:
    """The recorded screens one of whose names (`aliases`) is, or starts with, `name`; an exact name wins."""
    exact = [s for s in screens if name in s.aliases]
    return exact or [s for s in screens if any(alias.startswith(name) for alias in s.aliases)]
