#!/system/bin/sh
# Runs ON the Echo Dot. Starts a program inside Harald's Debian folder:
#   sh /data/local/tmp/deb/enter.sh python3 /opt/harald/bench.py
#   sh /data/local/tmp/deb/enter.sh --unmount      (lets go of the borrowed folders)
# The Dot's /dev and /proc are borrowed into the folder first (they stay borrowed until the
# Dot restarts or --unmount), so programs inside can reach the hardware and see processes.
# Harald's folder, /data/local/tmp/harald, is borrowed too and shows up inside as /harald.
D=/data/local/tmp/deb
R=$D/root
B=$D/busybox

mounted() { $B grep -q " $R/$1 " /proc/mounts; }

if [ "$1" = "--unmount" ]; then
  for m in harald tmp sys proc dev; do
    mounted $m && $B umount $R/$m
  done
  for m in harald tmp sys proc dev; do
    mounted $m && { echo "still mounted: $R/$m"; exit 1; }
  done
  exit 0
fi

[ -x $R/usr/bin/env ] || { echo "ERROR no Debian at $R"; exit 1; }
$B mkdir -p $R/dev $R/proc $R/sys $R/tmp
mounted dev  || $B mount -o bind /dev $R/dev   || { echo "ERROR couldn't borrow /dev"; exit 1; }
mounted proc || $B mount -t proc proc $R/proc  || { echo "ERROR couldn't mount /proc"; exit 1; }
mounted sys  || $B mount -o bind /sys $R/sys   || echo "(couldn't borrow /sys; carrying on)"
mounted tmp  || $B mount -t tmpfs -o size=64m tmpfs $R/tmp || echo "(no memory-backed /tmp; using the disk)"
# Harald's own folder on the Dot (micgrab, ears.py) appears inside as /harald
if [ -d /data/local/tmp/harald ]; then
  $B mkdir -p $R/harald
  mounted harald || $B mount -o bind /data/local/tmp/harald $R/harald || echo "(couldn't borrow Harald's folder)"
fi
exec $B chroot $R /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/root LANG=C.UTF-8 "$@"
