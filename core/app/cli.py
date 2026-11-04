"""Heavenfall Beta's command line: the mod the program installs, built into a folder.

    python -m core --rom game.3ds --out mod_folder [options]

Without options it builds what the program's Options page starts with (game/data/curated/gui_defaults.json):
single-screen mode, the lock-on with L, Select's kick, holding A, the HUD at 70 % and the cheats' defaults; each option
below changes one of them.
The game is your decrypted base game, European or American (.3ds, .cia, .zcci, .zcia...), never modified; the update is
not needed. The output folder is a mod folder: copy its contents into the emulator's load/mods/<title>/
(0004000000126100 for the European game, 0004000000126300 for the American one).
Advanced: --code, an executable of any version with a map (a code.bin or a game file: developers and tests).
"""

import argparse
import sys
from pathlib import Path

from core.app import presets
from core.app.edition import edition
from core.game.executable.rebase import RebaseError
from core.game.executable.versions import UnsupportedVersion
from core.app.pipeline import run
from core.app.settings import Cheat3D, CheatAspect, CheatFps, HudScale


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="core", description=f"{edition().window_title}: the mod in a folder")
    parser.add_argument("--rom", type=Path, help="your decrypted game file; never modified (required)")
    parser.add_argument("--out", type=Path, help="output (mod) folder (required)")
    parser.add_argument("--code", type=Path,
                        help="advanced: the executable to build from (a code.bin or game file of any version with a "
                             "map); taken from --rom by default")
    parser.add_argument("--single-screen", action=argparse.BooleanOptionalAction,
                        help="the touch screen's menus on the top screen, for the emulator's single screen view")
    parser.add_argument("--lock-on", dest="touchless_target", action=argparse.BooleanOptionalAction,
                        help="L + D-pad up locks on to a large monster or switches to the other one")
    parser.add_argument("--hold-a", action=argparse.BooleanOptionalAction,
                        help="holding A repeats picking up and gathering and moves on through reward panels")
    parser.add_argument("--hud-scale", choices=[scale.value for scale in HudScale], help="top-screen HUD size in %%")
    parser.add_argument("--cheat-3d-mode", choices=[value.value for value in Cheat3D],
                        help="3D: off (the game's own), dither_off or dither_on (3D forced off)")
    parser.add_argument("--cheat-no-bloom-dof", action=argparse.BooleanOptionalAction,
                        help="no glow (bloom) and no distant blur (depth of field)")
    parser.add_argument("--cheat-fps", choices=[value.value for value in CheatFps],
                        help="frame rate: off (the game's own), 30 or 60")
    parser.add_argument("--cheat-fov", type=int, metavar="DEGREES", help="camera field of view (50: the game's own)")
    parser.add_argument("--cheat-net-fix", action=argparse.BooleanOptionalAction,
                        help="longer waits for the online connection")
    parser.add_argument("--cheat-aspect-ratio", choices=[value.value for value in CheatAspect],
                        help="experimental: the shape of the emulator's picture, off (the game's own) or a ratio")
    parser.add_argument("--cheat-raw-unbloat", action=argparse.BooleanOptionalAction,
                        help="menus show weapons' true attack; the damage does not change")
    parser.add_argument("--update-installed", action="store_true",
                        help="rebuild the mod installed in the emulators' folders after the program was updated "
                             "(what the updater runs; needs nothing else)")
    args = parser.parse_args(argv)
    if args.update_installed:
        from core.install.update_mod import main as update_installed
        return update_installed()
    if args.rom is None or args.out is None:
        parser.error("the following arguments are required: --rom, --out")

    low, high = presets.field_range("cheat_fov")
    if args.cheat_fov is not None and not low <= args.cheat_fov <= high:
        parser.error(f"--cheat-fov must be between {low} and {high}")
    defaults = presets.personal_defaults()
    chosen = {name: value for name, value in vars(args).items() if name in defaults and value is not None}
    if args.cheat_aspect_ratio:
        chosen["cheat_aspect_allowed"] = True
    settings = presets.install_settings({**defaults, **chosen})
    try:
        result = run(args.rom, args.out, settings, code_path=args.code)
    except (UnsupportedVersion, RebaseError, ValueError) as error:     # not a game the mod can be built for
        print(f"Refused: {error}", file=sys.stderr)
        return 1
    if result.executable_path:
        print(f"Executable: {result.executable_path} (built from {result.game_version})")
    if result.single_screen_paths:
        print(f"Single screen: {len(result.single_screen_paths)} files in {result.output_dir / 'romfs'}")
    if result.hud_paths:
        print(f"HUD at {result.hud_scale.value} %: {len(result.hud_paths)} files in {result.output_dir / 'romfs'}")
    for warning in result.warnings:
        print(f"WARNING {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
