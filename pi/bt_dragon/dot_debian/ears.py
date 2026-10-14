"""
Harald's ears, running ON the Echo Dot (inside the small Debian that build.sh makes).

The Dot does the listening itself: it reads the buttons, records questions with micgrab,
and turns them into words with Vosk. Only words cross the network to the Pi, never sound.

The Pi connects over the hotspot (TCP, port 5577 by default) and must first send the key
from ears.key, which only the Pi and the Dot have. One line of JSON per message:

  Pi -> Dot   {"hello": KEY}                              first, always
              {"cmd": "say", "id": 8, "text": "...", "speed": 1.0, "pitch": -2, "lead": 0.6, "tail": 0.6,
               "file": "say1.wav"}     make speech with Piper, ready to play, in /harald/say1.wav
              {"cmd": "vocab", "words": [...]}            the words and phrases to listen for
              {"cmd": "hear", "id": 7, "max_s": 8, "words": [...]?, "free_if": "regex"?, "free": bool?}
                  record and recognize (again with the whole vocabulary if what was heard
                  matches free_if)
              {"cmd": "wake", "on": true}                   listen for "hey dragon" (or stop)
              {"cmd": "busy", "on": true}                   he's talking: don't hear himself
              {"cmd": "ping"}
  Dot -> Pi   {"hello": "ok", "ready": true/false}        ready = the speech model is loaded
              {"line": "KEY ACTION 1"}                    a button, straight away
              {"id": 7, "speech": true, "text": "...", "rec_s": 2.1, "stt_s": 0.7, "spk": [...]?}
                  (spk: a voice print, if the speaker model is installed: for voice profiles)
              {"pong": 1, "ready": true, "wake_state": {...}}
              {"wake": 1, "wake_state": {...}}              "hey dragon" was heard
              {"id": 8, "ok": true, "speech_s": 2.4, "tts_s": 1.9}

Runs as:  python3 -u /harald/ears.py [--port 5577]
"""
import argparse
import array
import asyncio
import collections
import glob
import json
import queue
import threading
import os
import re
import sys
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def normalize(path):
    """Raise a quiet recording so its loudest part is near full scale (in place)."""
    with wave.open(path, "rb") as w:
        params = w.getparams()
        s = array.array("h")
        s.frombytes(w.readframes(w.getnframes()))
    peak = max((abs(x) for x in s), default=0)
    if 0 < peak < 20000:
        k = min(20000 / peak, 20.0)
        s = array.array("h", (max(-32768, min(32767, int(x * k))) for x in s))
        with wave.open(path, "wb") as w:
            w.setparams(params)
            w.writeframes(s.tobytes())


OUT_RATE = 48000          # what the Dot's speaker chip plays cleanly: 48 kHz stereo 16-bit


