"""<updater>.exe's entry point (tools/release/heavenfall.spec): the console program that brings the program and the
installed mod to the latest published release (core/install/self_update.py)."""

import sys

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")     # a console that cannot show an accent shows "?" instead of failing
        except (AttributeError, ValueError):
            pass
    from core.install.self_update import main
    sys.exit(main())
