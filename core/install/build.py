"""Checking the game files and building the mod to install. Heavy imports are inside
functions."""

import shutil
from collections.abc import Callable
from pathlib import Path

from core.app.edition import edition

BUILD_MARKER = ".heavenfall_build"  # a build folder we made: the only kind build() clears
LEGACY_BUILD_MARKERS = edition().legacy_build_markers   # the names it had before: such a folder is still ours
DEFAULT_ROOT = edition().home / "build"

# What is wrong with a game file picked for a game it is not, as the English text the GUI translates
# (gui/strings.py GAME_PROBLEMS, by the same keys: a test keeps both in step). The title id of an unknown game follows
# in brackets.
GAME_PROBLEMS = {
    "wrong_mh4u": "this is not the European or American Monster Hunter 4 Ultimate",
    "wrong_mhgen": "this is not the European or American Monster Hunter Generations",
    "is_update": "this is the game update, not the game itself: choose the game (cartridge or eShop dump)",
    "is_mh4u": "this is Monster Hunter 4 Ultimate, not Monster Hunter Generations",
    "is_mhgen": "this is Monster Hunter Generations, not Monster Hunter 4 Ultimate",
    "unreadable": "the file cannot be read (check that it is not in use, that you have permission to open it, and "
                  "that its drive is connected)",
}
WRONG_MH4U, WRONG_MHGEN, IS_UPDATE, IS_MH4U, IS_MHGEN, UNREADABLE = GAME_PROBLEMS.values()


class InputsError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _game_problem(path: Path | None, label: str, is_mh4u: bool) -> str | None:
    from core.game.executable.extract import ExtractError
    from core.game.executable.romfs import RomFS
    from core.game.executable import titles
    if path is None or not Path(path).is_file():
        return f"{label}: the file was not found"
    try:
        title = RomFS(Path(path)).title_id
    except ExtractError as error:
        return f"{label}: {error}"
    except OSError:
        return f"{label}: {UNREADABLE}"
    kind = titles.identify(title)
    game = kind[0] if kind else None
    if is_mh4u:
        if game == titles.MH4U:
            return None
        reason = {titles.MH4U_UPDATE: IS_UPDATE, titles.MHGEN: IS_MHGEN}.get(game)
        return f"{label}: {reason}" if reason else f"{label}: {WRONG_MH4U} (title {title})"
    if game == titles.MHGEN:
        return None
    if game in (titles.MH4U, titles.MH4U_UPDATE):
        return f"{label}: {IS_MH4U}"
    return f"{label}: {WRONG_MHGEN} (title {title})"


def check_inputs(rom: Path | None, mhgen_rom: Path | None, need_mhgen: bool = True) -> list[str]:
    """What is wrong with the game files, one message each: MH4U must be the decrypted base game, European or
    American (not its update, not another game); MH Generations (needed by the ported monsters and gear) the
    decrypted game, European or American."""
    problems = [_game_problem(rom, "Monster Hunter 4 Ultimate", True)]
    if need_mhgen:
        problems.append(_game_problem(mhgen_rom, "Monster Hunter Generations", False))
    return [problem for problem in problems if problem]


def is_our_build_dir(folder: Path) -> bool:
    """Whether `folder` holds our build marker (the current name or an old one)."""
    return any((Path(folder) / name).is_file() for name in (BUILD_MARKER, *LEGACY_BUILD_MARKERS))


def prepare_build_dir(build_dir: Path) -> Path:
    """Empty `build_dir` (made if missing) and mark it ours; refuses a folder that is not empty and not ours."""
    build_dir = Path(build_dir)
    if build_dir.exists():
        if is_our_build_dir(build_dir):
            shutil.rmtree(build_dir)
        elif any(build_dir.iterdir()):
            raise InputsError([f"{build_dir} is not empty and was not made by this installer"])
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / BUILD_MARKER).write_text("", encoding="utf-8")
    return build_dir


# What a finished "install" build keeps: its settings, spoiler and logs.
KEPT_SUFFIXES = (".json", ".txt")


def discard_mod_files(build_dir: Path) -> None:
    """Delete the mod files of a build that was copied where it is played (romfs/, exefs/, luma/, the pack, the
    exheader...), keeping the marker and the top-level settings, spoiler and log files. Only a folder we made (the
    marker); a failure to delete is ignored: the next build clears the folder anyway."""
    build_dir = Path(build_dir)
    if not is_our_build_dir(build_dir):
        return
    try:
        items = list(build_dir.iterdir())
    except OSError:
        return
    for item in items:
        if item.name in (BUILD_MARKER, *LEGACY_BUILD_MARKERS) or (
                item.is_file() and item.suffix.lower() in KEPT_SUFFIXES):
            continue
        try:
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
        except OSError:
            continue


def default_build_dir(kind: str, console: bool = False) -> Path:
    return DEFAULT_ROOT / (kind + ("_3ds" if console else ""))


def clear_previous_runs(kind: str) -> None:
    """Delete the default build folders of `kind` (the emulator's and the 3DS form's): the previous run's mod
    files, spoilers, logs and settings. A folder that is not ours stays."""
    for console in (False, True):
        folder = default_build_dir(kind, console)
        if is_our_build_dir(folder):
            shutil.rmtree(folder)


def build(rom: Path, mhgen_rom: Path | None, settings, build_dir: Path | None = None, console: bool = False,
          progress: Callable[[int, int], None] | None = None, stage: Callable[[str], None] | None = None,
          kind: str = "install"):
    """Run the pipeline into `build_dir` (default `build/<kind>[_3ds]` in the edition's folder under the home; the
    default folders of both forms are deleted first, `clear_previous_runs`) and return its RunResult, built from the
    player's own game (the update is never read). `console`: the 3DS form (luma/ and the pack), with the emulator-only
    options at their defaults. Raises InputsError before touching anything. MH Generations' game is checked when the
    edition needs it (edition.json `needs_mhgen`)."""
    problems = check_inputs(rom, mhgen_rom, need_mhgen=edition().needs_mhgen)
    if problems:
        raise InputsError(problems)
    from core.app.pipeline import run
    if build_dir is None:
        clear_previous_runs(kind)
    build_dir = prepare_build_dir(Path(build_dir) if build_dir else default_build_dir(kind, console))
    if console:
        settings = settings.for_console()
    return run(Path(rom), build_dir, settings, mhgen_rom=Path(mhgen_rom) if mhgen_rom else None, stage=stage,
               progress=(lambda done, total, _report: progress(done, total)) if progress else None,
               console=console)
