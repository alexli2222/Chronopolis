@echo off
REM
REM fix-installation.bat - repair a Chronopolis installation IN PLACE.
REM
REM Run it from inside the installed folder when the app misbehaves. Unlike the
REM installer (which creates the folder), this repairs the folder it lives in: it
REM checks the dependencies, restores any missing or changed files and updates to
REM the latest version (by calling update.bat), then rebuilds the virtual
REM environment and reinstalls the Python dependencies.
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

REM ---- 1. restore/verify files + update to latest (via update.bat) -------
echo.
echo Verifying files and updating ...
call "update.bat"

REM ---- 2. virtual environment -------------------------------------------
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

REM ---- 3. dependencies --------------------------------------------------
echo Reinstalling dependencies (numpy, manim, tkinterdnd2) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install numpy manim tkinterdnd2
if errorlevel 1 echo Some dependencies failed to install.

echo.
echo Repair complete. Launch the app by double-clicking run.bat.
echo.
echo If Chronopolis still does not work, reinstall it from scratch:
echo download the newest installer release from
echo   %RELEASES%
pause
exit /b 0

:reinstall_hint_exit
echo.
echo If Chronopolis still does not work, reinstall it from scratch:
echo download the newest installer release from
echo   %RELEASES%
pause
exit /b 1
