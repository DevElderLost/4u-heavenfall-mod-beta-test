"""The game GUI recorder: exact snapshots of the game's interface, read only.

    python tools/ui_recorder.py                     the window: records the running emulator (one or two windows)
    python tools/ui_recorder.py --headless          the same without a window, a status line per change
    python tools/ui_recorder.py --state A.cst ...   imports save states as snapshots (no window)
                                [--session NAME] [--root DIR]

Everything goes into the main checkout's work/ui/ (recordings/<session>/, peticiones/ (the requests), recorder.log);
--root changes it. Live recording needs the recording probe installed (its frame marks); without it nothing is
recorded. The window speaks the edition's tools language (data/curated/edition.json); --lang es|en changes it."""

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mh4u_rando import local_config  # noqa: E402
from mh4u_rando.gamegui import strings as S  # noqa: E402
from mh4u_rando.gamegui.memory import local_candidates  # noqa: E402
from mh4u_rando.gamegui.recorder.checks import LayoutIndex, fallback_folders, layout_folders  # noqa: E402
from mh4u_rando.gamegui.recorder.exact import FrameMarks  # noqa: E402
from mh4u_rando.gamegui.recorder.live import LOG, RecorderService, setup_log  # noqa: E402
from mh4u_rando.gamegui.recorder.settings import load_settings  # noqa: E402
from mh4u_rando.gamegui.recorder.states import import_states  # noqa: E402
from mh4u_rando.gamegui.recorder.store import Session, session_name, ui_root  # noqa: E402


def states(paths: list[Path], root: Path, name: str | None, settings, config) -> int:
    session = Session(root, name or session_name("estados"))
    cache: dict = {}

    def layouts(_title):
        """Every installed mod's layouts and the dump's: a state may come from an earlier install than today's."""
        if not cache:
            where = (config.get("emulator_dir"), config.romfs_dir, settings.layout_language)
            cache[None] = LayoutIndex.from_folders(layout_folders(*where), fallback_folders(*where))
        return cache[None]

    kept = 0
    found = import_states(paths, session, local_candidates(), layouts, max_slots=settings.max_slots,
                          max_panes=settings.max_panes_per_group)
    for path, signature, reason in found:
        if signature:
            kept += 1
            print(f"{path.name}: kept, screen {signature}")
        else:
            print(f"{path.name}: not kept, {reason}")
            LOG.warning("state %s not kept: %s", path, reason)
    print(f"{kept} of {len(paths)} kept in {session.root}")
    return 0 if kept == len(paths) else 1


def live(root: Path, name: str | None, settings, config, headless: bool) -> int:
    service = RecorderService(settings, root, config.get("emulator_dir"), config.romfs_dir, local_candidates(),
                              FrameMarks.from_code_space(settings.frame_marks_variable), session=name)
    if headless:
        stop = threading.Event()
        thread = threading.Thread(target=service.run, args=(stop,), daemon=True)
        thread.start()
        last = None
        try:
            while True:
                status = service.status()
                line = " | ".join(f"{w['label']}: {w['status']}, {w['screen_name'] or w['screen'] or '-'}"
                                  for w in status["windows"]) or S.tr(S.HEADLESS_WAITING)
                line += " | " + S.tr(S.HEADLESS_COUNTS, screens=status["screens"], variants=status["variants"])
                if line != last:
                    print(time.strftime("%H:%M:%S"), line, flush=True)
                    last = line
                time.sleep(0.5)
        except KeyboardInterrupt:
            stop.set()
            thread.join(timeout=5)
        return 0
    from PySide6.QtWidgets import QApplication

    from mh4u_rando.gamegui.recorder.window import RecorderWindow
    app = QApplication.instance() or QApplication(sys.argv)
    window = RecorderWindow(service)
    window.show()
    return app.exec()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", nargs="+", type=Path, help="save states (.cst) to import as snapshots")
    parser.add_argument("--headless", action="store_true", help="record without a window")
    parser.add_argument("--session", help="the session's folder name (default: the date and time)")
    parser.add_argument("--root", type=Path, help="instead of the main checkout's work/ui")
    parser.add_argument("--lang", choices=("es", "en"), help="the window's language (default: the edition's)")
    args = parser.parse_args(argv)
    S.set_language(args.lang)
    config = local_config.load()
    root = args.root or ui_root()
    settings = load_settings()
    setup_log(root)
    if args.state:
        return states(args.state, root, args.session, settings, config)
    return live(root, args.session, settings, config, args.headless)


if __name__ == "__main__":
    sys.exit(main())
