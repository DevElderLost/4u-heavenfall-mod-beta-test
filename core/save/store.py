"""An emulator's save files: the three containers of one region
under an emulator's user folder, read and written through one object.

    <user folder>/sdmc/Nintendo 3DS/<id0>/<id1>/                        the console folder
        title/00040000/<title low>/data/00000001                        MH4U's save archive
        extdata/00000000/<id>/user                                      MH4U's extdata, Heavenfall's own extdata

Every write goes through `write_all`: the files it replaces or deletes are snapshotted first (core/save/backup.py),
each file is written to a temporary name beside it and moved over the old one, and a journal in the snapshot's folder
says what was being written (and the hash of every file it writes), so an interrupted write (a crash, a power cut) is
rolled back by `recover()` the next time a store is opened and no emulator runs: only the files that still hold what
the write left are put back, anything the game saved since stays. A store never creates a container folder by itself:
`create_container` does, from a source folder copied whole (a half-made extdata would make the game format it).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from core.save import files
from core.save.backup import JOURNAL, BackupSet, BackupStore, curated

TEMPORARY = ".hftmp"                # the suffix of a file being written
LIST_UNREADABLE = "an emulator (the list of running programs could not be read)"


class SaveStoreError(Exception):
    pass


class NoSaveFolder(SaveStoreError, FileNotFoundError):
    """The emulator has no console folder for the game yet."""


class ContainerMissing(SaveStoreError, FileNotFoundError):
    """A write wants a container folder that does not exist (the game has not made it; `create_container` copies
    one)."""


def _safe_name(name: str) -> str:
    if not name or name != Path(name).name or name.startswith(".") or name.endswith(TEMPORARY):
        raise ValueError(f"not a save file name: {name!r}")
    return name


class SaveStore:
    """The save files of `region` under the emulator user folder `user_folder`. `backups` (a BackupStore) rolls back an
    interrupted write when the store is opened and is used by `write_all` when it is not given one. `running` (default
    `running_emulators`) lists the emulators running: while one runs nothing is recovered (the tests' hook)."""

    def __init__(self, user_folder: str | Path, region: str, name: str = "", backups: BackupStore | None = None,
                 running: Callable[[], list[str]] | None = None):
        self.user_folder = Path(user_folder)
        self._running = running or running_emulators
        self.region = region
        self.name = name or self.user_folder.name
        self.backups = backups
        self.console, self.problem = self._find()
        if backups is not None and self.console is not None:
            self.recover()

    # ---- where ---------------------------------------------------------------------------------------------------

    def _find(self) -> tuple[Path | None, str]:
        root = self.user_folder / "sdmc" / "Nintendo 3DS"
        if not root.is_dir():
            return None, f"{self.user_folder} has no SD card folder yet (sdmc/Nintendo 3DS): start the emulator once"
        candidates = [p for p in sorted(root.glob("*/*")) if p.is_dir()]
        if not candidates:
            return None, f"{root} has no console folder yet: start the game once"
        best, best_score = None, 0
        for folder in candidates:
            score = sum((folder / files.container_path(c, self.region)).is_dir() for c in files.CONTAINERS)
            if score > best_score:
                best, best_score = folder, score
        if best is None:
            return None, f"{root} holds no MH4U save of region {self.region}: start the game once"
        return best, ""

    @property
    def found(self) -> bool:
        return self.console is not None

    def require(self) -> Path:
        """The console folder; NoSaveFolder (with the reason) when there is none."""
        if self.console is None:
            raise NoSaveFolder(self.problem)
        return self.console

    def folder(self, container: str) -> Path | None:
        """Where `container` is (or would be) — None when the store has no console folder."""
        if self.console is None:
            return None
        return self.console / files.container_path(container, self.region)

    def has_container(self, container: str) -> bool:
        folder = self.folder(container)
        return folder is not None and folder.is_dir()

    def containers(self) -> list[str]:
        return [c for c in files.CONTAINERS if self.has_container(c)]

    def path(self, container: str, name: str) -> Path:
        folder = self.folder(container)
        if folder is None:
            raise NoSaveFolder(self.problem)
        return folder / _safe_name(name)

    # ---- reading -------------------------------------------------------------------------------------------------

    def exists(self, container: str, name: str) -> bool:
        return self.found and self.path(container, name).is_file()

    def read(self, container: str, name: str) -> bytes | None:
        return self.path(container, name).read_bytes() if self.exists(container, name) else None

    def list(self, container: str) -> list[str]:
        folder = self.folder(container)
        if folder is None or not folder.is_dir():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_file() and not p.name.endswith(TEMPORARY))

    # ---- writing -------------------------------------------------------------------------------------------------

    def write_all(self, changes: Mapping[tuple[str, str], bytes | None], reason: str,
                  backups: BackupStore | None = None) -> BackupSet | None:
        """Write (bytes) or delete (None) every `(container, name)` of `changes`. The files it replaces or deletes are
        snapshotted first; the returned set is that snapshot (None when nothing changed). A failure rolls the files
        already written back and raises; a crash leaves the journal for `recover`. Raises ContainerMissing, before any
        write, when a container to write into is missing."""
        backups = backups or self.backups
        if backups is None:
            raise ValueError("write_all needs a BackupStore (given, or the store's own)")
        plan: list[tuple[str, str, Path, bytes | None, bool]] = []
        for (container, name), data in changes.items():
            folder = self.folder(container)
            if data is not None and (folder is None or not folder.is_dir()):
                raise ContainerMissing(f"{container} does not exist under {self.console or self.user_folder}")
            if folder is None or not folder.is_dir():
                continue
            target = folder / _safe_name(name)
            existed = target.is_file()
            if data is None and not existed:
                continue
            plan.append((container, name, target, data, existed))
        if not plan:
            return None
        saved = backups.snapshot([(c, n, t) for c, n, t, _, existed in plan if existed], reason, automatic=True,
                                 source=str(self.console))
        journal = saved.path / JOURNAL
        record = {"root": str(self.console),
                  "writes": [{"container": c, "name": n, "existed": e, "new": _digest(d)} for c, n, _, d, e in plan]}
        journal.write_text(json.dumps(record), encoding="utf-8")
        try:
            for _, _, target, data, _ in plan:
                if data is None:
                    target.unlink()
                else:
                    _write_atomically(target, data)
        except Exception:
            self._roll_back(saved, record)
            raise
        journal.unlink()
        return saved

    def _roll_back(self, saved: BackupSet, record: Mapping) -> None:
        """Put the files of the journal back as the snapshot had them (or remove what did not exist), but only those
        that still hold what the write left (its recorded hash) or are gone after a delete: a file that is neither
        (the game saved it since, or it is already as it was) is never touched. The journal stays when a file cannot
        be restored (the next start tries again)."""
        complete = True
        for item in record["writes"]:
            target = self.path(item["container"], item["name"])
            try:
                if "new" in item:                   # a journal of this program: the write's hash (None: a delete)
                    current = _digest(target.read_bytes()) if target.is_file() else None
                    if current == item["new"] and (current is not None or item["existed"]):
                        content = saved.read(item["container"], item["name"]) if item["existed"] else None
                        if content is not None:
                            if current is None or current != _digest(content):
                                _write_atomically(target, content)
                        elif not item["existed"] and current is not None:
                            target.unlink()
            except OSError:
                complete = False
            try:
                target.with_name(target.name + TEMPORARY).unlink(missing_ok=True)
            except OSError:
                pass
        if complete:
            (saved.path / JOURNAL).unlink(missing_ok=True)

    def recover(self, backups: BackupStore | None = None) -> int:
        """Roll back every interrupted write of this store (a snapshot set with a journal), unless an emulator runs (the
        game may be saving: it happens at the next start). Returns how many."""
        backups = backups or self.backups
        if backups is None or self.console is None:
            return 0
        pending = []
        for found in backups.sets():
            if not found.has_journal:
                continue
            try:
                record = json.loads((found.path / JOURNAL).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if record.get("root") == str(self.console):
                pending.append((found, record))
        if not pending or self._running():
            return 0
        for found, record in pending:
            self._roll_back(found, record)
        return len(pending)

    def create_container(self, container: str, source: str | Path) -> Path:
        """Make the container's folder as a whole copy of `source` (a folder made elsewhere, with every file the game
        needs); never an empty or half-filled one. Raises if it exists or the store has no console folder."""
        target = self.folder(container)
        if target is None:
            raise NoSaveFolder(self.problem)
        if target.exists():
            raise FileExistsError(str(target))
        staging = target.parent / (target.name + TEMPORARY)
        shutil.rmtree(staging, ignore_errors=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, staging)
        os.replace(staging, target)
        return target


def _digest(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def _write_atomically(target: Path, data: bytes) -> None:
    temporary = target.with_name(target.name + TEMPORARY)
    temporary.write_bytes(data)
    os.replace(temporary, target)


# ---- the emulators on this PC -------------------------------------------------------------------------------------

def emulator_places(targets: Iterable | None = None, backups: BackupStore | None = None,
                    regions: Iterable[str] = files.REGIONS) -> list[SaveStore]:
    """The stores of every emulator found (`targets`: install/targets.py's Target list, default those found), both
    regions, newest emulator first: only those where the game has a save folder or an extdata."""
    if targets is None:
        from core.install.targets import emulator_targets
        targets = emulator_targets()
    found = []
    for target in targets:
        for region in regions:
            store = SaveStore(target.base, region, target.name, backups)
            if store.found:
                found.append(store)
    return found


def installed_store(mod_folder: str | Path, backups: BackupStore | None = None) -> SaveStore | None:
    """The store of the emulator whose mod folder of MH4U is `mod_folder` (`<emulator user folder>/load/mods/<title>`),
    in the region of its title; None when the folder is not one (a plain folder, a mod of another game)."""
    folder = Path(mod_folder)
    region = next((r for r, title in files.MH4U_TITLES.items() if title.lower() == folder.name.lower()), None)
    if region is None or folder.parent.name.lower() != "mods" or folder.parent.parent.name.lower() != "load":
        return None
    user_folder = folder.parent.parent.parent
    return SaveStore(user_folder, region, name=user_folder.name, backups=backups)


def _process_names() -> list[str]:
    if sys.platform == "win32":
        done = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=30)
        return [row[0] for row in csv.reader(done.stdout.splitlines()) if row]
    done = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True, timeout=30)
    return [Path(line.strip()).name for line in done.stdout.splitlines() if line.strip()]


def running_emulators(listing: Callable[[], Iterable[str]] | None = None,
                      known: Iterable[str] | None = None) -> list[str]:
    """The names of the emulators running now, sorted (a save is not written under a running emulator). `listing`
    (default: the system's process list, `tasklist` or `ps`) and `known` (default: curated/save_backups.json) are the
    tests'. An error reading the list answers `LIST_UNREADABLE` (fail closed: a write is refused, not let through)."""
    known = [k.lower() for k in (curated("emulator_processes") if known is None else known)]
    try:
        names = list(listing() if listing is not None else _process_names())
    except (OSError, subprocess.SubprocessError, ValueError):
        return [LIST_UNREADABLE]
    running = set()
    for name in names:
        lower = name.lower()
        base = lower.removesuffix(".exe").removesuffix(".appimage")
        if base in known or (lower.endswith(".appimage") and lower.startswith(tuple(known))):
            running.add(base)
    return sorted(running)
