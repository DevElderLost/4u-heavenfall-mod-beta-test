"""The game GUI's arrangement tools: pictures of the recorded screens, the gallery, the checker and
the commands that answer the recorder's requests.

    python tools/ui.py render REF [--arranged] [--out DIR] [--mode M]
        both screens of a snapshot (.json.zst, a recorded screen's signature, or a screen's number or id: its first
        recorded screen) as PNGs, as recorded or arranged; default --out: the main checkout's output/ui/pictures
    python tools/ui.py gallery [--reviewed [SIGNATURE ...]] [--out DIR] [--mode M]
        output/ui/galeria/index.html (local, never published); --reviewed marks this build's pictures as reviewed
    python tools/ui.py compare REF SCREENSHOT [--arranged]
        how far a picture is from the emulator's screenshot of the same moment
    python tools/ui.py check [--json] [--no-pictures]
        the arrangement checker (as text, or JSON for scripts); exit code 1 when it finds problems
    python tools/ui.py pending [--json]
        the requests not answered yet, newest first: picture, note, recorded screen, the screens it matches
    python tools/ui.py show REF [--mode M]
        a screen (number or id: rule, blocks, final places, recorded screens, pictures) or a recorded screen
    python tools/ui.py set SCREEN BLOCK key=value ... [--mode M]
        a block's placement on a screen, absolute values only (x, y, scale, screen, priority, hidden; key=none)
    python tools/ui.py answer REQUEST TEXT [--commit SHA]
        marks a request answered (respuesta.json beside it; nothing is deleted)
    python tools/ui.py probe NAME [--install] [--two-screen]
        builds the next round output/ui/NAME_<n> (your mod's options, single-screen mode on, the recorder's marks;
        tools/ui_probe.py) and with --install puts it in the emulator's mod folder only over one of our own probes

Recordings and requests come from the main checkout's work/ui (--root changes it), the arrangement from
data/curated/game_gui (--arrangement changes it); layouts and textures from the installed mod's ARCs, then the RomFS
dump's (local.ini), in recorder.json's layout language. The texts are in the edition's tools language
(data/curated/edition.json); --lang es|en changes it."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mh4u_rando import local_config  # noqa: E402
from mh4u_rando.gamegui import check, edit, fidelity, gallery, render, requests  # noqa: E402
from mh4u_rando.gamegui import strings as S  # noqa: E402
from mh4u_rando.gamegui.config import ARRANGEMENT_DIR, MODES, load_arrangement  # noqa: E402
from mh4u_rando.gamegui.engine import unwrap_snapshot  # noqa: E402
from mh4u_rando.gamegui.recorded import find_recorded, recorded_screens  # noqa: E402
from mh4u_rando.gamegui.recorder.settings import load_settings  # noqa: E402
from mh4u_rando.gamegui.recorder.store import ui_root  # noqa: E402
from mh4u_rando.gamegui.snapshot import load  # noqa: E402


def pictures_dir() -> Path:
    return local_config.main_checkout() / "output" / "ui" / "pictures"


def find_snapshot(name: str, root: Path) -> Path:
    """A snapshot file, or the snapshot of the recorded screen whose signature is (or starts with) `name`."""
    return resolve(name, root)[0]


def resolve(name: str, root: Path, arrangement=None, mode: str = "single_screen") -> tuple[Path, str]:
    """(snapshot, the stem its pictures take): a file, a screen's id or number (its first recorded screen) or a
    recorded screen's signature."""
    path = Path(name)
    if path.is_file():
        return path, path.name.split(".")[0]
    screens = recorded_screens(root)
    if arrangement is not None:
        try:
            screen = edit.find_screen(arrangement, name, mode)
        except edit.EditError:
            screen = None
        if screen is not None:
            names = edit.screens_of_groups
            found = [s for s in screens if S.title(screen) in names(arrangement, s.groups)[mode]]
            if not found:
                raise SystemExit(f"{name}: no recorded screen matches screen {S.title(screen)}")
            return found[0].snapshot, found[0].signature
    found = find_recorded(screens, name)
    if len(found) != 1:
        raise SystemExit(f"{name}: {'no' if not found else len(found)} recorded screens match")
    return found[0].snapshot, found[0].signature


def assets() -> render.Assets:
    found = render.Assets.from_local(load_settings().layout_language)
    if not len(found.layouts):
        raise SystemExit("no layouts: local.ini's mh4u_romfs (and the installed mod) hold none")
    return found


def pool_inputs():
    """check.game_pools' three from this machine's update executable and RomFS dump, None without them."""
    config = local_config.load()
    code, romfs = config.input("code_update"), config.romfs_dir
    language = load_settings().layout_language
    if not code.is_file() or not (romfs / language / "data").is_dir():
        return None
    return check.game_pools(code.read_bytes(), romfs, language)


