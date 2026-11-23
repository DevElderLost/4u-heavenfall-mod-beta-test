"""Backups of the save files: a *set* is a folder holding copies of some files and a
`manifest.json` (when, why, who made it, every file's container, name, SHA-256 and size). Every program write to a save
snapshots the files it replaces first (core/save/store.py), every install or update snapshots the hunters' files, and a
set restores through the store, which snapshots what the restore replaces.

Automatic sets (before an install, before a write) are pruned to the counts of curated/save_backups.json; manual sets
(the player's own) have their own count; the newest set and every pinned set are never pruned. Reads nothing outside the
folder it is given.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.save import files

CURATED_FILE = CURATED_DIR / "save_backups.json"
MANIFEST = "manifest.json"
JOURNAL = "journal.json"             # written by the store while it writes; its presence means an interrupted write
FILES_FOLDER = "files"


def curated(key: str, path: Path = CURATED_FILE):
    """The value of `key` in curated/save_backups.json."""
    return json.loads(path.read_text(encoding="utf-8"))[key]["value"]


def default_root() -> Path:
    """The program's backup folder (`~/.heavenfall/save_backups` in the main edition)."""
    from core.app.edition import edition
    return edition().home / "save_backups"


@dataclass(frozen=True)
class Entry:
    container: str
    name: str
    sha256: str
    size: int


@dataclass(frozen=True)
class BackupSet:
    path: Path
    time: float
    reason: str
    automatic: bool
    pinned: bool
    version: str
    edition: str
    source: str                  # the console folder the files came from ("" when unknown)
    files: tuple[Entry, ...]

    @property
    def id(self) -> str:
        return self.path.name

    def file_path(self, container: str, name: str) -> Path:
        return self.path / FILES_FOLDER / container / name

    def read(self, container: str, name: str) -> bytes | None:
        path = self.file_path(container, name)
        return path.read_bytes() if path.is_file() else None

    @property
    def has_journal(self) -> bool:
        return (self.path / JOURNAL).is_file()

    def digests(self) -> tuple:
        """What a set holds, to tell two sets alike: the source and each file's (container, name, hash)."""
        ordered = sorted(self.files, key=lambda e: (e.container, e.name))
        return self.source, tuple((e.container, e.name, e.sha256) for e in ordered)