def to_dot_wav(src, dst, pitch=0.0, volume=0.9, lead=0.0, tail=0.0):
    """Piper's mono WAV -> 48 kHz stereo for the speaker, with silence before and after.
    Pitch works like a tape played slower: the samples are treated as if they were recorded
    at a different rate, which lowers the voice (Piper was already asked to speak that much
    faster, so the speed comes out right). Returns the seconds of speech."""
    with wave.open(src, "rb") as w:
        rate, raw = w.getframerate(), w.readframes(w.getnframes())
    rate = int(round(rate * 2 ** (pitch / 12)))
    try:
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        import audioop                        # fast, in C (Python 3.11 still has it)
        out, _ = audioop.ratecv(raw, 2, 1, rate, OUT_RATE, None)
        out = audioop.tostereo(audioop.mul(out, 2, volume), 2, 1, 1)
    except ImportError:
        s = array.array("h")
        s.frombytes(raw)
        n = int(len(s) * OUT_RATE / rate)
        o = array.array("h", bytes(4 * n))
        step, last = rate / OUT_RATE, len(s) - 1
        for i in range(n):
            x = i * step
            j = int(x)
            b = s[j + 1] if j < last else s[j]
            v = int((s[j] + (b - s[j]) * (x - j)) * volume)
            o[2 * i] = o[2 * i + 1] = max(-32768, min(32767, v))
        out = o.tobytes()
    speech_s = len(out) / (4 * OUT_RATE)
    with wave.open(dst, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(OUT_RATE)
        w.writeframes(bytes(int(lead * OUT_RATE) * 4) + out + bytes(int(tail * OUT_RATE) * 4))
    return speech_s


RATE = 16000
BLOCK_BYTES = 512             # 256 samples (16 ms) at a time, as `micgrab stream` sends them
WAKE_PHRASE = "hey dragon"
# Decoys: other words the recognizer may choose instead. With only "hey dragon" to pick
# from, every sound gets squeezed into the nearest thing it knows, which is "hey dragon";
# with lots of other words (the sound-alikes first) a cough or the telly turns into
# "they drag on" or "wagon" or [unk] instead. The stricter the knob, the more of them.
WAKE_DECOYS = (
    "hey okay the what and it is a to dragon "
    # sound-alikes
    "hay they day pay say way may play stay hate eight great "
    "drag dragged dragging drag on wagon again gone dragons tragic track truck drink drive "
    "dream draw drop rag bag flag brag grand gran grandad agony ago "
    "hey there hello hi oh no yes yeah right okay so "
    # everyday words, for everything else that gets said around him
    "i you he she we they me my your our his her their this that there here "
    "be was were are been have has had do did does done can could will would should "
    "get got go going went come came make made take took give gave know knew think "
    "see saw look want need like love tell told said ask call try use find work feel "
    "keep let put mean seem leave turn start show hear play run move live believe "
    "bring happen write sit stand lose pay meet include continue set learn change "
    "lead understand watch follow stop create speak read spend grow open walk win "
    "not all just now then when where why how who which out up down over back off "
    "on in at by for with about from into of as if or but because very really well "
    "good new first last long little big old right high different small large next "
    "time year people way day man woman thing child world life hand part place week "
    "case point home water room mother father mum dad money night food tea dinner "
    "one two three four five six seven eight nine ten hundred some more much many "
    "today tomorrow morning evening later sorry please thanks thank alright actually"
).split()
WAKE_FEW = 12                 # how many decoys at the loosest setting (the original list)


def wake_rules(strict):
    """What the strictness knob (0 to 100) does:
    - more decoys the stricter it is (12 at 0, all of them at 100);
    - from 20 up, a second look: when the quick listener thinks it heard the phrase, the
      last 2.5 s are decoded again in full, and both words must come out at least this
      sure of themselves (30% at 20, rising to 95% at 100);
    - from 70 up, "hey dragon" must also come after a little pause, not in the middle
      of somebody's sentence (or the telly's)."""
    s = max(0, min(100, int(strict)))
    words = list(dict.fromkeys(WAKE_DECOYS))
    n = WAKE_FEW + round((len(words) - WAKE_FEW) * s / 100)
    return {"strict": s, "grammar": [WAKE_PHRASE] + words[:n] + ["[unk]"],
            "confirm": s >= 20, "min_conf": round(0.30 + 0.65 * (s - 20) / 80, 2) if s >= 20 else 0.0,
            "pause": s >= 70}


def check_wake(result, rules, clip_s):
    """The second look: a full decode of the last couple of seconds, with word timings and
    confidences. Returns (ok, where, conf): `where` is (start of "hey", end of "dragon") in
    seconds from the start of the clip when ok, and why not otherwise."""
    words = result.get("result") or []
    for i in range(len(words) - 2, -1, -1):
        if words[i].get("word") == "hey" and words[i + 1].get("word") == "dragon":
            hey, drag = words[i], words[i + 1]
            conf = min(float(hey.get("conf", 1)), float(drag.get("conf", 1)))
            if conf < rules["min_conf"]:
                return False, f"only {round(conf * 100)}% sure", conf
            if rules["pause"]:
                before = [w for w in words[:i] if w.get("word") != "[unk]"]
                if before and float(hey.get("start", 0)) - float(before[-1].get("end", 0)) < 0.25:
                    return False, "in the middle of a sentence", conf
            return True, (float(hey.get("start", 0)), float(drag.get("end", clip_s))), conf
    return False, "not on a second listen", None


def _level(blk):
    s = array.array("h")
    s.frombytes(blk)
    return sum(abs(x) for x in s) // max(1, len(s))


class Vad:
    """When someone starts and stops talking: the same rules as micgrab's own recording."""

    def __init__(self, max_s=8, wait_s=4):
        self.noise, self.blocks, self.loud, self.quiet = 0, 0, 0, 0
        self.speech = False
        self.max_blocks = int(max_s * RATE / 256)
        self.wait_blocks = int(wait_s * RATE / 256)

    def feed(self, samples):
        """One block of 16-bit samples. Returns True when recording should stop."""
        lvl = sum(abs(x) for x in samples) // max(1, len(samples))
        self.blocks += 1
        if self.blocks <= 12:
            self.noise = lvl if self.blocks == 1 else (self.noise * 3 + lvl) // 4
            return False
        thr = max(160, self.noise * 5 // 2)
        if lvl > thr:
            self.loud, self.quiet = self.loud + 1, 0
            if self.loud >= 4:
                self.speech = True
        else:
            self.loud, self.quiet = 0, self.quiet + 1
            if not self.speech:
                self.noise = (self.noise * 15 + lvl) // 16
        if self.speech and self.quiet >= 50:
            return True
        if not self.speech and self.blocks >= self.wait_blocks:
            return True
        return self.blocks >= self.max_blocks


class Wake:
    """The wake word, entirely on the Dot: the microphones run continuously through
    `micgrab stream`, a Vosk recognizer with a tiny word list listens for "hey dragon", and
    only the news that it was heard goes to the Pi. Questions after it are recorded from
    the same stream (the microphones can only be opened once). Nothing is kept."""

    def __init__(self, ears):
        self.ears = ears
        self.on = False              # wanted (the Pi decides: the den's tick box, hours, mute)
        self.active = False          # sound is coming in right now
        self.heard = 0
        self.last = 0.0
        self.cpu = None              # share of one core the listening takes
        self.error = ""
        self.busy_until = 0.0        # he's talking: don't listen to himself
        self.busy = False
        self.taps = []
        self.n = 0                   # blocks so far
        self.pre = collections.deque(maxlen=int(3 * RATE / 256))     # the last 3 s: (number, block)
        self.cut = None              # where the wake word ended: the question starts after this
        self.cut_start = None        # ...and where it started (the quiet before it sets the noise level)
        self.strict = 50
        self.rules = wake_rules(self.strict)
        self.turned_down = 0         # near misses the second look said no to
        self.last_no = ""            # why the latest one was turned down
        self.last_conf = None        # how sure the second look was, the last time
        self.q = queue.Queue(maxsize=400)
        self.proc = None
        self.thread = None
        self.loop = None

    def state(self):
        return {"active": self.active, "heard": self.heard, "last": int(self.last),
                "cpu": self.cpu, "error": self.error, "strict": self.strict,
                "turned_down": self.turned_down, "last_no": self.last_no,
                "conf": None if self.last_conf is None else round(self.last_conf * 100)}

    def set_strict(self, strict):
        rules = wake_rules(strict)
        if rules != self.rules:
            self.rules, self.strict = rules, rules["strict"]
            log(f"wake word: strictness {self.strict}%, {len(rules['grammar']) - 2} decoys")

    async def run(self):
        self.loop = asyncio.get_running_loop()
        while True:
            if not (self.on and self.ears.loaded.is_set()):
                await asyncio.sleep(1)
                continue
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._detect, daemon=True)
                self.thread.start()
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    self.ears.args.micgrab, "stream", "8", stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL)
            except OSError as e:
                self.error = f"couldn't start the microphones: {e}"
                await asyncio.sleep(15)
                continue
            log("wake word: listening")
            buf = b""
            try:
                while self.on:
                    try:
                        data = await asyncio.wait_for(self.proc.stdout.read(4096), 5)
                    except asyncio.TimeoutError:
                        self.error = "the microphones stopped sending sound"
                        break
                    if not data:
                        break
                    if not self.active and data[:6] in (b"ERROR ", b"usage:"):
                        self.error = data.decode(errors="replace").strip().splitlines()[0][:100]
                        break
                    if not self.active:
                        self.active, self.error = True, ""
                        await self.ears.send({"wake_state": self.state()})
                    buf += data
                    while len(buf) >= BLOCK_BYTES:
                        self._block(buf[:BLOCK_BYTES])
                        buf = buf[BLOCK_BYTES:]
            finally:
                self.active = False
                if self.proc.returncode is None:
                    self.proc.kill()
                    await self.proc.wait()
                log("wake word: stopped")
                await self.ears.send({"wake_state": self.state()})
            await asyncio.sleep(2 if not self.error else 15)

    def _block(self, blk):
        self.n += 1
        self.pre.append((self.n, blk))
        for tap in list(self.taps):
            tap.put_nowait(blk)
        if self.busy or time.time() < self.busy_until or self.taps:
            return                   # talking, or already recording a question
        try:
            self.q.put_nowait((self.n, blk))
        except queue.Full:
            pass

    def _detect(self):
        """The quick listener runs on partial results (it doesn't wait for the end of a
        sentence). When it thinks it heard "hey dragon", it listens on for a quarter of a
        second, then (unless the knob is at the loosest) has a second, careful look."""
        import vosk
        rules, rec, check = None, None, None
        recent = collections.deque(maxlen=int(2.5 * RATE / 256))
        cpu0, audio, pending = time.thread_time(), 0.0, -1
        while True:
            try:
                n, blk = self.q.get(timeout=1)
            except queue.Empty:
                if not self.on:
                    return
                continue
            if rules is not self.rules:                  # the knob moved: new word lists
                rules = self.rules
                rec = vosk.KaldiRecognizer(self.ears.model, RATE, json.dumps(rules["grammar"]))
                check = vosk.KaldiRecognizer(self.ears.model, RATE, json.dumps(rules["grammar"]))
                check.SetWords(True)
                pending = -1
            recent.append((n, blk))
            audio += len(blk) / (2 * RATE)
            if rec.AcceptWaveform(blk):
                text = json.loads(rec.Result()).get("text", "")
            else:
                text = json.loads(rec.PartialResult()).get("partial", "")
            if pending < 0 and WAKE_PHRASE in text:
                rec.Reset()
                pending = 15 if rules["confirm"] else 0  # let "dragon" finish
            if pending == 0:
                pending = -1
                first = recent[0][0]
                if not rules["confirm"]:
                    self.cut, self.cut_start = n, None
                    self.loop.call_soon_threadsafe(self._woke)
                else:
                    clip = b"".join(b for _, b in recent)
                    check.AcceptWaveform(clip)
                    ok, where, conf = check_wake(json.loads(check.FinalResult()), rules, len(clip) / (2 * RATE))
                    self.last_conf = conf
                    if ok:
                        self.cut_start = first + int(where[0] * RATE / 256)
                        self.cut = first + int(where[1] * RATE / 256)
                        self.loop.call_soon_threadsafe(self._woke)
                    else:
                        self.loop.call_soon_threadsafe(self._no, where)
                recent.clear()
            elif pending > 0:
                pending -= 1
            if audio >= 10:
                self.cpu = round((time.thread_time() - cpu0) / audio, 2)
                cpu0, audio = time.thread_time(), 0.0

    def _no(self, why):
        self.turned_down += 1
        self.last_no = why
        log(f"wake word: turned down ({why})")
        asyncio.ensure_future(self.ears.send({"wake_state": self.state()}))

    def _woke(self):
        now = time.time()
        if now - self.last < 3:
            return
        self.last = now
        self.heard += 1
        while not self.q.empty():        # what follows is the question, not another wake word
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        log("wake word heard")
        asyncio.ensure_future(self.ears.send({"wake": 1, "wake_state": self.state()}))

    async def capture(self, path, max_s=8, pre_s=0.0):
        """Record a question from the stream until the speaker stops. True if there was speech."""
        tap = asyncio.Queue()
        n_pre = int(pre_s * RATE / 256)
        chunks = [b for _, b in self.pre][-n_pre:] if n_pre else []
        vad = Vad(max_s)
        done = False
        if pre_s and self.cut is not None:
            # After the wake word: everything since "dragon" ended. The second look and the
            # trip to the Pi and back take a moment, so the question may have started, or
            # even finished, already: the listening rules run over that part too, with the
            # noise level taken from the quiet before "hey".
            pre = list(self.pre)
            start = self.cut_start if self.cut_start is not None else self.cut - 60
            before = sorted(_level(b) for i, b in pre if i < start)
            after = [b for i, b in pre if i > self.cut - 4]
            if after:
                chunks = after
            if len(before) >= 12:
                vad.noise, vad.blocks = before[len(before) // 5], 12
                for b in chunks:
                    s = array.array("h")
                    s.frombytes(b)
                    if vad.feed(s):
                        done = True
                        break
        self.cut = self.cut_start = None
        self.taps.append(tap)
        try:
            while not done:
                try:
                    blk = await asyncio.wait_for(tap.get(), 3)
                except asyncio.TimeoutError:
                    break
                chunks.append(blk)
                s = array.array("h")
                s.frombytes(blk)
                if vad.feed(s):
                    break
        finally:
            self.taps.remove(tap)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b"".join(chunks))
        return vad.speech


