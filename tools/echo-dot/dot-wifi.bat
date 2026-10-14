@echo off
rem Puts a rooted Echo Dot (2nd gen) on your phone's hotspot, so your dragon can talk through it.
rem Before running: open wifi.txt, put your hotspot name on line 1 and its password
rem on line 2, and save it. The file is copied to the Dot, used, and deleted there.
rem This saves one Wi-Fi network on the Dot (it can be removed again later).
setlocal
cd /d "%~dp0"
set "OUT=dot-wifi.txt"
where adb >nul 2>nul || (echo Can't find adb. Put this folder's files next to adb.exe (platform-tools), or add adb to PATH. & pause & exit /b 1)
for %%f in (wifi.txt on-the-dot.sh) do if not exist %%f (echo %%f must be in the same folder as this file. & pause & exit /b 1)
findstr /c:"YourHotspotName" wifi.txt >nul && (echo Please put your real hotspot name and password in wifi.txt first. & pause & exit /b 1)
echo Make sure your phone's hotspot is ON.
adb wait-for-device
adb push wifi.txt /data/local/tmp/wifi.txt >nul
adb push on-the-dot.sh /data/local/tmp/on-the-dot.sh >nul
echo Adding the network and waiting for the Dot to connect (about 40 seconds)...
adb shell "sh /data/local/tmp/on-the-dot.sh; rm -f /data/local/tmp/on-the-dot.sh /data/local/tmp/wifi.txt" > "%OUT%" 2>&1
echo.
echo ===== Trying to reach the Dot over Wi-Fi from this computer (needs this computer on the hotspot too)
rem the Dot's address is on the "ip_address=" line of the Wi-Fi status
for /f "tokens=2 delims==" %%a in ('findstr /b /c:"ip_address=" "%OUT%"') do set "DOTIP=%%a"
if defined DOTIP (
  echo Dot address: %DOTIP%
  >> "%OUT%" echo ===== adb connect %DOTIP%:5555 from the computer
  adb connect %DOTIP%:5555 >> "%OUT%" 2>&1
  adb -s %DOTIP%:5555 shell "id; echo wifi-adb-works" >> "%OUT%" 2>&1
  adb disconnect %DOTIP%:5555 >nul 2>&1
) else (
  echo The Dot didn't get an address. See dot-wifi.txt.
)
echo.
echo Done. What happened is in dot-wifi.txt (your password is not in it).
echo You can now delete wifi.txt from this folder, since it holds your password.
pause
