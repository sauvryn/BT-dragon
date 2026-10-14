"""The wake-word trial: the Pi's copy of micgrab's "when are you talking" rules, and
recording a question from the stream."""
import array
import asyncio
import math
import os
import random
import tempfile
import wave

from bt_dragon import wake


def blocks(speech_start, speech_len, total):
    rnd = random.Random(1)
    n = 0
    while n * wake.BLOCK < total * wake.RATE:
        s = array.array("h")
        for i in range(wake.BLOCK):
            t = (n * wake.BLOCK + i) / wake.RATE
            v = rnd.randint(-100, 100)
            if speech_start <= t < speech_start + speech_len:
                v += int(1500 * math.sin(2 * math.pi * 220 * t) * (0.6 + 0.4 * math.sin(2 * math.pi * 3 * t)))
            s.append(v)
        yield s
        n += 1


def stop_time(speech_start, speech_len, max_s=8):
    v = wake.Vad(max_s)
    for i, b in enumerate(blocks(speech_start, speech_len, 30)):
        if v.feed(b):
            return (i + 1) * wake.BLOCK / wake.RATE, v.speech
    return None, v.speech


t, sp = stop_time(0.5, 2.0)
assert sp and 3.2 < t < 3.5, t            # stops 0.8 s after you stop talking (as micgrab does)
t, sp = stop_time(99, 0)
assert not sp and abs(t - 4.0) < 0.05, t  # nobody spoke: gives up after 4 s
t, sp = stop_time(0.5, 20)
assert sp and abs(t - 8.0) < 0.05, t      # never longer than 8 s


class Obj:
    pass


async def main():
    d = Obj()
    d.asking = d._speaking = False
    d.queue, d._last_spoke = [], 0.0
    m = wake.MicStream(d)
    m.active = True
    for b in blocks(99, 0, 1.0):          # a second of room sound before the question
        m._block(b.tobytes())
    assert m.q.qsize() > 0                 # it goes to the wake-word listener...
    path = os.path.join(tempfile.mkdtemp(), "q.wav")

    async def feed():
        while not m.taps:
            await asyncio.sleep(0.01)
        for b in blocks(0.3, 1.5, 4):
            if not m.taps:                 # the question's been recorded
                break
            m._block(b.tobytes())
            await asyncio.sleep(0)
    f = asyncio.ensure_future(feed())
    q_before = m.q.qsize()
    spoke = await m.capture(path, 8, pre_s=0.5)
    await f
    assert spoke and m.q.qsize() == q_before    # ...but not while a question is being recorded
    with wave.open(path) as w:
        secs = w.getnframes() / w.getframerate()
    assert 2.5 < secs < 3.4, secs          # 0.5 s from before + question + 0.8 s of quiet
    assert not m.taps


asyncio.run(main())
print("wake ok")

# how strict the wake word on the Dot is (the knob in Dev Tools)
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "dot_ears", os.path.join(os.path.dirname(__file__), "..", "bt_dragon", "dot_debian", "ears.py"))
ears = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ears)
loose, mid, tight = ears.wake_rules(0), ears.wake_rules(50), ears.wake_rules(100)
assert loose["grammar"][:13] == ["hey dragon", "hey", "okay", "the", "what", "and", "it", "is", "a", "to", "dragon",
                                 "hay", "they"][:13] and not loose["confirm"] and len(loose["grammar"]) == 14
assert len(loose["grammar"]) < len(mid["grammar"]) < len(tight["grammar"]) and tight["grammar"][-1] == "[unk]"
assert len(set(tight["grammar"])) == len(tight["grammar"]) and ears.wake_rules(500) == tight
assert mid["confirm"] and not mid["pause"] and tight["pause"] and mid["min_conf"] < tight["min_conf"] == 0.95


def said(*ws):
    return {"result": [{"word": w, "conf": c, "start": s, "end": s + 0.2} for w, c, s in ws]}


assert ears.check_wake(said(("hey", 0.9, 1.0), ("dragon", 0.8, 1.25)), mid, 2.5) == (True, (1.0, 1.45), 0.8)
assert ears.check_wake(said(("hey", 0.9, 1.0), ("dragon", 0.4, 1.25)), mid, 2.5)[:2] == (False, "only 40% sure")
assert ears.check_wake(said(("they", 0.9, 1.0), ("dragon", 0.9, 1.25)), mid, 2.5)[0] is False
mid_sentence = said(("what", 1, 0.5), ("hey", 1, 0.75), ("dragon", 1, 1.0))
assert ears.check_wake(mid_sentence, mid, 2.5)[0] and ears.check_wake(mid_sentence, ears.wake_rules(70), 2.5)[0] is False
assert ears.check_wake(said(("what", 1, 0.2), ("hey", 1, 1.0), ("dragon", 1, 1.25)), tight, 2.5)[0]
print("wake strictness ok")