def _write_json(path: Path, data: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _load(folder: Path) -> BackupSet | None:
    try:
        data = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
        return BackupSet(
            folder, float(data["time"]), str(data["reason"]), bool(data["automatic"]), bool(data.get("pinned", False)),
            str(data.get("version", "")), str(data.get("edition", "")), str(data.get("source", "")),
            tuple(Entry(f["container"], f["name"], f["sha256"], int(f["size"])) for f in data["files"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None                 # no manifest (a set that was being made) or a damaged one


def _manifest(found: BackupSet) -> dict:
    return {"time": found.time, "reason": found.reason, "automatic": found.automatic, "pinned": found.pinned,
            "version": found.version, "edition": found.edition, "source": found.source,
            "files": [{"container": e.container, "name": e.name, "sha256": e.sha256, "size": e.size}
                      for e in found.files]}


class BackupStore:
    """The sets under `root`. `root` is created by the first snapshot only (a program that backs up nothing leaves no
    folder). `limits` overrides the curated counts ({"automatic": n, "manual": n}); `version` and `edition_name`
    default to the program's."""

    def __init__(self, root: str | Path, limits: Mapping[str, int] | None = None, version: str | None = None,
                 edition_name: str | None = None):
        self.root = Path(root)
        self._limits = dict(limits) if limits is not None else None
        self._version, self._edition = version, edition_name

    def limits(self) -> dict[str, int]:
        if self._limits is not None:
            return self._limits
        return {"automatic": int(curated("automatic_sets")), "manual": int(curated("manual_sets"))}

    def _program(self) -> tuple[str, str]:
        if self._version is not None and self._edition is not None:
            return self._version, self._edition
        from core import __version__
        from core.app.edition import edition
        return (self._version if self._version is not None else __version__,
                self._edition if self._edition is not None else edition().name)

    # ---- listing -----------------------------------------------------------------------------------------------

    def sets(self) -> list[BackupSet]:
        """Every complete set, newest first."""
        if not self.root.is_dir():
            return []
        found = [s for s in (_load(p) for p in self.root.iterdir() if p.is_dir()) if s is not None]
        return sorted(found, key=lambda s: s.path.name, reverse=True)

    def get(self, set_id: str) -> BackupSet | None:
        return next((s for s in self.sets() if s.id == set_id), None)

    # ---- making a set ------------------------------------------------------------------------------------------

    def _new_folder(self, moment: float) -> Path:
        """A set folder that did not exist: the time to the second, then a counter above the sets of that second (two
        sets in a second differ and sort in the order made, also after a prune)."""
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(moment))
        cut = len(stamp) + 1
        taken = [int(p.name[cut:]) for p in self.root.glob(f"{stamp}-*") if p.name[cut:].isdigit()]
        for counter in range(max(taken, default=0) + 1, 1_000_000):     # past every one: the order by name holds
            folder = self.root / f"{stamp}-{counter:03d}"
            try:
                folder.mkdir()
            except FileExistsError:
                continue
            return folder
        raise OSError("no free backup folder name")

    def snapshot(self, files_: Iterable[tuple[str, str, Path]], reason: str, automatic: bool = False,
                 source: str = "") -> BackupSet:
        """Copy the files `(container, name, path)` (those that exist) into a new set. An automatic snapshot of the
        same files with the same bytes as the newest set makes no new set: that set is returned."""
        entries, data = [], []
        for container, name, path in files_:
            path = Path(path)
            if path.is_file():
                content = path.read_bytes()
                entries.append(Entry(container, name, hashlib.sha256(content).hexdigest(), len(content)))
                data.append(content)
        version, edition_name = self._program()
        moment = time.time()
        wanted = BackupSet(Path(), moment, reason, automatic, False, version, edition_name, source, tuple(entries))
        if automatic:
            newest = next(iter(self.sets()), None)
            if newest is not None and newest.digests() == wanted.digests():
                return newest
        folder = self._new_folder(moment)
        for entry, content in zip(entries, data):
            target = folder / FILES_FOLDER / entry.container / entry.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        made = replace(wanted, path=folder)
        _write_json(folder / MANIFEST, _manifest(made))        # last: a set without a manifest is not listed
        if automatic:
            self.prune()                                       # the retention applies after each automatic set
        return made

    # ---- pin, restore, prune -----------------------------------------------------------------------------------

    def pin(self, backup: BackupSet, pinned: bool = True) -> BackupSet:
        """Keep (or stop keeping) a set whatever the counts say."""
        changed = replace(backup, pinned=pinned)
        _write_json(backup.path / MANIFEST, _manifest(changed))
        return changed

    def restore(self, backup: BackupSet, store, containers: Iterable[str] | None = None) -> BackupSet | None:
        """Put the set's files back through `store.write_all`: what they replace is snapshotted first (the returned
        set; None when nothing was replaced). A file whose bytes no longer match the manifest stops the restore.
        `containers` limits what goes back; by default the main edition (its own save) restores Heavenfall's extdata
        only, never MH4U's own files, and Heavenfall Beta (which plays on them) restores every container of the set."""
        if containers is None:
            from core.app.edition import edition
            containers = (files.HEAVENFALL_EXTDATA,) if edition().own_save else files.CONTAINERS
        wanted = set(containers)
        changes: dict[tuple[str, str], bytes | None] = {}
        for entry in backup.files:
            if entry.container not in wanted:
                continue
            content = backup.read(entry.container, entry.name)
            if content is None or hashlib.sha256(content).hexdigest() != entry.sha256:
                raise ValueError(f"backup {backup.id}: {entry.container}/{entry.name} is missing or damaged")
            changes[(entry.container, entry.name)] = content
        return store.write_all(changes, f"restore {backup.id}", self)

    def holds(self, backup: BackupSet) -> tuple[str, ...]:
        """The containers a set holds files of, in the order of `files.CONTAINERS`."""
        return tuple(c for c in files.CONTAINERS if any(e.container == c for e in backup.files))

    def prune(self) -> list[BackupSet]:
        """Remove the sets beyond the limits: the newest set and the pinned ones stay, then the newest `automatic`
        automatic sets and the newest `manual` manual sets. A set with an unfinished write's journal stays too.
        Returns the sets removed."""
        everything = self.sets()
        limits = self.limits()
        keep = {s.id for s in everything[:1]}
        counts = {True: 0, False: 0}
        for found in everything:                    # newest first
            if found.pinned or found.has_journal:
                keep.add(found.id)
                continue
            counts[found.automatic] += 1
            if counts[found.automatic] <= limits["automatic" if found.automatic else "manual"]:
                keep.add(found.id)
        removed = [s for s in everything if s.id not in keep]
        for found in removed:
            shutil.rmtree(found.path, ignore_errors=True)
        return removed


# ---- the program's own snapshots ----------------------------------------------------------------------------------

def snapshot_saves(stores: Iterable, backups: BackupStore, reason: str, automatic: bool = True) -> list[BackupSet]:
    """Snapshot every hunter-related file of every store: the 14 names in each container that exists, the sidecars and
    the legacy files. One set per store holding something (an automatic one equal to the newest makes none)."""
    made = []
    for store in stores:
        if not store.found:
            continue
        wanted = [(container, name, store.path(container, name))
                  for container in files.CONTAINERS if store.has_container(container)
                  for name in files.hunter_names(container)]
        wanted = [item for item in wanted if item[2].is_file()]
        if wanted:
            made.append(backups.snapshot(wanted, reason, automatic, source=str(store.console)))
    return made


def snapshot_installed_saves(mod_folder: str | Path, backups: BackupStore | None = None,
                             reason: str = "before the mod was installed") -> list[BackupSet]:
    """The snapshot an install or an update takes: the saves of the emulator whose mod folder is `mod_folder`
    (`<emulator user folder>/load/mods/<title>`), in the region of its title. Nothing when the folder is not an
    emulator's mod folder of MH4U or the emulator has no saves yet. Raises on failure: the caller turns it into a
    notice, an install never stops for it."""
    from core.save.store import installed_store
    store = installed_store(mod_folder)
    if store is None:
        return []
    return snapshot_saves([store], backups or BackupStore(default_root()), reason)
