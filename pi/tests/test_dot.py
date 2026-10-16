"""The Echo Dot: speech text, ring frames, quiet hours, the recap, and a full run against a
pretend Dot (a fake `adb` that runs the commands in a temporary folder, with the real
light player script)."""
import asyncio
import os
import shutil
import stat
import sys
import tempfile
import time
import wave

from bt_dragon import ring
from bt_dragon import voice as voicemod
from bt_dragon.dot import DotLink, build_recap, in_quiet, DEFAULTS
from bt_dragon.store import Store

# ---------------------------------------------------------------- speech text
sp = voicemod.speakable
assert sp("TREAT! coffee_shop_Guest (WPA3, FANCY)") == "Treat! Coffee shop guest, W P A 3, fancy.", sp("TREAT! coffee_shop_Guest (WPA3, FANCY)")
assert sp("LEVEL UP! HARALD IS NOW LEVEL 3", "Harald") == "Level up! Harald is now level 3!" or \
       sp("LEVEL UP! HARALD IS NOW LEVEL 3", "Harald") == "Level up! Harald is now level 3.", sp("LEVEL UP! HARALD IS NOW LEVEL 3", "Harald")
assert sp("A STORM IS COMING! (-3.4 HPA)") == "A storm is coming! Minus 3.4 hectopascals.", sp("A STORM IS COMING! (-3.4 HPA)")
assert sp("BERRIES! 2 KNOWN NETWORKS +3 FOOD") == "Berries! 2 known networks plus 3 food.", sp("BERRIES! 2 KNOWN NETWORKS +3 FOOD")
assert sp("NOM! 3 NEW SNACKS") == "Nom nom! 3 new snacks.", sp("NOM! 3 NEW SNACKS")
assert sp("YOU'RE BACK! I WAS ASLEEP FOR 2 HOURS") == "You're back! I was asleep for 2 hours.", sp("YOU'RE BACK! I WAS ASLEEP FOR 2 HOURS")

# ---------------------------------------------------------------- ring frames
h = ring.hex_frame([ring.WHITE] * 12, balance=(1, 1, 1), brightness=1.0)
assert h == "FF" * 36, h
h = ring.hex_frame([ring.OFF] * 11 + [ring.RED], balance=(1, 0.5, 0.5), brightness=0.5)
assert len(h) == 72 and h[:66] == "0" * 66 and h[66:] == "800000", h
assert ring.hex_frame([(0.5, 0.5, 0.5)] * 12, balance=(1, 1, 1), brightness=1)[:2] == "37"   # gamma: 0.5 looks half as bright
txt = ring.to_text(ring.solid(ring.GOLD, 1.0) + ring.solid(ring.GOLD, 0.5) + ring.solid(ring.OFF, 0.2))
lines = txt.strip().split("\n")
assert len(lines) == 2 and lines[0].startswith("1.50 ") and lines[1] == "0.20 " + "0" * 72, txt
anims = ring.all_animations()
for name, frames in anims.items():
    t = ring.to_text(frames)
    for line in t.strip().split("\n"):
        s, hx = line.split(" ")
        assert float(s) > 0 and len(hx) == 72, (name, line)
assert {"off", "night", "mood_happy", "ev_storm", "ev_talk", "moon_0", "moon_12"} <= set(anims)
assert set(ring.MOOD_ANIM) >= {"content", "happy", "ecstatic", "alarmed", "asleep"}

# ---------------------------------------------------------------- quiet hours
assert in_quiet("22:00", "08:00", 23 * 60) and in_quiet("22:00", "08:00", 7 * 60 + 59)
assert not in_quiet("22:00", "08:00", 8 * 60) and not in_quiet("22:00", "08:00", 12 * 60)
assert in_quiet("13:00", "14:00", 13 * 60 + 30) and not in_quiet("13:00", "14:00", 14 * 60)
assert not in_quiet("10:00", "10:00", 600) and not in_quiet("bad", "08:00", 0)

