"""The program's entry point (tools/release/heavenfall.spec): the same as `python -m core.gui`."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()     # nothing starts a process today; one that did would reopen the window
    from core.gui.__main__ import main
    sys.exit(main())
