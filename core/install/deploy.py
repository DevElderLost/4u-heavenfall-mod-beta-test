"""Putting the mod in a mod folder and taking it out again, without touching what is not ours.

A mod folder (`.../load/mods/<title>`, or a 3DS' `luma/titles/<title>`) we installed holds `heavenfall_mod.json`,
the marker: what was installed and every file written. Reinstalling removes the previous install's files (from
the marker) so no stale `code.ips` / `code.bin` / `exheader.bin` or old archive stays; uninstalling removes only
those. A folder with anything else in it is UNKNOWN: never touched unless the caller says `replace_unknown`.
An install made under an old name of the marker (the edition's `legacy_markers`) is still ours: it is read, updated
(the new marker replaces it) and uninstalled like any other.
"""

import json
import os
import shutil
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from core import __version__
from core.app.edition import edition
from core.game.executable import titles
from core.install.luma import mod_titles

MARKER = edition().marker      # "heavenfall_mod.json" (game/data/curated/edition.json)
LEGACY_MARKERS = edition().legacy_markers       # the names it had before: an install marked with one is still ours
FORBIDDEN_PARTS = {"sdmc", "nand", "save", "saves", "extdata"}  # an emulator's SD card, NAND and saves
Progress = Callable[[int, int], None]
Stage = Callable[[str], None]


class State(Enum):
    EMPTY = "empty"      # no folder, or no file in it
    OURS = "ours"        # holds our marker
    UNKNOWN = "unknown"  # anything else


class UnsafeTarget(ValueError):
    """A path the installer must never write or remove."""


class ForeignContent(RuntimeError):
    """The mod folder holds files that are not ours and `replace_unknown` was not given."""


def assert_safe(mods_dir: Path, title: str | None = None) -> None:
    """Raise UnsafeTarget unless `mods_dir` is `.../load/mods/<title>` or `.../luma/titles/<title>`, the title of
    either MH4U region, outside an emulator's sdmc / nand / save folders. With `title` (the build's own) only that
    one: a USA build never goes into the European folder, nor the other way round."""
    path = Path(mods_dir).resolve()
    names = [part.lower() for part in path.parts]
    allowed = [titles.normal(title).upper()] if title else mod_titles()
    ok = path.name.upper() in allowed and len(path.parts) >= 4 and \
        (names[-3:-1] == ["load", "mods"] or names[-3:-1] == ["luma", "titles"])
    if not ok:
        raise UnsafeTarget(f"{path} is not a mod folder for {' / '.join(allowed)}")
    if FORBIDDEN_PARTS & set(names):
        raise UnsafeTarget(f"{path} is inside an emulator's SD card, NAND or save folder")


