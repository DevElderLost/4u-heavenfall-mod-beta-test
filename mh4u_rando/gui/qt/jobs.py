"""The work behind the Install and Randomizer buttons, shared by every page: build the mod with the pipeline, then
put it where the player plays (the emulator's mods folder or the 3DS SD card), or remove it.

A page reads the AppState on the main thread into a plain `InstallRequest` (`request_from_state`), asks the player
before replacing content that is not ours (`target_state`), and runs `run_install(request, report)` in a worker
(gui/qt/worker.py). Nothing here touches Qt widgets; heavy imports are inside the functions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

KINDS = ("install", "randomizer")


class NoTarget(Exception):
    """No emulator was found and no folder chosen (or no SD card chosen on the 3DS platform)."""


@dataclass(frozen=True)
class InstallRequest:
    rom: Path
    mhgen_rom: Path | None    # None: the edition needs no MH Generations (edition.json needs_mhgen)
    settings: object          # randomizer.Settings, complete (presets.install_settings / randomizer_settings)
    kind: str                 # "install" | "randomizer"
    console: bool             # the 3DS form (Luma3DS) on the SD card at `target`
    target: Path              # emulator: the mods folder .../load/mods/<title>; 3DS: the SD card's root
    title: str                # the folder's name: the title of the player's game (European or American)
    replace_unknown: bool = False


@dataclass(frozen=True)
class InstallOutcome:
    target: Path              # the folder the mod went into
    seed: str
    code: str                 # the checksum code "XXXX-XXXX" ("" when nothing was randomized)
    result: object            # pipeline.RunResult (notices, settings_path...)


def mods_dir(target: str, title: str, emulators: Callable[[], list] | None = None) -> Path | None:
    """The emulator's mods folder of `title`: the chosen `target` (an emulator's folder, its load/mods or a mod
    folder, of either region), or for "auto" the most recently used emulator's (None: none)."""
    from ...install.targets import emulator_targets, mods_folder_for
    if target and target != "auto":
        return mods_folder_for(target, title)
    found = (emulators or emulator_targets)()
    return found[0].mods_dir(title) if found else None


def mod_title_for(rom: str | Path, installed: Callable[[str], bool]) -> str:
    """The title the mod folder is named after: the region of the player's MH4U file. When it cannot be read (moved,
    not chosen yet) the region whose folder holds our mod (`installed(title)`), else the European one: an install
    can still be looked at and removed."""
    from ...exefs import titles
    from ...luma import mod_titles
    found = titles.mod_title_of_file(rom) if str(rom) else None
    return found or next((title for title in mod_titles() if installed(title)), mod_titles()[0])


def request_from_state(state, settings, kind: str, replace_unknown: bool = False,
                       emulators: Callable[[], list] | None = None) -> InstallRequest:
    """Snapshot what the run needs from the AppState (main thread). Raises NoTarget. `emulators`: where the
    emulators are found (default `install.targets.emulator_targets`)."""
    from ...install.deploy import read_marker
    from ...luma import luma_dir, mod_titles
    assert kind in KINDS
    if state.console:
        if not state.sd_root:
            raise NoTarget("no SD card chosen")
        root = Path(state.sd_root)

        def target_of(title: str) -> Path:
            return root

        def folder_of(title: str) -> Path:
            return root / luma_dir(title)
    else:
        if mods_dir(state.target, mod_titles()[0], emulators) is None:
            raise NoTarget("no emulator found")

        def target_of(title: str) -> Path:
            return mods_dir(state.target, title, emulators)

        folder_of = target_of
    title = mod_title_for(state.rom_path, lambda candidate: read_marker(folder_of(candidate)) is not None)
    return InstallRequest(Path(state.rom_path), Path(state.mhgen_rom_path) if state.mhgen_rom_path else None,
                          settings, kind, state.console, target_of(title), title, replace_unknown)


def install_folder(request: InstallRequest) -> Path:
    """Where the files go: the mods folder, or the SD card's luma/titles/<title>."""
    if not request.console:
        return request.target
    from ...luma import luma_dir
    return request.target / luma_dir(request.title)


def target_state(request: InstallRequest):
    """install.deploy.State of the install folder: EMPTY, OURS or UNKNOWN (ask before replace_unknown=True)."""
    from ...install.deploy import inspect_target
    return inspect_target(install_folder(request))


def installed_marker(request: InstallRequest) -> dict | None:
    """The marker of the mod installed there (kind, seed, code, settings...), None when it is not ours."""
    from ...install.deploy import read_marker
    return read_marker(install_folder(request))


def copy_mod(request: InstallRequest, build_dir: Path, seed: str, checksum: str, settings: dict, progress=None,
             title: str | None = None) -> None:
    """Copy a build into the request's destination (the emulator's mods folder or the SD card). `title` is the
    build's own (RunResult.mod_title; None: unknown, as when a saved build comes back): it must be the destination's,
    so a USA build never lands in the European folder or the other way round (raises UnsafeTarget)."""
    from ...install.console import build_title, install_sd
    from ...install.deploy import UnsafeTarget, install
    if request.console:
        built = build_title(build_dir)
        if built != request.title.upper():
            raise UnsafeTarget(f"the mod in {build_dir} is for {built}, the install is for {request.title}")
        install_sd(build_dir, request.target, request.kind, seed=seed, checksum=checksum, settings=settings,
                   replace_unknown=request.replace_unknown, progress=progress)
    else:
        install(build_dir, request.target, request.kind, seed=seed, checksum=checksum, settings=settings,
                replace_unknown=request.replace_unknown, progress=progress, title=title or request.title)


def discard_build(request: InstallRequest, build_dir: Path) -> None:
    """After a successful install or export: free the disk of an "install" build, whose mod files are copied and never
    read again (a "randomizer" build stays whole: the fix mode reads it and backs it up)."""
    if request.kind == "install":
        from ...install.build import discard_mod_files
        discard_mod_files(build_dir)


def run_install(request: InstallRequest, report) -> InstallOutcome:
    """Build the mod and install it (worker thread). `report` is a worker Reporter: the pipeline's stages and
    progress, then the stage "install" with the copy's progress, then "done"."""
    from ...install.build import build
    result = build(request.rom, request.mhgen_rom, request.settings, console=request.console, kind=request.kind,
                   progress=report.progress, stage=report.stage)
    code = result.checksum.code if result.checksum else ""
    settings = request.settings.for_console() if request.console else request.settings
    report.stage("install")
    copy_mod(request, result.output_dir, result.seed, code, settings.to_dict(), report.progress, result.mod_title)
    discard_build(request, result.output_dir)
    report.stage("done")
    return InstallOutcome(install_folder(request), result.seed, code, result)


def run_uninstall(request: InstallRequest, report) -> Path:
    """Remove our mod from the install folder (worker thread); foreign files stay."""
    from ...install.deploy import uninstall
    folder = install_folder(request)
    report.stage("install")
    uninstall(folder)
    report.stage("done")
    return folder
