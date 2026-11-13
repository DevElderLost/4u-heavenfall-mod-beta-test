"""Heavenfall Beta's command line: the mod the program installs, built into a folder.

    python -m core --rom game.3ds --out mod_folder [options]

Without options it builds what the program's Options page starts with (game/data/curated/gui_defaults.json):
single-screen mode, the lock-on with L, holding A, fast text, Layered Gear (its looks unlocked by rank), the Rare
Materials Exchange, the HUD at 70 % and the cheats' defaults; each option below changes one of them. They come in three
modules, each with a switch: --single-screen (with the HUD size, the lock-on, the aspect ratio and Select's kick),
--layered-equipment (with its unlocking by rank and the Rare Materials Exchange) and --quality-of-life (holding A, fast
text, the camera, the item boxes and the cheats); a module switched off leaves the game as it is in all it holds. The
game's START menu page Mod Settings lets the player change the lock-on, holding A, fast text and the cheats during play:
what is chosen here is what a character with no choice of its own gets.
The game is your base game, European or American (.3ds, .cia, .zcci, .zcia...), never modified, decrypted or encrypted
(an encrypted one is read with --keys aes_keys.txt / 3dskeys.txt); the update is
not needed. The output folder is a mod folder: copy its contents into the emulator's load/mods/<title>/
(0004000000126100 for the European game, 0004000000126300 for the American one).
--xx-rom (MH XX's decrypted game, optional) adds the looks of XX's weapons and armor to Layered Gear and the Wyporium's
trades of the new materials they cost.
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
    parser.add_argument("--xx-rom", type=Path,
                        help="MH XX's decrypted game file (optional, never modified): Layered Gear adds XX's looks")
    parser.add_argument("--keys", type=Path, metavar="FILE",
                        help="aes_keys.txt or 3dskeys.txt (or the folder with it and seeddb.bin): reads a game file "
                             "that is still encrypted. Without it the keys are looked for beside the game, in "
                             "HEAVENFALL_KEYS and in the emulators' sysdata folders")
    parser.add_argument("--layered-equipment", action=argparse.BooleanOptionalAction,
                        help="the Smithy's Layered Gear: looks bought once and worn over what you wear")
    parser.add_argument("--layered-by-rank", action=argparse.BooleanOptionalAction,
                        help="Layered Gear's looks and the Wyporium's new trades open with their rank (off: all at "
                             "once)")
    parser.add_argument("--rare-exchange", action=argparse.BooleanOptionalAction,
                        help="the Wyporium's Rare Materials Exchange (with Layered Gear)")
    parser.add_argument("--quality-of-life", action=argparse.BooleanOptionalAction,
                        help="the quality-of-life module: holding A, fast text, the camera, the item boxes and the "
                             "cheats (off: the game's own)")
    parser.add_argument("--code", type=Path,
                        help="advanced: the executable to build from (a code.bin or game file of any version with a "
                             "map); taken from --rom by default")
    parser.add_argument("--single-screen", action=argparse.BooleanOptionalAction,
                        help="the touch screen's menus on the top screen, for the emulator's single screen view")
    parser.add_argument("--lock-on", dest="touchless_target", action=argparse.BooleanOptionalAction,
                        help="L + D-pad up locks on to a large monster or switches to the other one")
    parser.add_argument("--hold-a", action=argparse.BooleanOptionalAction,
                        help="holding A repeats picking up and gathering and moves on through reward panels")
    parser.add_argument("--fast-text", action=argparse.BooleanOptionalAction,
                        help="holding B runs through the conversations at high speed")
    parser.add_argument("--box-equipment", action=argparse.BooleanOptionalAction,
                        help="every item box has Manage Equipment and Equipment Sets (Change Appearance stays "
                             "at home)")
    parser.add_argument("--damage-numbers", action=argparse.BooleanOptionalAction,
                        help="a number over the monster at each hit; its style, size and duration are in the game's "
                             "Mod Settings")
    parser.add_argument("--camera-speed", type=int, metavar="CAP",
                        help="the camera's top turning speed with the buttons (10: the game's own; 50: five times)")
    parser.add_argument("--hud-scale", choices=[scale.value for scale in HudScale], help="top-screen HUD size in %%")
    parser.add_argument("--cheat-3d-mode", choices=[value.value for value in Cheat3D],
                        help="3D: off (the game's own), dither_off or dither_on (3D forced off)")
    parser.add_argument("--cheat-no-bloom-dof", action=argparse.BooleanOptionalAction,
                        help="no glow (bloom) and no distant blur (depth of field)")
    parser.add_argument("--cheat-fps", choices=[value.value for value in CheatFps],
                        help="frame rate: off (the game's own) or every 5 from 30 to 60")
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

    if args.keys is not None:
        from core.game.executable import crypto
        try:
            crypto.use_keys(crypto.load_keys(args.keys))
        except (OSError, ValueError) as error:
            parser.error(f"--keys: {error}")
    low, high = presets.field_range("cheat_fov")
    if args.cheat_fov is not None and not low <= args.cheat_fov <= high:
        parser.error(f"--cheat-fov must be between {low} and {high}")
    low, high = presets.field_range("camera_speed")
    if args.camera_speed is not None and not low <= args.camera_speed <= high:
        parser.error(f"--camera-speed must be between {low} and {high}")
    defaults = presets.personal_defaults()
    chosen = {name: value for name, value in vars(args).items() if name in defaults and value is not None}
    if args.cheat_aspect_ratio:
        chosen["cheat_aspect_allowed"] = True
    settings = presets.install_settings({**defaults, **chosen})
    try:
        result = run(args.rom, args.out, settings, code_path=args.code, xx_rom=args.xx_rom)
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
