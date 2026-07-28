#!/bin/bash
#
# Launch Chronopolis (macOS / Linux). Run with `bash run.sh` or `./run.sh`.
#
# Flow:  check the released version -> if newer, hand off (kill self) to
# update.sh, which refreshes the files and re-runs this script -> launch the app.
#
# The version check is lightweight: it downloads only the tiny VERSION file (via
# curl/wget), not the whole repo. Offline or no update -> it just launches.
#
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"

REMOTE_VERSION_URL="https://raw.githubusercontent.com/alexli2222/Chronopolis/main/VERSION"

# True if version $1 is strictly newer than $2 (numeric, dot-separated).
_version_newer() {
    [ "$1" = "$2" ] && return 1
    newest="$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n 2>/dev/null | tail -n1)"
    [ "$newest" = "$1" ]
}

# ---- version check (skipped by the re-launch after an update) ----------------
if [ -z "${CHRONOPOLIS_UPDATED:-}" ] && [ -f "$DIR/update.sh" ] && [ -f "$DIR/VERSION" ]; then
    local_ver="$(tr -d '[:space:]' < "$DIR/VERSION" 2>/dev/null)"
    remote_ver=""
    if command -v curl >/dev/null 2>&1; then
        remote_ver="$(curl -fsS --max-time 5 "$REMOTE_VERSION_URL" 2>/dev/null | tr -d '[:space:]')"
    elif command -v wget >/dev/null 2>&1; then
        remote_ver="$(wget -qO- --timeout=5 "$REMOTE_VERSION_URL" 2>/dev/null | tr -d '[:space:]')"
    fi
    if [ -n "$remote_ver" ] && _version_newer "$remote_ver" "$local_ver"; then
        echo "A newer Chronopolis is available ($local_ver -> $remote_ver). Updating ..."
        # Kill self and hand off to update.sh; it refreshes the files and then
        # re-runs the (now updated) run script, which launches the app.
        exec bash "$DIR/update.sh" --then-run
    fi
fi

# ---- launch -----------------------------------------------------------------
# Prefer a project virtual environment; fall back to system Python.
if [ -x "$DIR/.venv/bin/python" ]; then
    PY="$DIR/.venv/bin/python"          # venv alongside this script (installed / dev)
elif [ -x "$DIR/../.venv/bin/python" ]; then
    PY="$DIR/../.venv/bin/python"       # venv one level up (older layout)
else
    PY="$(command -v python3 || command -v python)"
fi

if [ -z "$PY" ]; then
    echo "Could not find Python or a virtual environment. Run fix-installation.sh."
    exit 1
fi

exec "$PY" "$DIR/src/chronopolis.py"