def arrangement_of(args):
    return load_arrangement(args.arrangement)


def picture(args, root: Path) -> tuple[render.Picture, str]:
    arrangement = arrangement_of(args)
    path, stem = resolve(args.snapshot, root, arrangement, args.mode)
    snapshot = load(path)
    unwrap_snapshot(snapshot)           # a single-screen game's copy holds the engine's wrapper nulls
    if args.arranged:
        return render.render_arranged(snapshot, assets(), arrangement, args.mode), stem
    return render.render_recorded(snapshot, assets()), stem


def cmd_render(args, root: Path) -> int:
    settings = render.load_render_settings()
    result, stem = picture(args, root)
    out = args.out or pictures_dir()
    stem += "_arranged" if args.arranged else ""
    for name, screen in result.screens.items():
        image = render.outlined(screen, result.blocks, name, settings) if args.arranged else screen
        print(render.save_png(image, out / f"{stem}_{name}.png", settings.zoom))
    if result.screen:
        print(f"screen {S.title(result.screen)}")
    for place in result.blocks:
        print(f"block {place.number} {place.block.id}: {place.screen} {place.box}")
    for warning in result.warnings:
        print("warning:", warning)
    return 0


def cmd_gallery(args, root: Path) -> int:
    out = args.out or local_config.main_checkout() / "output" / "ui" / "galeria"
    page = gallery.build(root, out, assets(), arrangement_of(args), args.mode)
    print(page)
    if args.reviewed is not None:
        count = gallery.mark_reviewed(root, out, args.reviewed or None)
        print(f"{count} screens marked reviewed")
    return 0


def cmd_compare(args, root: Path) -> int:
    settings = render.load_render_settings()
    result, _stem = picture(args, root)
    shots = fidelity.split_screenshot(render.read_png(args.screenshot))
    for name, shot in shots.items():
        boxes = {p.number: p.box for p in result.blocks if p.box is not None and p.screen == name}
        found = fidelity.compare(result.screens[name], shot, settings.fidelity["changed_threshold"],
                                 settings.fidelity["shift_search"], boxes)
        print(f"{name}: {found.summary()}")
        for label, share in found.boxes.items():
            print(f"  {label}: {100 * share:.1f} %")
    return 0


def cmd_check(args, root: Path) -> int:
    folder = Path(args.arrangement)
    arrangement = load_arrangement(folder)
    settings = check.load_check_settings(folder / "check.json")
    found = None if args.no_pictures else _assets_or_none()
    from mh4u_rando.gamegui.recorder.coverage import load_coverage
    report = check.run(arrangement, root, settings, found, pool_inputs(), coverage=load_coverage())
    print(json.dumps(report.to_json(), ensure_ascii=False, indent=1) if args.json else report.text())
    return 0 if report.ok else 1


def _assets_or_none():
    try:
        return assets()
    except SystemExit:
        return None


def _window_record(arrangement, screens, record: dict, folder: Path) -> dict:
    if not record.get("snapshot"):
        return {"snapshot": None, "reason": record.get("reason", "")}
    found = find_recorded(screens, record.get("signature", ""))
    return {"snapshot": str(folder / record["snapshot"]), "signature": record.get("signature"),
            "recorded": found[0].signature if len(found) == 1 else None, "groups": record.get("groups", []),
            "screens": edit.screens_of_groups(arrangement, record.get("groups", []))}


def cmd_pending(args, root: Path) -> int:
    arrangement = arrangement_of(args)
    screens = recorded_screens(root)
    out = []
    for request in requests.pending(root):
        out.append({"id": request.id, "time": request.time, "note": request.note,
                     "picture": str(request.picture) if request.picture else None,
                     "windows": {window: _window_record(arrangement, screens, record, request.folder)
                                 for window, record in request.windows.items()}})
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(S.tr(S.PENDING_COUNT, count=len(out)))
    for item in out:
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item["time"]))
        print(f"\n{item['id']}  {when}" + (S.tr(S.PENDING_NOTE, note=item["note"]) if item["note"] else ""))
        print(S.tr(S.PENDING_PICTURE, picture=item["picture"] or S.tr(S.NO_PICTURE)))
        for window, record in item["windows"].items():
            if not record["snapshot"]:
                print(S.tr(S.PENDING_NO_SNAPSHOT, window=window, reason=record["reason"]))
                continue
            matches = "; ".join(f"{S.mode_name(mode)}: {', '.join(names) or S.tr(S.NO_SCREEN_MATCHED)}"
                                for mode, names in record["screens"].items())
            print(S.tr(S.PENDING_WINDOW, window=window, sig=record["recorded"] or record["signature"],
                       matches=matches))
            print(S.tr(S.PENDING_SNAPSHOT, path=record["snapshot"]))
    return 0