# ---------------------------------------------------------------- the recap
ev = [{"kind": "species", "text": "New species: Apple Watch"},
      {"kind": "species", "text": "New species: Garmin device"},
      {"kind": "landmark", "text": "Harald saw Kingsbridge Castle for the first time!"},
      {"kind": "landmark", "text": "Harald saw Kingsbridge Castle"},
      {"kind": "land", "text": "Harald claimed a new realm (realm 4, land 30)"},
      {"kind": "weather", "text": "A storm is coming: pressure fell 3.2 hPa in 3 hours"},
      {"kind": "level", "text": "Harald reached level 6"}]
r = build_recap("Harald", ev, 34, 5, 3 * 3600)
assert r.startswith("I'm home! I ate 34 snacks and 5 Wi-Fi treats today.") and "2 new types of gadget: Apple Watch and Garmin device!" in r \
       and "I saw Kingsbridge Castle!" in r and "1 new realm" in r and "storm" in r and "level 6" in r, r
assert build_recap("Harald", [{"kind": "wake", "text": "Harald woke up"}], 0, 0, 7200) is None
assert "1 snack " in build_recap("Harald", [], 1, 0, 600)

# ---------------------------------------------------------------- WAV conversion
tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "in.wav")
with wave.open(src, "wb") as w:
    w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
    w.writeframes(b"\x00\x10" * 22050)          # one second
dst = os.path.join(tmp, "out.wav")
voicemod.convert_py(src, dst, 0.5)
with wave.open(dst, "rb") as w:
    assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, 48000)
    assert abs(w.getnframes() - 48000) <= 2
    first = w.readframes(1)
assert int.from_bytes(first[:2], "little", signed=True) == 0x1000 // 2
assert voicemod.volume_factor(50) == 0.25
from bt_dragon.dot import volume_register
assert [volume_register(v) for v in (100, 50, 25, 10, 0)] == [127, 103, 79, 47, 0], [volume_register(v) for v in (100, 50, 25, 10, 0)]
voicemod.pad(dst, 1.0, 0.5)
with wave.open(dst, "rb") as w:
    assert abs(w.getnframes() - 48000 * 2.5) <= 3

# ---------------------------------------------------------------- a pretend Dot
ROOT = os.path.join(tmp, "dot")
os.makedirs(os.path.join(ROOT, "data"))
open(os.path.join(ROOT, "frame"), "w").write("0" * 72 + "\n")
BIN = os.path.join(tmp, "bin")
os.makedirs(BIN)
FAKE_ADB = r'''#!PYTHON
import os, shutil, subprocess, sys
ROOT = "ROOTDIR"
MAP = [("/sys/devices/soc/11007000.i2c/i2c-0/0-003f/frame", ROOT + "/frame"), ("/data/local/tmp", ROOT + "/data")]
def m(s):
    for a, b in MAP:
        s = s.replace(a, b)
    return s
args = sys.argv[1:]
if args[:1] == ["-s"]:
    args = args[2:]
cmd = args[0]
if cmd == "connect":
    print("connected to " + args[1])
elif cmd == "disconnect":
    print("disconnected " + args[1])
elif cmd == "push":
    src, dst = args[1], m(args[2])
    if os.path.isdir(src):
        out = os.path.join(dst, os.path.basename(src.rstrip("/")))
        shutil.copytree(src, out, dirs_exist_ok=True)
        for mg in ("micgrab", "micgrab.new"):
          if os.path.exists(os.path.join(out, mg)):   # the real one is an ARM program: pretend
            open(os.path.join(out, mg), "w").write(
                "#!/bin/sh\nif [ \"$1\" = keys ]; then echo READY; sleep 60; exit 0; fi\n"
                "cp " + ROOT + "/question.wav \"$1\"; echo \"SPEECH 1500 ms\"\n")
            os.chmod(os.path.join(out, mg), 0o755)
        for f in os.listdir(out):
            if f.endswith(".sh"):
                p = os.path.join(out, f)
                text = m(open(p).read())
                open(p, "w").write(text)
    else:
        shutil.copy(src, dst)
    print("pushed")
elif cmd == "pull":
    shutil.copy(m(args[1]), args[2])
    print("pulled")
elif cmd == "shell":
    pre = ("getprop() { case $1 in ro.build.version.name) echo 'Fire OS 6574.1';; ro.serialno) echo G090TEST;; "
           "ro.product.model) echo AEOBC;; esac; }; "
           "stop() { echo stop $1 >> " + ROOT + "/log; }; start() { echo start $1 >> " + ROOT + "/log; }; "
           "")
    env = dict(os.environ, PATH=ROOT + "/bin:" + os.environ["PATH"])
    sys.exit(subprocess.run(["bash", "-c", pre + m(args[1])], env=env).returncode)
'''.replace("PYTHON", sys.executable).replace("ROOTDIR", ROOT)
open(os.path.join(BIN, "adb"), "w").write(FAKE_ADB)
os.makedirs(os.path.join(ROOT, "bin"))
for tool in ("tinyplay", "tinymix", "wpa_cli", "iptables", "ip6tables"):    # the Dot's tools, pretending
    p = os.path.join(ROOT, "bin", tool)
    # (a firewall check, -C, finds no such rule yet)
    open(p, "w").write(f"#!/bin/sh\necho {tool} \"$@\" >> {ROOT}/log\n[ \"$1\" = -C ] && exit 1\nexit 0\n")
    os.chmod(p, 0o755)
