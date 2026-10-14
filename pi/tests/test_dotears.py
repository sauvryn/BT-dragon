"""Listening on the Dot: the Dot's half (dot_debian/ears.py, run here with a pretend Vosk
and a pretend micgrab) talking to the Pi's half (dotears.py) over a real local connection,
and DotLink using it for questions, buttons and "stop"."""
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import wave

from bt_dragon import dotears
from bt_dragon.dot import DotLink
from bt_dragon.store import Store

tmp = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "..", "bt_dragon", "dot_debian", "ears.py")

# a pretend Vosk: "hears" a fixed sentence, and notes which word list it was given
os.makedirs(os.path.join(tmp, "fakevosk", "vosk"))
open(os.path.join(tmp, "fakevosk", "vosk", "__init__.py"), "w").write('''
import json, os
def SetLogLevel(n): pass
class Model:
    def __init__(self, path): self.path = path
class SpkModel:
    def __init__(self, path): self.path = path
class KaldiRecognizer:
    def __init__(self, model, rate, grammar=None):
        self.g = json.loads(grammar) if grammar else None
        self.spk = None
        open(os.environ["GRAMMAR_LOG"], "a").write(json.dumps(self.g) + "\\n")
    def SetSpkModel(self, spk): self.spk = spk
    def SetWords(self, on): self.words = on
    def _voice(self, out):
        # a pretend voice print: whoever is named in the .voice file (A or B), with a little wobble
        v = os.environ["GRAMMAR_LOG"] + ".voice"
        if self.spk and os.path.exists(v):
            who = open(v).read().strip()
            base = [1.0 if (i % 2 == 0) == (who == "A") else 0.1 for i in range(128)]
            out["spk"] = [x + 0.05 * ((i * 7) % 3) for i, x in enumerate(base)]
            out["spk_frames"] = 250
        return json.dumps(out)
    def AcceptWaveform(self, data): return False
    def Result(self): return json.dumps({"text": ""})
    def Reset(self): pass
    def PartialResult(self):
        f = os.environ["GRAMMAR_LOG"] + ".wake"          # "hey dragon" is said once per file
        if self.g and "hey dragon" in self.g and os.path.exists(f):
            os.remove(f)
            return json.dumps({"partial": "hey dragon"})
        return json.dumps({"partial": ""})
    def FinalResult(self):
        if getattr(self, "words", False):               # the wake word's second look
            c = os.environ["GRAMMAR_LOG"] + ".conf"
            hc, dc = (open(c).read().split() if os.path.exists(c) else ("0.97", "0.9"))
            open(os.environ["GRAMMAR_LOG"] + ".checked", "a").write("x")
            return json.dumps({"text": "hey dragon", "result": [
                {"word": "hey", "conf": float(hc), "start": 0.9, "end": 1.1},
                {"word": "dragon", "conf": float(dc), "start": 1.12, "end": 1.6}]})
        q = os.environ["GRAMMAR_LOG"] + ".queue"         # scripted answers, one per recording
        if os.path.exists(q):
            lines = open(q).read().splitlines()
            if lines:
                open(q, "w").write("\\n".join(lines[1:]))
                return self._voice({"text": lines[0]})
        if self.g and "stop" in self.g and len(self.g) < 20:
            return json.dumps({"text": "okay stop"})
        if os.path.exists(os.environ["GRAMMAR_LOG"] + ".sumac"):      # an item the list doesn't know
            # with the word list, the nearest word it knows; with every word, the right one
            return json.dumps({"text": "add raspberries to the shopping list" if self.g else "add cranberries to the shopping list"})
        return json.dumps({"text": "what time is it in [unk] texas"})
''')
# a pretend micgrab: buttons, and a "recording" (speech, or silence when asked)
wav = os.path.join(tmp, "q.wav")
with wave.open(wav, "wb") as w:
    w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
    w.writeframes(b"\x10\x00\xf0\xff" * 8000)
