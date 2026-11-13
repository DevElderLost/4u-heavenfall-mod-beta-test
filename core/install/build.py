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
    "wrong_mhxx": "this is not the Japanese Monster Hunter XX",
    "is_mhxx": "this is Monster Hunter XX, not the game asked for here",
    "unreadable": "the file cannot be read (check that it is not in use, that you have permission to open it, and "
                  "that its drive is connected)",
    # After the refusal of an encrypted file whose name says it is decrypted: an emulator with the console's keys
    # plays it, and a decryptor may skip it by its name (Batch CIA 3DS Decryptor Redux does, without a word).
    "misnamed_encrypted": "its name says it is decrypted, but it is not (an emulator with the console's keys plays "
                          "it anyway); decryptors skip a file whose name says decrypted, so rename it first",
}
(WRONG_MH4U, WRONG_MHGEN, IS_UPDATE, IS_MH4U, IS_MHGEN, WRONG_MHXX, IS_MHXX, UNREADABLE,
 MISNAMED_ENCRYPTED) = GAME_PROBLEMS.values()


class InputsError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _game_problem(path: Path | None, label: str, wanted: str) -> str | None:
    """What is wrong with the file picked for the game `wanted` (titles.MH4U, MHGEN or MHXX); None when it is that
    game."""
    from core.game.executable.containers import ENCRYPTED
    from core.game.executable.extract import ExtractError
    from core.game.executable.romfs import RomFS
    from core.game.executable import titles
    if path is None or not Path(path).is_file():
        return f"{label}: the file was not found"
    try:
        title = RomFS(Path(path)).title_id
    except ExtractError as error:
        if error.kind == ENCRYPTED and "decrypt" in Path(path).name.lower():
            return f"{label}: {error}; {MISNAMED_ENCRYPTED}"
        return f"{label}: {error}"
    except OSError:
        return f"{label}: {UNREADABLE}"
    kind = titles.identify(title)
    game = kind[0] if kind else None
    if game == wanted:
        return None
    if wanted == titles.MH4U:
        reason = {titles.MH4U_UPDATE: IS_UPDATE, titles.MHGEN: IS_MHGEN, titles.MHXX: IS_MHXX}.get(game)
        return f"{label}: {reason}" if reason else f"{label}: {WRONG_MH4U} (title {title})"
    if wanted == titles.MHGEN:
        if game in (titles.MH4U, titles.MH4U_UPDATE):
            return f"{label}: {IS_MH4U}"
        if game == titles.MHXX:
            return f"{label}: {IS_MHXX}"
        return f"{label}: {WRONG_MHGEN} (title {title})"
    return f"{label}: {WRONG_MHXX} (title {title})"


def check_inputs(rom: Path | None, xx_rom: Path | None = None, need_xx: bool = False) -> list[str]:
    """What is wrong with the game files, one message each: MH4U must be the decrypted base game, European or
    American (not its update, not another game); MH XX (`need_xx`: a ported monster or the models pack is on, the
    only other game a run reads) the decrypted Japanese game."""
    from core.game.executable import titles
    problems = [_game_problem(rom, "Monster Hunter 4 Ultimate", titles.MH4U)]
    return [problem for problem in problems if problem] + (xx_problems(xx_rom) if need_xx else [])


def xx_problems(xx_rom: Path | None) -> list[str]:
    """What is wrong with MH XX's file, one message each (none: the decrypted Japanese game)."""
    from core.game.executable import titles
    problem = _game_problem(xx_rom, "Monster Hunter XX", titles.MHXX)
    return [problem] if problem else []


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


def build(rom: Path, settings, build_dir: Path | None = None, console: bool = False,
          progress: Callable[[int, int], None] | None = None, stage: Callable[[str], None] | None = None,
          kind: str = "install", xx_rom: Path | None = None):
    """Run the pipeline into `build_dir` (default `build/<kind>[_3ds]` in the edition's folder under the home; the
    default folders of both forms are deleted first, `clear_previous_runs`) and return its RunResult, built from the
    player's own game (the update is never read). `console`: the 3DS form (luma/ and the pack), with the emulator-only
    options at their defaults. Raises InputsError before touching anything. `xx_rom`, MH XX's, is needed when the
    settings add a ported monster or the models pack (Settings.needs_xx); an edition where it is optional
    (`Edition.xx_optional`) checks it only when one is given."""
    problems = check_inputs(rom, xx_rom=xx_rom,
                            need_xx=settings.needs_xx or (edition().xx_optional and xx_rom is not None))
    if problems:
        raise InputsError(problems)
    from core.app.pipeline import run
    if build_dir is None:
        clear_previous_runs(kind)
    build_dir = prepare_build_dir(Path(build_dir) if build_dir else default_build_dir(kind, console))
    if console:
        settings = settings.for_console()
    return run(Path(rom), build_dir, settings, stage=stage,
               progress=(lambda done, total, _report: progress(done, total)) if progress else None,
               console=console, xx_rom=Path(xx_rom) if xx_rom else None)
