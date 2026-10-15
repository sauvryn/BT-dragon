"""
Harald's voice: text in, a WAV file the Echo Dot can play out.

Speech is made on the Pi by Piper, a neural text-to-speech engine that runs offline. A
voice is a ~60 MB model file (.onnx) plus its settings (.onnx.json); the installer fetches
a northern English male voice. Piper writes 16-bit mono WAV at the voice's own rate
(22,050 Hz for most voices).

The Dot's speaker only takes 48,000 Hz stereo 16-bit WAV (that's what played cleanly in
testing), so the sound is converted afterwards. With SoX installed that's one command
that also sets the volume and can lower the pitch for a deeper, more dragonish voice;
without SoX a small pure-Python converter does the rate change and volume.

Piper is kept running between sentences while the Dot is around (loading the voice takes
a few seconds on a Pi Zero 2), and stopped when the Dot goes away to give the memory back.
"""
import array
import asyncio
import json
import logging
import os
import re
import shutil
import wave

log = logging.getLogger("voice")

PIPER_PATHS = ["/opt/bt-dragon/piper/piper", "/usr/local/bin/piper", "/usr/bin/piper"]
VOICE_DIR = "/opt/bt-dragon/voices"
OUT_RATE = 48000

# Words the screen spells in capitals that a voice should say differently
SAY_AS = {
    "HPA": "hectopascals", "XP": "X P", "GPS": "G P S", "WIGLE": "wiggle", "KM": "kilometers",
    "M UP": "meters up", "WPA3": "W P A 3", "WPA2": "W P A 2", "WEP": "wep", "HP": "H P",
    "NOM!": "Nom nom!", "PWNAGOTCHI": "pwnagotchi", "LAIR": "Lair",
}


def speakable(text, name=""):
    """Turn a status-line message (ALL CAPS, terse) into something that reads aloud well."""
    t = " " + text.strip() + " "
    for k, v in SAY_AS.items():
        t = re.sub(rf"(?<![A-Za-z0-9]){re.escape(k)}(?![A-Za-z0-9])", "\x00" + v + "\x01", t)
    t = t.replace("_", " ").replace("*", " ")      # *YAWN* is a sound, not "asterisk yawn asterisk"
    t = re.sub(r"\+(\d)", r"plus \1", t)
    t = re.sub(r"(^|\s|\()-(\d)", r"\1minus \2", t)
    t = re.sub(r"\((.*?)\)", r", \1,", t)
    # lower-case everything except the replacements, then capitalize sentences
    parts = re.split(r"(\x00[^\x01]*\x01)", t)
    t = "".join(p[1:-1] if p.startswith("\x00") else p.lower() for p in parts)
    if name:
        t = re.sub(rf"\b{re.escape(name.lower())}\b", name, t)
    t = re.sub(r"\s+", " ", t).strip(" ,")
    t = re.sub(r" ,", ",", t)
    t = re.sub(r"([.!?]),", r"\1", t)
    t = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
    t = re.sub(r"\bi\b", "I", t)
    if t and t[-1] not in ".!?":
        t += "."
    return t


def sentences(text, shortest=30):
    """Split speech into sentences, so the first can be spoken while the next is being made.
    Very short ones are kept with the next ("Nom nom! 3 new snacks." stays together)."""
    parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    out = []
    for p in parts:
        if out and len(out[-1]) < shortest:
            out[-1] += " " + p
        else:
            out.append(p)
    if len(out) > 1 and len(out[-1]) < shortest:        # a short last one joins the one before
        last = out.pop()
        out[-1] += " " + last
    return out


def find_piper():
    for p in PIPER_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("piper")


def find_voice(wanted=""):
    """The voice model to use: the one named in the settings, or the first one installed."""
    if wanted and os.path.isfile(wanted):
        return wanted
    if wanted:
        p = os.path.join(VOICE_DIR, wanted if wanted.endswith(".onnx") else wanted + ".onnx")
        if os.path.isfile(p):
            return p
    try:
        models = sorted(f for f in os.listdir(VOICE_DIR) if f.endswith(".onnx"))
    except OSError:
        return None
    return os.path.join(VOICE_DIR, models[0]) if models else None


