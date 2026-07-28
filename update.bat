@echo off
REM
REM update.bat - update Chronopolis in place to the latest released version.
REM
REM Runs inside the installed folder (a git checkout) and does an efficient git
REM update: fetch, then hard-reset the tracked files to the repository. git is
REM content-addressed, so only changed files are transferred - unchanged files
REM are not re-downloaded. The virtual environment, outputs, and preferences are
REM untracked (git-ignored) and are left untouched.
REM
REM Called by run.bat (with --then-run, which launches the refreshed app after)
REM and by fix-installation.bat (without it, to just refresh the files).
REM
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".git" (
    echo This folder is not a git checkout - cannot update.
    echo Reinstall from the latest installer release:
    echo   https://github.com/alexli2222/Chronopolis/releases
    if "%~1"=="--then-run" (set "CHRONOPOLIS_UPDATED=1" & call "run.bat")
    exit /b 1
)

echo Updating files ...
git fetch origin >nul 2>&1
if errorlevel 1 goto offline
git reset --hard origin/main >nul 2>&1
if errorlevel 1 (echo   update failed ^(git reset^) - keeping current files.) else (echo   updated to the latest version.)
goto after_update
:offline
REM Offline: still restore any missing/changed tracked files to the local commit.
git reset --hard HEAD >nul 2>&1
if errorlevel 1 (echo   offline - could not restore files.) else (echo   offline - restored files to the installed version.)
:after_update

REM When asked, hand off to the refreshed run script to launch the app. The flag
REM stops run.bat from checking again, so there is no update loop.
if "%~1"=="--then-run" (
    set "CHRONOPOLIS_UPDATED=1"
    call "run.bat"
)
