#!/bin/bash
#
# update.sh - update Chronopolis in place to the latest released version.
#
# It runs inside the installed folder (a git checkout) and does an efficient git
# update: fetch, then hard-reset the tracked files to the repository. git is
# content-addressed, so only changed files are transferred - unchanged files are
# not re-downloaded. Your virtual environment, outputs, and preferences are
# untracked (git-ignored) and are left untouched.
#
# Called by run.sh (with --then-run, which launches the refreshed app afterward)
# and by fix-installation.sh as its terminal step (without the flag - it just
# refreshes the files; fix-installation execs into this so its own script can be
# safely overwritten by the reset).
#
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"

if [ ! -d .git ]; then
    echo "This folder is not a git checkout - cannot update."
    echo "Reinstall from the latest installer release:"
    echo "  https://github.com/alexli2222/Chronopolis/releases"
    [ "${1:-}" = "--then-run" ] && CHRONOPOLIS_UPDATED=1 exec bash "$DIR/run.sh"
    exit 1
fi

echo "Updating files ..."
if git fetch origin >/dev/null 2>&1; then
    git reset --hard origin/main >/dev/null 2>&1 && echo "  updated to the latest version." \
        || echo "  update failed (git reset) - keeping current files."
else
    # Offline: still restore any missing/changed tracked files to the local commit.
    git reset --hard HEAD >/dev/null 2>&1 && echo "  offline - restored files to the installed version." \
        || echo "  offline - could not restore files."
fi

# When asked, hand off to the refreshed run script to launch the app. The flag
# stops run.sh from checking again, so there is no update loop.
if [ "${1:-}" = "--then-run" ]; then
    CHRONOPOLIS_UPDATED=1 exec bash "$DIR/run.sh"
fi