# the Dot's interfaces, as a 2nd-generation Dot shows them: its setup network on p2p0
IFCONFIG = os.path.join(ROOT, "bin", "ifconfig")
open(IFCONFIG, "w").write("""#!/bin/sh
cat <<'X'
wlan0     Link encap:Ethernet  HWaddr 00:fc:8b:00:00:01
          inet addr:10.154.85.84  Bcast:10.154.85.255  Mask:255.255.255.0
          UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1

p2p0      Link encap:Ethernet  HWaddr 02:fc:8b:00:00:01
          inet addr:10.201.126.241  Bcast:0.0.0.0  Mask:255.255.255.240
          UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1

lo        Link encap:Local Loopback
          inet addr:127.0.0.1  Mask:255.0.0.0
X
""")
os.chmod(IFCONFIG, 0o755)
os.chmod(os.path.join(BIN, "adb"), 0o755)
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]

# a real Piper and its small test voice, if they're around (otherwise the voice part is skipped)
SCRATCH = os.environ.get("PIPER_TEST_DIR", "")
have_piper = SCRATCH and os.path.exists(os.path.join(SCRATCH, "piper", "piper"))
if have_piper:
    voicemod.PIPER_PATHS = [os.path.join(SCRATCH, "piper", "piper")]
    voicemod.VOICE_DIR = os.path.join(SCRATCH, "src", "etc")
else:
    voicemod.PIPER_PATHS, voicemod.VOICE_DIR = [], os.path.join(tmp, "novoices")


class Obj:
    pass


