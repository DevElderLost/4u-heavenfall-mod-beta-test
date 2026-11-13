"""What the web page asks of Python: the options it shows, the check of the player's game (and of MH XX's, optional)
and the mod as one zip.

The page's worker (web/worker.js) runs this module in the browser, in Pyodide, on the game files the player chose
(decrypted, or encrypted with the key file the player chose: `use_keys`); nothing is sent anywhere.
tools/release/build_web.py writes `options` into the site, so the page shows them before its
engine is loaded. Nothing here knows of a browser: the run is the program's own (core/app/pipeline.py), and the module's
heavy imports are inside the functions that need them.
"""

import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

from core.app import presets

ZIP_STAGE = "zip"       # announced after pipeline.STAGES, while the mod goes into its zip
ZIP_NAME = "Heavenfall-Beta-{region}.zip"


def _texts(option, defaults: dict, language: str) -> dict:
    """One option as the page draws it. `requires` and `also_with` mean what they mean in core/gui/options.py."""
    drawn = {"field": option.field, "label": option.label(language), "help": option.tooltip(language),
             "default": defaults[option.field], "requires": option.requires, "also_with": option.also_with}
    if option.choices:
        return {**drawn, "kind": "choice", "compact": option.compact,
                "choices": [{"value": choice.value.value, "label": choice.label(language),
                             "help": choice.tooltip(language)} for choice in option.choices if not choice.legacy]}
    if option.maximum > option.minimum:
        return {**drawn, "kind": "number", "minimum": option.minimum, "maximum": option.maximum, "step": option.step}
    return {**drawn, "kind": "bool"}


def options(language: str) -> list[dict]:
    """The program's Options page (core/gui/options.py, INSTALL_SECTIONS) as plain data: sections, their groups and
    their options, in `language`, each with its starting value."""
    from core.gui.options import INSTALL_SECTIONS
    defaults = presets.personal_defaults()
    return [{"title": section.title(language),
             "groups": [{"title": group.title(language), "description": group.description(language),
                         "warning": group.warning(language),
                         "hint": group.hint and {"fields": list(group.hint.fields), "on": group.hint.on(language),
                                                 "off": group.hint.off(language)},
                         "options": [_texts(option, defaults, language) for option in group.options]}
                        for group in section.groups]}
            for section in INSTALL_SECTIONS]


def use_keys(location: str | Path | None) -> dict:
    """The player's key files, for the games that are still encrypted: `location` is a folder holding aes_keys.txt or
    3dskeys.txt (and maybe seeddb.bin), or None to go back to none. Returns `ok`, and `keys` (the names of the keys
    found, as the key file spells them) and `seeds` (how many) or, when the file holds no key, `reason`: "empty".
    The page tells the player, in its own language. Nothing is kept beyond this run of Python."""
    from core.game.executable import crypto
    if not location:
        crypto.use_keys(None)
        return {"ok": True, "keys": [], "seeds": 0}
    try:
        keys = crypto.KeySet.load(Path(location))
    except OSError:
        return {"ok": False, "reason": "unreadable"}
    if not keys:
        crypto.use_keys(None)
        return {"ok": False, "reason": "empty"}
    crypto.use_keys(keys)
    return {"ok": True, "keys": keys.names(), "seeds": len(keys.seeds), "aes": crypto.backend_name()}


def check_game(game: str | Path, language: str) -> dict:
    """The player's game file: `ok`, and either `problem` (why it cannot be used, in `language`) or `title` (the mod
    folder's name) and `region` (its name in `language`)."""
    from core.game.executable import titles
    from core.gui.strings import REGIONS, describe_problem
    from core.install.build import check_inputs
    problems = check_inputs(Path(game))
    if problems:
        return {"ok": False, "problem": "; ".join(describe_problem(problem, language) for problem in problems)}
    return {"ok": True, "title": titles.mod_title_of_file(game), "region": REGIONS[titles.file_kind(game)[1]](language)}


def check_xx(xx: str | Path, language: str) -> dict:
    """MH XX's file, optional (with it, Layered Gear also has XX's looks): `ok`, and `problem` (why it cannot be used,
    in `language`) when it is not the decrypted Japanese game."""
    from core.gui.strings import describe_problem
    from core.install.build import xx_problems
    problems = xx_problems(Path(xx))
    if problems:
        return {"ok": False, "problem": "; ".join(describe_problem(problem, language) for problem in problems)}
    return {"ok": True}


def write_zip(folder: Path, title: str, target: Path) -> int:
    """`folder` into the zip `target`, as one folder named `title`, uncompressed: the zip is made on the device that
    uses it and the game's files are compressed already. Each file is deleted once in, so the mod is never in memory
    twice. Returns how many files it holds."""
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as archive:
        for path in files:
            archive.write(path, f"{title}/{path.relative_to(folder).as_posix()}")
            path.unlink()
    return len(files)


def build(game: str | Path, target: str | Path, personal: dict, language: str,
          stage: Callable[[str], None] | None = None, xx: str | Path | None = None) -> dict:
    """The mod of the player's game, with `personal` (installer options; a missing one keeps its default, and what is no
    installer option, as something an older page saved, is ignored), as the zip `target`; with `xx` (MH XX's file,
    checked by check_xx), Layered Gear also has XX's looks. `stage` is told pipeline.STAGES and then ZIP_STAGE. Returns
    `ok`, and either `problem` or the zip's `title`, `zip_name`, `files`, the `notices` of features left out and the
    game's `version`."""
    from core.app.pipeline import run
    from core.game.executable import titles
    from core.game.executable.rebase import RebaseError
    from core.game.executable.versions import UnsupportedVersion
    from core.gui.strings import describe_problem
    announce = stage or (lambda _name: None)
    defaults = presets.personal_defaults()
    chosen = {name: value for name, value in dict(personal).items() if name in defaults}
    with tempfile.TemporaryDirectory() as temporary:
        try:
            settings = presets.install_settings({**defaults, **chosen})
            result = run(Path(game), Path(temporary) / "mod", settings, stage=announce,
                         xx_rom=Path(xx) if xx else None)
        except (UnsupportedVersion, RebaseError, ValueError) as error:     # not a game the mod can be built for
            return {"ok": False, "problem": describe_problem(str(error), language)}
        announce(ZIP_STAGE)
        files = write_zip(result.output_dir, result.mod_title, Path(target))
    region = titles.file_kind(game)[1].upper()
    return {"ok": True, "title": result.mod_title, "zip_name": ZIP_NAME.format(region=region), "files": files,
            "notices": result.notices, "version": result.game_version}
