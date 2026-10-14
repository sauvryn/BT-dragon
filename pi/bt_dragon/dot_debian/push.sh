#!/bin/bash
# Copies the Debian that build.sh made onto the Echo Dot, then times Piper and Vosk there.
# Run on the Pi (after build.sh):
#   bash /opt/bt-dragon/bt_dragon/dot_debian/push.sh              (finds the Dot Harald uses)
#   bash /opt/bt-dragon/bt_dragon/dot_debian/push.sh 10.1.2.3     (or give its address)
#   bash /opt/bt-dragon/bt_dragon/dot_debian/push.sh --test-only  (just run the timings again)
# It only writes inside /data/local/tmp/deb on the Dot; Fire OS itself isn't changed.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=/opt/bt-dragon/dot-debian
D=/data/local/tmp/deb
say() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }

TEST_ONLY=""
[ "$1" = "--test-only" ] && { TEST_ONLY=1; shift; }
if [ -n "$1" ]; then
  T="$1:5555"
  adb connect "$T" >/dev/null 2>&1 || true
else
  T=$(adb devices | awk '/:5555[ \t]+device$/ {print $1; exit}')
fi
[ -n "$T" ] || { echo "No Dot connected. Is Harald talking to it? Or give its address: bash $0 10.x.x.x"; exit 1; }
dot() { timeout 600 adb -s "$T" shell "$1"; }
echo "Using the Dot at $T"
[ "$(dot 'echo hi' | tr -d '\r')" = "hi" ] || { echo "The Dot isn't answering."; exit 1; }

if [ -z "$TEST_ONLY" ]; then
  [ -f "$OUT/debian.tar.gz" ] && [ -f "$OUT/busybox" ] || { echo "Run build.sh first."; exit 1; }
  dot "mkdir -p $D"
  adb -s "$T" push "$OUT/busybox" "$HERE/enter.sh" "$D/" >/dev/null
  dot "chmod 755 $D/busybox; sed -i 's/\r\$//' $D/enter.sh 2>/dev/null; true"

  say "Checking there's room"
  need=$(( $(du -sm "$OUT/root" 2>/dev/null | cut -f1) + $(du -m "$OUT/debian.tar.gz" | cut -f1) + 100 ))
  # the free space is 3rd from the end of the last line (a long disk name can wrap onto a line of its own)
  have=$(dot "$D/busybox df -m /data | $D/busybox awk 'END {print \$(NF-2)}'" | tr -d '\r')
  old=$(dot "[ -d $D/root ] && $D/busybox du -sxm $D/root | $D/busybox cut -f1 || echo 0" | tr -d '\r')
  case "$have" in ''|*[!0-9]*) echo "Couldn't read the Dot's free space (got: '$have')"; have=0 ;; esac
  case "$old" in ''|*[!0-9]*) old=0 ;; esac
  echo "needs about $need MB; the Dot has $have MB free (plus $old MB from an earlier copy)"
  [ $((have + old)) -gt "$need" ] || { echo "Not enough room on the Dot."; exit 1; }

  say "Copying to the Dot ($(du -m "$OUT/debian.tar.gz" | cut -f1) MB; a few minutes over Wi-Fi)"
  adb -s "$T" push "$OUT/debian.tar.gz" "$D/debian.tar.gz"

  say "Unpacking on the Dot"
  # the old copy is only deleted once nothing is borrowed into it any more
  out=$(dot "B=$D/busybox
    [ -d $D/root ] && sh $D/enter.sh --unmount
    if \$B grep -q ' $D/root/' /proc/mounts; then echo STILL_MOUNTED; exit; fi
    rm -rf $D/root.new; mkdir $D/root.new
    \$B tar -xzf $D/debian.tar.gz -C $D/root.new && rm -f $D/debian.tar.gz &&
      rm -rf $D/root && mv $D/root.new $D/root && echo UNPACKED_OK" 2>&1 | tr -d '\r')
  echo "$out" | tail -5
  echo "$out" | grep -q UNPACKED_OK || { echo "Unpacking didn't finish (see above)."; exit 1; }
fi

# the latest timing test and word list (so --test-only tries out changes without a rebuild)
tmpv=$(mktemp)
PYTHONPATH=/opt/bt-dragon /opt/bt-dragon/venv/bin/python -c \
  'import json; from bt_dragon.ask import GRAMMAR; print(json.dumps(GRAMMAR))' > "$tmpv" &&
  adb -s "$T" push "$tmpv" "$D/root/opt/harald/vocab.json" >/dev/null || true
adb -s "$T" push "$HERE/bench.py" "$D/root/opt/harald/bench.py" >/dev/null || true
rm -f "$tmpv"

say "What the Dot is busy with right now"
dot "$D/busybox free -m; echo; cat /proc/loadavg; echo; top -n 1 -m 8 2>/dev/null | tail -n 12"

say "Timing Piper and Vosk on the Dot"
dot "sh $D/enter.sh python3 /opt/harald/bench.py" 2>&1 | tr -d '\r'
echo
echo "Done. Please send these timings (and the ones build.sh printed for the Pi)."