async def main():
    app = Obj()
    app.data_dir = os.path.join(tmp, "pi")
    os.makedirs(app.data_dir)
    app.store = Store(os.path.join(app.data_dir, "dragon.db"))
    app.cfg = {"home_wifi": {"ssid": "Home"}, "backup_wifi": [],
               "dot": {"enabled": True, "address": "127.0.0.1", "networks": [], "voice": "", "audio_device": 23,
                       "amp_on_after": 0.2,
                       "recap_after_minutes": 30, "stop_services": ["puffin", "ahe"]}}
    app.home_ssid = "Home"
    app.stop = asyncio.Event()
    app.events = []
    app.event = lambda k, t: app.events.append((k, t))

    async def _sleep(s):
        try:
            await asyncio.wait_for(app.stop.wait(), s)
        except asyncio.TimeoutError:
            pass
    app._sleep = _sleep
    pet = Obj()
    pet.name, pet.sleeping, pet.total_meals, pet.total_treats = "Harald", False, 100, 10
    pet.mood = lambda: "happy"
    pet.say = lambda *a, **k: None
    app.pet = pet

    d = DotLink(app)
    d.s["quiet_from"] = d.s["quiet_to"] = "00:00"      # never quiet during the test
    # not on the main hotspot: doesn't even look
    app.home_ssid = "Library_Free"
    assert not await d.find() and "main hotspot" in d.state
    app.home_ssid = "Home"
    assert await d.find(), d.state
    assert d.s["serial"] == "G090TEST" and app.events and "Echo Dot" in app.events[0][1]
    d.connected = True
    assert await d.setup(), d.state
    log = open(os.path.join(ROOT, "log")).read()
    assert "stop ledcontroller" in log and "stop mixer" in log and "stop puffin" in log and "stop ahe" in log
    assert "tinymix Ext_Speaker_Amp_Switch Off" in log
    # its open setup network is locked (nothing gets in on p2p0) and closed, never the hotspot's
    assert "iptables -I INPUT -i p2p0 -j DROP" in log and "ip6tables -I INPUT -i p2p0 -j DROP" in log, log
    assert "p2p_group_remove p2p0" in log and "-i wlan0 -j DROP" not in log
    os.rename(IFCONFIG, IFCONFIG + ".off")                 # no setup network up: nothing to do
    open(IFCONFIG, "w").write("#!/bin/sh\necho 'wlan0     Link encap:Ethernet'\necho '          inet addr:10.154.85.84'\n")
    os.chmod(IFCONFIG, 0o755)
    assert await d.lock_setup_network() == ""
    os.replace(IFCONFIG + ".off", IFCONFIG)
    assert os.path.exists(os.path.join(ROOT, "data", "harald", "anim", "mood_happy.txt"))
    # the player is running: it draws his mood
    await d.base("mood_happy")
    happy = {l.split(" ")[1].strip() for l in open(os.path.join(ROOT, "data", "harald", "anim", "mood_happy.txt"))}
    seen = set()
    for _ in range(30):
        await asyncio.sleep(0.05)
        seen.add(open(os.path.join(ROOT, "frame")).read().strip())
    assert seen & happy, (list(seen)[:3], list(happy)[:3])
    # a one-off: level up
    level = {l.split(" ")[1].strip() for l in open(os.path.join(ROOT, "data", "harald", "anim", "ev_level.txt"))}
    await d.once("ev_level")
    seen = set()
    for _ in range(30):
        await asyncio.sleep(0.05)
        seen.add(open(os.path.join(ROOT, "frame")).read().strip())
    assert seen & level, "the level-up animation didn't play"

    # questions: the action button, recording, understanding, answering
    with wave.open(os.path.join(ROOT, "question.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"\x10\x00\xf0\xff" * 8000)

    class FakeEars:
        available = True
        heard_files = []

        reply = "what time is it in texas"

        async def hear(self, path, vocabulary=None):
            self.heard_files.append(os.path.exists(path))
            return "stop" if vocabulary and len(vocabulary) < 20 else self.reply

        def forget(self):
            pass
    d.ears = FakeEars()
    d.on_key("KEY ACTION 1")
    for _ in range(100):
        await asyncio.sleep(0.05)
        if not d.asking and d.answered:
            break
    assert d.heard == "what time is it in texas" and d.answered.startswith("In Texas it's"), (d.heard, d.answered)
    assert FakeEars.heard_files == [True] and "understanding" in d.timing and not os.path.exists(os.path.join(app.data_dir, "dot", "ask.wav"))
    assert not os.path.exists(os.path.join(ROOT, "data", "harald", "ask.wav"))   # recordings aren't kept
    assert d.queue and d.queue[0].startswith("In Texas")
    d.queue.clear()
    # the wake word: the question comes from the stream instead of a separate recording
    import array as _array
    import math as _math
    from bt_dragon import wake as wakemod
    d.mic.active = True
    FakeEars.reply = "what is the date"
    d.answered = ""

    async def feed_stream():
        while not d.mic.taps:
            await asyncio.sleep(0.01)
        n = 0
        while d.mic.taps:
            blk = _array.array("h", (int(1500 * _math.sin(i / 3.0)) if 30 <= n < 120 else (i % 7) * 10
                                     for i in range(wakemod.BLOCK)))
            d.mic._block(blk.tobytes())
            n += 1
            await asyncio.sleep(0)
    feeder = asyncio.ensure_future(feed_stream())
    d.on_wake()
    for _ in range(200):
        await asyncio.sleep(0.05)
        if d.answered:
            break
    await feeder
    assert d.answered.startswith("Today is") and d.timing.startswith("wake word"), (d.answered, d.timing)
    d.mic.active = False
    d.queue.clear()
    FakeEars.reply = "what time is it in texas"
    assert d.set("wake", "true") is None and d.s["wake"] and d.set("wake_from", "7:30") is None
    assert d.set("wake_to", "99:00")
    d.s["wake"] = False
    vol = d.s["volume"]
    d.on_key("KEY VOLUP 1")
    assert d.s["volume"] == min(100, vol + 10)
    d.s["volume"] = vol
    d.on_key("KEY MUTE 1")
    assert d.mic_muted and d.wanted_base() == "muted"
    await d.ask_spoken()
    assert d.queue and "ears are covered" in d.queue[-1]
    d.queue.clear()
    d.on_key("KEY MUTE 1")
    assert not d.mic_muted
    # a timer: the ring counts down, then it rings until the action button is pressed
    assert "Timer set" in await d.answer("set a timer for two seconds")
    assert d.wanted_base().startswith("timer_")
    loop_task = asyncio.ensure_future(d._timer_loop())
    for _ in range(60):
        await asyncio.sleep(0.1)
        if d.alarm and d.queue:
            break
    assert d.alarm and "is done" in d.queue[-1], (d.alarm, d.queue)
    d.on_key("KEY ACTION 1")
    assert d.alarm is None and not d.queue
    # a volume button silences it too (without changing the volume)
    await d.answer("set a timer for one second")
    for _ in range(40):
        await asyncio.sleep(0.1)
        if d.alarm:
            break
    vol = d.s["volume"]
    d.on_key("KEY VOLDOWN 1")
    assert d.alarm is None and d.s["volume"] == vol
    # ...and so does saying "stop" while it rings, without pressing anything
    await d.answer("set a timer for one second")
    for _ in range(40):
        await asyncio.sleep(0.1)
        if d.alarm:
            break
    assert d.alarm
    d.queue.clear()
    await d._listen_for_stop()
    assert d.alarm is None, "didn't hear stop"
    loop_task.cancel()
    assert (await d.answer("how long left on the timer")) == "You don't have any timers running."
    assert (await d.answer("mumble")) == "Sorry, I didn't catch that."

    # what gets said
    d.s["chatty"] = "big"
    d.on_say("NOM! 2 NEW SNACKS", "eating")
    assert d.queue == []
    d.on_say(["LEVEL UP! HARALD IS NOW LEVEL 4", "LVL 4"], "proud")
    assert d.queue == ["Level up! Harald is now level 4!"] or d.queue == ["Level up! Harald is now level 4."], d.queue
    d.s["chatty"] = "recap"
    d.on_say("A STORM IS COMING!", "ecstatic")
    assert len(d.queue) == 1
    d.queue.clear()
    d.s["chatty"] = "all"
    d.on_say("MY DEN: 10.0.0.2:8080", None)
    assert d.queue == []
    for i in range(8):                     # a busy street doesn't build a backlog
        d.on_say(f"NOM! {i} NEW SNACKS", "eating")
    assert len(d.queue) == 4 and d.queue[-1].startswith("Nom nom! 7"), d.queue
    d.queue.clear()

    # the recap after time apart
    app.store.put("dot_contact", {"ts": time.time() - 3 * 3600, "meals": 70, "treats": 8})
    app.store.event("species", "New species: Apple Watch", ts=time.time() - 3600)
    d._prepare_recap(time.time())
    assert d.recap_pending and d.recap_pending.startswith("I'm home! I ate 30 snacks and 2 Wi-Fi treats"), d.recap_pending
    d.recap_pending = None

    if have_piper:
        d.say("Hello, I am Harald.", force=True)
        task = asyncio.ensure_future(d.speaker_loop())
        for _ in range(100):
            await asyncio.sleep(0.1)
            if "tinyplay" in open(os.path.join(ROOT, "log")).read():
                break
        app.stop.set()
        d.queue_event.set()
        await asyncio.wait_for(task, 10)
        app.stop.clear()
        log = open(os.path.join(ROOT, "log")).read()
        assert "-D 0 -d 23" in log, log
        amp = [l for l in log.splitlines() if "Ext_Speaker_Amp_Switch" in l]
        assert amp[-2:] == ["tinymix Ext_Speaker_Amp_Switch On", "tinymix Ext_Speaker_Amp_Switch Off"], amp
        assert "tinymix PCM Playback Volume 103 103" in log, log    # volume 50 = -12 dB
        with wave.open(os.path.join(ROOT, "data", "harald", "say1.wav"), "rb") as w:
            assert (w.getnchannels(), w.getframerate()) == (2, 48000) and w.getnframes() > 20000
        await d.voice.stop()
        print("voice: spoke through the pretend Dot")
    else:
        print("voice: skipped (set PIPER_TEST_DIR to a folder with piper/ and src/etc/test_voice.onnx)")

    # setup-mode rescue: only your Dot's own setup network, only after it's been missing a while
    from bt_dragon import wifi as wifimod
    joined = []

    async def fake_connect(name, timeout=45):
        joined.append(name)
        return True, "ok"
    wifimod.connect_profile = fake_connect
    wifimod.ensure_rescue_profile = lambda ssid, address="": joined.append("profile:" + ssid) or True
    app._switching = False
    app.cfg["home_wifi"]["ssid"] = "Home"
    switched = []

    async def fake_best(visible=None, reason=""):
        switched.append(reason)
    app.switch_to_best = fake_best
    app.pet.say = lambda *a, **k: None
    assert d.set("setup_network", "Linksys1234") and d.set("setup_network", "Amazon-XY7") is None
    aps = [{"ssid": "Amazon-XY7", "rssi": -60}]
    was = d.connected
    d.connected = False
    d._missing_since = time.time() - 30
    assert not d.rescue_wanted(aps)                          # missing only 30 s: wait
    d._missing_since = time.time() - 120
    assert not d.rescue_wanted([{"ssid": "Amazon-ZZ9", "rssi": -50}])   # someone else's Echo: never
    assert d.rescue_wanted(aps)
    d.s["serial"] = "SOMEONEELSE"                             # the device there isn't ours
    r = await d.rescue()
    log = open(os.path.join(ROOT, "log")).read()
    assert "different Echo" in d.state and "enable_network" not in log, d.state
    assert joined[:2] == ["profile:Amazon-XY7", "bt-dragon-dot-rescue"] and joined[-1] == "bt-dragon-home", joined
    assert not d.rescue_wanted(aps)                           # cooling down after a try
    d.s["serial"] = "G090TEST"
    d._last_rescue_try = 0
    await d.rescue()
    assert d.state.startswith("rescued"), d.state
    assert app.store.get("dot_last_rescue") and app._switching is False and not d.rescuing
    assert any("rescued the Echo Dot" in t for _, t in app.events)
    # its setup network on the air while we think it's on the hotspot: that alone doesn't drop
    # it (an old scan, or the network lingering after a rescue). It's asked straight away instead.
    d.connected, d.ready, d._last_rescue_try, d._doubt = True, True, 0, None
    assert not d.rescue_wanted(aps) and d.connected and d._doubt
    d._doubt = None
    assert not d.rescue_wanted([{"ssid": "Amazon-XY7", "rssi": -60, "age_ms": 40000}]) and not d._doubt  # stale
    d._setup_ok_until = time.time() + 60                      # it answered a moment ago: leave it be
    assert not d.rescue_wanted(aps) and not d._doubt
    d._setup_ok_until = 0.0
    d.mark_lost("test")                                       # really gone: then it's rescued as before
    d._missing_since = time.time() - 120
    assert d.rescue_wanted(aps) and not d._doubt
    assert not d.rescue_wanted([])                            # not on the air: nothing to rescue

    # nothing answering on its setup network (adbd stuck) isn't a stranger's Echo: it says so,
    # and waits longer each time (3, 6, 12, then 30 minutes), instead of hopping away every 3
    from bt_dragon import dot as dotmod
    real_adb = d._adb

    async def deaf_adb(*a, timeout=20, target=True):
        return 1, "error: device offline"
    d._adb = deaf_adb
    waits = []
    for _ in range(5):
        d._last_rescue_try = 0
        await d.rescue()
        waits.append(d._rescue_wait)
        assert "didn't answer" in d.state and "different Echo" not in d.state, d.state
    assert waits == [360, 720, 1440, 1800, 1800], waits
    d._last_rescue_try = time.time() - 400
    assert not d.rescue_wanted(aps)                           # (still waiting: 30 minutes now)
    d._adb = real_adb
    # its network gone mid-join (the Dot restarting): once more in 30 seconds, then as usual
    async def no_join(name, timeout=45):
        joined.append(name)
        return (False, "802.1X supplicant took too long") if name == "bt-dragon-dot-rescue" else (True, "ok")
    wifimod.connect_profile = no_join
    d._last_rescue_try = 0
    await d.rescue()
    assert d._rescue_wait == dotmod.RESCUE_RETRY_S, d._rescue_wait
    d._last_rescue_try = time.time() - 40
    assert d.rescue_wanted(aps)
    await d.rescue()
    assert d._rescue_wait == dotmod.RESCUE_WAIT_S
    wifimod.connect_profile = fake_connect
    d._last_rescue_try = 0
    await d.rescue()
    assert d.state.startswith("rescued") and d._rescue_wait == dotmod.RESCUE_WAIT_S, d.state

    # half-connected: its ears still answer over the hotspot, so it's here and only adb is
    # stuck: no rescue hops, and the ears are asked to restart adbd (a few times, spaced out)
    d.mark_lost("test")
    d._missing_since = time.time() - 120
    d._last_rescue_try = 0
    fixes = []

    async def fix_adb():
        fixes.append(1)
        return {"ok": True, "stopped": 1}
    real_fix, d.dot_ears.fix_adb = d.dot_ears.fix_adb, fix_adb
    d.dot_ears.connected = True
    assert not d.rescue_wanted(aps)
    t = time.time()
    await d._half_connected(t)
    assert fixes == [1] and d.state.startswith("half-connected"), d.state
    await d._half_connected(t + 60)                            # too soon for another
    assert fixes == [1]
    await d._half_connected(t + 200)
    await d._half_connected(t + 400)
    await d._half_connected(t + 600)                           # three is enough: unplug it
    assert len(fixes) == 3 and "unplugging" in d.state, d.state
    d.mark_lost("again")                                       # a new loss: three more tries
    await d._half_connected(time.time())
    assert len(fixes) == 4
    d.dot_ears.connected, d.dot_ears.fix_adb = False, real_fix
    d.connected = was

    # going away: the player stops and the ring goes dark
    await d.release()
    for _ in range(40):
        await asyncio.sleep(0.05)
        if not os.path.exists(os.path.join(ROOT, "data", "harald", "pid")):
            break
    assert open(os.path.join(ROOT, "frame")).read().strip() == "0" * 72
    await d.forget()
    assert d.s["serial"] == "" and "start puffin" in open(os.path.join(ROOT, "log")).read()

    # settings from the den
    assert d.set("volume", "150") is None and d.s["volume"] == 100
    assert d.set("chatty", "loud") and d.set("quiet_from", "25:00") and d.set("serial", "x")
    assert d.set("pitch", "-2.5") is None and d.s["pitch"] == -2.5
    assert d.set("enabled", "false") is None and d.s["enabled"] is False
    assert set(d.status()) >= set(DEFAULTS) | {"state", "connected", "voice"}


try:
    asyncio.run(main())
finally:   # never leave a pretend player running, even when a check fails
    if os.path.isdir(os.path.join(ROOT, "data", "harald")):
        open(os.path.join(ROOT, "data", "harald", "quit"), "a").close()
print("dot ok")
