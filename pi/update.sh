#!/bin/bash
# Update BT Dragon's code without reinstalling everything.
# Copy the new "pi" folder to the Pi (see README, "Updating"), then run:
#   sudo bash ~/bt-dragon-new/update.sh
set -e
if [ "$(id -u)" != "0" ]; then echo "Please run with sudo:  sudo bash $0"; exit 1; fi
SRC="$(cd "$(dirname "$0")" && pwd)"
echo "== Updating BT Dragon from $SRC"
rm -rf /opt/bt-dragon/bt_dragon
cp -r "$SRC/bt_dragon" /opt/bt-dragon/
chmod -R a+rX /opt/bt-dragon/bt_dragon   # readable by everyone (files copied from Windows arrive private)
cp "$SRC/bt-dragon.service" /etc/systemd/system/bt-dragon.service
cp "$SRC/install-voice.sh" /opt/bt-dragon/install-voice.sh   # kept here, since the copied folder is deleted afterwards
# keep the copy on the boot partition current too, for future reinstalls
BOOT=/boot/firmware; [ -d "$BOOT" ] || BOOT=/boot
if [ -d "$BOOT/bt-dragon" ] && [ "$SRC" != "$BOOT/bt-dragon" ]; then
  rm -rf "$BOOT/bt-dragon" && cp -r "$SRC" "$BOOT/bt-dragon" || true
fi
systemctl daemon-reload
bash "$SRC/gentle-card.sh" || true      # the system log in memory, not on the card
if ! command -v rtl_433 >/dev/null || ! command -v rtl_adsb >/dev/null; then
  echo "== Adding the radio stick's programs (rtl-sdr, rtl-433), for planes and little radios"
  { apt-get update -qq && apt-get install -y -qq rtl-sdr rtl-433; } >/dev/null 2>&1 \
    || echo "   (Couldn't add them now: no internet? Later: sudo apt-get install -y rtl-sdr rtl-433)"
fi
if [ ! -x /opt/bt-dragon/piper/piper ] || ! command -v adb >/dev/null; then
  echo "== Tip: for Harald's voice through an Echo Dot, also run:  sudo bash /opt/bt-dragon/install-voice.sh"
fi
echo "== Restarting your dragon (a few seconds' nap)"
systemctl restart bt-dragon
sleep 3
systemctl is-active --quiet bt-dragon && echo "== Done. Your dragon is awake." || \
  { echo "Your dragon didn't start. Last log lines:"; journalctl -u bt-dragon -n 20 --no-pager; }
