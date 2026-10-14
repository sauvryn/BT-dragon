"""
The wake word ("Hey dragon"), as a trial.

While it's switched on (in the den, during the hours you choose), `micgrab stream` on the
Echo Dot sends the microphones, mixed to one channel, to the Pi for as long as the Pi
reads them: 16,000 samples a second, 32 KB/s, over your own hotspot only. Nothing is
saved. A background thread on the Pi feeds the sound to Vosk with a tiny word list
("hey dragon" plus a few everyday decoys); when it hears "hey dragon", Harald listens for
a question exactly as if you'd pressed the action button.

The same stream is used for questions and for "stop" while a timer rings, since the Dot's
microphones can only be opened by one program at a time.
"""
import array
import asyncio
import collections
import json
import logging
import os
import queue
import threading
import time
import wave

log = logging.getLogger("wake")

RATE = 16000
BLOCK = 256                    # samples per piece (16 ms), as micgrab sends them
BLOCK_BYTES = BLOCK * 2
WAKE_PHRASE = "hey dragon"
# decoys: everyday words for the recognizer to choose instead, so not everything sounds
# like "hey dragon" to it
GRAMMAR = [WAKE_PHRASE, "hey", "okay", "the", "what", "and", "it", "is", "a", "to", "dragon", "[unk]"]


class Vad:
    """When someone starts and stops talking: the same rules as micgrab's (see micgrab.c)."""

    def __init__(self, max_s=8, wait_s=4):
        self.noise, self.blocks, self.loud, self.quiet = 0, 0, 0, 0
        self.speech = False
        self.max_blocks = int(max_s * RATE / BLOCK)
        self.wait_blocks = int(wait_s * RATE / BLOCK)

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


def write_wav(path, chunks):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(chunks))


