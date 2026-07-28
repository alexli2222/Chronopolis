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
REM and by fix-installation.bat as its terminal step (without the flag, to just
REM refresh the files after everything else it does has finished).
REM
REM Self-replacement: cmd holds the running .bat files (update.bat, run.bat,
REM fix-installation.bat) open, so git's reset cannot overwrite them in place -
REM they would otherwise stay one version behind forever. So after the reset we
REM extract the fresh copies from git, and if any differ we launch a detached
REM PowerShell swapper that waits for this process tree to exit (releasing the
REM locks), moves the new copies into place, and relaunches the app if we were
REM mid-run. On POSIX this is unnecessary - see update.sh - because git replaces
REM files by a new inode and the shell exec-chains through them.
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
set "REF=origin/main"
git reset --hard origin/main >nul 2>&1
if errorlevel 1 (echo   update failed ^(git reset^) - keeping current files.) else (echo   updated to the latest version.)
goto self_replace
:offline
REM Offline: still restore any missing/changed tracked files to the local commit.
set "REF=HEAD"
git reset --hard HEAD >nul 2>&1
if errorlevel 1 (echo   offline - could not restore files.) else (echo   offline - restored files to the installed version.)
goto self_replace

:self_replace
REM The reset above could not overwrite any launcher script that cmd currently
REM holds open. Extract the fresh copies and, if any differ, hand off to a
REM detached swapper. Needs PowerShell (built into Windows 10+); if it is
REM missing we simply skip - no worse than before.
where powershell >nul 2>&1 || goto after_update
set "NEEDSWAP="
for %%F in (update.bat run.bat fix-installation.bat) do (
    git show %REF%:%%F > "%%F.new" 2>nul
    if exist "%%F.new" (
        fc /b "%%F" "%%F.new" >nul 2>&1
        if errorlevel 1 (set "NEEDSWAP=1") else (del "%%F.new" >nul 2>&1)
    )
)
if not defined NEEDSWAP goto after_update

set "RUNVAL=$false"
if "%~1"=="--then-run" set "RUNVAL=$true"

REM Write the swapper (PowerShell keeps this readable and avoids batch escaping).
set "PS1=%TEMP%\chronopolis_swap_%RANDOM%.ps1"
> "%PS1%" echo $ErrorActionPreference = 'SilentlyContinue'
>> "%PS1%" echo Set-Location -LiteralPath '%CD%'
>> "%PS1%" echo $files = @('update.bat','run.bat','fix-installation.bat')
>> "%PS1%" echo for ($i = 0; $i -lt 120; $i++) {
>> "%PS1%" echo   $pending = $false
>> "%PS1%" echo   foreach ($f in $files) {
>> "%PS1%" echo     if (Test-Path -LiteralPath ($f + '.new')) {
>> "%PS1%" echo       try { Move-Item -Force -LiteralPath ($f + '.new') -Destination $f -ErrorAction Stop } catch { $pending = $true }
>> "%PS1%" echo     }
>> "%PS1%" echo   }
>> "%PS1%" echo   if (-not $pending) { break }
>> "%PS1%" echo   Start-Sleep -Milliseconds 500
>> "%PS1%" echo }
>> "%PS1%" echo $run = %RUNVAL%
>> "%PS1%" echo if ($run) { $env:CHRONOPOLIS_UPDATED = '1'; Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','run.bat' -WorkingDirectory (Get-Location).Path }
>> "%PS1%" echo Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -ErrorAction SilentlyContinue

echo   refreshing launcher scripts ...
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
REM Exit the whole chain so cmd releases the .bat files and the swapper can
REM replace them. The swapper relaunches the app if we were mid-run.
exit /b 0

:after_update
REM No launcher scripts changed. When asked, hand off to run.bat to launch the
REM app. The flag stops run.bat checking again, so there is no update loop.
if "%~1"=="--then-run" (
    set "CHRONOPOLIS_UPDATED=1"
    call "run.bat"
)
