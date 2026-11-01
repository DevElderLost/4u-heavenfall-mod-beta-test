"""End-to-end run of Heavenfall Beta: the player's game -> a Citra/Azahar mod folder.

Heavenfall Beta puts the touch screen's menus on the top screen (single-screen mode, with the lock-on with L),
shrinks the HUD and applies five cheats, all for the emulator (docs/how_it_works.md). Input: the player's decrypted
base game, European or American; the executable and the interface's files are read from it in memory, and the update is
never needed.

Output (copy its contents into the emulator's load/mods/<title>/: 0004000000126100 European, 0004000000126300
American; the program does it for the player):

    romfs/<lang>/data/*.arc        the single-screen layouts and the smaller HUD
    exefs/code.bin, exheader.bin   the whole executable with the patches: written for the canonical executable and
                                   carried onto the player's own version (docs/how_it_works.md, "The executable"); the
                                   exheader is his game's, extended when a patch uses the executable's extension
    settings_<seed>.json           the settings used

The original files are never modified; every run starts from them.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from core.game.executable.romfs import RomFS
from core.game.executable.code_bin import is_container
from core.game.executable import session, titles
from core.cheats.cheats import patch_cheats, supports_cheats, wants_cheats
from core.game.executable.memory_split import patch_memory_split, resource_to_root_mb
from core.game.executable.output import remove_exefs, write_exefs
from core.game.executable.player_code import open_code
from core.game.executable.rebase import feature_gaps
from core.interface.single_screen.executable.single_screen import patch_single_screen, supports_single_screen
from core.game.executable.versions import VersionMap
from core.interface.hud.build import hud_files, remove_hud_files
from core.interface.hud.build import hint_files
from core.interface.hud.code_patch import patch_interface
from core.interface.single_screen.layout.single_screen import remove_single_screen_files
from core.app.record import RunRecord, save_run
from core.app.settings import HudScale, Settings
from core.interface.single_screen.run import single_screen_romfs

# Stages announced through run(stage=...), in order.
STAGES = ("rom", "write")
# Why a run leaves a feature out (its notice): the game version lacks its code, or the input is no game ROM
NOT_AVAILABLE = "not available on this game version"
NEEDS_ROM = "needs the game ROM"


@dataclass(frozen=True)
class Probe:
    """A developer probe's own executable patch (tools/ui/ui_probe.py's frame counters): `patch` takes the canonical
    executable after every patch of the mod and returns it patched; `layout` places the blocks it places (the committed
    layout plus the probe's), so the run carries them to the player's version like the mod's."""
    patch: Callable[[bytes], bytes]
    layout: object      # exefs.code_space.Layout


@dataclass
class RunResult:
    output_dir: Path
    seed: str
    executable_path: Path | None = None  # exefs/code.bin (None: the run patches no executable)
    hud_scale: HudScale = HudScale.FULL
    hud_paths: list[Path] = field(default_factory=list)  # files of the smaller HUD
    single_screen_paths: list[Path] = field(default_factory=list)  # single-screen layouts
    interface_patched: bool = False  # the executable carries the interface patches
    notices: list[str] = field(default_factory=list)  # features left out (no ROM, or not on this game version)
    game_version: str | None = None  # the version the executable was built from (game/executable/versions.py key)
    checksum: None = None  # nothing is randomized: there is no code to compare
    settings_path: Path | None = None  # settings_<seed>.json
    # the mod folder's name: the game's region (game/executable/titles.py)
    mod_title: str = titles.mod_title(titles.EUR)

    @property
    def warnings(self) -> list[str]:
        return list(self.notices)


def game_mod_title(game: Path) -> str:
    """The mod folder's title for the player's game file: its region's (another file: European)."""
    return titles.mod_title_of_file(game) or titles.mod_title(titles.EUR)


def mod_folder(output_dir: Path) -> Path:
    """Root of the mod."""
    return Path(output_dir)


def version_notices(version: VersionMap) -> list[str]:
    """The patch sites the player's version lacks (rebase.feature_gaps), one notice per module that names them: its
    feature cannot patch that version (its own byte checks then leave it out)."""
    return [f"{module}: {NOT_AVAILABLE} ({', '.join(names)})" for module, names in feature_gaps(version).items()]


def left_out(feature: str, kept: str, why: str) -> str:
    """The notice of a feature the run leaves out: `why` (NOT_AVAILABLE or NEEDS_ROM), then what the game keeps."""
    return f"{feature}: {why}; {kept}"


def write_interface_files(result: RunResult, rom: RomFS | None, settings: Settings, with_code_patch: bool,
                          single_screen: bool = False) -> tuple[dict[int, int], bytes | None]:
    """The HUD size's and the single-screen mode's RomFS files. Both may change the same ARCs, so single-screen mode
    is made on the HUD's copies and everything is written once; files of an earlier run are removed first (they would
    still be loaded). Returns the single-screen mode's draw order offsets and the game GUI engine's table
    (interface/single_screen/executable/single_screen.patch_single_screen; empty and None without it)."""
    output_dir = result.output_dir
    remove_hud_files(output_dir)
    remove_single_screen_files(output_dir)
    resize_hud = settings.hud_scale != HudScale.FULL
    target_hint = settings.touchless_target and rom is not None  # the L + D-pad up glyph in the item selector
    if resize_hud:
        hud = dict(hud_files(rom, settings.hud_scale.factor, with_code_patch, target_hint))
    else:
        hud = dict(hint_files(rom)) if target_hint else {}
    screens, offsets, engine_table = {}, {}, None
    if single_screen:       # last: it places whole layouts, with what the HUD added (single_screen.py)
        made = single_screen_romfs(rom, hud)
        screens, offsets, engine_table = made.files, made.offsets, made.engine_table
    for path, data in {**hud, **screens}.items():
        target = output_dir / "romfs" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if path in hud:
            result.hud_paths.append(target)
        if path in screens:
            result.single_screen_paths.append(target)
    if resize_hud:
        result.hud_scale = HudScale(settings.hud_scale)
    return offsets, engine_table


def run(game: Path, output_dir: Path, settings: Settings, progress: Callable | None = None,
        code_path: Path | None = None, stage: Callable[[str], None] | None = None, record: RunRecord | None = None,
        mhgen_rom: Path | None = None, console: bool = False, probe: Probe | None = None) -> RunResult:
    """`game` is the player's base game (European or American). The executable is his own: the game's, or
    `code_path`'s (a code.bin or game file of any version with a map, for developers and tests). It is laid out as the
    canonical one, every patcher works on that image, and the patched image is carried back onto his bytes
    (game/executable/player_code.py): an executable of no known version raises versions.UnsupportedVersion before any
    work, a patch his version cannot take rebase.RebaseError. A feature whose code his version lacks is left out with a
    notice. `stage` is told when each of STAGES starts. `progress`, `mhgen_rom` and `console` are kept for the
    installer's sake: Heavenfall Beta counts nothing, needs no MH Generations and makes no mod for a real 3DS. `probe`:
    a developer probe's own patch, after the mod's (Probe)."""
    if console:
        raise ValueError("Heavenfall Beta is for the emulator only: it makes no mod for a real 3DS")
    if not is_container(game):
        raise ValueError(f"{game} is not a decrypted game file (.3ds, .cia, .zcci, .zcia...)")
    announce = stage or (lambda _name: None)
    announce("rom")
    # The player's executable (the game's, or code_path's) as the canonical one: an unknown one fails before any work
    player = open_code(code_path or game, game)
    code = player.image
    notices = version_notices(player.version)
    patch_interface_code = settings.patches_interface_code
    # the touch screen's menus on the top screen (interface/single_screen/executable/single_screen.py, single_screen.py)
    single_screen = settings.single_screen and supports_single_screen(code)
    if settings.single_screen and not single_screen:
        notices.append(left_out("single screen", "the touch screen's menus stay on it", NOT_AVAILABLE))
    cheats = wants_cheats(settings) and supports_cheats(code)
    if wants_cheats(settings) and not cheats:
        notices.append(left_out("cheats", "the game keeps its picture, camera, frame rate and online waits",
                                NOT_AVAILABLE))

    announce("write")
    output_dir = mod_folder(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = RunResult(output_dir=output_dir, seed=settings.seed, notices=notices, mod_title=game_mod_title(game))
    screen_offsets, engine_table = write_interface_files(result, RomFS(game), settings, patch_interface_code,
                                                         single_screen)
    if not (patch_interface_code or single_screen or cheats or probe is not None):
        remove_exefs(output_dir)  # nothing to patch; a patch left by an earlier run would still be applied
    else:
        notes = session.Session()   # what the patchers write that depends on where the game's code sits
        with session.recording(notes):
            # room for the executable's extension on an Old 3DS (docs/how_it_works.md, "The executable")
            patched = patch_memory_split(code, resource_to_root_mb())
            if cheats:
                patched = patch_cheats(patched, settings)
            if patch_interface_code:
                patched = patch_interface(patched, settings.hud_scale.factor, settings.touchless_target,
                                          settings.touchless_target)
                result.interface_patched = True
            if single_screen:
                patched = patch_single_screen(patched, screen_offsets, engine_table=engine_table)
            if probe is not None:
                patched = probe.patch(patched)
        # The patches carried onto the player's own executable, and the whole code.bin written with his game's
        # exheader (extended when a block is in the extension)
        built = player.carry(patched, notes, probe.layout if probe is not None else None)
        result.executable_path = write_exefs(output_dir, player.original, built.code, player.exheader)
        result.game_version = player.version.key
    result.settings_path = output_dir / f"settings_{settings.seed}.json"
    save_run(result.settings_path, settings, record or RunRecord())
    return result


__all__ = ["NEEDS_ROM", "NOT_AVAILABLE", "STAGES", "Probe", "RunResult", "game_mod_title", "left_out", "mod_folder",
           "run", "version_notices", "write_interface_files"]