class Voice:
    """Piper, kept running between sentences (loading the voice takes a few seconds)."""

    def __init__(self, args):
        self.args = args
        voices = sorted(glob.glob(os.path.join(args.voices, "*.onnx")))
        self.model = next((v for v in voices if os.path.basename(v)[:-5] == args.voice), voices[0] if voices else None)
        self.proc = None
        self.scale = None
        self.lock = asyncio.Lock()

    @property
    def available(self):
        return bool(self.model and os.access(self.args.piper, os.X_OK))

    async def _start(self, scale):
        await self.stop()
        self.proc = await asyncio.create_subprocess_exec(
            self.args.piper, "--model", self.model, "--json-input", "--length_scale", f"{scale:.3f}",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        self.scale = scale
        log(f"Piper started with {os.path.basename(self.model)}")

    async def stop(self):
        p, self.proc = self.proc, None
        if p and p.returncode is None:
            p.kill()
            await p.wait()

    async def make(self, text, path, scale, timeout=60):
        if self.proc is None or self.proc.returncode is not None or self.scale != scale:
            await self._start(scale)
        try:
            os.remove(path)
        except OSError:
            pass
        self.proc.stdin.write((json.dumps({"text": text, "output_file": path}) + "\n").encode())
        await self.proc.stdin.drain()
        while True:                            # Piper prints the file's path once it's written
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout)
            if not line:
                self.proc = None
                raise ConnectionError("Piper stopped")
            if line.decode(errors="replace").strip().endswith(os.path.basename(path)):
                return

    async def say(self, req):
        out = {"id": req.get("id"), "ok": False}
        async with self.lock:
            try:
                t0 = time.monotonic()
                speed = max(0.5, min(2.0, float(req.get("speed", 1.0))))
                pitch = max(-12.0, min(12.0, float(req.get("pitch", 0.0))))
                scale = round(2 ** (pitch / 12) / speed, 3)
                raw = os.path.join(self.args.tmp, "voice-raw.wav")
                await self.make(str(req.get("text", ""))[:1000], raw, scale)
                # one file per sentence, so one can play while the next is being made
                name = str(req.get("file") or "")
                dst = os.path.join(os.path.dirname(self.args.say_file), name) \
                    if re.fullmatch(r"say\d?\.wav", name) else self.args.say_file
                out["speech_s"] = round(await asyncio.to_thread(
                    to_dot_wav, raw, dst, pitch, float(req.get("volume", 0.9)),
                    float(req.get("lead", 0.0)), float(req.get("tail", 0.0))), 2)
                out["tts_s"] = round(time.monotonic() - t0, 2)
                out["ok"] = True
            except Exception as e:
                out["error"] = f"{type(e).__name__}: {e}"[:160]
                if self.proc and self.proc.returncode is None:
                    self.proc.kill()
                self.proc = None
            log("speech:", "made" if out["ok"] else "failed", f"in {out.get('tts_s', '?')} s", out.get("error", ""))
            return out


