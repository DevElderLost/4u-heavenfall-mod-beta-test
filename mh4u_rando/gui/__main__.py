"""Starts the Qt app: `python -m mh4u_rando.gui`, the `duality` command and the Windows program (tools/build_exe.py).

Without PySide6 (running from source) it says how to install it instead of ending in a traceback.
"""

import sys
from pathlib import Path

from ..edition import edition

LOG_PATH = edition().home / f"{edition().app_name.lower()}.log"

MISSING_PYSIDE6 = (
    "The graphical interface needs PySide6, which is not installed.\n"
    "Install it with:  python -m pip install PySide6\n"
    "(or every package the project pins:  python -m pip install -r requirements.txt)\n"
    "and start again.  The command line works without it:  python -m mh4u_rando --help\n"
)


def keep_streams(log_path: Path = LOG_PATH) -> None:
    """A windowed Windows program (the app's .exe) has no stdout or stderr: anything that prints would raise.
    They go to `log_path` (rewritten at each start), where a crash leaves its traceback."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, "w", encoding="utf-8", buffering=1)
    except OSError:
        log = open("NUL" if sys.platform == "win32" else "/dev/null", "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


def main(argv: list[str] | None = None) -> int:
    keep_streams()
    try:
        from .qt.app import main as run
    except ImportError as error:
        if (error.name or "").split(".")[0] != "PySide6":
            raise
        if isinstance(error, ModuleNotFoundError):
            sys.stderr.write(MISSING_PYSIDE6)
        else:       # PySide6 is installed but Qt cannot load (a DLL, a plugin): the error says which
            sys.stderr.write(f"PySide6 could not be loaded: {error}\n")
        return 1
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
