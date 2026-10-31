"""Save states (`.cst`) as snapshots: a state is frozen, so its copy is
exact by nature (proof "save_state"); it passes the same checks as a live copy and its screen is kept at once (no
stability to wait for, no blink to measure). The installed mod and the language are left unknown: the state may come
from another install."""

import os
from pathlib import Path

from core.interface.game_gui.savestate import NotAState, StateMemory, load_state
from core.interface.game_gui.snapshot import Proof, Snapshot, Source
from core.interface.game_gui.recorder import checks
from core.interface.game_gui.recorder import reader as default_reader
from core.interface.game_gui.recorder.screens import variant_key
from core.interface.game_gui.recorder.store import Session


def state_snapshot(path: Path, candidates, layouts, reader=default_reader, max_slots: int = 8192,
                   max_panes: int = 4096) -> tuple[Snapshot | None, str]:
    """(the snapshot, "") of the save state `path`, or (None, why it is not kept). `layouts(title)` gives the
    LayoutIndex for a version's title."""
    try:
        memory = StateMemory.detect(load_state(path), candidates)
    except (NotAState, OSError) as error:
        return None, f"not read: {error}"
    try:
        managers = reader.read_gui(memory, max_slots, max_panes)
    except (ValueError, LookupError) as error:
        return None, f"not read: {error}"
    title = getattr(memory.version, "title_id", None)
    result = checks.check(managers, layouts(title))
    if not result["ok"]:
        return None, "failed the checks: " + "; ".join(result["failures"][:3])
    snapshot = Snapshot(Source("state", path=str(Path(path).resolve())), os.path.getmtime(path), Proof("save_state"),
                        reader.NAME, managers, getattr(memory.version, "key", None), None, None, result)
    return snapshot, ""


def import_states(paths, session: Session, candidates, layouts, reader=default_reader, max_slots: int = 8192,
                  max_panes: int = 4096) -> list[tuple[Path, str | None, str]]:
    """Each state's (path, its screen's signature or None, why not kept); the kept ones are in `session`."""
    out = []
    for path in paths:
        snapshot, reason = state_snapshot(Path(path), candidates, layouts, reader, max_slots, max_panes)
        if snapshot is None:
            out.append((Path(path), None, reason))
            continue
        groups = set(snapshot.shown())
        out.append((Path(path), session.add_screen(groups, snapshot, None, variant_key(snapshot, groups)), ""))
    return out
