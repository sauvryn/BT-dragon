@echo off
rem Turns the Echo Dot's saved hotspot back on after a restart or power cut.
rem (On an Echo that hasn't been set up in the Alexa app, Amazon's Wi-Fi service switches
rem saved networks off each time it starts. The network is still saved, so no password
rem is needed.) Plug the Dot into this computer by USB first.
setlocal
cd /d "%~dp0"
set "PATH=%~dp0;%PATH%"
where adb >nul 2>nul || (echo Can't find adb. Put this file next to adb.exe ^(platform-tools^), or add adb to PATH. & pause & exit /b 1)
echo Waiting for the Dot (plug it in by USB)...
adb wait-for-device
echo Switching its saved Wi-Fi back on...
adb shell "wpa_cli -i wlan0 enable_network all >/dev/null; wpa_cli -i wlan0 save_config >/dev/null; sleep 12; wpa_cli -i wlan0 status | grep -E '^(ssid|wpa_state|ip_address)='"
echo.
echo If it says wpa_state=COMPLETED with an ip_address, it's back on your hotspot.
echo Unplug it from this computer, power it normally, and your dragon will find it
echo within a minute or two. If not, make sure the hotspot is on and run this again.
pause