mg = os.path.join(tmp, "micgrab")
open(mg, "w").write(f'''#!/bin/sh
if [ "$1" = keys ]; then
  sleep 0.5; echo "KEY VOLUP 1"; echo "KEY VOLUP 0"
  while [ ! -f {tmp}/press ]; do sleep 0.1; done; echo "KEY ACTION 1"; sleep 60; exit 0
fi
if [ "$1" = stream ]; then exec {sys.executable} {tmp}/stream.py; fi
if [ -f {tmp}/silent ]; then echo "SILENCE 4000 ms"; exit 0; fi
cp {wav} "$1"; echo "SPEECH 1500 ms"
''')
os.chmod(mg, 0o755)
# the microphones for the wake word: quiet, until a "talk" file appears: then half a second
# of quiet, a second of "speech" (a loud tone) and quiet again
open(os.path.join(tmp, "stream.py"), "w").write(f"""
import math, os, struct, sys, time
talk, n = None, 0
while True:
    if os.path.exists("{tmp}/talk"):
        os.remove("{tmp}/talk"); talk = n
    loud = talk is not None and 30 <= n - talk < 90
    blk = b"".join(struct.pack("<h", int(4000 * math.sin(i / 2.0)) if loud else (i % 5) * 4) for i in range(256))
    try:
        sys.stdout.buffer.write(blk); sys.stdout.buffer.flush()
    except BrokenPipeError:
        break
    n += 1
    time.sleep(0.016)
""")
keyfile = os.path.join(tmp, "ears.key")
# a pretend Piper (--json-input): writes half a second of tone per line, then prints the path
os.makedirs(os.path.join(tmp, "voices"))
open(os.path.join(tmp, "voices", "en_GB-test-medium.onnx"), "w").close()
fp = os.path.join(tmp, "piper")
open(fp, "w").write(f"""#!{sys.executable}
import json, sys, wave
print(" ".join(sys.argv[1:]), file=open("{tmp}/piper-args", "a"))
for line in sys.stdin:
    req = json.loads(line)
    with wave.open(req["output_file"], "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(b"\\x00\\x10" * 11025)
    print(req["output_file"], flush=True)
""")
os.chmod(fp, 0o755)

s = socket.socket()
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
s.close()
dotears.PORT = port


class Obj:
    pass


def ask_words_yes(g):
    """The listen after "Shall I...?" was given only the little yes/no list."""
    yes = __import__("bt_dragon.ask", fromlist=["x"]).YES_GRAMMAR
    return any(json.loads(line) in (yes, yes + ["[unk]"]) for line in open(g) if line.strip() and line.strip() != "null")