# ------------------------------------------------------------------ WAV conversion
def convert_py(src, dst, volume=1.0):
    """Mono/stereo 16-bit WAV at any rate -> 48 kHz stereo 16-bit, with volume. Linear
    interpolation between samples: plenty for a voice."""
    with wave.open(src, "rb") as w:
        ch, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("expected 16-bit audio")
    s = array.array("h")
    s.frombytes(raw)
    if ch == 2:
        s = array.array("h", ((s[i] + s[i + 1]) // 2 for i in range(0, len(s) - 1, 2)))
    n_out = int(len(s) * OUT_RATE / rate)
    out = array.array("h", bytes(4 * n_out))
    step = rate / OUT_RATE
    last = len(s) - 1
    for i in range(n_out):
        x = i * step
        j = int(x)
        f = x - j
        a = s[j]
        b = s[j + 1] if j < last else a
        v = int((a + (b - a) * f) * volume)
        v = 32767 if v > 32767 else -32768 if v < -32768 else v
        out[2 * i] = out[2 * i + 1] = v
    with wave.open(dst, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(OUT_RATE)
        w.writeframes(out.tobytes())


def pad(path, lead=0.0, tail=0.0):
    """Add silence before and after a 16-bit WAV (in place). The Dot's speaker chip takes
    about 1.2 seconds to wake up, and its amplifier is only switched on once it's awake,
    so the lead-in silence keeps the first word from being cut off."""
    with wave.open(path, "rb") as w:
        params = w.getparams()
        data = w.readframes(w.getnframes())
    frame = params.nchannels * params.sampwidth
    pre = bytes(int(lead * params.framerate) * frame)
    post = bytes(int(tail * params.framerate) * frame)
    with wave.open(path, "wb") as w:
        w.setparams(params)
        w.writeframes(pre + data + post)


def duration(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (OSError, wave.Error, EOFError):
        return 0.0


def volume_factor(percent):
    """0-100 on the slider -> loudness. Ears hear loudness on a curve, so the slider
    is squared: 50 sounds about half as loud as 100."""
    p = max(0.0, min(100.0, float(percent))) / 100
    return p * p


async def convert(src, dst, volume=70, pitch=0.0):
    """Make `dst` ready for the Dot. Returns True on success."""
    k = volume_factor(volume)
    sox = shutil.which("sox")
    if sox:
        cmd = [sox, "-q", src, "-b", "16", dst, "vol", f"{k:.3f}"]
        if pitch:
            cmd += ["pitch", str(int(pitch * 100))]   # SoX counts pitch in cents
        cmd += ["rate", str(OUT_RATE), "channels", "2"]
        p = await asyncio.create_subprocess_exec(*cmd, stderr=asyncio.subprocess.PIPE)
        _, err = await p.communicate()
        if p.returncode == 0:
            return True
        log.warning("sox failed (%s), using the built-in converter", err.decode(errors="replace").strip()[:200])
    try:
        await asyncio.to_thread(convert_py, src, dst, k)
        return True
    except (OSError, ValueError, wave.Error, EOFError) as e:
        log.warning("couldn't convert the speech: %s", e)
        return False


# ------------------------------------------------------------------ Piper
class Piper:
    def __init__(self, voice="", speed=1.0):
        self.voice_name = voice
        self.speed = speed
        self.proc = None
        self.lock = asyncio.Lock()

    @property
    def available(self):
        return bool(find_piper() and find_voice(self.voice_name))

    async def _start(self):
        exe, model = find_piper(), find_voice(self.voice_name)
        if not exe or not model:
            return False
        self.proc = await asyncio.create_subprocess_exec(
            exe, "--model", model, "--json-input", "--length_scale", f"{1 / max(0.5, self.speed):.2f}",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        log.info("Piper started with %s", os.path.basename(model))
        return True

    async def stop(self):
        p, self.proc = self.proc, None
        if p and p.returncode is None:
            try:
                p.stdin.close()
                await asyncio.wait_for(p.wait(), 5)
            except (asyncio.TimeoutError, OSError, ConnectionError):
                p.kill()

    async def say(self, text, path, timeout=60):
        """Write `text` as speech to `path` (Piper's own format). True on success."""
        async with self.lock:
            if self.proc is None or self.proc.returncode is not None:
                if not await self._start():
                    return False
            try:
                if os.path.exists(path):
                    os.remove(path)
                line = json.dumps({"text": text, "output_file": path}) + "\n"
                self.proc.stdin.write(line.encode())
                await self.proc.stdin.drain()
                # Piper prints the file's path once it's written
                while True:
                    out = await asyncio.wait_for(self.proc.stdout.readline(), timeout)
                    if not out:
                        raise ConnectionError("Piper stopped")
                    if out.decode(errors="replace").strip().endswith(os.path.basename(path)):
                        break
                return os.path.exists(path)
            except (asyncio.TimeoutError, ConnectionError, OSError) as e:
                log.warning("Piper didn't answer (%s); restarting it next time", e)
                if self.proc and self.proc.returncode is None:
                    self.proc.kill()
                self.proc = None
                return False


async def espeak(text, path, pitch=0.0):
    """Fallback voice if Piper isn't installed: robotic but tiny."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return False
    p = await asyncio.create_subprocess_exec(exe, "-v", "en-gb", "-s", "150", "-p", str(int(40 + pitch * 4)),
                                             "-w", path, text, stderr=asyncio.subprocess.DEVNULL)
    await p.wait()
    return p.returncode == 0 and os.path.exists(path)
