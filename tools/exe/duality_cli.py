"""duality-cli.exe's entry point (tools/duality.spec): the same as `python -m mh4u_rando`."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from mh4u_rando.__main__ import main
    sys.exit(main())
