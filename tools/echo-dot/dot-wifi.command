#!/bin/bash
# macOS / Linux version of dot-wifi.bat: puts a rooted Echo Dot (2nd gen) on your phone's
# hotspot. Put your hotspot name on line 1 of wifi.txt and its password on line 2 first.
# Needs adb (macOS: brew install android-platform-tools; Linux: sudo apt install adb).
# Run:  bash dot-wifi.command   (on macOS you can also double-click it)
cd "$(dirname "$0")"
OUT=dot-wifi.txt
command -v adb >/dev/null || { echo "Can't find adb (see the top of this file)."; exit 1; }
for f in wifi.txt on-the-dot.sh; do [ -f "$f" ] || { echo "$f must be in the same folder as this file."; exit 1; }; done
grep -q YourHotspotName wifi.txt && { echo "Please put your real hotspot name and password in wifi.txt first."; exit 1; }
echo "Make sure your phone's hotspot is ON. Waiting for the Dot (plug it in by USB)..."
adb wait-for-device
adb push wifi.txt /data/local/tmp/wifi.txt >/dev/null
adb push on-the-dot.sh /data/local/tmp/on-the-dot.sh >/dev/null
echo "Adding the network and waiting for the Dot to connect (about 40 seconds)..."
adb shell "sh /data/local/tmp/on-the-dot.sh; rm -f /data/local/tmp/on-the-dot.sh /data/local/tmp/wifi.txt" > "$OUT" 2>&1
ip=$(grep '^ip_address=' "$OUT" | head -1 | cut -d= -f2 | tr -d '\r')
if [ -n "$ip" ]; then
  echo "Dot address: $ip"
  { echo "===== adb connect $ip:5555 from this computer"; adb connect "$ip:5555"; adb -s "$ip:5555" shell "id; echo wifi-adb-works"; } >> "$OUT" 2>&1
  adb disconnect "$ip:5555" >/dev/null 2>&1
else
  echo "The Dot didn't get an address. See $OUT."
fi
echo "Done. What happened is in $OUT (your password is not in it). You can delete wifi.txt now."