async def main():
    app = Obj()
    app.data_dir = os.path.join(tmp, "pi")
    os.makedirs(app.data_dir)
    app.store = Store(os.path.join(app.data_dir, "dragon.db"))
    app.cfg = {"home_wifi": {"ssid": "Home"}, "backup_wifi": [],
               "dot": {"enabled": True, "address": "", "networks": [], "voice": "", "audio_device": 23,
                       "amp_on_after": 0.2, "recap_after_minutes": 30, "stop_services": []}}
    app.home_ssid = "Home"
    app.stop = asyncio.Event()
    app.event = lambda k, t: None

    async def _sleep(sec):
        try:
            await asyncio.wait_for(app.stop.wait(), sec)
        except asyncio.TimeoutError:
            pass
    app._sleep = _sleep
    pet = Obj()
    pet.name, pet.sleeping = "Harald", False
    pet.mood = lambda: "happy"
    pet.say = lambda *a, **k: None
    app.pet = pet

    d = DotLink(app)
    d.s["quiet_from"] = d.s["quiet_to"] = "00:00"
    e = d.dot_ears
    # the key is made once and kept; the stage gets the Dot's half and the key
    assert len(e.key) == 32 and DotLink(app).dot_ears.key == e.key
    os.makedirs(os.path.join(tmp, "stage"))
    e.stage(os.path.join(tmp, "stage"))
    assert open(os.path.join(tmp, "stage", "ears.key")).read().strip() == e.key
    assert os.path.exists(os.path.join(tmp, "stage", "ears.py"))
    open(keyfile, "w").write(e.key + "\n")

    # starting it: the command that stops an old copy must never contain the new one's
    # command line, or `pkill -f` on the Dot stops the very shell that's starting it
    sent = []

    async def fake_sh(script, timeout=20):
        sent.append(script)
        return ""
    real_sh, d.sh = d.sh, fake_sh
    await e.restart()
    d.sh = real_sh
    assert any("pkill" in c for c in sent) and any("ears.py --port" in c for c in sent), sent
    assert not [c for c in sent if "pkill" in c and "harald/ears.py" in c], sent
    # ...and the Dot's firewall is opened for the ears' port (only the Pi, when it knows its address)
    fw = [c for c in sent if "iptables" in c]
    assert len(fw) == 2 and f"--dport {port} -j ACCEPT" in fw[0] and "iptables -C INPUT" in fw[0], fw

    env = dict(os.environ, PYTHONPATH=os.path.join(tmp, "fakevosk"), GRAMMAR_LOG=os.path.join(tmp, "grammar"))
    server = subprocess.Popen([sys.executable, "-u", SERVER, "--port", str(port), "--key-file", keyfile,
                               "--model", tmp, "--micgrab", mg, "--tmp", tmp,
                               "--piper", fp, "--voices", os.path.join(tmp, "voices"), "--voice", "en_GB-test-medium",
                               "--say-file", os.path.join(tmp, "say.wav"), "--spk", tmp],
                              env=env, stdout=open(os.path.join(tmp, "ears.log"), "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(50):                       # wait for it to start listening
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)

        # a stranger without the key is turned away
        r, w = await asyncio.open_connection("127.0.0.1", port)
        w.write(b'{"hello": "guess"}\n')
        await w.drain()
        assert await asyncio.wait_for(r.read(), 5) == b""
        w.close()

        # Harald connects; the buttons come through the Dot's ears, not adb
        d.connected = d.ready = True
        d.target = f"127.0.0.1:{port}"
        e.installed = True
        e.last_up = time.time()
        assert e.handles_keys
        task = asyncio.ensure_future(e.run())
        for _ in range(100):
            await asyncio.sleep(0.05)
            if e.connected and e.ready:
                break
        assert e.connected and e.ready and e.state == "listening on the Dot", e.state
        vol = d.s["volume"]
        for _ in range(40):
            await asyncio.sleep(0.05)
            if d.s["volume"] != vol:
                break
        assert d.s["volume"] == min(100, vol + 10), "the volume button didn't come through"
        st = d.status()
        assert st["ears_where"] == "Dot" and st["ears"] and st["ears_note"] == ""
        assert "on hold" in d.mic.why_not()

        # the action button: a question recorded and understood on the Dot
        open(os.path.join(tmp, "press"), "w").close()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if d.answered and not d.asking:
                break
        assert d.heard == "what time is it in texas", d.heard            # [unk] dropped
        assert d.answered.startswith("In Texas it's") and "understood on the Dot" in d.timing, (d.answered, d.timing)
        grammars = [json.loads(l) for l in open(os.path.join(tmp, "grammar"))]
        assert "what time is it in" in grammars[-1] and grammars[-1][-1] == "[unk]"   # phrases sent over
        assert not [f for f in os.listdir(tmp) if f.startswith("hear-")]             # nothing kept
        d.queue.clear()

        # speech made on the Dot: Piper there, converted for the speaker, silence around it
        assert e.voice
        r = await e.say("Hello.", speed=1.0, pitch=0.0, volume=0.5, lead=0.6, tail=0.6)
        assert r and r["ok"] and abs(r["speech_s"] - 0.5) < 0.01, r
        with wave.open(os.path.join(tmp, "say.wav")) as w:
            assert (w.getnchannels(), w.getframerate()) == (2, 48000)
            assert abs(w.getnframes() / 48000 - 1.7) < 0.01
            w.readframes(int(0.6 * 48000) + 100)
            v = int.from_bytes(w.readframes(1)[:2], "little", signed=True)
        assert 0x1000 * 0.5 - 50 < v < 0x1000 * 0.5 + 50, v               # volume applied
        # a deeper voice: Piper speaks faster, and the playback is slowed down to match
        r = await e.say("Hello.", speed=1.0, pitch=-12, lead=0, tail=0)
        assert r["ok"] and abs(r["speech_s"] - 1.0) < 0.01, r                 # an octave down: twice as long
        assert "--length_scale 0.500" in open(os.path.join(tmp, "piper-args")).read()
        # Harald speaking: made on the Dot, the Pi's Piper not needed
        d._ask_done, d.timing = time.monotonic(), "button, understood on the Dot: listening 1 s"
        await d._speak("It's eleven o'clock.")
        assert "making speech" in d.timing and d.timing.endswith("on the Dot"), d.timing
        # a longer answer: a sentence at a time, the next one made while one plays
        played = []
        real_play = d._play

        async def fake_play(name, secs):
            played.append((name, round(secs, 2), os.path.exists(os.path.join(tmp, name))))
            await asyncio.sleep(0.05)
        d._play = fake_play
        d._ask_done, d.timing = time.monotonic(), "button, understood on the Dot: listening 1 s"
        await d._speak("Right now it's 16 degrees, and overcast. Later today: between 10 and 17 degrees. "
                       "Tomorrow it should stay dry all day long.")
        assert [p[0] for p in played] == ["say1.wav", "say2.wav", "say1.wav"] and all(p[2] for p in played), played
        assert "(first of 3 sentences)" in d.timing and not d._speaking, d.timing
        # told to be quiet in the middle: the rest isn't said
        played.clear()

        async def hushing_play(name, secs):
            played.append(name)
            d.hush()
        d._play = hushing_play
        await d._speak("One sentence that is long enough. Another sentence that is long enough. And a third one here.")
        assert played == ["say1.wav"], played
        d._play = real_play

        # the shopping list by voice: an item the word list doesn't know (heard as a word it
        # does know) is caught by a second listen with the whole vocabulary
        open(os.path.join(tmp, "grammar.sumac"), "w").close()
        d.answered = ""
        d.on_key("KEY ACTION 1")
        for _ in range(100):
            await asyncio.sleep(0.05)
            if d.answered and not d.asking:
                break
        os.remove(os.path.join(tmp, "grammar.sumac"))
        assert d.heard == "add cranberries to the shopping list", d.heard
        assert d.answered == "I've added cranberries to the shopping list." and d.shopping.find("cranberries"), d.answered
        assert not d.shopping.find("raspberries")
        grammars = [json.loads(l) for l in open(os.path.join(tmp, "grammar"))]
        assert grammars[-1] is None and grammars[-2]                       # second listen: no list
        d.shopping.add("sumac")
        assert "sumac" in d.grammar()                                     # typed items are known by ear
        assert (await d.answer("what's on the shopping list")).endswith("Other: sumac.")
        assert await d.answer("take sumac off the list") == "I've taken sumac off the shopping list."
        assert await d.answer("add to the shopping list") == \
            "I didn't catch the item. You can type it on the shopping list page in my den."
        d.queue.clear()

        # voice profiles: "Set a voice profile", "Who is speaking?", a name, a sentence or two
        from bt_dragon import tuning
        G = os.path.join(tmp, "grammar")
        open(G + ".voice", "w").write("A")
        open(G + ".queue", "w").write("set a voice profile\nmy name is sam\ntoday i went for a lovely walk in the park\n")
        d.answered = ""
        d.on_key("KEY ACTION 1")
        for _ in range(200):
            await asyncio.sleep(0.05)
            if d.answered and not d.asking:
                break
        assert d.answered == "Got it, Sam. I'll know your voice from now on.", d.answered
        assert [p["name"] for p in d.voices.items] == ["Sam"] and d.voices.items[0]["samples"] == 3
        d.queue.clear()
        tuning._over["name_chance"] = 100.0                         # always use the name, for the test
        open(G + ".queue", "w").write("what time is it\n")
        d.answered = ""
        d.on_key("KEY ACTION 1")
        for _ in range(100):
            await asyncio.sleep(0.05)
            if d.answered and not d.asking:
                break
        assert d.answered.startswith("It's") and d.answered.endswith(", Sam."), d.answered
        assert d.speaker == "Sam" and d.heard_from.startswith("Sam ("), d.heard_from
        d.queue.clear()
        open(G + ".voice", "w").write("B")                           # someone else
        open(G + ".queue", "w").write("who am i\n")
        d.answered = ""
        d.on_key("KEY ACTION 1")
        for _ in range(100):
            await asyncio.sleep(0.05)
            if d.answered and not d.asking:
                break
        assert d.speaker is None and d.answered.startswith("I'm not sure"), (d.speaker, d.answered)
        del tuning._over["name_chance"]
        os.remove(G + ".voice")
        d.queue.clear()

        # "go to sleep" / "take a nap": he checks first, and only a clear yes counts
        rested = []

        async def shutdown(how="SLEEP"):
            rested.append(how)

        async def nap():
            rested.append("NAP")
        app.shutdown, app.nap = shutdown, nap
        for said, answer, expect in (("go to sleep", "no", []), ("go to sleep", "[unk]", []),
                                     ("take a nap", "yes please", ["NAP"]), ("go to sleep", "yeah", ["SLEEP"])):
            rested.clear()
            open(G + ".queue", "w").write(f"{said}\n{answer}\n")
            d.answered, d.heard = "", ""
            d.on_key("KEY ACTION 1")
            for _ in range(150):
                await asyncio.sleep(0.05)
                if d.heard.startswith(said) and not d.asking:
                    break
            await asyncio.sleep(0.1)
            assert rested == expect, (said, answer, rested, d.heard)
            assert d.heard == f"{said}, then: {answer if answer != '[unk]' else '(nothing)'}", d.heard
            if expect == ["NAP"]:
                assert d.answered == "I'll have a lie down for a bit. Wake me up later."
            elif expect:
                assert d.answered == "Going to sleep now. Good night!"
            d.queue.clear()
        assert ask_words_yes(G)
        d.queue.clear()

        # the wake word, on the Dot: "hey dragon", then the question from the same stream
        assert d._wake_status()["wake_why"] == "switched off"
        d.s["wake"], d.s["wake_from"], d.s["wake_to"] = True, "00:00", "00:00"
        assert d.wake_reason() == ""
        await e.set_wake(True)
        for _ in range(100):
            await asyncio.sleep(0.05)
            if e.wake_state.get("active"):
                break
        st = d._wake_status()
        assert st["wake_active"] and st["wake_where"] == "Dot" and st["wake_why"] == "", st
        open(G + ".queue", "w").write("what time is it\n")
        d.answered = ""
        open(G + ".wake", "w").close()
        open(os.path.join(tmp, "talk"), "w").close()
        for _ in range(200):
            await asyncio.sleep(0.05)
            if d.answered and not d.asking:
                break
        assert d.answered.startswith("It's") and d.timing.startswith("wake word"), (d.answered, d.timing, e.wake_state)
        assert e.wake_state["heard"] == 1 and e.wake_state["strict"] == 50 and e.wake_state["conf"] == 90
        assert os.path.exists(G + ".checked") and d.wake_unasked == 0
        d.queue.clear()
        # not sure enough: turned down, and the den says why
        open(G + ".conf", "w").write("0.95 0.4")
        open(G + ".wake", "w").close()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if e.wake_state.get("turned_down"):
                break
        assert e.wake_state["heard"] == 1 and e.wake_state["turned_down"] == 1, e.wake_state
        assert d._wake_status()["wake_last_no"] == "only 40% sure" and d._wake_status()["wake_conf"] == 40
        # looser: the same is good enough
        tuning._over["wake_strict"] = 25
        await e.set_wake(True, 25)
        await asyncio.sleep(3.2)                          # past the 3 s between wake-ups
        open(G + ".wake", "w").close()
        for _ in range(200):
            await asyncio.sleep(0.05)
            if e.wake_state.get("heard") == 2 and not d.asking:
                break
        assert e.wake_state["heard"] == 2 and e.wake_state["strict"] == 25, e.wake_state
        for _ in range(100):
            await asyncio.sleep(0.05)
            if d.wake_unasked:
                break
        assert d.wake_unasked == 1                        # woke, then nobody asked anything
        del tuning._over["wake_strict"]
        os.remove(G + ".conf")
        d.queue.clear()
        # while he's talking he doesn't listen to himself
        await e.busy(True)
        open(G + ".wake", "w").close()
        await asyncio.sleep(1.0)
        assert e.wake_state["heard"] == 2 and os.path.exists(G + ".wake")
        await e.busy(False)
        os.remove(G + ".wake")
        d.s["wake"] = False
        await e.set_wake(False)
        for _ in range(100):
            await asyncio.sleep(0.05)
            if not e.wake_state.get("active"):
                break
        assert not e.wake_state.get("active") and d._wake_status()["wake_why"] == "switched off"

        # nobody speaks: no answer, no error
        open(os.path.join(tmp, "silent"), "w").close()
        text, where, _, _ = await d._hear("ask.wav", 8)
        assert text is None and where == "Dot"
        os.remove(os.path.join(tmp, "silent"))

        # "stop" while a timer rings uses its own short word list
        d.alarm = {"names": ["your timer"], "since": time.time(), "next": time.time() + 99}
        await d._listen_for_stop()
        assert d.alarm is None, "didn't hear stop"

        # a firewall in the way: after a few tries the same connection goes through adb instead
        d.connected = False
        e._writer.close()
        await asyncio.wait_for(task, 10)
        forwards = []

        async def fake_adb(*a, timeout=20, target=True):
            forwards.append(a)
            return 0, ""
        real_adb, d._adb = d._adb, fake_adb
        real_sleep = app._sleep
        app._sleep = lambda sec: real_sleep(min(sec, 0.1))
        dotears.PORT, dotears.LOCAL_PORT = 1, port          # nothing listens on port 1
        d.connected = True
        task = asyncio.ensure_future(e.run())
        for _ in range(100):
            await asyncio.sleep(0.05)
            if e.connected:
                break
        assert e.connected and e.via_adb and ("forward", f"tcp:{port}", "tcp:1") in forwards, forwards
        assert "through the debug link" in e.state and d.status()["ears_note"] == "through the debug link"
        text, where, _, _ = await d._hear("ask.wav", 8)
        assert text == "what time is it in texas" and where == "Dot"
        d._adb, app._sleep = real_adb, real_sleep

        # the Dot's ears go away: questions fall back to the Pi (none installed here) quietly
        server.kill()
        server.wait()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if not e.connected:
                break
        assert not e.connected and d.status()["ears_where"] != "Dot"
        app.stop.set()
        await asyncio.wait_for(task, 10)
    finally:
        if server.poll() is None:
            server.kill()


asyncio.run(main())

# the same second listen when the Pi does the hearing (no Debian on the Dot)
sys.path.insert(0, os.path.join(tmp, "fakevosk"))
os.environ["GRAMMAR_LOG"] = os.path.join(tmp, "grammar-pi")
from bt_dragon import hearing  # noqa: E402
os.makedirs(os.path.join(tmp, "model", "conf"))
open(os.path.join(tmp, "model", "conf", "model.conf"), "w").close()
hearing.MODEL_DIRS = [os.path.join(tmp, "model")]
ears = hearing.Ears(["add", "eggs"])
open(os.environ["GRAMMAR_LOG"] + ".sumac", "w").close()
from bt_dragon import ask  # noqa: E402
r = asyncio.run(ears.hear_full(wav, ["add", "eggs"], ask.FREE_IF))
assert r == {"text": "add raspberries to the shopping list", "free_text": "add cranberries to the shopping list"}, r
r = asyncio.run(ears.hear_full(wav, ["add", "eggs"], r"\btimer\b"))       # not a shopping request
assert "free_text" not in r, r
print("dotears ok")
