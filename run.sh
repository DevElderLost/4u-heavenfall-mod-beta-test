#!/bin/sh
# Starts the program from this folder on Linux or macOS: sh run.sh
# The first run makes a Python environment in .venv with the packages the program needs, at the versions
# requirements.txt names; a run whose install failed starts over. Another Python: PYTHON=python3.13 sh run.sh
set -e
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if [ ! -f .venv/installed ]; then
    if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
        echo "The program needs Python 3.12 or newer. Install it, or name one: PYTHON=python3.13 sh run.sh" >&2
        exit 1
    fi
    rm -rf .venv
    if ! "$PYTHON" -m venv .venv; then
        rm -rf .venv
        echo "Python could not make its environment. On Debian or Ubuntu, install python3-venv first." >&2
        exit 1
    fi
    grep -E '^(PySide6|numpy|zstandard)==' requirements.txt > .venv/packages.txt
    .venv/bin/python -m pip install -r .venv/packages.txt
    touch .venv/installed
fi
exec .venv/bin/python -m core.gui "$@"