def cmd_show(args, root: Path) -> int:
    try:
        print(edit.show(arrangement_of(args), args.ref, root, pictures_dir(), args.mode))
    except edit.EditError as error:
        print(S.tr(S.NOT_FOUND, error=error), file=sys.stderr)
        return 2
    return 0


def cmd_set(args, root: Path) -> int:
    try:
        old, new = edit.set_placement(args.arrangement, args.screen, args.block, args.values, args.mode)
    except edit.EditError as error:
        print(S.tr(S.SET_REFUSED, error=error), file=sys.stderr)
        return 2
    print(f"{args.screen} {args.block}: {edit.placement_text(old)} -> {edit.placement_text(new)}")
    print(S.tr(S.SET_NEXT))
    return 0


def cmd_answer(args, root: Path) -> int:
    try:
        print(requests.answer(root, args.request, args.text, args.commit))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    return 0


def cmd_probe(args, root: Path) -> int:
    import ui_probe                          # the pipeline and the installer: only this command needs them
    probes = local_config.main_checkout() / "output" / "ui"
    out = ui_probe.next_out(probes, args.name)
    result, settings, _marks = ui_probe.build(out, single_screen=not args.two_screen)
    print(S.tr(S.PROBE_BUILT, out=out))
    if not args.install:
        return 0
    emulator = local_config.load().get("emulator_dir")
    if emulator is None:
        print(S.tr(S.NOT_INSTALLED_NO_EMULATOR), file=sys.stderr)
        return 2
    mods = Path(emulator) / "load" / "mods" / result.mod_title
    try:
        ui_probe.install_probe(out, mods, probes, settings.to_dict(), result.mod_title)
    except ValueError as error:
        print(S.tr(S.NOT_INSTALLED, error=error), file=sys.stderr)
        return 2
    print(S.tr(S.PROBE_INSTALLED, mods=mods))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, help="instead of the main checkout's work/ui")
    parser.add_argument("--arrangement", type=Path, default=ARRANGEMENT_DIR, help="the arrangement's folder")
    parser.add_argument("--lang", choices=("es", "en"), help="the texts' language (default: the edition's)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("render", "compare"):
        command = commands.add_parser(name)
        command.add_argument("snapshot", help="a snapshot file, a recorded screen's signature or a screen's number")
        if name == "compare":
            command.add_argument("screenshot", type=Path, help="the emulator's screenshot (Ctrl+P)")
        command.add_argument("--arranged", action="store_true", help="apply the arrangement")
        command.add_argument("--mode", choices=MODES, default="single_screen")
        if name == "render":
            command.add_argument("--out", type=Path)
    command = commands.add_parser("gallery")
    command.add_argument("--reviewed", nargs="*", help="mark this build's pictures reviewed (all, or these)")
    command.add_argument("--mode", choices=MODES, default="single_screen")
    command.add_argument("--out", type=Path)
    command = commands.add_parser("check")
    command.add_argument("--json", action="store_true", help="machine-readable")
    command.add_argument("--no-pictures", action="store_true", help="skip the names, overlaps and edges")
    command = commands.add_parser("pending")
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("show")
    command.add_argument("ref", help="a screen's number or id, or a recorded screen's signature")
    command.add_argument("--mode", choices=MODES)
    command = commands.add_parser("set")
    command.add_argument("screen", help="the screen's number or id")
    command.add_argument("block", help="the block's id")
    command.add_argument("values", nargs="+", help="key=value, absolute (x, y, scale, screen, priority, hidden)")
    command.add_argument("--mode", choices=MODES)
    command = commands.add_parser("answer")
    command.add_argument("request")
    command.add_argument("text", help="the one-line answer")
    command.add_argument("--commit", default="")
    command = commands.add_parser("probe")
    command.add_argument("name", help="the probe's name (its rounds: output/ui/<name>_<n>)")
    command.add_argument("--install", action="store_true", help="install it over one of our own probes only")
    command.add_argument("--two-screen", action="store_true", help="single-screen mode off (a recording probe)")
    args = parser.parse_args(argv)
    S.set_language(args.lang)
    root = args.root or ui_root()
    return {"render": cmd_render, "gallery": cmd_gallery, "compare": cmd_compare, "check": cmd_check,
            "pending": cmd_pending, "show": cmd_show, "set": cmd_set, "answer": cmd_answer,
            "probe": cmd_probe}[args.command](args, root)


if __name__ == "__main__":
    sys.exit(main())
