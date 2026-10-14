"""
Harald's ears: turning a recorded question into words, offline, with Vosk.

Vosk is a speech recognizer that runs on small computers. A "small" English model is about
40 MB; the installer puts it in /opt/bt-dragon/vosk-model. Harald gives it a fixed list of
words (ask.VOCABULARY): with a short list it only has to choose between a few hundred
words instead of tens of thousands, which makes it both faster and much more accurate on
a Pi Zero 2. Nothing you say leaves the Pi.

The model is loaded the first time it's needed (it takes a few seconds and ~100 MB of
memory) and let go again when the Dot has been away for a while.
"""
import array
import asyncio
import json
import logging
import os
import re
import wave

log = logging.getLogger("hearing")

MODEL_DIRS = ["/opt/bt-dragon/vosk-model"]
SPK_DIRS = ["/opt/bt-dragon/vosk-spk"]     # the speaker model (voice prints), for voice profiles


def find_model():
    for d in MODEL_DIRS:
        if os.path.isdir(os.path.join(d, "am")) or os.path.isfile(os.path.join(d, "conf", "model.conf")):
            return d
    return None


def normalize(path):
    """Raise a quiet 16-bit mono recording so its loudest part is near full scale (in place).
    Returns the peak level before (0-32767)."""
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
    return peak


class Ears:
    def __init__(self, vocabulary):
        self.vocabulary = vocabulary
        self.model = None
        self.lock = asyncio.Lock()

    @property
    def available(self):
        try:
            import vosk  # noqa: F401
        except ImportError:
            return False
        return find_model() is not None

    def _load(self):
        import vosk
        vosk.SetLogLevel(-1)
        self.model = vosk.Model(find_model())
        spk = next((d for d in SPK_DIRS if os.path.isdir(d)), None)
        self.spk = None
        if spk:
            try:
                self.spk = vosk.SpkModel(spk)
            except Exception as e:
                log.warning("no speaker model: %s", e)

    def preload(self):
        """Load the model now, so the first question isn't slow (a few seconds on a Pi Zero 2)."""
        if self.model is None and self.available:
            self._load()

    def _recognize(self, path, vocabulary=None, free=False, keep_unk=False, voice=False):
        import vosk
        if self.model is None:
            self._load()
        with wave.open(path, "rb") as w:
            rec = vosk.KaldiRecognizer(self.model, w.getframerate()) if free else \
                vosk.KaldiRecognizer(self.model, w.getframerate(),
                                     json.dumps(list(vocabulary or self.vocabulary) + ["[unk]"]))
            if voice and getattr(self, "spk", None):
                rec.SetSpkModel(self.spk)
            while True:
                data = w.readframes(4000)
                if not data:
                    break
                rec.AcceptWaveform(data)
        res = json.loads(rec.FinalResult())
        text = res.get("text", "")
        text = text if keep_unk else " ".join(x for x in text.split() if x != "[unk]")
        return dict(res, text=text) if voice else text

    def _recognize_full(self, path, vocabulary, free_if, free=False):
        res = self._recognize(path, vocabulary, free=free, keep_unk=True, voice=True)
        text = res["text"]
        out = {"text": " ".join(x for x in text.split() if x != "[unk]")}
        if res.get("spk"):
            out["spk"], out["spk_frames"] = res["spk"], res.get("spk_frames", 0)
        if free_if and re.search(free_if, text):
            out["free_text"] = self._recognize(path, free=True)
        return out

    async def hear(self, path, vocabulary=None):
        """The words in a recording ('' if nothing recognisable). A shorter `vocabulary`
        (like just "stop") makes it quicker and surer still."""
        async with self.lock:
            return await asyncio.to_thread(self._recognize, path, vocabulary)

    async def hear_full(self, path, vocabulary=None, free_if=None, free=False):
        """Like hear, but returns a dict: "text", a voice print ("spk") if the speaker model
        is installed, and if what was heard matches the pattern `free_if`, the recording
        listened to again with every word the model knows ("free_text")."""
        async with self.lock:
            return await asyncio.to_thread(self._recognize_full, path, vocabulary, free_if, free)

    def forget(self):
        self.model = None