def read_marker(folder: Path) -> dict | None:
    """The marker of an install of ours in `folder`: the new file, else one of the old names; None if neither."""
    for name in (MARKER, *LEGACY_MARKERS):
        try:
            data = json.loads((Path(folder) / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("files"), list):
            return data
    return None


def inspect_target(folder: Path) -> State:
    folder = Path(folder)
    if not folder.is_dir():
        return State.EMPTY
    if read_marker(folder) is not None:
        return State.OURS
    for _root, _dirs, files in os.walk(folder):
        if files:
            return State.UNKNOWN
    return State.EMPTY


def _retrying(action: Callable[[], None], seconds: float = 3.0) -> None:
    """`action` (a removal or replacement of the marker), tried again while Windows refuses it because another thread
    has the file open for a moment (the GUI reads the marker to describe the folder while a job works)."""
    end = time.monotonic() + seconds
    while True:
        try:
            return action()
        except PermissionError:
            if time.monotonic() >= end:
                raise
            time.sleep(0.02)


def write_marker(folder: Path, kind: str, files: list[str], seed: str = "", checksum: str = "",
                 settings: dict | None = None) -> None:
    """Write `folder`'s marker (atomically): the last thing an install does. An old marker of the folder is removed
    once the new one is in place (it lists the same files, which the new one holds)."""
    data = {"kind": kind, "seed": seed, "checksum": checksum, "version": __version__,
            "settings": settings or {}, "files": sorted(set(files) - {MARKER, *LEGACY_MARKERS})}
    temp = Path(folder) / (MARKER + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _retrying(lambda: os.replace(temp, Path(folder) / MARKER))
    for name in LEGACY_MARKERS:
        if (Path(folder) / name).is_file():
            _retrying((Path(folder) / name).unlink)


def _member(folder: Path, rel: str) -> Path:
    """`folder`/`rel`, refusing anything that resolves outside `folder`."""
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise UnsafeTarget(f"bad path in the marker: {rel!r}")
    path = Path(folder) / rel
    try:
        path.resolve().relative_to(Path(folder).resolve())
    except ValueError:
        raise UnsafeTarget(f"{rel} leads outside {folder}") from None
    return path


def _prune(folder: Path, top: Path) -> None:
    """Remove `folder` and its parents up to `top` (included) while empty."""
    top = Path(top)
    while folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
        if folder == top:
            break
        folder = folder.parent


def _remove_files(folder: Path, rels: list[str]) -> None:
    paths = [_member(folder, rel) for rel in rels]  # every path checked before the first removal
    for path in paths:
        if path.is_file() or path.is_symlink():
            path.unlink()
    for path in paths:
        _prune(path.parent, folder)


def tree_files(root: Path, *subpaths: str) -> list[tuple[Path, str]]:
    """(file, path relative to `root`) of every file under the given sub-paths of `root`, sorted."""
    out = []
    for sub in subpaths:
        base = Path(root) / sub
        if base.is_file():
            out.append((base, sub))
        elif base.is_dir():
            out += [(p, p.relative_to(root).as_posix()) for p in sorted(base.rglob("*")) if p.is_file()]
    return out


def deploy_files(plan: list[tuple[Path, str]], target: Path, kind: str, seed: str = "", checksum: str = "",
                 settings: dict | None = None, replace_unknown: bool = False, progress: Progress | None = None,
                 stage: Stage | None = None, title: str | None = None) -> None:
    """Install `plan` ((source, relative path) pairs) as the mod in `target`. Files are copied to a temp folder
    beside `target` first; the previous install's files go only after every copy succeeded; the marker is last.
    `title`: the build's own title, which `target` must be named after (`assert_safe`)."""
    progress = progress or (lambda done, total: None)
    stage = stage or (lambda text: None)
    target = Path(target)
    assert_safe(target, title)
    state = inspect_target(target)
    if state is State.UNKNOWN and not replace_unknown:
        raise ForeignContent(f"{target} holds files this installer did not put there")
    old = read_marker(target) if state is State.OURS else None
    old_files = [str(rel) for rel in old["files"]] if old else []
    for rel in old_files:
        _member(target, rel)
    rels = [rel for _, rel in plan]
    total = 2 * len(plan)
    temp = target.parent / (target.name + ".heavenfall_new")
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    try:
        stage("Copying files")
        for done, (source, rel) in enumerate(plan, 1):
            (temp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, temp / rel)
            progress(done, total)
        stage("Installing")
        if state is not State.OURS:
            if target.exists():
                shutil.rmtree(target)  # empty, or foreign and replace_unknown
            write_marker(temp, kind, rels, seed, checksum, settings)
            os.replace(temp, target)
        else:
            write_marker(target, old.get("kind", kind), old_files + rels, old.get("seed", ""),
                         old.get("checksum", ""), old.get("settings"))  # the union, until the new marker
            _remove_files(target, old_files)
            for done, rel in enumerate(rels, len(plan) + 1):
                (target / rel).parent.mkdir(parents=True, exist_ok=True)
                os.replace(temp / rel, target / rel)
                progress(done, total)
            write_marker(target, kind, rels, seed, checksum, settings)
        progress(total, total)
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)


def top_files(build_dir: Path, kind: str) -> list[tuple[Path, str]]:
    """The run's files at the top of the mod folder: the settings file and, for a randomized game, the spoiler log
    (beside the mod it describes; the logs for programs stay in the build)."""
    patterns = ("settings_*.json",) + (("spoiler_*.txt",) if kind == "randomizer" else ())
    return [(p, p.name) for pattern in patterns for p in sorted(Path(build_dir).glob(pattern))]


def install(build_dir: Path, mods_dir: Path, kind: str, seed: str = "", checksum: str = "",
            settings: dict | None = None, replace_unknown: bool = False, progress: Progress | None = None,
            stage: Stage | None = None, title: str | None = None) -> None:
    """Install a run's output folder (romfs/, exefs/, exheader.bin and `top_files`) into the emulator's
    `mods_dir`. `kind` is "install" or "randomizer"; `title` the build's own (RunResult.mod_title): the folder
    must be that one's."""
    build_dir = Path(build_dir)
    plan = tree_files(build_dir, "romfs", "exefs", "exheader.bin") + top_files(build_dir, kind)
    deploy_files(plan, mods_dir, kind, seed, checksum, settings, replace_unknown, progress, stage, title)


def uninstall(mods_dir: Path) -> None:
    """Remove what our install put in `mods_dir` (and then the empty folders); foreign files stay."""
    mods_dir = Path(mods_dir)
    assert_safe(mods_dir)
    state = inspect_target(mods_dir)
    if state is State.EMPTY:
        return
    if state is State.UNKNOWN:
        raise ForeignContent(f"{mods_dir} was not installed by this installer")
    _remove_files(mods_dir, [str(rel) for rel in read_marker(mods_dir)["files"]])
    for name in (MARKER, *LEGACY_MARKERS):
        if (mods_dir / name).is_file():
            _retrying((mods_dir / name).unlink)
    _prune(mods_dir, mods_dir)
