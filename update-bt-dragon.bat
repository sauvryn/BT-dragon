@echo off
rem Update your BT Dragon from this folder. Double-click me after extracting a new BT Dragon zip.
setlocal
cd /d "%~dp0"
if not exist "pi\update.sh" (
  echo Can't find the "pi" folder next to this file. Keep this file in the extracted folder.
  pause & exit /b 1
)
rem Your answers are remembered in %USERPROFILE%\.bt_dragon_updater for next time.
set "CFG=%USERPROFILE%\.bt_dragon_updater"
set "SAVED_USER="
set "SAVED_HOST="
if exist "%CFG%" (
  for /f "usebackq tokens=1,* delims==" %%a in ("%CFG%") do (
    if "%%a"=="user" set "SAVED_USER=%%b"
    if "%%a"=="host" set "SAVED_HOST=%%b"
  )
)
if not defined SAVED_HOST set "SAVED_HOST=bt-dragon.local"

echo Your LOGIN NAME on the Pi: the username you chose in Raspberry Pi Imager
echo (the part before @ in  ssh name@bt-dragon.local). Not the Pi's own name.
set "DUSER="
if defined SAVED_USER (
  set /p DUSER=Login name [press Enter to keep "%SAVED_USER%"]: 
) else (
  set /p DUSER=Login name: 
)
if not defined DUSER set "DUSER=%SAVED_USER%"
if not defined DUSER ( echo No login name given. & pause & exit /b 1 )

echo.
echo The Pi's ADDRESS: bt-dragon.local, or its IP address if that doesn't work
echo (your phone's hotspot screen lists it, e.g. 172.20.10.3).
set "DHOST="
set /p DHOST=Address [press Enter to keep "%SAVED_HOST%"]: 
if not defined DHOST set "DHOST=%SAVED_HOST%"

> "%CFG%" (
  echo user=%DUSER%
  echo host=%DHOST%
)

echo.
echo == Copying the new code to %DUSER%@%DHOST%  (type the Pi's password if asked)
rem a fresh folder name each time, so a leftover copy can never get in the way
set "DEST=bt-dragon-new-%RANDOM%%RANDOM%"
scp -r -q pi %DUSER%@%DHOST%:%DEST% || ( echo Copy failed. Is the dragon on, and is this computer on the same hotspot? & pause & exit /b 1 )
echo.
echo == Installing and restarting your dragon
ssh -t %DUSER%@%DHOST% "sudo bash ~/%DEST%/update.sh; rm -rf ~/%DEST% ~/bt-dragon-new"
echo.
pause
