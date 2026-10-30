"""The program's entry point (tools/duality.spec): the same as `python -m mh4u_rando.gui`."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()     # nothing starts a process today; one that did would reopen the window
    from mh4u_rando.gui.__main__ import main
    sys.exit(main())