class Ears:
    def __init__(self, args):
        self.args = args
        self.key = open(args.key_file).read().strip()
        self.model = None
        self.spk = None                # the speaker model: voice prints, for voice profiles
        self.vocab = []
        self.client = None             # the StreamWriter of the Pi that's connected
        self.lock = asyncio.Lock()     # the microphones can only be opened once at a time
        self.loaded = asyncio.Event()
        self.voice = Voice(args)
        self.wake = Wake(self)

    # ------------------------------------------------------------ the speech model
    def _load(self):
        import vosk
        vosk.SetLogLevel(-1)
        t = time.time()
        self.model = vosk.Model(self.args.model)
        log(f"speech model loaded in {time.time() - t:.1f} s")
        if self.args.spk and os.path.isdir(self.args.spk):
            try:
                self.spk = vosk.SpkModel(self.args.spk)
                log("speaker model loaded (voice profiles)")
            except Exception as e:
                log("no speaker model:", e)

    def _recognize(self, path, words, free=False, voice=False):
        """The words in a recording. With `free`, Vosk's whole vocabulary instead of a list;
        otherwise words it doesn't know come back as [unk]. With `voice`, the result also
        has a voice print ("spk": 128 numbers describing how the voice sounds, not what was
        said) when the speaker model is installed."""
        import vosk
        with wave.open(path, "rb") as w:
            grammar = [] if free else list(words or self.vocab)
            rec = vosk.KaldiRecognizer(self.model, w.getframerate(), json.dumps(grammar + ["[unk]"])) \
                if grammar else vosk.KaldiRecognizer(self.model, w.getframerate())
            if voice and self.spk:
                rec.SetSpkModel(self.spk)
            while True:
                data = w.readframes(4000)
                if not data:
                    break
                rec.AcceptWaveform(data)
        res = json.loads(rec.FinalResult())
        return res if voice else res.get("text", "")

    # ------------------------------------------------------------ sending to the Pi
    async def send(self, msg, to=None):
        w = to or self.client
        if not w:
            return
        try:
            w.write((json.dumps(msg) + "\n").encode())
            await w.drain()
        except (ConnectionError, OSError):
            pass

    # ------------------------------------------------------------ buttons
    async def keys(self):
        """`micgrab keys` prints a line per button press; pass them straight on."""
        while True:
            try:
                p = await asyncio.create_subprocess_exec(
                    self.args.micgrab, "keys", stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL)
            except OSError as e:
                log("can't read the buttons:", e)
                await asyncio.sleep(10)
                continue
            while True:
                line = await p.stdout.readline()
                if not line:
                    break
                line = line.decode(errors="replace").strip()
                if line.startswith("KEY "):
                    await self.send({"line": line})
            await p.wait()
            log("button reader stopped; starting it again")
            await asyncio.sleep(2)

    # ------------------------------------------------------------ questions
    async def hear(self, req):
        out = {"id": req.get("id"), "speech": False, "text": ""}
        path = os.path.join(self.args.tmp, f"hear-{os.getpid()}.wav")
        async with self.lock:
            try:
                t0 = time.monotonic()
                max_s = max(1, min(15, int(req.get("max_s", 8))))
                if self.wake.active:
                    # the microphones are already open for the wake word: record from that
                    spoke = await self.wake.capture(path, max_s, float(req.get("pre_s", 0)))
                    said = "SPEECH" if spoke else "SILENCE"
                else:
                    p = await asyncio.create_subprocess_exec(
                        self.args.micgrab, path, str(max_s), stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT)
                    said, _ = await asyncio.wait_for(p.communicate(), max_s + 10)
                    said = said.decode(errors="replace").strip()
                out["rec_s"] = round(time.monotonic() - t0, 2)
                if not said.startswith("SPEECH"):
                    if not said.startswith("SILENCE"):
                        out["error"] = said[:120] or "the recorder said nothing"
                    return out
                out["speech"] = True
                await asyncio.wait_for(self.loaded.wait(), 30)
                t1 = time.monotonic()
                await asyncio.to_thread(normalize, path)
                res = await asyncio.to_thread(self._recognize, path, req.get("words"), bool(req.get("free")), True)
                text = res.get("text", "")
                out["text"] = " ".join(x for x in text.split() if x != "[unk]")
                if res.get("spk"):
                    out["spk"] = [round(x, 4) for x in res["spk"]]
                    out["spk_frames"] = res.get("spk_frames", 0)
                # a request whose words could be anything ("add cranberries to the shopping
                # list"): listen to the same recording again with every word Vosk knows
                if req.get("free_if") and re.search(str(req["free_if"]), text):
                    out["free_text"] = await asyncio.to_thread(self._recognize, path, None, True)
                out["stt_s"] = round(time.monotonic() - t1, 2)
                return out
            except Exception as e:
                out["error"] = f"{type(e).__name__}: {e}"[:160]
                return out
            finally:
                try:
                    os.remove(path)          # recordings are never kept
                except OSError:
                    pass
                # what was said goes to Harald only, never into this log
                log("question:", "speech" if out["speech"] else "nobody spoke",
                    f"recording {out.get('rec_s', 0)} s, understanding {out.get('stt_s', 0)} s",
                    out.get("error", ""))

    # ------------------------------------------------------------ the Pi's connection
    async def serve(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            first = await asyncio.wait_for(reader.readline(), 10)
            hello = json.loads(first or b"{}")
        except (asyncio.TimeoutError, ValueError, ConnectionError):
            hello = {}
        if not isinstance(hello, dict) or hello.get("hello") != self.key:
            log("turned away a connection without the key from", peer)
            writer.close()
            return
        if self.client and self.client is not writer:      # the newest connection wins
            self.client.close()
        self.client = writer
        log("Harald connected from", peer)
        await self.send({"hello": "ok", "ready": self.loaded.is_set(), "voice": self.voice.available}, writer)
        tasks = set()
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    req = json.loads(line)
                except ValueError:
                    continue
                cmd = req.get("cmd")
                if cmd == "vocab":
                    self.vocab = [str(w) for w in req.get("words", [])][:5000]
                elif cmd == "hear":
                    async def answer(r=req, w=writer):
                        await self.send(await self.hear(r), w)
                    t = asyncio.ensure_future(answer())
                    tasks.add(t)
                    t.add_done_callback(tasks.discard)
                elif cmd == "say":
                    async def spoken(r=req, w=writer):
                        await self.send(await self.voice.say(r), w)
                    t = asyncio.ensure_future(spoken())
                    tasks.add(t)
                    t.add_done_callback(tasks.discard)
                elif cmd == "wake":            # the Pi: listen for "hey dragon" now, or stop
                    self.wake.on = bool(req.get("on"))
                    if "strict" in req:
                        self.wake.set_strict(req["strict"])
                    if not self.wake.on and self.wake.proc and self.wake.proc.returncode is None:
                        self.wake.proc.kill()
                    await self.send({"wake_state": self.wake.state()}, writer)
                elif cmd == "busy":            # he's talking (don't hear himself), or done
                    self.wake.busy = bool(req.get("on"))
                    if not self.wake.busy:
                        self.wake.busy_until = time.time() + 0.7
                elif cmd == "ping":
                    await self.send({"pong": 1, "ready": self.loaded.is_set(), "wake_state": self.wake.state()},
                                    writer)
        except (ConnectionError, OSError):
            pass
        finally:
            if self.client is writer:
                self.client = None
            writer.close()
            log("Harald disconnected")

    async def main(self):
        server = await asyncio.start_server(self.serve, "0.0.0.0", self.args.port)
        log(f"listening for Harald on port {self.args.port}")
        asyncio.ensure_future(self.keys())
        asyncio.ensure_future(self.wake.run())
        try:
            await asyncio.to_thread(self._load)
            self.loaded.set()
            await self.send({"pong": 1, "ready": True})
        except Exception as e:
            log("the speech model didn't load:", e)
        async with server:
            await server.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5577)
    ap.add_argument("--key-file", default=os.path.join(HERE, "ears.key"))
    ap.add_argument("--model", default="/opt/vosk-model")
    ap.add_argument("--micgrab", default=os.path.join(HERE, "micgrab"))
    ap.add_argument("--tmp", default="/tmp")
    ap.add_argument("--spk", default="/opt/vosk-spk", help="speaker model, for voice profiles")
    ap.add_argument("--piper", default="/opt/piper/piper")
    ap.add_argument("--voices", default="/opt/voices")
    ap.add_argument("--voice", default="", help="voice name; the first one found if not given")
    ap.add_argument("--say-file", default=os.path.join(HERE, "say.wav"))
    args = ap.parse_args()
    try:
        asyncio.run(Ears(args).main())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
