#!/bin/bash
# Update your BT Dragon from this folder (macOS and Linux).
# After extracting a new BT Dragon zip, open Terminal in the extracted folder and run:
#     bash update-bt-dragon.sh
set -e
cd "$(dirname "$0")"
if [ ! -f pi/update.sh ]; then
  echo "Can't find the \"pi\" folder next to this script. Run it from the extracted folder."
  exit 1
fi

# Your answers are remembered here for next time.
CFG="$HOME/.bt_dragon_updater"
SAVED_USER=""; SAVED_HOST="bt-dragon.local"
if [ -f "$CFG" ]; then
  while IFS='=' read -r k v; do
    case "$k" in user) SAVED_USER="$v" ;; host) [ -n "$v" ] && SAVED_HOST="$v" ;; esac
  done < "$CFG"
fi

echo "Your LOGIN NAME on the Pi: the username you chose in Raspberry Pi Imager"
echo "(the part before @ in  ssh name@bt-dragon.local). Not the Pi's own name."
if [ -n "$SAVED_USER" ]; then
  read -r -p "Login name [press Enter to keep \"$SAVED_USER\"]: " DUSER
else
  read -r -p "Login name: " DUSER
fi
DUSER="${DUSER:-$SAVED_USER}"
[ -n "$DUSER" ] || { echo "No login name given."; exit 1; }

echo
echo "The Pi's ADDRESS: bt-dragon.local, or its IP address if that doesn't work"
echo "(your phone's hotspot screen lists it, e.g. 172.20.10.3)."
read -r -p "Address [press Enter to keep \"$SAVED_HOST\"]: " DHOST
DHOST="${DHOST:-$SAVED_HOST}"

printf 'user=%s\nhost=%s\n' "$DUSER" "$DHOST" > "$CFG"

# a fresh folder name each time, so a leftover copy can never get in the way
DEST="bt-dragon-new-$RANDOM$RANDOM"
echo
echo "== Copying the new code to $DUSER@$DHOST  (type the Pi's password if asked)"
if ! scp -r -q pi "$DUSER@$DHOST:$DEST"; then
  echo "Copy failed. Is the dragon on, and is this computer on the same hotspot?"
  exit 1
fi
echo
echo "== Installing and restarting your dragon"
ssh -t "$DUSER@$DHOST" "sudo bash ~/$DEST/update.sh; rm -rf ~/$DEST ~/bt-dragon-new"
