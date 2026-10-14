#!/bin/bash
# macOS / Linux version of dot-reconnect.bat: turns the Echo Dot's saved hotspot back on
# after a restart. Plug the Dot in by USB first. Run:  bash dot-reconnect.command
command -v adb >/dev/null || { echo "Can't find adb (macOS: brew install android-platform-tools; Linux: sudo apt install adb)."; exit 1; }
echo "Waiting for the Dot (plug it in by USB)..."
adb wait-for-device
echo "Switching its saved Wi-Fi back on..."
adb shell "wpa_cli -i wlan0 enable_network all >/dev/null; wpa_cli -i wlan0 save_config >/dev/null; sleep 12; wpa_cli -i wlan0 status | grep -E '^(ssid|wpa_state|ip_address)='"
echo
echo "If it says wpa_state=COMPLETED with an ip_address, it's back on your hotspot."
