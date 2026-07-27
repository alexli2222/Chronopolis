#!/bin/bash
#
# Launch Chronopolis (Linux). Run with `bash run.sh` or `./run.sh` (after
# `chmod +x run.sh`). Finds the virtual environment - the installer creates it
# in the parent folder, and a dev checkout usually has it alongside - then runs
# src/chronopolis.py.
#
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"

# Prefer a project virtual environment; fall back to system Python.
if [ -x "$DIR/.venv/bin/python" ]; then
    PY="$DIR/.venv/bin/python"          # venv alongside this script (dev layout)
elif [ -x "$DIR/../.venv/bin/python" ]; then
    PY="$DIR/../.venv/bin/python"       # venv in the installer's folder (installed)
else
    PY="$(command -v python3 || command -v python)"
fi

if [ -z "$PY" ]; then
    echo "Could not find Python or a virtual environment. Run the installer first."
    exit 1
fi

"$PY" "$DIR/src/chronopolis.py"
