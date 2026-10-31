"""heavenfall-cli.exe's entry point (tools/release/heavenfall.spec): the same as `python -m core`."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from core.app.cli import main
    sys.exit(main())
