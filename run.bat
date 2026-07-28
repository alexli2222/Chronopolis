@echo off
REM
REM Launch Chronopolis (Windows). Double-click, or run from a command prompt.
REM
REM Flow:  check the released version -> if it differs (the repo only moves
REM forward, so a difference means newer), hand off to update.bat, which
REM refreshes the files and re-runs this script -> launch the app.
REM
REM The version check is lightweight: it downloads only the tiny VERSION file
REM (via curl, built into Windows 10+), not the whole repo. Offline or no update
REM -> it just launches.
REM
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ---- version check (skipped by the re-launch after an update) --------------
if defined CHRONOPOLIS_UPDATED goto launch
if not exist "update.bat" goto launch
if not exist "VERSION" goto launch
where curl >nul 2>&1
if errorlevel 1 goto launch

set "LOCAL_VER="
for /f "usebackq delims=" %%v in ("VERSION") do if not defined LOCAL_VER set "LOCAL_VER=%%v"
set "REMOTE_VER="
for /f "usebackq delims=" %%v in (`curl -fsS --max-time 5 https://raw.githubusercontent.com/alexli2222/Chronopolis/main/VERSION 2^>nul`) do if not defined REMOTE_VER set "REMOTE_VER=%%v"

if not defined REMOTE_VER goto launch
if "!REMOTE_VER!"=="!LOCAL_VER!" goto launch

echo A newer Chronopolis is available (!LOCAL_VER! -^> !REMOTE_VER!). Updating ...
REM Hand off to update.bat; it refreshes the files and re-runs this script, which
REM launches the app.
call "update.bat" --then-run
goto :eof

:launch
REM Prefer a project virtual environment; fall back to system Python.
set "PY="
if exist "%CD%\.venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"
if not defined PY if exist "%CD%\..\.venv\Scripts\python.exe" set "PY=%CD%\..\.venv\Scripts\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py"

if not defined PY (
    echo Could not find Python or a virtual environment. Run fix-installation.bat.
    pause
    exit /b 1
)

"%PY%" "%CD%\src\chronopolis.py"
