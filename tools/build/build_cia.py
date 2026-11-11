"""Write a run's mod as CIAs for a real 3DS (core/install/title/build_title.py and
update_romfs.md), for developers until the GUI does it. The run's folder may be in the emulator's form or Luma's (a
`--3ds` run), which is moved back to the emulator's form first.

    python tools/build/build_cia.py --mod RUN --out Heavenfall_EUR.cia [--manifest base.json] [--rom GAME]
    python tools/build/build_cia.py --update --mod RUN --manifest base.json --out Heavenfall_EUR_update.cia
    python tools/build/build_cia.py --split --mod RUN --out Heavenfall_EUR.cia [--rom GAME]

The first writes the base title (the game with the mod over it) and, with --manifest, the list of the mod's files it
holds. The second writes the update title for a later run: its executable and only the files that differ from that
list (the run must be a console title build, whose executable reads the update). The third writes the split title:
the edition's title with only the mod's files, and the game data (an add-on content title, the dump's RomFS as it is)
as <out>_game.cia, installed once. GAME: local.ini's mh4u_rom.

    python tools/build/build_cia.py --edition beta --out HeavenfallBeta_EUR.cia [--rom GAME]

The third makes the edition's own mod for a console (no single-screen mode, no MH XX) and writes its title, with no
--mod (core/install/title/edition_build.py).
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.app.local_config import load  # noqa: E402
from core.install.luma import from_luma  # noqa: E402
from core.install.title.edition_build import build_edition_cia  # noqa: E402
from core.install.title.build_title import (  # noqa: E402
    build_cia, build_game_cia, build_mod_cia, build_update_cia, mod_manifest, read_manifest, write_manifest,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mod", type=Path, help="a run's output folder")
    parser.add_argument("--edition", help="an edition (editions/<name>): make its mod for a console and its title")
    parser.add_argument("--out", type=Path, required=True, help="the CIA to write")
    parser.add_argument("--rom", type=Path, help="the decrypted base game the run was made from (default: mh4u_rom)")
    parser.add_argument("--manifest", type=Path,
                        help="the base title's file list: written with a base, read with --update")
    parser.add_argument("--update", action="store_true", help="write the update title for the base of --manifest")
    parser.add_argument("--split", action="store_true",
                        help="write the split title: the edition's title with the mod's "
                             "files only to --out, and the game data beside it as <out>_game.cia")
    args = parser.parse_args(argv)
    rom = args.rom or load().get("mh4u_rom")
    if rom is None:
        raise SystemExit("no game: pass --rom or set mh4u_rom in local.ini")
    if bool(args.mod) == bool(args.edition):
        raise SystemExit("pass --mod (a run's folder) or --edition (an edition to build)")
    if args.edition and (args.update or args.manifest):
        raise SystemExit("--edition builds the base title alone: no --update or --manifest")
    if args.split and (args.edition or args.update or args.manifest):
        raise SystemExit("--split takes a run's --mod alone")
    if args.update and not args.manifest:
        raise SystemExit("--update needs the base title's --manifest")
    if args.mod:
        from_luma(args.mod)
    started = time.monotonic()
    shown = [0.0]

    def progress(done: int, total: int) -> None:
        if time.monotonic() - shown[0] > 5 or done == total:
            shown[0] = time.monotonic()
            print(f"  {done / 2**20:,.0f} / {total / 2**20:,.0f} MB", flush=True)

    def stage(name: str) -> None:
        print(name, flush=True)

    if args.edition:
        title = build_edition_cia(rom, args.out, args.edition, progress, stage)
    elif args.split:
        game_out = args.out.with_name(args.out.stem + "_game.cia")
        game = build_game_cia(rom, game_out, progress, stage)
        print(f"{game_out}: game data {game}, {game_out.stat().st_size / 2**20:,.1f} MiB")
        title = build_mod_cia(rom, args.mod, args.out, progress, stage)
    elif args.update:
        title, count = build_update_cia(rom, args.mod, read_manifest(args.manifest), args.out, progress, stage)
        print(f"{count} files differ from the base")
    else:
        title = build_cia(rom, args.mod, args.out, progress, stage)
        if args.manifest:
            write_manifest(mod_manifest(args.mod), args.manifest)
    size = args.out.stat().st_size
    print(f"{args.out}: title {title}, {size / 2**20:,.1f} MiB, {time.monotonic() - started:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
