#!/bin/bash
# Builds a small 32-bit Debian for the Echo Dot, on the Pi.
#
# The Dot runs Fire OS (Android), whose programs use a different C library from normal
# Linux, so Python, Vosk and Piper can't run on it directly. This makes a folder holding a
# minimal Debian (armhf: the Dot's 32-bit ARM type) with Python, Vosk, Piper, the speech
# model and Harald's voice in it. On the Dot, programs started "inside" that folder with
# chroot see it as the whole disk and find Debian's libraries, while still running on the
# Dot's own processor at full speed.
#
# The Pi can run 32-bit ARM programs itself, so it builds and tests the exact same files the
# Dot will use. Nothing here touches the Dot; push.sh copies the result across.
#
# Run on the Pi:   sudo bash /opt/bt-dragon/bt_dragon/dot_debian/build.sh
# Takes 15-30 minutes on a Pi Zero 2 and downloads about 70 MB. Safe to run again.
set -e
[ "$(id -u)" = 0 ] || { echo "Please run with sudo:  sudo bash $0"; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
BT=/opt/bt-dragon
OUT=$BT/dot-debian
ROOT=$OUT/root
SUITE=bookworm                       # Debian 12: happy on the Dot's older (3.18) kernel
MIRROR=http://deb.debian.org/debian
PIPER_VERSION=2023.11.14-2
say() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- mounts while building
# /proc and /dev are borrowed from the Pi while programs run inside the folder. They must
# always be let go of before anything is deleted, or deleting would reach the Pi's own /dev.
mounts_in_root() { grep -E " $ROOT/(proc|dev|sys)" /proc/mounts || true; }
unmount_all() {
  for m in sys dev/pts dev proc; do
    mountpoint -q "$ROOT/$m" 2>/dev/null && umount -l "$ROOT/$m" || true
  done
}
mount_all() {
  mkdir -p "$ROOT/proc" "$ROOT/dev" "$ROOT/sys"
  mountpoint -q "$ROOT/proc" || mount -t proc proc "$ROOT/proc"
  mountpoint -q "$ROOT/dev"  || mount --bind /dev "$ROOT/dev"
  mountpoint -q "$ROOT/sys"  || mount --bind /sys "$ROOT/sys"
  mkdir -p "$ROOT/dev/pts"
  mountpoint -q "$ROOT/dev/pts" || mount --bind /dev/pts "$ROOT/dev/pts" || true
}
inside() { chroot "$ROOT" /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/root LANG=C.UTF-8 "$@"; }
trap unmount_all EXIT

# ---------------------------------------------------------------- checks
[ -x "$BT/piper/piper" ] && [ -f "$BT/vosk-model/conf/model.conf" ] || {
  echo "Harald's voice and ears aren't installed yet. First run:  sudo bash $BT/install-voice.sh"; exit 1; }
ls "$BT"/voices/*.onnx >/dev/null 2>&1 || { echo "No Piper voice in $BT/voices"; exit 1; }
free_mb=$(df -Pm "$BT" | awk 'NR==2 {print $4}')
[ "$free_mb" -gt 1200 ] || { echo "Only $free_mb MB free on the Pi's card; this needs about 1200 MB."; exit 1; }

say "Installing the building tools"
apt-get install -y debootstrap debian-archive-keyring curl

# ---------------------------------------------------------------- the base system
if [ ! -x "$ROOT/usr/bin/python3" ]; then
  unmount_all
  [ -z "$(mounts_in_root)" ] || { echo "Something is still mounted inside $ROOT; not deleting it."; exit 1; }
  rm -rf "$ROOT"
  mkdir -p "$ROOT"
  say "Building a minimal 32-bit Debian ($SUITE). This is the slow part."
  debootstrap --arch=armhf --variant=minbase \
    --include=python3,python3-cffi-backend,python3-requests,python3-tqdm,busybox-static \
    "$SUITE" "$ROOT" "$MIRROR"
fi
mount_all
cp /etc/resolv.conf "$ROOT/etc/resolv.conf"
PYD=$(inside python3 -c 'import sys; print("/usr/local/lib/python%d.%d/dist-packages" % sys.version_info[:2])')
PYV=$(inside python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
mkdir -p "$ROOT$PYD"
# libraries Vosk's and Piper's ready-made programs need that a minimal Debian leaves out
missing=""
for p in libatomic1 libgomp1; do inside dpkg -s "$p" >/dev/null 2>&1 || missing="$missing $p"; done
if [ -n "$missing" ]; then
  say "Adding$missing"
  inside apt-get update -q
  inside apt-get install -y $missing
fi
if ! inside python3 -c 'import srt' 2>/dev/null; then
  inside apt-get update -q || true
  inside apt-get install -y python3-srt || {
    # Vosk imports this for making subtitles, which Harald never does: a stand-in is enough
    echo "(no python3-srt package; using a stand-in)"
    echo "# stand-in: Harald doesn't make subtitles" > "$ROOT$PYD/srt.py"; }
fi

# ---------------------------------------------------------------- Vosk (ears)
if ! inside python3 -c 'import vosk' 2>/dev/null; then
  say "Adding Vosk (32-bit) for Python $PYV"
  VV=$("$BT/venv/bin/python" -c 'import importlib.metadata as m; print(m.version("vosk"))' 2>/dev/null || true)
  tmp=$(mktemp -d)
  "$BT/venv/bin/pip" download --no-deps --only-binary=:all: --platform linux_armv7l \
    --python-version "$PYV" -d "$tmp" "vosk${VV:+==$VV}"
  mkdir -p "$ROOT$PYD"
  # a wheel is a zip of the finished files: unpacking it is installing it
  python3 -m zipfile -e "$tmp"/vosk-*.whl "$ROOT$PYD"
  rm -rf "$tmp"
fi
mkdir -p "$ROOT/opt"
rm -rf "$ROOT/opt/vosk-model"
cp -r "$BT/vosk-model" "$ROOT/opt/vosk-model"
if [ -d "$BT/vosk-spk" ]; then                     # voice profiles (Harald copies it later if not)
  rm -rf "$ROOT/opt/vosk-spk"
  cp -r "$BT/vosk-spk" "$ROOT/opt/vosk-spk"
fi

# ---------------------------------------------------------------- Piper (voice)
if [ ! -x "$ROOT/opt/piper/piper" ]; then
  say "Adding Piper (32-bit)"
  tmp=$(mktemp -d)
  curl -fL --retry 3 -o "$tmp/piper.tgz" \
    "https://github.com/rhasspy/piper/releases/download/$PIPER_VERSION/piper_linux_armv7l.tar.gz"
  tar -xzf "$tmp/piper.tgz" -C "$ROOT/opt"
  rm -rf "$tmp"
fi
rm -rf "$ROOT/opt/voices"
mkdir -p "$ROOT/opt/voices"
cp "$BT"/voices/*.onnx "$BT"/voices/*.onnx.json "$ROOT/opt/voices/"

# ---------------------------------------------------------------- Harald's bits
mkdir -p "$ROOT/opt/harald"
cp "$HERE/bench.py" "$ROOT/opt/harald/"
# the words Harald's questions use, so the test listens the same way he does
PYTHONPATH=$BT "$BT/venv/bin/python" -c \
  'import json; from bt_dragon.ask import GRAMMAR; print(json.dumps(GRAMMAR))' \
  > "$ROOT/opt/harald/vocab.json"

# ---------------------------------------------------------------- tidy and test
say "Tidying"
inside apt-get clean
rm -rf "$ROOT"/var/lib/apt/lists/* "$ROOT"/usr/share/doc/* "$ROOT"/usr/share/man/* "$ROOT"/usr/share/info/*
rm -f "$ROOT/etc/resolv.conf"

say "Testing it here on the Pi first"
# any library still missing shows up here as "not found"
inside sh -c "ldd $PYD/vosk/libvosk.so /opt/piper/piper /opt/piper/*.so* 2>/dev/null | grep 'not found' | sort -u" || true
inside python3 -c 'import vosk; print("Vosk loads.")'
echo "Hello." | inside /opt/piper/piper --model "$(ls "$ROOT"/opt/voices/*.onnx | head -1 | sed "s|^$ROOT||")" \
  --output_file /tmp/piper-test.wav >/tmp/piper-test.log 2>&1 && echo "Piper speaks." ||
  { tail -5 /tmp/piper-test.log; echo "Piper didn't run."; exit 1; }
rm -f "$ROOT/tmp/piper-test.wav"
echo "-- timings on the Pi, to compare with the Dot later:"
inside python3 /opt/harald/bench.py || true
unmount_all

say "Packing it up for the Dot"
cp "$ROOT/bin/busybox" "$OUT/busybox"          # a toolbox for the Dot, to unpack and mount with
tar -C "$ROOT" --numeric-owner --exclude='./dev/*' --exclude='./proc/*' --exclude='./sys/*' \
  --exclude='./tmp/*' -czf "$OUT/debian.tar.gz.new" .
mv -f "$OUT/debian.tar.gz.new" "$OUT/debian.tar.gz"
echo
echo "Done. Size unpacked: $(du -sm "$ROOT" | cut -f1) MB; to copy: $(du -m "$OUT/debian.tar.gz" | cut -f1) MB."
echo "Next, put it on the Dot:   bash $HERE/push.sh"
