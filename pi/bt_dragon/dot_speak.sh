#!/system/bin/sh
# Plays one of Harald's sentences on the Echo Dot without pops or whine.
#   speak.sh WAV OUTPUT VOLUME AMP_ON_AFTER AMP_ON_FOR
# The speaker chip takes about 1.2 s to wake up before it starts playing, and it clicks
# when it un-mutes at the start and mutes at the end. So the amplifier stays off until the
# sound is actually playing (the stream's state turns RUNNING), switches on during the
# 0.6 s of silence at the start of the file (AMP_ON_AFTER seconds in), and off again just
# after the last word, during the silence at the end. Nobody hears the clicks.
AMP=Ext_Speaker_Amp_Switch
ST=/proc/asound/card0/pcm${2}p/sub0/status
tinymix 'PCM Playback Volume' $3 $3 >/dev/null 2>&1
tinyplay $1 -D 0 -d $2 >/dev/null 2>&1 &
p=$!
n=0
while [ $n -lt 80 ] && ! grep -q RUNNING $ST 2>/dev/null; do
  sleep 0.05; n=$((n+1))        # wait (up to 4 s) for the chip to wake and start playing
done
sleep $4
tinymix $AMP On >/dev/null 2>&1
sleep $5
tinymix $AMP Off >/dev/null 2>&1
wait $p
