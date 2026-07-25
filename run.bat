@echo off
REM
REM Launch Chronopolis (Windows). Double-click, or run from a command prompt.
REM Finds the virtual environment - the installer creates it in the parent
REM folder, and a dev checkout usually has it alongside - then runs
REM src\chronopolis.py.
REM
cd /d "%~dp0"

REM Prefer a project virtual environment; fall back to system Python.
set "PY="
if exist "%CD%\.venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"
if not defined PY if exist "%CD%\..\.venv\Scripts\python.exe" set "PY=%CD%\..\.venv\Scripts\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py"

if not defined PY (
    echo Could not find Python or a virtual environment. Run the installer first.
    pause
    exit /b 1
)

"%PY%" "%CD%\src\chronopolis.py"
