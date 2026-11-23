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
from core.install.self_update import LANGUAGES, MOD_REBUILT, language

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
    "rebuilding": ("{folder}: updating the mod ({old} to {new}). This can take a minute...",
                   "{folder}: actualizando el mod ({old} a {new}). Puede tardar un minuto..."),
    "saves_not_saved": ("{folder}: your saves could not be backed up first ({reason}); the update goes on.",
                        "{folder}: no se pudo hacer antes una copia de tus partidas ({reason}); la actualización "
                        "sigue."),
    "hunters_not_moved": ("{folder}: your earlier Heavenfall hunters could not be moved to the new save ({reason}); "
                          "the update goes on.",
                          "{folder}: no se pudieron pasar tus cazadores anteriores de Heavenfall a la partida nueva "
                          "({reason}); la actualización sigue."),
    "hunters_waiting": ("{folder}: your earlier Heavenfall hunters were not moved to the new save because "
                        "{emulators} is "
                        "running; they move at the next update, install or visit of the Saves page.",
                        "{folder}: tus cazadores anteriores de Heavenfall no se pasaron a la partida nueva porque "
                        "{emulators} está abierto; se pasan en la próxima actualización, instalación o visita a "
                        "Partidas."),
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
        """The exit code: 1 if a folder failed, MOD_REBUILT if a mod changed, else 0."""
        return 1 if self.failed else MOD_REBUILT if self.rebuilt else 0


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


def find_games(title: str, preferences, search: Callable | None, want_xx: bool) -> tuple[Path | None, Path | None]:
    """The player's MH4U file of the region of the mod folder `title` and, when `want_xx` (the saved options need it,
    or the edition offers it), MH XX's:
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
    xx = None
    if want_xx:
        xx = remembered(preferences.xx_rom_path, titles.MHXX) or next((c.path for c in found().xx), None)
    return rom, xx


def _every_tenth(show: Callable[[int], None]) -> Callable[[int, int], None]:
    """A progress callback that calls `show(percent)` each time another tenth of the work is done."""
    last = [-1]

    def progress(done: int, total: int) -> None:
        if total and done * 10 // total != last[0]:
            last[0] = done * 10 // total
            show(last[0] * 10)

    return progress


def _move_earlier_hunters(mod_folder: Path, backups=None) -> list[str]:
    """The edition with a save of its own: the hunters the earlier system kept beside MH4U's files (`hfuserN`) move
    into Heavenfall's own extdata (core/save/bring.py, `migrate_legacy`), as an install does (gui/qt/jobs.py). Not while
    an emulator runs (the running game keeps saving into the old files): the emulators running are returned and nothing
    moves; it happens at the next install, update or visit of the Saves page."""
    from core.save.backup import BackupStore, default_root
    from core.save.bring import migrate_legacy
    from core.save.store import installed_store, running_emulators
    found = installed_store(mod_folder)
    if found is None:
        return []
    running = running_emulators()
    if running:
        return running
    migrate_legacy(found, backups if backups is not None else BackupStore(default_root()))
    return []


def update_installed(targets: Iterable | None = None, preferences=None, search: Callable | None = None,
                     build_dir: Path | None = None, lang: str | None = None, say: Callable[[str], None] = print,
                     version: str = __version__, snapshot: Callable[[Path], object] | None = None) -> Report:
    """Rebuild every emulator mod folder that holds our marker with a version other than `version`; see the module.
    The arguments are the tests': `targets` (default the emulators found), `preferences` (default the program's saved
    ones), `search` (default install/find_games.find), `build_dir` (default the program's build folder), `snapshot`
    (default: a backup of the emulator's saves, taken before each rebuild; a failure of it is only told)."""
    from core.install.build import InputsError, build, discard_mod_files
    from core.game.executable.romfs import RomFS
    from core.install.deploy import ForeignContent, State, UnsafeTarget, inspect_target, install, read_marker
    from core.install.hd_textures import adapt_pack, clear_generated
    if snapshot is None:
        try:
            from core.save.backup import snapshot_installed_saves as snapshot
        except ImportError:     # an edition that ships no core/save: no backup of the saves to take
            snapshot = None
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
        elif marker.get("version") == version and not marker.get("incomplete"):
            tell("current", folder=folder, version=version)
        else:
            settings = settings_from_marker(marker.get("settings"))
            needs_xx = settings.needs_xx    # MH XX's file: needed by the saved options, or offered by the edition
            rom, xx = find_games(folder.name.upper(), preferences, search, needs_xx or current.xx_offered)
            if rom is None or (needs_xx and xx is None):
                tell("no_game", folder=folder)
                report.left.append(folder)
                continue
            tell("rebuilding", folder=folder, old=marker.get("version") or "?", new=version)
            try:
                if snapshot is not None:
                    snapshot(folder)
            except Exception as error:      # noqa: BLE001 - a backup of the saves never stops an update
                tell("saves_not_saved", folder=folder, reason=error)
            if current.own_save:
                try:
                    running = _move_earlier_hunters(folder)
                    if running:
                        tell("hunters_waiting", folder=folder, emulators=", ".join(running))
                except Exception as error:  # noqa: BLE001 - moving the earlier hunters never stops an update
                    tell("hunters_not_moved", folder=folder, reason=error)
            try:
                result = build(rom, settings, build_dir=build_dir, kind="install", xx_rom=xx,
                               progress=_every_tenth(lambda percent: tell("progress", percent=percent)))
                code = result.checksum.code if result.checksum else ""
                install(result.output_dir, folder, "install", seed=result.seed, checksum=code,
                        settings=settings.to_dict(), title=result.mod_title)
                if settings.hd_pack:                                         # as Install
                    adapt_pack(folder, Path(result.output_dir) / "romfs", lambda game=rom: RomFS(game))
                else:
                    clear_generated(folder)
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
    """`--update-installed`: the exit code of `Report.code`."""
    return update_installed().code
