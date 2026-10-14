#!/bin/bash
# BT Dragon installer. Run on the Pi:   sudo bash /boot/firmware/bt-dragon/install.sh
# Safe to run again: it updates the code and keeps your dragon's memory and settings.
set -e

if [ "$(id -u)" != "0" ]; then
  echo "Please run with sudo:  sudo bash $0"; exit 1
fi

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/bt-dragon
BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot

say() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }

say "Checking the internet connection"
# Only fetch the response headers (a few hundred bytes), allow 30 s, and try 3 times,
# so a slow or busy connection isn't mistaken for no connection.
online=0
for try in 1 2 3; do
  if curl -sI --max-time 30 -o /dev/null https://github.com; then online=1; break; fi
  echo "  ...no answer yet (attempt $try of 3)"; sleep 5
done
if [ "$online" != "1" ]; then
  echo "Can't reach the internet. Is his network on, 2.4 GHz, and is a VPN on this network paused?"
  echo "If it's on but very slow (big uploads or downloads running), pause them and try again."
  exit 1
fi

say "Installing system packages (this can take 10+ minutes on a Pi Zero)"
apt-get update
apt-get install -y python3-venv python3-pil bluez iw git rfkill
# screen-driver helpers: names differ a little between OS releases, so try each one
for pkg in python3-spidev python3-gpiozero python3-lgpio; do
  apt-get install -y "$pkg" || echo "(skipping $pkg)"
done

say "Turning on SPI (the e-ink screen's connection)"
raspi-config nonint do_spi 0 || true

say "Copying BT Dragon to $DEST"
mkdir -p "$DEST"
rm -rf "$DEST/bt_dragon"
cp -r "$SRC/bt_dragon" "$DEST/"
chmod -R a+rX "$DEST/bt_dragon"

say "Setting up Python and the Bluetooth library (bleak)"
[ -d "$DEST/venv" ] || python3 -m venv --system-site-packages "$DEST/venv"
"$DEST/venv/bin/pip" install --upgrade "bleak>=0.22,<4"

say "Fetching the Waveshare e-ink driver"
if [ ! -d "$DEST/vendor/waveshare_epd" ]; then
  tmp=$(mktemp -d)
  git clone -q --depth 1 --filter=blob:none --sparse https://github.com/waveshareteam/e-Paper "$tmp/e-Paper"
  (cd "$tmp/e-Paper" && git sparse-checkout set RaspberryPi_JetsonNano/python/lib/waveshare_epd)
  mkdir -p "$DEST/vendor"
  cp -r "$tmp/e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd" "$DEST/vendor/"
  rm -rf "$tmp"
fi

if [ ! -f "$BOOT/bt-dragon.toml" ]; then
  say "No settings file found: putting a starter one in $BOOT/bt-dragon.toml"
  cp "$SRC/bt-dragon.toml" "$BOOT/bt-dragon.toml"
fi

say "Stopping anything else that wants the screen or the radio"
# BT Dragon is meant for repurposed Pwnagotchi hardware. If this card still has Pwnagotchi's
# software on it, its services are switched off (not deleted) so they don't fight over the
# screen and the radio. On a fresh Raspberry Pi OS card there's nothing to stop.
for svc in pwnagotchi bettercap pwngrid-peer; do
  systemctl disable --now "$svc" 2>/dev/null || true
done

say "Giving him a voice (for the optional Echo Dot; skipped if the download fails)"
cp "$SRC/install-voice.sh" "$DEST/install-voice.sh"
bash "$DEST/install-voice.sh" || echo "(The voice didn't install. You can try again later: sudo bash $DEST/install-voice.sh)"

say "Installing the bt-dragon service"
mkdir -p /var/lib/bt-dragon
cp "$SRC/bt-dragon.service" /etc/systemd/system/bt-dragon.service
systemctl daemon-reload
systemctl enable bt-dragon

say "Done! Rebooting in 5 seconds. Your dragon will appear on the screen in about a minute."
echo "Afterwards, open  http://$(hostname).local:8080  (or http://<Pi's IP>:8080) on your phone."
if [ "$(hostname)" != "bt-dragon" ]; then
  echo "(This Pi is called \"$(hostname)\", not \"bt-dragon\", so use that name in the address above"
  echo " and when the updater asks for the Pi's address.)"
fi
sleep 5
reboot
