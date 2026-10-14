#!/system/bin/sh
# Harald's light player. Runs ON the Echo Dot; the Pi sends it there each time it connects.
#
# It plays the animation named in "base" over and over (Harald's mood), and whenever the
# Pi writes a new "<number> <name>" line into "once", it plays that animation once (a
# storm, a new species...) and goes back to the mood. Each animation is a text file with
# one frame per line: "<seconds> <72 hex digits>", written straight to the ring's chip.
# Creating the file "quit" stops it and turns the ring off.
H=/data/local/tmp/harald
C=/sys/devices/soc/11007000.i2c/i2c-0/0-003f/frame
OFF=000000000000000000000000000000000000000000000000000000000000000000000000
echo $$ > $H/pid
rm -f $H/quit
[ -f $H/once ] || echo "0 off" > $H/once
[ -f $H/base ] || echo off > $H/base
read last < $H/once

play() {  # play NAME; stops early when a new one-off arrives or "quit" appears
  [ -f "$H/anim/$1.txt" ] || { sleep 0.5; return; }
  while read d hex; do
    echo $hex > $C
    sleep $d
    read o < $H/once
    [ "$o" != "$last" ] && return
    [ -f $H/quit ] && return
  done < "$H/anim/$1.txt"
}

while [ ! -f $H/quit ]; do
  read o < $H/once
  if [ "$o" != "$last" ]; then
    last=$o
    play "${o#* }"
    continue
  fi
  read b < $H/base
  play "$b"
done
echo $OFF > $C
rm -f $H/pid $H/quit
