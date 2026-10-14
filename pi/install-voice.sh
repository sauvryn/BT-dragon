#!/bin/bash
# Gives Harald a voice and ears: installs adb (to talk to the Echo Dot), SoX (sound
# conversion), Piper (offline text-to-speech) with one voice, and Vosk (offline speech
# recognition) with its small English model. About 140 MB to download.
# Run on the Pi:   sudo bash /opt/bt-dragon/install-voice.sh
# Optional: pick another voice, e.g.  sudo bash install-voice.sh en_GB-alan-medium
set -e
if [ "$(id -u)" != "0" ]; then echo "Please run with sudo:  sudo bash $0"; exit 1; fi

VOICE="${1:-en_GB-northern_english_male-medium}"
PIPER_VERSION=2023.11.14-2
DEST=/opt/bt-dragon
say() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }

say "Installing adb and SoX"
apt-get install -y adb || apt-get install -y android-tools-adb
apt-get install -y sox || echo "(SoX didn't install: the voice still works, but the pitch setting won't)"

# The Pi's software can be 64-bit (arm64) or 32-bit (armhf) even on the same board,
# so ask the package manager rather than the kernel which one this card runs.
case "$(dpkg --print-architecture)" in
  arm64) ARCH=aarch64 ;;
  armhf) ARCH=armv7l ;;
  amd64) ARCH=x86_64 ;;
  *) echo "Piper has no build for $(dpkg --print-architecture)"; exit 1 ;;
esac

if [ ! -x "$DEST/piper/piper" ]; then
  say "Downloading Piper ($ARCH)"
  tmp=$(mktemp -d)
  curl -fL --retry 3 -o "$tmp/piper.tgz" \
    "https://github.com/rhasspy/piper/releases/download/$PIPER_VERSION/piper_linux_$ARCH.tar.gz"
  mkdir -p "$DEST"
  tar -xzf "$tmp/piper.tgz" -C "$DEST"
  rm -rf "$tmp"
fi

say "Downloading the voice $VOICE"
# voice names look like  en_GB-northern_english_male-medium  =  language-name-quality
lang="${VOICE%%-*}"; rest="${VOICE#*-}"; name="${rest%-*}"; quality="${rest##*-}"
base="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/${lang%%_*}/$lang/$name/$quality/$VOICE"
mkdir -p "$DEST/voices"
for ext in onnx onnx.json; do
  [ -s "$DEST/voices/$VOICE.$ext" ] || curl -fL --retry 3 -o "$DEST/voices/$VOICE.$ext" "$base.$ext"
done
chmod -R a+rX "$DEST/piper" "$DEST/voices"

say "Installing Harald's ears (Vosk speech recognition)"
"$DEST/venv/bin/pip" install --upgrade vosk || echo "(Vosk didn't install; questions by voice won't work, typed ones will)"
if [ ! -f "$DEST/vosk-model/conf/model.conf" ]; then
  tmp=$(mktemp -d)
  curl -fL --retry 3 -o "$tmp/model.zip" https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip \
    && python3 -m zipfile -e "$tmp/model.zip" "$tmp" \
    && rm -rf "$DEST/vosk-model" && mv "$tmp/vosk-model-small-en-us-0.15" "$DEST/vosk-model" \
    || echo "(The speech model didn't download; try again later)"
  rm -rf "$tmp"
fi
chmod -R a+rX "$DEST/vosk-model" 2>/dev/null || true

say "Adding the speaker model (voice profiles: telling voices apart)"
if [ ! -d "$DEST/vosk-spk" ]; then
  tmp=$(mktemp -d)
  curl -fL --retry 3 -o "$tmp/spk.zip" https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip \
    && python3 -m zipfile -e "$tmp/spk.zip" "$tmp" \
    && mv "$tmp/vosk-model-spk-0.4" "$DEST/vosk-spk" \
    || echo "(The speaker model didn't download; voice profiles won't work until it does)"
  rm -rf "$tmp"
fi
chmod -R a+rX "$DEST/vosk-spk" 2>/dev/null || true

say "Testing the voice"
echo "Hello! I'm your dragon." | "$DEST/piper/piper" --model "$DEST/voices/$VOICE.onnx" --output_file /tmp/bt-dragon-voice-test.wav \
  && echo "Piper works." || echo "Piper didn't run; see the messages above."
rm -f /tmp/bt-dragon-voice-test.wav
echo
echo "Done. If more than one voice is installed, choose one with  voice = \"$VOICE\"  under [dot]"
echo "in bt-dragon.toml. Restart your dragon to use it:  sudo systemctl restart bt-dragon"
