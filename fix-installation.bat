@echo off
REM
REM fix-installation.bat - repair a Chronopolis installation IN PLACE.
REM
REM Run it from inside the installed folder when the app misbehaves. Unlike the
REM installer (which creates the folder), this repairs the folder it lives in: it
REM checks the dependencies, rebuilds the virtual environment, reinstalls the
REM Python dependencies, and then - as its very last action - hands off to
REM update.bat to restore any missing/changed files and update to the latest
REM version.
REM
REM update.bat is the TERMINAL step on purpose: git's reset may rewrite tracked
REM files. Everything this script needs to do runs before that hand-off, so once
REM update.bat runs this script has finished its work.
REM
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "RELEASES=https://github.com/alexli2222/Chronopolis/releases"

echo === Chronopolis: fix installation ===

REM ---- checks (Python 3.11+, a compiler for 3.14+, ffmpeg, git) ----------
set "PY="
for %%V in (3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "PY=py -%%V"
    )
)
for %%C in (python py) do (
    if not defined PY (
        %%C -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "PY=%%C"
    )
)
if not defined PY (
    echo Python 3.11+ was not found - cannot rebuild the environment.
    goto reinstall_hint_exit
)
where git >nul 2>&1
if errorlevel 1 (
    echo git was not found - cannot verify or update the files.
    goto reinstall_hint_exit
)
%PY% -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,14) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "HAVE_COMPILER="
    where gcc >nul 2>&1 && set "HAVE_COMPILER=1"
    where cl >nul 2>&1 && set "HAVE_COMPILER=1"
    if not defined HAVE_COMPILER echo Warning: Python 3.14+ needs a C++ compiler (MSVC C++ Build Tools) to build moderngl.
)
where ffmpeg >nul 2>&1
if errorlevel 1 echo Warning: ffmpeg not found - videos will not render until it is installed.

REM ---- 1. virtual environment -------------------------------------------
echo.
if exist ".venv\Scripts\python.exe" (
    echo Virtual environment present.
) else (
    echo Rebuilding virtual environment .venv ...
    %PY% -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo Could not create the virtual environment.
    goto reinstall_hint_exit
)

REM ---- 2. dependencies --------------------------------------------------
echo Reinstalling dependencies (numpy, manim, tkinterdnd2) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install numpy manim tkinterdnd2
if errorlevel 1 echo Some dependencies failed to install.

REM ---- 3. restore/verify files + update (TERMINAL step) -----------------
REM This is the last thing we do. We reach it only after all of the above has
REM finished, then hand off to update.bat, so its git reset is free to refresh
REM the tracked files. Launch the app afterward by double-clicking run.bat.
echo.
echo Dependencies ready.
call :reinstall_hint
echo.
echo Final step: verifying and updating project files ...
call "update.bat"
exit /b 0

:reinstall_hint
echo.
echo If Chronopolis still does not work, reinstall it from scratch:
echo download the newest installer release from
echo   %RELEASES%
goto :eof

:reinstall_hint_exit
call :reinstall_hint
pause
exit /b 1
