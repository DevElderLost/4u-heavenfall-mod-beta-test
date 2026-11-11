"""The game GUI recorder's probe: the mod with single-screen mode off,
plus the frame counters the recorder needs to copy the GUI only between frames
(core/interface/game_gui/gui_frame_marks.s).

    python tools/ui/ui_probe.py --out output/ui/rec<N>_<round> [--single-screen] [--rom GAME]

Writes OUT: a whole mod without the randomizer, as the GUI installs it (presets.install_settings) with the
installer options this machine's GUI has saved, `single_screen` off (the recordings are the game's own GUI) and
`layered_equipment` on (its menus are recorded too), and the frame counters: the variable `gui_frame_marks`
(game/executable/blocks.py) that sMhMain::frame's two hooks keep (started, done). GAME is the player's base game,
European or American (default: local.ini `mh4u_rom`); XX is MH XX's decrypted .3ds
(defaults: local.ini `mhxx_rom`). `--single-screen`: single-screen mode on instead (the migration's probes: today's look
with the arranged themes placed by the game GUI engine), to record
the arranged screens.
Nothing is installed here; `python tools/ui/ui.py probe NAME --install` builds the next round and installs it over one
of our own probes only (`install_probe`).
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.app import local_config, pipeline, presets  # noqa: E402
from core.game.executable.code_space import Layout, encode_branch, load_layout  # noqa: E402

BLOCK = "gui_frame_marks_probe"     # game/executable/blocks.py: in the committed layout, after every block of a mod
# The frame's wait for the GPU, where the main thread spends almost
# all of each frame, and its two calls: the render's `bl` (GX flag 0x200 set) and the GX end's `b` (otherwise)
GX_WAIT = 0xBF5FEC          # FUN_00bf5fec, GAME_SYMBOLS gx_frame_wait
RENDER_SITE = 0xBFA718      # FUN_00bfa6c0 (the GX's render)
GX_END_SITE = 0xBFA470      # FUN_00bfa460 (the GX's end)


def counters_layout() -> Layout:
    """The committed layout: the counters' block is packed after every block of a mod, so it fits beside any of them."""
    return load_layout()


def patch_frame_counters(code: bytes, layout: Layout) -> bytes:
    """`code`, the canonical executable, with the counters' block and both calls of the frame's wait going through it
    (each site must still call the wait)."""
    out = bytearray(code)
    layout.place(out, BLOCK)
    wrapper = layout.symbol(BLOCK, "frame_wait")
    layout.hook(out, RENDER_SITE, wrapper, calls=GX_WAIT)
    layout.hook(out, GX_END_SITE, wrapper, original=encode_branch(GX_END_SITE, GX_WAIT), link=False)
    return bytes(out)


def next_out(probes: Path, name: str) -> Path:
    """`probes/<name>_<round>`, the round after the highest one there (1 for the first): a new name each round."""
    rounds = [int(found.name[len(name) + 1:]) for found in Path(probes).glob(f"{name}_*")
              if found.name[len(name) + 1:].isdigit()]
    return Path(probes) / f"{name}_{max(rounds, default=0) + 1}"


def _sha256(path: Path) -> str | None:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def foreign_mod(mods_dir: Path, probes: Path) -> str | None:
    """Why a probe must not go into `mods_dir` (in the tools' language), or None: the folder is empty or holds one of
    our probes (its marker's kind "probe" and its executable one of `probes`' builds, the main checkout's output/ui).
    Your own mod, a probe made elsewhere or anything else stays as it is."""
    from core.interface.game_gui import strings as S
    from core.install.deploy import State, inspect_target, read_marker
    state = inspect_target(mods_dir)
    if state is State.EMPTY:
        return None
    marker = read_marker(mods_dir) if state is State.OURS else None
    if marker is None or marker.get("kind") != "probe":
        return S.tr(S.PROBE_NOT_OURS, folder=mods_dir)
    installed = _sha256(Path(mods_dir) / "exefs" / "code.bin")
    if installed is None or installed not in {_sha256(code) for code in Path(probes).glob("*/exefs/code.bin")}:
        return S.tr(S.PROBE_OTHER_SESSION, folder=mods_dir, probes=probes)
    return None


def install_probe(build: Path, mods_dir: Path, probes: Path, settings: dict, title: str) -> None:
    """Install the probe `build` into the emulator's `mods_dir` (deploy.install, kind "probe") when `foreign_mod`
    finds nothing against it; ValueError with the reason otherwise, nothing touched."""
    from core.install.deploy import install
    reason = foreign_mod(mods_dir, probes)
    if reason is not None:
        raise ValueError(reason)
    install(build, mods_dir, "probe", settings=settings, title=title)


def recording_settings(single_screen: bool = False):
    """The settings the GUI installs with this machine's saved installer options, layered equipment on when the
    edition offers it (its menus are recorded too) and single-screen mode off (on with `single_screen`)."""
    from core.gui.preferences import Preferences
    defaults = presets.personal_defaults()
    saved = {k: v for k, v in Preferences.load().install_options.items() if k in defaults}
    layered = {"layered_equipment": True} if "layered_equipment" in defaults else {}
    return presets.install_settings({**defaults, **saved, "single_screen": single_screen, **layered})


def build(out: Path, single_screen: bool, rom: Path | None = None,
          xx: Path | None = None):
    """Writes the probe into `out` (a new folder); returns (the run's result, the settings, the counters' address)."""
    config = local_config.load()
    rom = rom or config.get("mh4u_rom")
    if rom is None:
        raise SystemExit("no base game: --rom, or local.ini mh4u_rom")
    if Path(out).exists():
        raise SystemExit(f"{out} exists: a new name each round")
    layout = counters_layout()
    probe = pipeline.Probe(lambda code: patch_frame_counters(code, layout), layout)
    settings = recording_settings(single_screen)
    result = pipeline.run(Path(rom), Path(out), settings,
                          xx_rom=xx or config.get("mhxx_rom"), probe=probe)
    for notice in result.notices:
        print(f"notice: {notice}")
    return result, settings, layout.address("gui_frame_marks")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rom", type=Path, help="the base game (default: local.ini mh4u_rom)")
    parser.add_argument("--xx-rom", type=Path, help="MH XX's .3ds (default: local.ini mhxx_rom)")
    parser.add_argument("--single-screen", action="store_true",
                        help="single-screen mode on (the arranged screens placed by the game GUI engine)")
    args = parser.parse_args()
    result, _settings, counters = build(args.out, args.single_screen, args.rom, args.xx_rom)
    print(f"{args.out}: {result.game_version}, frame counters at {counters:#x}, executable {result.executable_path}")


if __name__ == "__main__":
    main()
