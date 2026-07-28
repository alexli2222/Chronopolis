#!/bin/bash
#
# fix-installation.sh - repair a Chronopolis installation IN PLACE.
#
# Run it from inside the installed folder when the app misbehaves. Unlike the
# installer (which creates the folder), this repairs the folder it lives in: it
# checks the dependencies, restores any missing or changed files and updates to
# the latest version (by calling update.sh), then rebuilds the virtual
# environment and reinstalls the Python dependencies.
#
set -u
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"
RELEASES="https://github.com/alexli2222/Chronopolis/releases"

reinstall_hint() {
    echo
    echo "If Chronopolis still does not work, reinstall it from scratch:"
    echo "download the newest installer release from"
    echo "  $RELEASES"
}

echo "=== Chronopolis: fix installation ==="

# ---- checks (Python 3.11+, a compiler for 3.14+, ffmpeg, git) ----------
PY=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "Python 3.11+ was not found - cannot rebuild the environment."
    reinstall_hint
    exit 1
fi
if ! command -v git >/dev/null 2>&1; then
    echo "git was not found - cannot verify or update the files."
    reinstall_hint
    exit 1
fi
if "$PY" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 14) else 1)' 2>/dev/null; then
    if [ "$(uname -s)" = "Darwin" ]; then
        xcode-select -p >/dev/null 2>&1 || echo "Warning: Python 3.14+ needs the Xcode Command Line Tools (xcode-select --install) to build moderngl."
    elif ! command -v cc >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1; then
        echo "Warning: Python 3.14+ needs a C/C++ compiler (build-essential / gcc-c++) to build moderngl."
    fi
fi
command -v ffmpeg >/dev/null 2>&1 || echo "Warning: ffmpeg not found - videos will not render until it is installed."

# ---- 1. restore/verify files + update to latest (via update.sh) -------
echo
echo "Verifying files and updating ..."
bash "$DIR/update.sh"

# ---- 2. virtual environment -------------------------------------------
echo
if [ -x ".venv/bin/python" ]; then
    echo "Virtual environment present."
else
    echo "Rebuilding virtual environment (.venv) ..."
    "$PY" -m venv .venv || { echo "Could not create the virtual environment."; reinstall_hint; exit 1; }
fi

# ---- 3. dependencies --------------------------------------------------
echo "Reinstalling dependencies (numpy, manim, tkinterdnd2) ..."
.venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1
.venv/bin/python -m pip install numpy manim tkinterdnd2 || echo "Some dependencies failed to install."

echo
echo "Repair complete. Launch the app with:  bash $DIR/run.sh"
reinstall_hint
