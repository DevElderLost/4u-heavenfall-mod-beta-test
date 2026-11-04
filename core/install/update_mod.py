"""Rebuilding the installed mod after the program was updated: `<cli>.exe --update-installed`, which the updater
(install/self_update.py) starts once the new program is in place.

It looks at the emulators' mod folders (and the one the player chose in the program). A folder holding our marker with
another version is rebuilt like the Install page does, with the options its marker saved over today's defaults (an
option the program no longer offers is dropped), from the game the program remembers or, failing that, the one found
in the emulators' and the player's folders, of the region of that folder. Anything else is left as it is and the player
is told to open the program: a folder with no marker (empty, or another mod), a randomized game, a game that cannot be
found. Nothing from the Qt GUI is imported: the command-line bundle has none.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from core import __version__
from core.app.edition import edition
from core.install.self_update import LANGUAGES, language

MESSAGES: dict[str, tuple[str, str]] = {
    "nothing": ("No {name} mod is installed in the emulator folders found. Open {app} to install it.",
                "No hay ningún mod de {name} instalado en las carpetas de emulador encontradas. Abre {app} para "
                "instalarlo."),
    "current": ("{folder}: already version {version}.", "{folder}: ya está en la versión {version}."),
    "empty": ("{folder}: no {name} mod is installed there; it was left as it is. Open {app} to install it.",
              "{folder}: no hay ningún mod de {name} instalado; se ha dejado como estaba. Abre {app} para instalarlo."),
    "foreign": ("{folder}: this is not a {name} mod; it was left as it is.",
                "{folder}: esto no es un mod de {name}; se ha dejado como estaba."),
    "randomizer": ("{folder}: this is a randomized game; it was left as it is. Open {app} and make it again on its "
                   "Randomizer page.",
                   "{folder}: es una partida aleatoria; se ha dejado como estaba. Abre {app} y créala de nuevo en su "
                   "página Randomizer."),
    "no_game": ("{folder}: your game file was not found; the mod was left as it is. Open {app} to choose it.",
                "{folder}: no se ha encontrado tu archivo del juego; el mod se ha dejado como estaba. Abre {app} para "
                "elegirlo."),
    "rebuilding": ("{folder}: updating the mod ({old} to {new})...",
                   "{folder}: actualizando el mod ({old} a {new})..."),
    "progress": ("  {percent} %", "  {percent} %"),
    "rebuilt": ("{folder}: updated.", "{folder}: actualizado."),
    "failed": ("{folder}: the mod could not be updated ({reason}); it was left as it is.",
               "{folder}: no se pudo actualizar el mod ({reason}); se ha dejado como estaba."),
}


def text(key: str, lang: str, **params) -> str:
    return MESSAGES[key][LANGUAGES.index(lang) if lang in LANGUAGES else 0].format(**params)


@dataclass
class Report:
    rebuilt: list[Path] = field(default_factory=list)
    left: list[Path] = field(default_factory=list)         # left as they were: the player is told to open the program
    failed: list[Path] = field(default_factory=list)

    @property
    def code(self) -> int:
        return 1 if self.failed else 0


def settings_from_marker(saved: object):
    """The options this program offers, as the marker saved them, over today's defaults. A saved key the program does
    not offer (a marker holds the whole Settings), a value it no longer accepts and a number out of its range are left
    out, so an old marker always gives a valid install."""
    from core.app import presets
    from core.app.settings import Settings
    offered = presets.personal_defaults()
    ranges = presets.load_presets()["ranges"]
    chosen: dict = {}
    for key, value in (saved if isinstance(saved, dict) else {}).items():
        if key not in offered:
            continue
        try:
            Settings.from_dict({key: value})
            if key in ranges and not ranges[key][0] <= value <= ranges[key][1]:
                raise ValueError(key)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
        chosen[key] = value
    return presets.install_settings({**offered, **chosen})


def mod_folders(targets: Iterable | None = None, chosen: str = "auto") -> list[Path]:
    """The existing mod folders of either region in the emulators `targets` (default: those found) and in the folder
    the player chose in the program (`chosen`, a preference)."""
    from core.install.luma import mod_titles
    from core.install.targets import emulator_targets, mods_folder_for
    found: list[Path] = []
    emulators = list(emulator_targets() if targets is None else targets)
    for title in mod_titles():
        folders = [target.mods_dir(title) for target in emulators]
        if chosen and chosen != "auto":
            folders.append(mods_folder_for(chosen, title))
        for folder in folders:
            if folder.is_dir() and folder.resolve() not in [seen.resolve() for seen in found]:
                found.append(folder)
    return found


def find_games(title: str, preferences, search: Callable | None, need_mhgen: bool) -> tuple[Path | None, Path | None]:
    """The player's MH4U file of the region of the mod folder `title` and, when the edition needs it, MH Generations':
    the ones the program remembers, else the first found (install/find_games.py). None for what is missing."""
    from core.game.executable import titles
    from core.install import find_games as finder
    searched = []

    def found():
        if not searched:
            searched.append((search or finder.find)())
        return searched[0]

    def remembered(path: str, game: str) -> Path | None:
        kind = titles.file_kind(path) if path and Path(path).is_file() else None
        return Path(path) if kind and kind[0] == game else None

    rom = remembered(preferences.rom_path, titles.MH4U)
    if rom is None or titles.mod_title_of_file(rom) != title:
        rom = next((c.path for c in found().mh4u if titles.mod_title(c.region) == title), None)
    mhgen = None
    if need_mhgen:
        mhgen = remembered(preferences.mhgen_rom_path, titles.MHGEN) or next((c.path for c in found().mhgen), None)
    return rom, mhgen


def _every_tenth(show: Callable[[int], None]) -> Callable[[int, int], None]:
    """A progress callback that calls `show(percent)` each time another tenth of the work is done."""
    last = [-1]

    def progress(done: int, total: int) -> None:
        if total and done * 10 // total != last[0]:
            last[0] = done * 10 // total
            show(last[0] * 10)

    return progress


def update_installed(targets: Iterable | None = None, preferences=None, search: Callable | None = None,
                     build_dir: Path | None = None, lang: str | None = None, say: Callable[[str], None] = print,
                     version: str = __version__) -> Report:
    """Rebuild every emulator mod folder that holds our marker with a version other than `version`; see the module.
    The arguments are the tests': `targets` (default the emulators found), `preferences` (default the program's saved
    ones), `search` (default install/find_games.find), `build_dir` (default the program's build folder)."""
    from core.install.build import InputsError, build, discard_mod_files
    from core.install.deploy import ForeignContent, State, UnsafeTarget, inspect_target, install, read_marker
    if preferences is None:
        from core.gui.preferences import Preferences
        preferences = Preferences.load()
    lang = lang or language()
    current = edition()
    names = {"name": current.name, "app": current.app_name}
    report = Report()

    def tell(key: str, **params) -> None:
        say(text(key, lang, **params, **names))

    folders = mod_folders(targets, preferences.install_target)
    if not folders:
        tell("nothing")
    for folder in folders:
        state = inspect_target(folder)
        marker = read_marker(folder) if state is State.OURS else None
        if state is State.EMPTY:
            tell("empty", folder=folder)
            report.left.append(folder)
        elif marker is None:
            tell("foreign", folder=folder)
            report.left.append(folder)
        elif marker.get("kind") != "install":
            tell("randomizer", folder=folder)
            report.left.append(folder)
        elif marker.get("version") == version:
            tell("current", folder=folder, version=version)
        else:
            rom, mhgen = find_games(folder.name.upper(), preferences, search, current.needs_mhgen)
            if rom is None or (current.needs_mhgen and mhgen is None):
                tell("no_game", folder=folder)
                report.left.append(folder)
                continue
            settings = settings_from_marker(marker.get("settings"))
            tell("rebuilding", folder=folder, old=marker.get("version") or "?", new=version)
            try:
                result = build(rom, mhgen, settings, build_dir=build_dir, kind="install",
                               progress=_every_tenth(lambda percent: tell("progress", percent=percent)))
                code = result.checksum.code if result.checksum else ""
                install(result.output_dir, folder, "install", seed=result.seed, checksum=code,
                        settings=settings.to_dict(), title=result.mod_title)
                discard_mod_files(result.output_dir)
            except (InputsError, UnsafeTarget, ForeignContent, OSError, ValueError, RuntimeError) as error:
                # ValueError: a game the mod cannot be built for (UnsupportedVersion, RebaseError)
                tell("failed", folder=folder, reason=error)
                report.failed.append(folder)
                continue
            tell("rebuilt", folder=folder)
            report.rebuilt.append(folder)
    return report


def main() -> int:
    """`--update-installed`: the exit code is 0 unless a folder that should have been rebuilt failed."""
    return update_installed().code