class MicStream:
    def __init__(self, dot):
        self.dot = dot
        self.active = False            # sound is arriving right now
        self.proc = None
        self.taps = []                 # questions being recorded from the stream
        self.pre = collections.deque(maxlen=int(1.0 * RATE / BLOCK))   # the last second
        self.q = queue.Queue(maxsize=400)
        self.thread = None
        self.loop = None
        self.heard = 0                 # how many times he's heard the wake word
        self.last_heard = 0.0
        self.cpu = None                # share of one processor core the listening takes
        self._quit = False
        self._last_wake = 0.0
        self.error = ""                # what went wrong with the stream, if anything

    # ------------------------------------------------------------ when to listen
    def why_not(self):
        """'' if he should be listening now, otherwise the reason he isn't (for the den)."""
        d = self.dot
        from .dot import in_quiet       # the same "between these times" rule
        lt = time.localtime()
        in_hours = in_quiet(d.s["wake_from"], d.s["wake_to"], lt.tm_hour * 60 + lt.tm_min) \
            or d.s["wake_from"] == d.s["wake_to"]
        for bad, why in ((d.dot_ears.installed, "on hold while the Dot does the listening"),
                         (not d.s["wake"], "switched off"), (not d.s["listen"], "answering questions is off"),
                         (not in_hours, "outside the listening hours"),
                         (not (d.connected and d.ready), "the Dot isn't connected"),
                         (d.rescuing, "rescuing the Dot"), (d.mic_muted, "the microphones are off"),
                         (not d.ears.available, "the speech recognizer isn't installed")):
            if bad:
                return why
        return ""

    def wanted(self):
        return not self.why_not()

    # ------------------------------------------------------------ the stream
    async def run(self):
        """Keep the stream going whenever it's wanted, for as long as the Dot is connected."""
        from .dot import H
        self.loop = asyncio.get_running_loop()
        d = self.dot
        while d.connected and not d.app.stop.is_set():
            if not self.wanted():
                await d.app._sleep(5)
                continue
            self._start_thread()
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    "adb", "-s", d.target, "exec-out",
                    f"pkill -f 'micgrab [s]tream'; exec {H}/micgrab stream 8",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            except OSError as e:
                self.error = f"couldn't start adb: {e}"
                return
            log.info("wake word: starting to listen")
            buf = b""
            try:
                while self.wanted():
                    try:
                        data = await asyncio.wait_for(self.proc.stdout.read(4096), 5)
                    except asyncio.TimeoutError:
                        break
                    if not data:
                        break
                    if not self.active and data[:6] in (b"ERROR ", b"usage:", b"SPEECH", b"SILENC"):
                        # micgrab printed a message instead of sound: show it in the den
                        self.error = data.decode(errors="replace").strip().splitlines()[0][:100]
                        log.warning("wake word stream: %s", self.error)
                        break
                    self.active, self.error = True, ""
                    buf += data
                    while len(buf) >= BLOCK_BYTES:
                        self._block(buf[:BLOCK_BYTES])
                        buf = buf[BLOCK_BYTES:]
            finally:
                self.active = False
                if self.proc and self.proc.returncode is None:
                    self.proc.kill()
                self.proc = None
                log.info("wake word: stopped listening")
            if not self.active and self.wanted() and not self.error:
                self.error = "the Dot didn't send any sound"
            await d.app._sleep(2 if not self.error else 15)
        self._quit = True

    def _block(self, blk):
        self.pre.append(blk)
        for tap in list(self.taps):
            tap.put_nowait(blk)
        d = self.dot
        busy = d.asking or d._speaking or d.queue or time.time() - d._last_spoke < 0.7
        if not busy and not self.taps:      # he can't hear himself think while he talks
            try:
                self.q.put_nowait(blk)
            except queue.Full:
                pass

    # ------------------------------------------------------------ hearing the wake word
    def _start_thread(self):
        if self.thread and self.thread.is_alive():
            return
        self._quit = False
        self.thread = threading.Thread(target=self._detect, name="wake-word", daemon=True)
        self.thread.start()

    def _detect(self):
        try:
            import vosk
            ears = self.dot.ears
            ears.preload()
            rec = vosk.KaldiRecognizer(ears.model, RATE, json.dumps(GRAMMAR))
        except Exception as e:
            log.warning("wake word: the recognizer didn't start: %s", e)
            return
        cpu0, audio = time.thread_time(), 0.0
        while not self._quit:
            try:
                blk = self.q.get(timeout=1)
            except queue.Empty:
                continue
            audio += len(blk) / (2 * RATE)
            if rec.AcceptWaveform(blk):
                text = json.loads(rec.Result()).get("text", "")
            else:
                text = json.loads(rec.PartialResult()).get("partial", "")
            if WAKE_PHRASE in text:
                rec.Reset()
                if self.loop:
                    self.loop.call_soon_threadsafe(self._woke)
            if audio >= 10:
                self.cpu = round((time.thread_time() - cpu0) / audio, 2)
                cpu0, audio = time.thread_time(), 0.0

    def _woke(self):
        now = time.time()
        if now - self._last_wake < 3:
            return
        self._last_wake = now
        self.heard += 1
        self.last_heard = now
        log.info("wake word heard")
        # drop anything waiting, so the question isn't mistaken for another wake word
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self.dot.on_wake()

    # ------------------------------------------------------------ recording from the stream
    async def capture(self, path, max_s=8, wait_s=4, pre_s=0.5):
        """Record from the stream until the speaker stops (like micgrab does). Includes the
        last `pre_s` seconds, in case the question followed the wake word without a pause.
        Returns True if there was speech."""
        tap = asyncio.Queue()
        chunks = list(self.pre)[-int(pre_s * RATE / BLOCK):] if pre_s else []
        vad = Vad(max_s, wait_s)
        self.taps.append(tap)
        try:
            while True:
                try:
                    blk = await asyncio.wait_for(tap.get(), 3)
                except asyncio.TimeoutError:
                    break                     # the stream stopped
                chunks.append(blk)
                s = array.array("h")
                s.frombytes(blk)
                if vad.feed(s):
                    break
        finally:
            self.taps.remove(tap)
        await asyncio.to_thread(write_wav, path, chunks)
        return vad.speech
