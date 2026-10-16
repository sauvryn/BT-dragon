"""
Harald's voice and light ring, borrowed from an Echo Dot (2nd generation) running a
rooted Fire OS.

How it fits together
  * The Dot joins the same hotspot as the Pi. Rooted Dots listen for ADB (Android Debug
    Bridge) on TCP port 5555, which gives a root shell without asking for a password.
    The Pi uses the ordinary `adb` program to talk to it.
  * Finding it: hotspots hand out addresses as they please, so the Pi tries the Dot's
    last address first, then knocks on port 5555 of every address on the hotspot's own
    network (only on your main hotspot, or networks you list in the settings). The first
    Dot it meets is "claimed" by its serial number, and after that only that Dot is used.
  * Setting it up (each time it's found, since a Dot restart undoes everything): Alexa's
    services and Amazon's light program are paused, and a small player script plus
    Harald's animations are copied to /data/local/tmp/harald and started.
  * Speaking: Piper makes the speech on the Pi, the WAV file is copied over, and the
    Dot's own `tinyplay` plays it through card 0, device 8.
  * What he says: his status-line messages (the screen is his voice already), filtered by
    how chatty you've set him in the den, plus a welcome-home recap when the Dot sees
    him again after a while apart.
"""
import asyncio
import ipaddress
import json
import math
import logging
import os
import re
import shutil
import subprocess
import time

from . import ask
from . import dotears
from . import hearing
from . import ring
from . import agenda
from . import shopping
from . import tuning
from . import wayfinding
from .phonevoice import PhoneVoice
from . import voices as voicesmod
from . import voice as voicemod
from . import wake as wakemod
from .config import networks as config_networks

log = logging.getLogger("dot")

H = "/data/local/tmp/harald"
CHIP = "/sys/devices/soc/11007000.i2c/i2c-0/0-003f/frame"
PORT = 5555
MODES = ("all", "big", "recap", "silent", "adventure")
BIG_MOODS = {"proud", "happy", "excited", "ecstatic", "adventure", "riding", "alarmed", "sunglasses"}
NEVER_SAY = ("MY DEN:",)

DEFAULTS = {
    "enabled": True,
    "chatty": "all",          # all | big | recap | silent
    "volume": 50,             # 0-100 (the speaker chip's own volume)
    "adv_volume": 30,         # ...in Adventure mode (out and about: quieter)
    "brightness": 60,         # 0-100 (0 turns the ring off)
    "quiet_from": "22:00",
    "quiet_to": "08:00",
    "red": 100, "green": 50, "blue": 65,   # color balance, percent
    "pitch": 0.0,             # semitones; negative is deeper
    "speed": 1.0,             # speaking speed
    "gap": 4,                 # seconds of quiet between remarks at least
    "serial": "", "model": "", "last_ip": "",
    "setup_network": "",      # the Dot's own setup-mode network, e.g. "Amazon-XY7"
    "listen": True,           # answer questions when the action button is pressed
    "wake": False,            # also listen for "Hey dragon" (a trial)
    "wake_from": "08:00", "wake_to": "22:00",   # ...between these times
    "home_town": "", "home_lat": None, "home_lon": None,   # where "the weather" is, without GPS
    "phone": False,           # also (or instead) speak through the phone (Termux helper)
    "phone_backup": True,     # the Dot's voice, but the phone while the Dot is lost
    # weather news said out loud (his screen always shows it): from the Lair...
    "say_lair_temp": True, "say_lair_storm": True, "say_lair_sun": True, "say_lair_warnings": True,
    "say_lair_pollen": True, "say_lair_pollen_when": "increased",    # "all" high readings, or "increased" only
    "say_lair_uv": True, "say_lair_uv_when": "increased",
    "say_lair_air": True, "say_lair_air_when": "increased", "say_lair_aurora": True,
    # ...and from the phone's own sensors
    "say_phone_storm": True, "say_phone_sun": True,
}
SAY_BOOLS = ("say_lair_temp", "say_lair_storm", "say_lair_sun", "say_lair_warnings", "say_lair_pollen", "say_lair_uv",
             "say_lair_air", "say_lair_aurora",
             "say_phone_storm", "say_phone_sun")
LIMITS = {"volume": (0, 100), "adv_volume": (0, 100), "brightness": (0, 100), "red": (0, 100), "green": (0, 100),
          "blue": (0, 100), "pitch": (-8, 8), "speed": (0.6, 1.6), "gap": (0, 120)}


SETUP_IP = "10.201.126.241"      # the Dot's address on its own setup network
SETUP_NET_PREFIX = "10.201.126."  # (its setup network's addresses)
LOCK_AGAIN_S = 600               # the setup network seen again while the Dot answers: lock it again, at most this often
RESCUE_WAIT_S = 180              # between rescue tries...
RESCUE_WAIT_MAX_S = 1800         # ...doubling, up to this, while the Dot doesn't answer on its setup network
RESCUE_RETRY_S = 30              # its network vanished while joining (it restarting, say): soon again
ADB_FIX_EVERY_S = 180            # the ears restarting adbd: at most this often...
ADB_FIX_MAX = 3                  # ...and this many times for each time the Dot is lost
SETUP_NET_RE = re.compile(r"^Amazon-[A-Za-z0-9]{2,8}$")
AMP = "Ext_Speaker_Amp_Switch"   # the speaker amplifier's on/off switch
LEAD_S, TAIL_S = 0.6, 0.6        # silence around each sentence (see dot_speak.sh)


def volume_register(percent):
    """The den's 0-100 volume -> the speaker chip's "PCM Playback Volume" setting.
    The chip counts in half-decibel steps with 127 = 0 dB (normal), so 107 is 10 dB
    quieter. Loudness is heard on a log scale, so the slider maps to decibels:
    100 = 0 dB, 50 = -12 dB, 25 = -24 dB, 10 = -40 dB."""
    if float(percent) <= 0:
        return 0                     # -63.5 dB: as good as silent
    p = max(1.0, min(100.0, float(percent)))
    db = max(-60.0, 40 * math.log10(p / 100))
    return int(round(127 + 2 * db))


def parse_hhmm(s):
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", str(s))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def in_quiet(start, end, minute_of_day):
    """Is this minute of the day inside the quiet hours (which may run past midnight)?"""
    a, b = parse_hhmm(start), parse_hhmm(end)
    if a is None or b is None or a == b:
        return False
    if a < b:
        return a <= minute_of_day < b
    return minute_of_day >= a or minute_of_day < b


def _plural(n, word, words=None):
    return f"{n} {word if n == 1 else (words or word + 's')}"


def _list(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def build_recap(name, events, meals, treats, away_s):
    """What Harald tells you when he's back: a few sentences about the time apart.
    `events` are diary entries (dicts with kind and text) since you were last together."""
    hours = away_s / 3600
    when = "today" if hours < 10 else "while we were apart"
    parts = ["I'm home!"]
    ate = []
    if meals:
        ate.append(_plural(meals, "snack"))
    if treats:
        ate.append(_plural(treats, "Wi-Fi treat"))
    species = [e["text"].split(": ", 1)[-1] for e in events if e["kind"] == "species"]
    if ate:
        parts.append(f"I ate {_list(ate)} {when}.")
    if species:
        shown = species[:3]
        more = len(species) - len(shown)
        tail = f", and {_plural(more, 'more')}" if more else ""
        parts.append(f"{'A new type of gadget' if len(species) == 1 else _plural(len(species), 'new type of gadget', 'new types of gadget')}: "
                     f"{_list(shown)}{tail}!")
    marks = []
    for e in events:
        if e["kind"] == "landmark":
            m = re.match(rf"{re.escape(name)} saw (.*?)( for the first time!)?( \+\d+ Conquest points?\.)?$", e["text"])
            if m and m.group(1) not in marks:
                marks.append(m.group(1))
    if marks:
        parts.append(f"I saw {_list(marks[:3])}!")
    outings = []
    for e in events:
        if e["kind"] == "green":
            m = re.match(rf"{re.escape(name)}: (Took a walk in|Went for a run in|Biked through) (.*?)!$", e["text"])
            if m and m.group(2) not in outings:
                outings.append(m.group(2))
    if outings:
        parts.append(f"We went to {_list(outings[:3])}!")
    realms = sum(1 for e in events if e["kind"] == "land" and "new realm" in e["text"])
    if realms:
        parts.append(f"I claimed {_plural(realms, 'new realm')}.")
    friends = [e for e in events if e["kind"] == "friend" and e["text"].startswith("Made a new friend")]
    if friends:
        parts.append(f"I made {_plural(len(friends), 'new friend')}.")
    stars = sum(1 for e in events if e["kind"] == "star")
    if stars:
        parts.append("I found new stars in the sky." if stars > 1 else "I found a new star in the sky.")
    if any(e["kind"] == "weather" and e["text"].startswith("A storm") for e in events):
        parts.append("And I smelled a storm coming.")
    levels = [e["text"] for e in events if e["kind"] == "level"]
    if levels:
        m = re.search(r"level (\d+)", levels[-1])
        if m:
            parts.append(f"I'm level {m.group(1)} now!")
    if len(parts) == 1:
        return None     # nothing worth telling (he was probably switched off most of the time)
    return " ".join(parts)


class DotLink:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg["dot"]
        self.store = app.store
        s = dict(DEFAULTS)
        s.update(self.store.get("dot_settings") or {})
        self.s = s
        self.dir = os.path.join(app.data_dir, "dot")
        self.stage = os.path.join(self.dir, "harald")       # copied to the Dot as-is
        os.makedirs(os.path.join(self.stage, "anim"), exist_ok=True)
        # speech and recordings are made, used and thrown away in moments: they go in the Pi's
        # memory (/dev/shm, a folder that lives in RAM), never onto the card
        self.tmp = os.path.join("/dev/shm", "bt-dragon") if os.path.isdir("/dev/shm") else self.dir
        try:
            os.makedirs(self.tmp, exist_ok=True)
        except OSError:
            self.tmp = self.dir
        self.target = None          # "ip:5555" while connected
        self.connected = False
        self.ready = False          # player running with current animations
        self.state = "starting"     # a few words for the den
        self.voice = voicemod.Piper(self.cfg["voice"], s["speed"])
        self.queue = []             # [(text, kind)] waiting to be spoken
        self.queue_event = asyncio.Event()
        self.recap_pending = None   # text, waiting for the end of quiet hours
        self._seq = int(time.time()) % 100000
        self._base = None
        self._anims_pushed = None
        self._last_spoke = 0.0
        self._speaking = False
        self._hush_seq = 0          # goes up when he's told to be quiet mid-answer
        self._last_scan = 0.0
        self._last_full = 0.0
        self._fails = 0
        self._lost_at = None
        self._doubt = None             # when something made us doubt it's really still here
        self._setup_ok_until = 0.0     # its setup network lingering while it answers us: fine
        self._missing_since = time.time()
        self._last_rescue_try = 0.0
        self._rescue_wait = RESCUE_WAIT_S   # until the next rescue try (longer after ones that got nowhere)
        self._adb_fixes = 0                 # times the ears restarted adbd since the Dot was lost
        self._adb_fixed_at = 0.0
        self._locked_at = 0.0               # when the setup network was last locked and closed
        self.rescuing = False
        self.spoken = 0
        # questions, buttons and timers
        self.ears = hearing.Ears(ask.GRAMMAR)
        self.timers = ask.Timers(self.store)
        self.shopping = shopping.ShoppingList(self.store)
        self.calendar = agenda.Calendar(self.store)
        self.voices = voicesmod.VoiceProfiles(self.store)
        self.speaker = None         # who asked the last question, if he knows their voice
        self.heard_from = ""        # ...in words, for the den
        self._voice = (None, 0)     # the last recording's voice print, and how much speech it had
        self._speak_lock = asyncio.Lock()
        self.alarm = None           # {"names": [...], "since": ts, "next": ts} while a timer rings
        self.asking = False
        self.wake_unasked = 0        # woke up, but nobody asked anything
        self.last_landmark = None    # (landmark, when): the one he pointed out last
        self.phone = PhoneVoice()
        self._free_text = None       # the open second listen of the last question, if any
        self.mic_muted = False
        self.heard = ""             # the last question heard, for the den
        self.timing = ""            # how long each step of the last question took
        self._ask_done = None
        self._alarm_listening = False
        self.answered = ""
        self._keys_proc = None
        self.mic = wakemod.MicStream(self)
        # Adventure mode: what's been announced today (so far)
        self._adv = {"walk": None, "climb": None, "lands": 0, "land_ts": 0.0, "pack_full": None}
        self.dot_ears = dotears.DotEars(self)   # listening on the Dot itself, when it can

    # ------------------------------------------------------------ settings
    def save(self):
        self.store.put("dot_settings", self.s)

    def set(self, key, value):
        """Change one setting from the den. Returns an error string or None."""
        if key not in DEFAULTS or key in ("serial", "model", "last_ip", "home_lat", "home_lon"):
            return "no such setting"
        if key in ("enabled", "listen", "wake", "phone", "phone_backup") + SAY_BOOLS:
            self.s[key] = str(value).lower() in ("1", "true", "on", "yes")
        elif key == "home_town":
            self.s[key] = value.strip()[:40]
            self.s["home_lat"] = self.s["home_lon"] = None
            if self.s[key]:
                asyncio.ensure_future(self._find_home(self.s[key]))
        elif key in ("say_lair_pollen_when", "say_lair_uv_when", "say_lair_air_when"):
            if value not in ("all", "increased"):
                return "choose all or increased"
            self.s[key] = value
        elif key == "chatty":
            if value not in MODES:
                return "choose all, big, recap, silent or adventure"
            self.s[key] = value
        elif key == "setup_network":
            value = value.strip()
            if value and not SETUP_NET_RE.match(value):
                return 'that doesn\'t look like an Echo setup network (it should be like "Amazon-XY7")'
            self.s[key] = value
            if value:   # your own device: never a treat, never uploaded to WiGLE
                self.store.forget_network(value)
        elif key in ("quiet_from", "quiet_to", "wake_from", "wake_to"):
            if parse_hhmm(value) is None:
                return "use a time like 22:00"
            self.s[key] = value.strip()
        else:
            try:
                v = float(value)
            except ValueError:
                return "give a number"
            lo, hi = LIMITS[key]
            v = max(lo, min(hi, v))
            self.s[key] = v if key in ("pitch", "speed") else int(round(v))
            if key == "speed":
                self.voice.speed = v
                asyncio.ensure_future(self.voice.stop())   # restart Piper at the new speed
        self.save()
        if key in ("brightness", "red", "green", "blue") and self.connected:
            asyncio.ensure_future(self.push_animations())
        return None

    def wake_reason(self):
        """'' if "hey dragon" should be listened for right now, otherwise why not."""
        lt = time.localtime()
        in_hours = in_quiet(self.s["wake_from"], self.s["wake_to"], lt.tm_hour * 60 + lt.tm_min) \
            or self.s["wake_from"] == self.s["wake_to"]
        for bad, why in ((not self.s["wake"], "switched off"), (not self.s["listen"], "answering questions is off"),
                         (not in_hours, "outside the listening hours"),
                         (getattr(self.app, "napping", False), f"{self.app.pet.name} is napping"),
                         (self.rescuing, "rescuing the Dot"), (self.mic_muted, "the microphones are off")):
            if bad:
                return why
        return ""

    def _wake_status(self):
        if not self.dot_ears.installed:            # the old way: the Pi listens to a stream
            return {"wake_active": self.mic.active, "wake_heard": self.mic.heard, "wake_where": "Pi",
                    "wake_why": self.mic.why_not() or self.mic.error,
                    "wake_last": int(self.mic.last_heard), "wake_cpu": self.mic.cpu if self.mic.cpu is not None else ""}
        ws = self.dot_ears.wake_state if self.dot_ears.connected else {}
        active = bool(ws.get("active"))
        why = self.wake_reason() or ("" if active else (ws.get("error") or
                                     ("starting up" if self.dot_ears.connected else "the Dot's ears aren't connected")))
        return {"wake_active": active, "wake_heard": ws.get("heard", 0), "wake_where": "Dot", "wake_why": why,
                "wake_last": ws.get("last", 0), "wake_cpu": ws.get("cpu") if ws.get("cpu") is not None else "",
                "wake_strict": ws.get("strict", ""), "wake_turned_down": ws.get("turned_down", 0),
                "wake_last_no": ws.get("last_no", ""), "wake_conf": ws.get("conf") if ws.get("conf") is not None else "",
                "wake_unasked": self.wake_unasked}

    def quiet_now(self, ts=None):
        lt = time.localtime(ts or time.time())
        return in_quiet(self.s["quiet_from"], self.s["quiet_to"], lt.tm_hour * 60 + lt.tm_min)

    def status(self):
        v = "piper" if self.voice.available else ("espeak" if shutil.which("espeak-ng") or shutil.which("espeak") else "none")
        model = voicemod.find_voice(self.cfg["voice"])
        contact = self.store.get("dot_contact") or {}
        return {"state": self.state, "connected": self.connected and self.ready, "ip": (self.target or "").split(":")[0],
                "voice": v, "voice_name": os.path.basename(model or "").replace(".onnx", ""),
                "adb": bool(shutil.which("adb")), "quiet_now": self.quiet_now(), "queued": len(self.queue),
                "last_contact": int(contact.get("ts", 0)), "spoken": self.spoken,
                "last_rescue": int(self.store.get("dot_last_rescue") or 0), "rescuing": self.rescuing,
                "ears": self.can_hear, "heard": self.heard, "heard_from": self.heard_from,
                "ears_where": "Dot" if self.dot_ears.connected else ("Pi" if self.ears.available else ""),
                "ears_note": ("through the debug link" if self.dot_ears.via_adb else "") if self.dot_ears.connected
                else self.dot_ears.state, "answered": self.answered, "timing": self.timing,
                **self._wake_status(),
                "mic_muted": self.mic_muted, "alarm": bool(self.alarm),
                "phone_listening": self.phone.listening(), "phone_route": self.phone_route() or "",
                **{k: self.s[k] for k in DEFAULTS}}

    # ------------------------------------------------------------ adb
    async def _adb(self, *args, timeout=20, target=True):
        cmd = ["adb"] + (["-s", self.target] if target and self.target else []) + list(args)
        try:
            p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.STDOUT)
        except OSError as e:
            return 127, str(e)
        try:
            out, _ = await asyncio.wait_for(p.communicate(), timeout)
        except asyncio.TimeoutError:
            p.kill()
            return 124, "timed out"
        return p.returncode, out.decode(errors="replace")

    async def sh(self, script, timeout=20):
        """Run a shell command on the Dot. Returns its output, or None if the Dot didn't answer."""
        rc, out = await self._adb("shell", script, timeout=timeout)
        if rc != 0 and ("error" in out.lower() or rc in (124, 127)):
            return None
        return out

    # ------------------------------------------------------------ finding the Dot
    def _allowed_network(self):
        ssid = self.app.home_ssid
        if not ssid:
            return False
        nets = [s for s, _ in config_networks(self.app.cfg)]
        return (nets and ssid == nets[0]) or ssid in self.cfg["networks"]

    @staticmethod
    def _my_network():
        try:
            out = subprocess.run(["ip", "-4", "-o", "addr", "show", "wlan0"], capture_output=True,
                                 text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", out)
        if not m:
            return None
        prefix = max(24, int(m.group(2)))    # never knock on more than 254 addresses
        return ipaddress.ip_interface(f"{m.group(1)}/{prefix}")

    @staticmethod
    async def _port_open(ip, timeout=0.8):
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(str(ip), PORT), timeout)
            w.close()
            return True
        except (OSError, asyncio.TimeoutError):
            return False

    async def _candidates(self, full=True):
        fixed = self.cfg["address"].strip()
        if fixed:
            return [fixed]
        out = []
        if self.s["last_ip"] and await self._port_open(self.s["last_ip"]):
            out.append(self.s["last_ip"])
        net = await asyncio.to_thread(self._my_network) if full or not self.s["last_ip"] else None
        if not net:
            return out
        hosts = [h for h in net.network.hosts() if h != net.ip]
        for i in range(0, len(hosts), 64):
            batch = hosts[i:i + 64]
            found = await asyncio.gather(*(self._port_open(h) for h in batch))
            out += [str(h) for h, ok in zip(batch, found) if ok and str(h) not in out]
        return out

    async def _try(self, ip):
        """Connect to ip:5555 and check it's our Dot. True if it is."""
        self.target = f"{ip}:{PORT}"
        await self._adb("disconnect", self.target, target=False, timeout=5)
        rc, out = await self._adb("connect", self.target, target=False, timeout=10)
        if "connected" not in out or "unable" in out or "failed" in out:
            self.target = None
            return False
        info = await self.sh(f"getprop ro.build.version.name; getprop ro.serialno; getprop ro.product.model; "
                             f"[ -e {CHIP} ] && echo RING", timeout=10)
        lines = [x.strip() for x in (info or "").splitlines()]
        ok = len(lines) >= 4 and "Fire OS" in lines[0] and "RING" in lines
        serial = lines[1] if len(lines) > 1 else ""
        if ok and self.s["serial"] and serial != self.s["serial"]:
            log.info("found a different Echo at %s (not the claimed one); leaving it alone", ip)
            ok = False
        if not ok:
            await self._adb("disconnect", self.target, target=False, timeout=5)
            self.target = None
            return False
        if not self.s["serial"]:
            self.s["serial"], self.s["model"] = serial, lines[2]
            self.app.event("dot", f"{self.app.pet.name} found an Echo Dot to talk through ({lines[2]})")
        self.s["last_ip"] = ip
        self.save()
        return True

    async def find(self, full=True):
        if not shutil.which("adb"):
            self.state = "adb isn't installed on the Pi (sudo apt install adb)"
            return False
        if not self._allowed_network():
            self.state = "waiting for the main hotspot"
            return False
        self.state = "looking for the Dot"
        for ip in await self._candidates(full):
            if await self._try(ip):
                return True
        self.state = "no Dot found on this network"
        return False

    # ------------------------------------------------------------ setting it up
    def _anim_key(self):
        return (self.s["brightness"], self.s["red"], self.s["green"], self.s["blue"])

    def _write_animations(self):
        kw = {"balance": (self.s["red"] / 100, self.s["green"] / 100, self.s["blue"] / 100),
              "brightness": self.s["brightness"] / 100}
        d = os.path.join(self.stage, "anim")
        for name, frames in ring.all_animations().items():
            with open(os.path.join(d, name + ".txt"), "w", newline="\n") as f:
                f.write(ring.to_text(frames, **kw))
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "dot_player.sh"), encoding="utf-8") as f:
            player = f.read().replace("\r\n", "\n")
        with open(os.path.join(self.stage, "player.sh"), "w", newline="\n") as f:
            f.write(player)
        with open(os.path.join(here, "dot_speak.sh"), encoding="utf-8") as f:
            speak = f.read().replace("\r\n", "\n")
        with open(os.path.join(self.stage, "speak.sh"), "w", newline="\n") as f:
            f.write(speak)
        # micgrab goes over as "micgrab.new" and is renamed into place on the Dot, which works
        # even if an old copy is still running (writing over a running program fails)
        shutil.copyfile(os.path.join(here, "dot_files", "micgrab"), os.path.join(self.stage, "micgrab.new"))
        try:
            os.remove(os.path.join(self.stage, "micgrab"))
        except OSError:
            pass
        self.dot_ears.stage(self.stage)

    async def push_animations(self):
        key = self._anim_key()
        await asyncio.to_thread(self._write_animations)
        rc, out = await self._adb("push", self.stage, "/data/local/tmp/", timeout=60)
        if rc == 0:
            self._anims_pushed = key
        else:
            log.warning("couldn't copy the animations to the Dot: %s", out.strip()[-200:])
        return rc == 0

    async def setup(self):
        self.state = "setting up the Dot"
        services = " ".join(re.sub(r"[^A-Za-z0-9_.-]", "", s) for s in self.cfg["stop_services"])
        # Amazon's "mixer" holds the speaker chip (output 23) open all the time, so it has to
        # pause too. Without it the chip sleeps between sounds and the amplifier, left on,
        # whines; so the amplifier is switched off and only turned on while Harald speaks.
        # old button and microphone readers from before a restart would hold micgrab busy
        if await self.sh(f"for s in ledcontroller mixer {services}; do stop $s; done; "
                         f"tinymix '{AMP}' Off; mkdir -p {H}/anim; "
                         f"pkill -f 'micgrab [k]eys'; pkill -f 'micgrab [s]tream'", 30) is None:
            return False
        await self.lock_setup_network()
        if not await self.push_animations():
            return False
        await self.sh(f"mv -f {H}/micgrab.new {H}/micgrab; chmod 755 {H}/micgrab", 10)
        if not await self.player_running():
            await self.sh(f"rm -f {H}/quit; cd {H} && (setsid sh player.sh || nohup sh player.sh) "
                          f"</dev/null >/dev/null 2>&1 &", 10)
            await asyncio.sleep(1.5)
            if not await self.player_running():
                self.state = "the light player didn't start on the Dot"
                return False
        self._base = None
        self.ready = True
        self.state = "connected"
        on_dot = await self.dot_ears.start()          # the Dot listens itself, if it has its Debian
        asyncio.ensure_future(self._keys_loop())
        asyncio.ensure_future(self.mic.run())
        if on_dot:
            self.ears.forget()                          # the Pi's copy of the model isn't needed
        elif self.s["listen"] and self.ears.available:  # so the first question isn't slow
            asyncio.ensure_future(asyncio.to_thread(self.ears.preload))
        return True

    async def player_running(self):
        out = await self.sh(f"[ -f {H}/pid ] && kill -0 $(cat {H}/pid) 2>/dev/null && echo RUNNING", 10)
        return bool(out and "RUNNING" in out)

    # ------------------------------------------------------------ the ring
    async def base(self, name):
        if name != self._base and self.ready:
            if await self.sh(f"echo {name} > {H}/base", 10) is not None:
                self._base = name

    async def once(self, name):
        asked = name.startswith(("ev_test", "ev_alarm", "ev_listen", "ev_think", "ev_hush", "vol_"))
        if not self.ready or (self.quiet_now() and not asked):
            return
        self._seq += 1
        await self.sh(f"echo '{self._seq} {name}' > {H}/once", 10)

    def wanted_base(self):
        if self.s["brightness"] <= 0:
            return "off"
        if self.mic_muted:
            return "muted"
        t = self.timers.soonest()
        if t and not self.alarm:      # a kitchen timer: the ring empties like a clock
            left = max(0.0, t["end"] - time.time()) / max(1.0, t["length"])
            return f"timer_{max(1, math.ceil(left * ring.LEDS))}"
        if self.quiet_now() or self.app.pet.sleeping:
            return "night"
        mood = self.app.pet.mood()
        return "mood_" + mood if mood in ring.MOOD_ANIM else "mood_content"

    # ------------------------------------------------------------ what he says
    def on_say(self, wordings, mood):
        """Hooked into Pet.say: every status-line message."""
        text = wordings[0] if isinstance(wordings, (list, tuple)) else wordings
        up = text.upper()
        if up.startswith("NOM!"):
            self._ring_soon("ev_nom")
        elif up.startswith("A STAR RISES") or up.endswith("STARS RISING!"):
            self._ring_soon("ev_star")
        elif "NEW LAND" in up and "CLAIMED" in up:
            self._ring_soon("ev_land")
        if not self.speaks() or any(up.startswith(p) for p in NEVER_SAY):
            return
        mode = self.s["chatty"]
        if mode in ("recap", "silent", "adventure") or (mode == "big" and mood not in BIG_MOODS):
            return          # (Adventure mode speaks only its own announcements: see adventure())
        self.say(voicemod.speakable(text, self.app.pet.name))

    def news(self, text, big=False):
        """A remark that isn't on his screen word for word (the Lair's temperature, say),
        spoken by the same rules as his screen messages: how chatty, quiet hours."""
        if not self.speaks():
            return
        mode = self.s["chatty"]
        if mode in ("recap", "silent", "adventure") or (mode == "big" and not big):
            return
        self.say(text)

    def on_event(self, kind, text, ts):
        """Hooked into the diary: things that happened, for the ring."""
        name = {"species": "ev_species", "level": "ev_level", "landmark": "ev_landmark",
                "star": "ev_star", "green": "ev_landmark", "friend": "ev_friend", "treat": "ev_treat", "berries": "ev_nom",
                "pack": "ev_nom", "tracker": "ev_alert", "adventure": "ev_realm"}.get(kind)
        if kind == "weather":
            name = "ev_storm" if text.startswith("A storm") else "ev_weather"
        elif kind == "land" and "new realm" in text:
            name = "ev_realm"
        elif kind == "moon":
            from . import moon as moonmod
            name = f"moon_{round(moonmod.now_info(ts)['lit'] * ring.LEDS)}"
        if name:
            self._ring_soon(name)
        if kind == "level":
            m = re.search(r"level (\d+)", text)
            if m:
                self.adventure("level", level=int(m.group(1)))

    # ------------------------------------------------------------ Adventure mode
    # Out and about with the Dot (on a power bank): he only says things about the adventure,
    # quietly. Never anything about Bluetooth or Wi-Fi he's heard (no snacks, species, treats,
    # feasts or berries): that's other people's business.
    def adventure(self, kind, **k):
        if self.s["chatty"] != "adventure" or not self.speaks():
            return
        if kind == "land":
            self._adv["lands"] += 1                  # said a little later, a few at a time
            self._adv["land_ts"] = time.time()
            return
        text = None
        if kind == "realm":
            text = "A new realm! I claim it for us!"
        elif kind == "landmark":
            text = (f"Look! It's {k['title']}! I've never seen it before!" if k.get("first")
                    else f"Look, it's {k['title']} again!")
        elif kind == "green_found":
            text = f"A new green space! {k['name']}!"
        elif kind == "green_visit":
            text = k["text"]
        elif kind == "sunny":
            text = "Wow! It's sunny out today!"
        elif kind == "constellation":
            text = f"A new constellation in the sky: {k['name']}!"
        elif kind == "stars":
            n = k["n"]
            text = "I spotted a new star in the sky!" if n == 1 else f"I spotted {n} new stars in the sky!"
        elif kind == "level":
            text = f"Level up! I'm level {k['level']} now!"
        elif kind == "storm":
            text = "I can smell a storm coming!"
        elif kind == "weather":
            text = "Looks like a change in the weather soon."
        elif kind == "moon":
            text = k["text"]
        if text:
            self.say(text)

    @staticmethod
    def _km_words(km):
        if km == 0.5:
            return "half a kilometre"
        return f"{km:g} kilometre" + ("" if km == 1 else "s")

    def _adventure_tick(self):
        """Milestones: today's walking and climbing, new lands (a few at a time), a full pack."""
        if self.s["chatty"] != "adventure" or not self.speaks():
            self._adv.update(walk=None, climb=None, lands=0, pack_full=None)
            return
        from . import tuning
        a = self._adv
        walked = self.app.activity.today.get("walked", 0.0) / 1000
        step = max(0.1, tuning.get("adv_walk_km"))
        n = int(walked / step + 1e-9)
        if a["walk"] is None or n < a["walk"]:       # just switched on, or a new day
            a["walk"] = n
        elif n > a["walk"]:
            a["walk"] = n
            self.say(f"We've walked {self._km_words(round(n * step, 2))} today!")
        climbed = self.app.pet.climbed_today
        cstep = max(1.0, tuning.get("adv_climb_m"))
        c = int(climbed / cstep + 1e-9)
        if a["climb"] is None or c < a["climb"]:
            a["climb"] = c
        elif c > a["climb"]:
            a["climb"] = c
            self.say(f"We've climbed {round(c * cstep):g} metres today!")
        if a["lands"] and time.time() - a["land_ts"] >= 15:   # a quiet spell: say how many
            n, a["lands"] = a["lands"], 0
            words = {1: "A new land", 2: "Two new lands", 3: "Three new lands", 4: "Four new lands",
                     5: "Five new lands"}.get(n, f"{n} new lands")
            self.say(f"{words}! I claim {'it' if n == 1 else 'them'}!")
        cap = self.app.pet.pack_cap()
        full = cap > 0 and self.app.pet.pack >= cap - 0.05
        if a["pack_full"] is None:
            a["pack_full"] = full                    # don't announce a pack that was already full
        elif full and not a["pack_full"]:
            a["pack_full"] = True
            self.say("Smashing! My pack is full up!")
        elif a["pack_full"] and self.app.pet.pack < cap * 0.8:
            a["pack_full"] = False                   # ready to cheer again once it's refilled

    def _ring_soon(self, name):
        if self.connected and self.ready and self.s["enabled"]:
            asyncio.ensure_future(self.once(name))

    def speaks(self):
        """Has he a voice at all: the Dot, or the phone?"""
        return bool(self.s["enabled"] or self.s["phone"])

    def phone_route(self):
        """'phone' (the phone only), 'both', 'dot' or None: where a remark goes right now."""
        dot = self.s["enabled"]
        if self.s["phone"]:
            return "both" if dot else "phone"
        if dot and self.s["phone_backup"] and not (self.connected and self.ready) and self.phone.listening():
            return "phone"           # the Dot's lost: the phone stands in until it's back
        return "dot" if dot else None

    def say(self, text, force=False):
        if not text or getattr(self.app, "napping", False):
            return
        route = self.phone_route()
        if route in ("phone", "both") and (force or not self.quiet_now()):
            self.phone.push(text)
        if route in ("phone", None):
            return
        if not (self.connected and self.ready):
            return              # the Dot's away: nothing is saved up (the recap covers time apart),
                                # or a timer would come back as a pile of stale "pasta is done!"
        if not force:
            if self.quiet_now():
                return
            # don't let a busy street build a backlog: keep the newest few (Adventure mode's
            # news is rarer and worth hearing, so it keeps more)
            self.queue = self.queue[-(8 if self.s["chatty"] == "adventure" else 3):]
        self.queue.append(text)
        self.queue_event.set()

    async def _make_speech_here(self, text, name="say.wav"):
        """Piper on the Pi, converted for the Dot's speaker and copied over as `name`.
        Returns the seconds of speech, or None."""
        raw = os.path.join(self.tmp, "voice-raw.wav")
        wav = os.path.join(self.tmp, name)
        ok = await self.voice.say(text, raw)
        if not ok:
            ok = await voicemod.espeak(text, raw, self.s["pitch"])
        if not ok:
            self.state = "connected (no voice installed: see the README)"
            return None
        # full strength in the file; the speaker chip's own volume makes it quieter
        if not await voicemod.convert(raw, wav, 95, self.s["pitch"]):
            return None
        speech_s = voicemod.duration(wav)
        await asyncio.to_thread(voicemod.pad, wav, LEAD_S, TAIL_S)
        rc, out = await self._adb("push", wav, f"{H}/{name}", timeout=30)
        return speech_s if rc == 0 else None

    async def _make_speech(self, text, name):
        """One sentence, ready to play on the Dot as `name`: made on the Dot itself if it
        can (only the words travel, and Piper is quicker there), otherwise on the Pi.
        Returns (seconds of speech or None, where)."""
        if self.dot_ears.voice:
            r = await self.dot_ears.say(text, self.s["speed"], self.s["pitch"],
                                        voicemod.volume_factor(95), LEAD_S, TAIL_S, file=name)
            if r and r.get("ok"):
                if self.voice.proc:
                    await self.voice.stop()          # the Pi's copy of Piper isn't needed
                return float(r["speech_s"]), "Dot"
            if r:
                log.warning("making speech on the Dot failed: %s", r.get("error"))
        return await self._make_speech_here(text, name), "Pi"

    async def _play(self, name, speech_s):
        dev = int(self.cfg["audio_device"])
        # both counted from the moment the sound actually starts playing
        amp_on = min(LEAD_S - 0.05, float(self.cfg["amp_on_after"]))
        amp_for = LEAD_S - amp_on + speech_s + 0.25
        vol = self.s["adv_volume"] if self.s["chatty"] == "adventure" else self.s["volume"]
        await self.sh(f"sh {H}/speak.sh {H}/{name} {dev} {volume_register(vol)} "
                      f"{amp_on:.2f} {amp_for:.2f}", timeout=speech_s + LEAD_S + TAIL_S + 15)

    def hush(self):
        """Stop talking: what's queued, and the rest of what he's in the middle of saying."""
        self.queue.clear()
        self._hush_seq += 1

    async def _speak(self, text):
        async with self._speak_lock:            # one thing at a time through the speaker
            if self.dot_ears.connected:
                await self.dot_ears.busy(True)  # so the wake word doesn't hear him talk
            try:
                await self._speak_now(text)
            finally:
                if self.dot_ears.connected:
                    await self.dot_ears.busy(False)

    async def _speak_now(self, text):
        """Say `text` a sentence at a time: while one sentence plays, the next is being
        made, so he starts talking as soon as the first one is ready."""
        t_tts = time.monotonic()
        parts = voicemod.sentences(text)
        if not parts:
            return
        hush = self._hush_seq
        names = ["say1.wav", "say2.wav"]          # one plays while the other is being made
        making = asyncio.ensure_future(self._make_speech(parts[0], names[0]))
        started = False
        try:
            for i, part in enumerate(parts):
                speech_s, where = await making
                making = None
                if speech_s is None or hush != self._hush_seq:
                    return
                if i + 1 < len(parts):
                    making = asyncio.ensure_future(self._make_speech(parts[i + 1], names[(i + 1) % 2]))
                if not started:
                    started = True
                    if self._ask_done and self.timing and "making speech" not in self.timing:
                        more = f" (first of {len(parts)} sentences)" if len(parts) > 1 else ""
                        self.timing += f", making speech {time.monotonic() - t_tts:.1f} s on the {where}{more}"
                        self._ask_done = None
                    self._speaking = True
                    await self.once("ev_talk")
                await self._play(names[i % 2], speech_s)
            self.spoken += 1
        finally:
            if making:
                making.cancel()
            if started:
                await self.once("ev_hush")
                self._speaking = False
                self._last_spoke = time.time()

    async def speaker_loop(self):
        while not self.app.stop.is_set():
            if not self.queue:
                self.queue_event.clear()
                try:
                    await asyncio.wait_for(self.queue_event.wait(), 30)
                except asyncio.TimeoutError:
                    continue
                continue
            wait = self._last_spoke + self.s["gap"] - time.time()
            if wait > 0:
                await self.app._sleep(min(wait, 5))
                continue
            text = self.queue.pop(0)
            if not (self.connected and self.ready):
                continue
            try:
                await self._speak(text)
            except Exception:
                log.exception("speaking failed")

    # ------------------------------------------------------------ welcome home
    def _contact(self, now):
        self.store.put("dot_contact", {"ts": now, "meals": self.app.pet.total_meals,
                                       "treats": self.app.pet.total_treats})

    def _prepare_recap(self, now):
        c = self.store.get("dot_contact")
        if not c or now - c["ts"] < self.cfg["recap_after_minutes"] * 60:
            return
        events = [e for e in self.store.events(500) if e["ts"] > c["ts"]]
        events.reverse()
        text = build_recap(self.app.pet.name, events,
                           max(0, self.app.pet.total_meals - c.get("meals", 0)),
                           max(0, self.app.pet.total_treats - c.get("treats", 0)), now - c["ts"])
        if text:
            self.recap_pending = text
            log.info("recap ready (%d characters)", len(text))

    def _deliver_recap(self):
        if self.recap_pending and self.s["enabled"] and self.s["chatty"] not in ("silent", "adventure") \
                and not self.quiet_now():
            text, self.recap_pending = self.recap_pending, None
            self.queue.insert(0, text)
            self.queue_event.set()

    # ------------------------------------------------------------ the main loop
    async def run(self):
        if not self.cfg["enabled"]:
            self.state = "switched off in bt-dragon.toml"
            await self._timer_loop()     # timers still work (on his screen)
            return
        await asyncio.gather(self.speaker_loop(), self._link_loop(), self._timer_loop())

    async def _link_loop(self):
        last_health = 0.0
        while not self.app.stop.is_set():
            now = time.time()
            if getattr(self.app, "napping", False):
                # a nap: the Dot goes dark and quiet, and isn't even looked for
                if self.connected:
                    await self.release()
                self.queue.clear()
                self.state = f"{self.app.pet.name} is napping"
                self._last_scan = self._last_full = 0.0     # look for it straight away on waking
                await self.app._sleep(5)
                continue
            if not self.s["enabled"]:
                if self.connected:
                    await self.release()
                self.state = "switched off in the den"
                await self.app._sleep(5)
                continue
            if not self.connected:
                if self._missing_since is None:
                    self._missing_since = now
                # its last address is tried every minute; the whole hotspot only every
                # 3 minutes, so a long walk doesn't mean knocking on 254 doors a minute
                if now - self._last_scan >= 60:
                    full = now - self._last_full >= 180
                    self._last_scan = now
                    if full:
                        self._last_full = now
                    if await self.find(full):
                        self.connected, self._fails = True, 0
                        self._missing_since = None
                        self._rescue_wait, self._adb_fixes = RESCUE_WAIT_S, 0
                        if self._lost_at:
                            log.info("found the Dot again")
                        self._prepare_recap(now)
                        if not await self.setup():
                            self.connected = self.ready = False
                            self.state = self.state if "didn't" in self.state else "couldn't set up the Dot"
                if not self.connected and self.dot_ears.connected:
                    await self._half_connected(now)
                if self._lost_at and now - self._lost_at > 300 and not self.dot_ears.connected:
                    await self.voice.stop()        # give the memory back while he's apart
                    self.ears.forget()
                    self._lost_at = None
                await self.app._sleep(5)
                continue
            # connected
            doubt = self._doubt
            if doubt or now - last_health >= 20:
                last_health = now
                self._doubt = None
                if "ok" not in (await self.sh("echo ok", 10) or ""):   # any other answer: not really there
                    self._fails += 1
                    if doubt:      # its setup network is up AND it didn't answer: it's gone
                        self.mark_lost("its setup network is on the air and it didn't answer")
                        continue
                    if self._fails >= 2:
                        self.mark_lost("it stopped answering")
                        continue
                elif doubt:
                    # it answered: the setup network is an echo (an old scan, or the Dot
                    # closing it after a rescue). Stop worrying about it for a couple of minutes.
                    self._fails = 0
                    self._setup_ok_until = now + 120
                    log.info("the Dot's setup network showed up, but the Dot still answers: staying")
                    if now - self._locked_at >= LOCK_AGAIN_S:
                        await self.lock_setup_network()
                else:
                    self._fails = 0
                    self._contact(now)
                    if not await self.player_running():     # the Dot restarted?
                        self.ready = False
                        await self.setup()
            if self.ready:
                if self.dot_ears.connected:
                    await self.dot_ears.set_wake(self.wake_reason() == "", int(tuning.get("wake_strict")))
                if self._anims_pushed != self._anim_key():
                    await self.push_animations()
                await self.base(self.wanted_base())
                self._deliver_recap()
            await self.app._sleep(2)

    # ------------------------------------------------------------ buttons
    async def _keys_loop(self):
        """Listen to the Dot's buttons for as long as it's connected. `micgrab keys` on the
        Dot prints a line per press, straight away; it runs inside one long adb shell.
        When the Dot's own ears are running, they pass the buttons on instead."""
        while self.connected and self.ready and not self.app.stop.is_set():
            if self.dot_ears.handles_keys:
                await self.app._sleep(3)
                continue
            try:
                proc = await asyncio.create_subprocess_exec(
                    "adb", "-s", self.target, "shell", f"{H}/micgrab keys",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            except OSError:
                return
            self._keys_proc = proc
            try:
                while not self.dot_ears.connected:
                    try:
                        line = await asyncio.wait_for(proc.stdout.readline(), 3)
                    except asyncio.TimeoutError:
                        continue
                    if not line:
                        break
                    self.on_key(line.decode(errors="replace").strip())
            finally:
                if proc.returncode is None:
                    proc.kill()
                self._keys_proc = None
            await self.app._sleep(3)

    def on_key(self, line):
        parts = line.split()
        if len(parts) != 3 or parts[0] != "KEY" or parts[2] != "1":
            return
        key = parts[1]
        if self.alarm and key in ("ACTION", "VOLUP", "VOLDOWN"):
            self.stop_alarm()          # any button silences a ringing timer
            return
        if key == "ACTION":
            if not (self.asking or self._speaking or self.queue):
                asyncio.ensure_future(self.ask_spoken())
        elif key in ("VOLUP", "VOLDOWN"):
            v = max(0, min(100, int(self.s["volume"]) + (10 if key == "VOLUP" else -10)))
            self.s["volume"] = v
            self.save()
            asyncio.ensure_future(self.once(f"vol_{round(v / 100 * ring.LEDS)}"))
        elif key == "MUTE":
            # the button cuts the microphones in hardware; this only keeps track for the ring
            self.mic_muted = not self.mic_muted
            log.info("microphones %s", "off" if self.mic_muted else "on")

    # ------------------------------------------------------------ questions
    async def _record(self, name, max_s, wait_s=4, pre_s=0.0):
        """Record until the speaker stops; returns the local WAV path, or None if nobody spoke.
        From the wake-word stream if it's running (the microphones can't be opened twice),
        otherwise with micgrab on the Dot."""
        local = os.path.join(self.tmp, name)
        if self.mic.active:
            return local if await self.mic.capture(local, max_s, wait_s, pre_s) else None
        out = await self.sh(f"{H}/micgrab {H}/{name} {max_s}", timeout=max_s + 12) or ""
        if not out.startswith("SPEECH"):
            if "ERROR" in out or not out:
                log.warning("recording failed: %s", out.strip())
            await self.sh(f"rm -f {H}/{name}", 10)
            return None
        rc, _ = await self._adb("pull", f"{H}/{name}", local, timeout=20)
        await self.sh(f"rm -f {H}/{name}", 10)
        return local if rc == 0 and os.path.exists(local) else None

    @property
    def can_hear(self):
        return self.dot_ears.connected or self.ears.available

    def grammar(self):
        """What a question can contain: the usual words and phrases, plus every item that's
        ever been on the shopping list, and the names of the landmarks and green spaces
        he knows near here."""
        extra = [w for w in self.shopping.words() if w not in ask.VOCABULARY]
        for p in self.known_landmarks() + self.known_greens(200):
            extra += [w for w in wayfinding.name_words(p["title"]) if w not in ask.VOCABULARY]
            extra.append(wayfinding.name_phrase(p["title"]))
        return ask.GRAMMAR + list(dict.fromkeys(x for x in extra if x))

    # ------------------------------------------------------------ which way is it
    def saw_landmark(self, lm):
        """He's just pointed this one out: "where is that landmark?" means this one for a while."""
        self.last_landmark = (lm, time.time())

    def _here(self):
        """(lat, lon, minutes old) from the GPS (or, without one, a Wi-Fi position), if it's
        recent enough to be useful."""
        gps = getattr(self.app, "gps", None)
        fix = getattr(gps, "fix", None)
        wifipos = getattr(self.app, "wifipos", None)
        if (not fix or time.time() - fix["ts"] > 30 * 60) and wifipos is not None:
            fix = wifipos.current() or fix
        if not fix or time.time() - fix["ts"] > 30 * 60:
            return None
        return fix["lat"], fix["lon"], int((time.time() - fix["ts"]) // 60)

    def known_landmarks(self, limit=300):
        """Famous places he knows about, nearest first when he knows where we are."""
        app = self.app
        if not getattr(app, "landmarks", None):
            return []
        try:
            places = app.store.landmarks_list(tuning.get("landmark_langs"))
        except Exception:
            return []
        here = self._here()
        if here:
            places.sort(key=lambda p: wayfinding.distance_m(here[0], here[1], p["lat"], p["lon"]))
        else:
            places.sort(key=lambda p: -p.get("langs", 0))
        return places[:limit]

    def known_greens(self, limit=300):
        """Parks, woods and so on he knows about, as places: nearest edge first when he
        knows where we are (0 when we're in one)."""
        from . import greens as greensmod
        app = self.app
        if not getattr(app, "greens", None):
            return []
        try:
            found = app.store.greens_list()
        except Exception:
            return []
        here = self._here()
        out = []
        for g in found:
            d = greensmod.locate(g, here[0], here[1])[0] if here else -g.get("area", 0)
            out.append({"title": g["name"], "lat": g["lat"], "lon": g["lon"], "green": g, "dist": d,
                        "first_seen": g.get("first_seen"), "last_seen": g.get("last_seen")})
        out.sort(key=lambda p: p["dist"])
        return out[:limit]

    def _way_to(self, place, here):
        """Words for where a place is from here: to the nearest edge of a green space."""
        from . import greens as greensmod
        from .landmarks import clean_title
        title = clean_title(place["title"])
        if place.get("green"):
            d, pt = greensmod.locate(place["green"], here[0], here[1])
            if d <= tuning.get("green_margin_m"):
                return f"We're in {title} right now!"
            return wayfinding.where_words(title, here[:2], pt)
        return wayfinding.where_words(title, here[:2], (place["lat"], place["lon"]))

    @staticmethod
    def _was(here, words):
        if here[2] < 2:
            return words
        if words.startswith("We're") or words.startswith("The "):
            return f"From where we were {here[2]} minutes ago: " + words[0].lower() + words[1:]
        return f"From where we were {here[2]} minutes ago, " + words

    def answer_nearest(self, here, unseen=False, green=False):
        """'Where is the closest landmark?': the nearest famous place he knows of, and
        whether he's seen it (and when he last did). With `unseen`, the nearest one he
        hasn't seen yet. With `green`, parks and woods instead ("explored")."""
        what = "green space" if green else "landmark"
        if not here:
            return (f"I don't know where we are right now, so I can't tell which {what} is closest. "
                    "My position comes from your phone's GPS.")
        places = self.known_greens(5000) if green else self.known_landmarks(1000)
        if not places:
            return f"I don't know any {what}s around here yet. Let's go exploring!"
        if unseen:
            places = [p for p in places if not (p.get("last_seen") or p.get("first_seen"))]
            if not places:
                return (f"I've {'explored' if green else 'seen'} every {what} I know of around here! "
                        "Let's explore somewhere new.")
        from .landmarks import clean_title
        place = places[0]
        self.last_landmark = (place, time.time())       # so "how far is it?" means this one
        title = clean_title(place["title"])
        if green:
            from . import greens as greensmod
            d, pt = greensmod.locate(place["green"], here[0], here[1])
            if d <= tuning.get("green_margin_m"):
                words = f"We're in {title} right now!"
            else:                                # direction and distance to its nearest edge
                words = wayfinding.nearest_words(title, here[:2], pt, "green space I haven't explored yet"
                                                 if unseen else "green space I know of")
                if not unseen:
                    words += " " + wayfinding.seen_words(place.get("last_seen") or place.get("first_seen"),
                                                         did="explored", done="explored")
        else:
            words = wayfinding.nearest_words(title, here[:2], (place["lat"], place["lon"]),
                                             "landmark I haven't seen yet" if unseen else "landmark I know of")
            if not unseen:
                words += " " + wayfinding.seen_words(place.get("last_seen") or place.get("first_seen"))
        return self._was(here, words)

    def answer_where(self, q, alt_text=None):
        here = self._here()
        if q.get("nearest"):
            return self.answer_nearest(here, q.get("unseen", False), q.get("green", False))
        if q["name"] is None:
            last = self.last_landmark
            if not last or time.time() - last[1] > 180:
                return ("I haven't pointed out a landmark in the last few minutes. "
                        "Ask me about one by name: where is, and the name.")
            place = last[0]
        else:
            names = [q["name"]]
            alt = ask.parse(alt_text) if alt_text else None
            if alt and alt.get("intent") == "where" and alt.get("name"):
                names.append(alt["name"])          # the open listen may have caught an odd word
            place, best = None, 0.0
            known = self.known_landmarks(1000) + self.known_greens(5000)
            for name in names:
                p = wayfinding.best_match(name, known, here)
                score = wayfinding.match_score(name, p["title"]) if p else 0.0
                if p and score > best:
                    place, best = p, score
            if not place:
                city = ask.find_place(" ".join(names))
                if city:
                    tz, lat, lon, say = ask.PLACES[city]
                    place = {"title": say, "lat": lat, "lon": lon}
            if not place:
                return (f"I don't know a place called {q['name']}. I only know famous places, parks "
                        "and woods near where we've been, and big cities.")
        from .landmarks import clean_title
        if not here:
            return (f"I don't know where we are right now, so I can't tell where {clean_title(place['title'])} is. "
                    "My position comes from your phone's GPS.")
        return self._was(here, self._way_to(place, here))

    @staticmethod
    def _better(text, free_text):
        """The second, open listen wins when it makes sense of a shopping-list request."""
        if free_text:
            q = ask.parse(free_text)
            if q["intent"] in ("shop_add", "shop_remove") and q["items"]:
                return free_text
        return text

    async def _hear(self, name, max_s, words=None, pre_s=0.0, free=False):
        """Record until the speaker stops and turn it into words: on the Dot if it can,
        otherwise recorded there and understood here. Returns (text, where, record_s,
        understand_s); text is None if nobody spoke. With `free`, every word Vosk knows
        (for a name); otherwise his word list. The recording's voice print, if any, is
        left in self._voice."""
        free_if = None
        self._voice = (None, 0)
        self._free_text = None
        if free:
            words = None
        elif words is None:                        # a question: the full list, and a second
            words, free_if = self.grammar(), ask.FREE_IF   # listen for unknown shopping items
        if self.dot_ears.connected and not self.mic.active:
            r = await self.dot_ears.hear(max_s, words, free_if, free, pre_s)
            if r is not None:
                if r.get("error"):
                    log.warning("listening on the Dot: %s", r["error"])
                if not r.get("speech"):
                    return None, "Dot", r.get("rec_s", 0), 0
                self._voice = (r.get("spk"), r.get("spk_frames", 0))
                self._free_text = r.get("free_text")
                return (self._better(r.get("text", ""), r.get("free_text")), "Dot",
                        r.get("rec_s", 0), r.get("stt_s", 0))
            if not self.ears.available:
                return None, "Dot", 0, 0
        t0 = time.monotonic()
        local = await self._record(name, max_s, pre_s=pre_s)
        t1 = time.monotonic()
        if not local:
            return None, "Pi", t1 - t0, 0
        try:
            await asyncio.to_thread(hearing.normalize, local)
            if hasattr(self.ears, "hear_full") and (free_if or free or words is None or len(words) > 20):
                r = await self.ears.hear_full(local, words, free_if, free)
                text = self._better(r["text"], r.get("free_text"))
                self._free_text = r.get("free_text")
                self._voice = (r.get("spk"), r.get("spk_frames", 0))
            else:
                text = await self.ears.hear(local, words)
        except Exception as e:
            log.warning("couldn't understand the recording: %s", e)
            text = ""
        finally:
            try:
                os.remove(local)              # recordings are never kept
            except OSError:
                pass
        return text, "Pi", t1 - t0, time.monotonic() - t1

    def on_wake(self):
        """ "Hey dragon" was heard."""
        if self.alarm:
            self.stop_alarm()
        elif not (self.asking or self._speaking or self.queue):
            asyncio.ensure_future(self.ask_spoken(via_wake=True))

    async def ask_spoken(self, via_wake=False):
        """Record a question (after the action button or the wake word), understand it, answer it."""
        if not self.s["listen"]:
            return
        if self.mic_muted:
            self.say("My ears are covered. Press the microphone button so I can hear you.", force=True)
            return
        if not self.can_hear:
            self.say("I can't understand speech yet: the speech recognizer isn't installed.", force=True)
            return
        self.asking = True
        try:
            await self.once("ev_listen")
            text, where, rec_s, stt_s = await self._hear("ask.wav", 8, pre_s=1.0 if via_wake else 0.0)
            if via_wake and (text is None or not text.replace("hey dragon", "").replace("[unk]", "").strip()):
                self.wake_unasked += 1       # woke for nothing: probably a false alarm
            if text is None:
                await self.once("ev_hush")
                return
            await self.once("ev_think")
            self.heard = text
            log.info("heard a question on the %s (%d words)", where, len(text.split()))   # never what was said
            first_voice = self._voice
            self.speaker, pct, guess = self.voices.identify(*first_voice)
            self.heard_from = (self.speaker + f" ({pct}% alike)" if self.speaker else
                               f"not sure (closest: {guess}, {pct}% alike)" if guess else "")
            q = ask.parse(text)
            if q["intent"] == "voice_enrol":
                await self.once("ev_hush")
                await self._enrol(first_voice)
                return
            if q["intent"] in ("sleep", "nap"):
                await self.once("ev_hush")
                await self._rest(q["intent"])
                return
            alt_text = self._free_text
            t3 = time.monotonic()
            if q["intent"] == "voice_who":
                reply = self.answer_who(first_voice)
            elif q["intent"] == "where":
                reply = voicesmod.with_name(self.answer_where(q, alt_text), self.speaker)
            else:
                reply = voicesmod.with_name(await self.answer(text), self.speaker) \
                    if q["intent"] not in ("stop", None) else await self.answer(text)
            self.answered = reply
            t4 = time.monotonic()
            self.timing = (f"{'wake word' if via_wake else 'button'}, understood on the {where}: "
                           f"listening {rec_s:.1f} s, understanding {stt_s:.1f} s, answer {t4 - t3:.1f} s")
            self._ask_done = time.monotonic()
            log.info("question timing: %s", self.timing)
            await self.once("ev_hush")
            if reply:
                self.say(reply, force=True)
        finally:
            self.asking = False

    # ------------------------------------------------------------ voice profiles
    def answer_who(self, voice):
        vec, frames = voice
        if not vec:
            return ("I can't tell voices apart yet: the speaker model isn't installed. "
                    "Run install-voice.sh on the Pi.")
        if not self.voices.items:
            return "I don't know anyone's voice yet. Say: set a voice profile."
        if frames < voicesmod.MIN_FRAMES:
            return "That was too short for me to tell. Ask me again in a longer sentence."
        name, pct, guess = self.voices.identify(vec, frames)
        if name:
            return f"You sound like {name}!"
        return f"I'm not sure. You sound a little like {guess}, but not enough to be certain."

    async def _rest(self, which):
        """'Go to sleep' / 'take a nap': ask first, and only a clear yes counts."""
        await self._speak("Shall I go to sleep now?" if which == "sleep" else "Shall I take a nap now?")
        await self.once("ev_listen")
        text, *_ = await self._hear("yes.wav", 4, words=ask.YES_GRAMMAR)
        await self.once("ev_hush")
        self.heard = f"{'go to sleep' if which == 'sleep' else 'take a nap'}, then: {text or '(nothing)'}"
        if not ask.is_yes(text):
            self.answered = ""
            log.info("%s: no clear yes, staying awake", which)
            return
        self.answered = ("Going to sleep now. Good night!" if which == "sleep"
                         else "I'll have a lie down for a bit. Wake me up later.")
        await self._speak(self.answered)
        log.info("%s, asked by voice", which)
        if which == "sleep":
            asyncio.ensure_future(self.app.shutdown("SLEEP"))
        else:
            asyncio.ensure_future(self.app.nap())

    async def _enrol(self, first):
        """'Set a voice profile': ask who's speaking, ask for a sentence or two more, and
        keep the average voice print under that name."""
        if not first[0]:
            self.answered = ("I can't learn voices yet: the speaker model isn't installed. "
                             "Run install-voice.sh on the Pi.")
            self.say(self.answered, force=True)
            return
        samples = [first]
        await self._speak("Okay! Who is speaking?")
        await self.once("ev_listen")
        text, *_ = await self._hear("name.wav", 6, free=True)
        await self.once("ev_hush")
        name = voicesmod.clean_name(text or "")
        if not name:
            self.answered = "Sorry, I didn't catch your name. Say: set a voice profile, to try again."
            self.say(self.answered, force=True)
            return
        samples.append(self._voice)
        known = self.voices.find(name) is not None
        await self._speak(f"{'Hello again' if known else 'Nice to meet you'}, {name}! Now say a sentence or two, "
                          f"so I can learn your voice. Tell me about your day.")
        await self.once("ev_listen")
        more, *_ = await self._hear("voice.wav", 12, free=True)
        await self.once("ev_hush")
        if more:
            samples.append(self._voice)
        profile, new = self.voices.add(name, samples)
        if not profile:
            self.answered = "Sorry, I didn't hear enough of your voice. Let's try again later."
        elif new:
            self.answered = f"Got it, {name}. I'll know your voice from now on."
            self.app.event("voice", f"{self.app.pet.name} learned a new voice: {name}")
        else:
            self.answered = f"Thanks, {name}. I've learned a bit more about your voice."
        self.heard = f"set a voice profile ({name})"
        self.say(self.answered, force=True)

    async def answer(self, text):
        """Words for a question (spoken or typed). '' means: nothing to say. A short version
        for his screen, where there is one, is left in self.screen_answer."""
        self.screen_answer = None
        q = ask.parse(text or "")
        i = q["intent"]
        if i == "stop":
            if self.alarm:
                self.stop_alarm()
            self.hush()
            return ""
        if i == "time":
            return ask.answer_time(q["place"])
        if i in ("date", "day"):
            return ask.answer_date(q.get("tomorrow"), i == "day")
        if i and i.startswith("timer"):
            return ask.answer_timer(q, self.timers)
        if i == "weather":
            return await self._weather(q)
        if i == "conditions":
            return await self._conditions(q)
        if i and i.startswith("shop_"):
            return self.answer_shopping(q)
        if i == "cal_day":
            return self.answer_calendar(q["day"])
        if i == "voice_enrol":
            return "Press my Dot's button and say it out loud, so I can hear your voice."
        if i == "voice_who":
            return "I can only tell who's talking when I hear you: ask me on the Dot."
        if i in ("sleep", "nap"):
            return ("Ask me on the Dot, and I'll check with you first. Or use the buttons in my den."
                    if i == "sleep" else "Ask me on the Dot, or use the Nap button in my den.")
        if i == "where":
            return self.answer_where(q)
        if i == "trip":
            return self.answer_trip(q.get("today", False))
        if i == "cal_edit":
            return "I can't change my calendar by voice yet. You can do it on the calendar page in my den."
        return "Sorry, I didn't catch that." if text else "Sorry, I didn't hear a question."

    def answer_trip(self, today=False):
        """'How far have we gone on this walk?'"""
        from . import activity as actmod
        act = getattr(self.app, "activity", None)
        if act is None:
            return "I can't tell how far we've gone: I'm not keeping track of walks."
        t = act.trip_now()
        so_far = act.today.get("walked", 0.0) if act.today.get("date") == time.strftime("%Y-%m-%d") else 0.0
        if t and t["meters"] >= 10 and not today:
            return (f"We've gone {wayfinding.metric(t['meters'])} on this {t['kind']}, about "
                    f"{wayfinding.imperial(t['meters'])}, in {actmod.duration_words(t['seconds'])}.")
        if so_far >= 10:
            lead = "" if today else "We're not out on a walk right now. "
            return (f"{lead}Today we've gone {wayfinding.metric(so_far)} together under our own steam, "
                    f"about {wayfinding.imperial(so_far)}.")
        return "We haven't been anywhere together today yet. Let's go for a walk!"

    def answer_calendar(self, which, today=None):
        import datetime as dt
        today = today or dt.date.today()
        if which == "today":
            return self.calendar.spoken_day(today, "today")
        if which == "tomorrow":
            return self.calendar.spoken_day(today + dt.timedelta(days=1), "tomorrow")
        ahead = (ask.WEEKDAYS.index(which) - today.weekday()) % 7
        day = today + dt.timedelta(days=ahead)
        return self.calendar.spoken_day(day, "today" if ahead == 0 else f"on {which.capitalize()}")

    def remind(self, now=None):
        """Calendar reminders that are due: a vague one on his screen (anyone can see it),
        and the real one, with the event's name, through the Dot (even in quiet hours: you
        asked for it, like a kitchen timer)."""
        for ev, day, r in self.calendar.due(now):
            self.app.pet.say(self.calendar.screen_text(ev, day, now), "excited", 120, speak=False)
            self.app.pet.message_hold = time.time() + 120      # so it stays up a while
            self.say(self.calendar.spoken_reminder(ev, day, now), force=True)
            self._ring_soon("ev_alarm")
            log.info("calendar reminder for event %s", ev["id"])

    def answer_shopping(self, q):
        sl = self.shopping
        if q["intent"] == "shop_read":
            return sl.spoken()
        if not q["items"]:
            return ("I didn't catch the item. You can type it on the shopping list page in my den."
                    if q["intent"] == "shop_add" else "I didn't catch what to take off the list.")
        if q["intent"] == "shop_add":
            added, back, already = [], [], []
            for name in q["items"]:
                result, item = sl.add(name)
                if item:
                    {"added": added, "back": back, "already": already}[result].append(item["name"].lower())
            parts = []
            if added:
                parts.append(f"I've added {_list(added)} to the shopping list.")
            if back:
                parts.append(f"I've put {_list(back)} back on the list.")
            if already:
                names = _list(already)
                verb = "is" if len(already) == 1 else "are"
                parts.append(f"{names[:1].upper() + names[1:]} {verb} already on the list.")
            return " ".join(parts) or "I didn't catch the item."
        gone, missing = [], []
        for name in q["items"]:
            item = sl.remove(name)
            (gone if item else missing).append(item["name"].lower() if item else shopping.tidy(name).lower())
        parts = []
        if gone:
            parts.append(f"I've taken {_list(gone)} off the shopping list.")
        if missing:
            verb = "isn't" if len(missing) == 1 else "aren't"
            names = _list(missing)
            parts.append(f"{names[:1].upper() + names[1:]} {verb} on the list.")
        return " ".join(parts)

    def _target(self, q):
        """Where a weather question is about: (lat, lon, words, country code), or words saying why not.
        'At home' or 'at the Lair' means the Lair; a named place means there; otherwise here
        (GPS or Wi-Fi), and if he doesn't know where here is, the Lair."""
        lair = getattr(self.app, "lair", None)
        at_lair = lair.where() if lair else None
        if q.get("home"):
            if not at_lair:
                return f"I don't know where my Lair is yet. Set it in my den, under {self.app.pet.name}'s Lair."
            return at_lair[0], at_lair[1], "at the Lair", lair.s.get("code")
        if q.get("place"):
            _, lat, lon, label = ask.PLACES[q["place"]]
            return lat, lon, f"in {label}", None
        fix = self.app.where_now() if hasattr(self.app, "where_now") else None
        if fix:
            return fix["lat"], fix["lon"], "here", None
        if at_lair:
            return at_lair[0], at_lair[1], "at the Lair", lair.s.get("code")
        if self.s["home_lat"] is not None:
            return self.s["home_lat"], self.s["home_lon"], "here", None
        return (f"I don't know where we are. Set my Lair in my den, under {self.app.pet.name}'s Lair, "
                "or link a GPS.")

    async def _weather(self, q):
        t = self._target(q)
        if isinstance(t, str):
            return t
        lat, lon, where, _ = t
        try:
            data = await asyncio.to_thread(ask.fetch_weather, lat, lon)
        except Exception as e:
            log.warning("weather lookup failed: %s", e)
            return "I couldn't get the weather just now. Are we connected to the internet?"
        if q["when"] == "now":
            from . import lair as lairmod
            self.screen_answer = lairmod.screen_conditions("temperature", where, data)
        return ask.answer_weather(data, q["when"], None if where == "here" else where.removeprefix("in "))

    def _warnings_answer(self):
        lair = getattr(self.app, "lair", None)
        if not lair or not lair.complete:
            return f"I don't know where my Lair is yet. Set it in my den, under {self.app.pet.name}'s Lair."
        source, _ = lair.warnings_where()
        if not source:
            return "I can only get official weather warnings for a Lair in the United Kingdom or the United States so far."
        if not lair.announcing:
            return "I only keep an eye on weather warnings while Local announcements are on, in my den."
        active = lair.s.get("warn_active") or []
        if not active:
            return "There are no weather warnings at the Lair right now."
        if len(active) == 1:
            return f"There's one weather warning at the Lair: {active[0]['spoken']}."
        return f"There are {len(active)} weather warnings at the Lair: " + "; ".join(w["spoken"] for w in active) + "."

    async def _conditions(self, q):
        """Humidity, air pressure, pollen, sunrise and sunset, UV, air quality."""
        from . import lair as lairmod
        if q["what"] == "warnings":
            return self._warnings_answer()
        t = self._target(q)
        if isinstance(t, str):
            return t
        lat, lon, where, code = t
        try:
            if q["what"] in ("pollen", "air"):
                return lairmod.answer_conditions(q["what"], where, air=await asyncio.to_thread(lairmod.fetch_air, lat, lon),
                                                 code=code)
            cond = await asyncio.to_thread(lairmod.fetch_conditions, lat, lon)
            self.screen_answer = lairmod.screen_conditions(q["what"], where, cond, tomorrow=q.get("tomorrow", False))
            return lairmod.answer_conditions(q["what"], where, cond, tomorrow=q.get("tomorrow", False), code=code)
        except Exception as e:
            log.warning("conditions lookup failed: %s", e)
            return "I couldn't look that up just now. Are we connected to the internet?"

    async def _find_home(self, name):
        try:
            g = await asyncio.to_thread(ask.geocode, name)
        except Exception as e:
            log.warning("couldn't look up a place: %s", e)
            g = None
        if g and self.s["home_town"] == name:
            self.s["home_town"], self.s["home_lat"], self.s["home_lon"] = g
            self.save()

    # ------------------------------------------------------------ timers
    async def _timer_loop(self):
        while not self.app.stop.is_set():
            now = time.time()
            if getattr(self.app, "napping", False):
                # no ringing in a nap: a timer that ends meanwhile rings on waking, as it
                # would after being switched off (and so does a calendar reminder)
                if self.alarm:
                    self.stop_alarm()
                await self.app._sleep(1)
                continue
            if now - getattr(self, "_adv_checked", 0) >= 2:
                # Adventure mode's milestones, here rather than in the Dot's own loop, so the
                # phone voice gets them too (this loop runs with or without a Dot)
                self._adv_checked = now
                try:
                    self._adventure_tick()
                except Exception:
                    log.exception("adventure milestones")
            if now - getattr(self, "_cal_checked", 0) >= 15:
                self._cal_checked = now
                try:
                    self.remind(now)
                except Exception:
                    log.exception("calendar reminders")
            done = self.timers.due(now)
            if done:
                names = [ask.label(t) for t in done]
                self.alarm = {"names": names, "since": now, "next": now}
                self.app.pet.say("TIMER DONE!", "excited", 30)
            if self.alarm:
                if now - self.alarm["since"] > 300:          # five minutes is plenty
                    self.stop_alarm()
                elif now >= self.alarm["next"]:
                    self.alarm["next"] = now + 12
                    words = " and ".join(self.alarm["names"])
                    self.say(f"{words[0].upper() + words[1:]} {'is' if len(self.alarm['names']) == 1 else 'are'} done!",
                             force=True)
                    await self.once("ev_alarm")
                    if not self._alarm_listening:
                        asyncio.ensure_future(self._listen_for_stop())
            await self.app._sleep(1)

    STOP_WORDS = ["stop", "okay", "ok", "enough", "thanks", "thank", "you", "cancel", "quiet", "done", "harald"]

    async def _listen_for_stop(self):
        """While a timer rings, listen (without a button press) for "stop" between announcements."""
        if not (self.ready and self.s["listen"] and not self.mic_muted and self.can_hear):
            return
        self._alarm_listening = True
        try:
            for _ in range(40):                    # wait for the announcement to finish
                if not self.alarm:
                    return
                if not (self._speaking or self.queue or self.asking):
                    break
                await asyncio.sleep(0.25)
            if not self.alarm:
                return
            text, where, _, _ = await self._hear("stop.wav", 4, words=self.STOP_WORDS)
            if self.alarm and text:
                words = text.split()
                log.info("while ringing, heard something on the %s", where)
                if any(w in ("stop", "okay", "ok", "enough", "thanks", "thank", "cancel", "quiet") for w in words):
                    self.stop_alarm()
        except Exception as e:
            log.warning("listening for stop failed: %s", e)
        finally:
            self._alarm_listening = False

    def stop_alarm(self):
        if self.alarm:
            self.alarm = None
            self.hush()
            asyncio.ensure_future(self.once("ev_hush"))

    # ------------------------------------------------------------ setup-mode rescue
    # An Echo that was never registered with Amazon goes into setup mode at every start: it
    # switches its saved networks off and broadcasts an open network of its own (named like
    # "Amazon-XY7"), where it can be reached at 10.201.126.241, ADB included. When Harald
    # sees *your* Dot's setup network and the Dot is missing from the hotspot, he hops over
    # for a moment, checks it really is your Dot (serial number), switches its saved
    # networks back on and hops home. That also closes the open network quickly.
    async def lock_setup_network(self):
        """Lock and close the Dot's own setup network, once Harald is in over the hotspot.

        After a restart the Dot runs an open network (like "Amazon-XY7") on a second Wi-Fi
        interface (p2p0 on a 2nd-generation Dot: wpa_supplicant hosting it, dnsmasq handing out
        addresses), and adb answers on it with no password. A rescue switches its saved networks
        back on, but with Amazon's setup program paused the setup network can stay on the air.
        So, on the Dot:
          1. the lock: its firewall drops everything arriving on that interface (anyone joining
             it can't reach adb, or anything else). Firewall rules are forgotten when the Dot
             restarts, so the next rescue still gets in;
          2. closing it: wpa_supplicant is asked to take the network down.
        Returns the interface's name, or "" if no setup network was up."""
        self._locked_at = time.time()
        out = await self.sh("ifconfig -a 2>/dev/null || netcfg", 10) or ""
        iface, current = "", ""
        for line in out.splitlines():
            if line and not line[0].isspace():
                current = line.split()[0].rstrip(":")
            if SETUP_NET_PREFIX in line and current:
                iface = current
                break
        iface = re.sub(r"[^A-Za-z0-9_.-]", "", iface)
        if not iface or iface.startswith("wlan0"):
            return ""
        rule = f"INPUT -i {iface} -j DROP"
        res = await self.sh(
            f"iptables -C {rule} 2>/dev/null || iptables -I {rule}; "
            f"ip6tables -C {rule} 2>/dev/null || ip6tables -I {rule} 2>/dev/null; "
            f"wpa_cli -i {iface} p2p_group_remove {iface} 2>/dev/null || "
            f"wpa_cli -i wlan0 p2p_group_remove {iface} 2>/dev/null; echo done", 20)
        log.info("the Dot's setup network (on %s): locked and asked to close%s", iface,
                 "" if res and "done" in res else " (no answer)")
        return iface

    async def _half_connected(self, now):
        """The Dot's ears still answer on their own line, but the debug link (adb) doesn't: the
        Dot is on the hotspot, and only adbd, its end of the debug link, is stuck. The ears run
        as root on the Dot, so they can restart it; Fire OS starts a fresh one by itself."""
        self.state = "half-connected: the Dot's ears answer, but its debug link doesn't"
        if self._adb_fixes >= ADB_FIX_MAX or now - self._adb_fixed_at < ADB_FIX_EVERY_S:
            if self._adb_fixes >= ADB_FIX_MAX:
                self.state += " (unplugging the Dot for 10 seconds will fix it)"
            return
        self._adb_fixes += 1
        self._adb_fixed_at = now
        reply = await self.dot_ears.fix_adb()
        log.info("half-connected: asked the Dot's ears to restart adbd (try %d): %s", self._adb_fixes,
                 "stopped it" if reply and reply.get("ok") else (reply or {}).get("error") or "no luck")
        if reply and reply.get("ok"):
            await self._adb("kill-server", target=False, timeout=10)   # and a fresh start at the Pi's end, too
            await self.app._sleep(4)      # a moment for the new adbd to start
            self._last_scan = self._last_full = 0.0

    def mark_lost(self, why, now=None):
        """The Dot isn't on the hotspot any more: stop using it and look for it again."""
        now = now or time.time()
        log.info("lost the Dot: %s", why)
        self.connected = self.ready = False
        self.state = "lost the Dot; looking again"
        self._lost_at, self._last_scan, self._last_full = now, 0.0, 0.0
        self._missing_since = now
        self._adb_fixes, self._adb_fixed_at = 0, 0.0
        self._fails = 0
        self._doubt = None
        self.queue.clear()

    SETUP_FRESH_MS = 15000

    def setup_mode_seen(self, aps):
        """Is the Dot's own setup network on the air right now? Only a fresh sighting counts:
        a cached scan can still list it for a while after it closed (after a rescue, say)."""
        name = self.s["setup_network"]
        return bool(name) and any(ap.get("ssid") == name and ap.get("rssi", -100) >= -85
                                  and ap.get("age_ms", 0) <= self.SETUP_FRESH_MS for ap in aps)

    def rescue_wanted(self, aps, now=None):
        now = now or time.time()
        name = self.s["setup_network"]
        if not (self.cfg["enabled"] and self.s["enabled"] and name and self.s["serial"]):
            return False
        if getattr(self.app, "napping", False):
            return False
        if self.connected and not self.rescuing and now >= self._setup_ok_until and self.setup_mode_seen(aps):
            # it may have restarted into setup mode while we still thought it was here. Don't
            # drop it on that alone (the network can linger, or be an old scan): ask it now,
            # and only a Dot that doesn't answer is lost.
            if not self._doubt:
                self._doubt = now
        if self.connected or self.rescuing or self.app._switching:
            return False
        if self.dot_ears.connected:
            return False        # its ears answer over the hotspot, so it's here: no use hopping away
        if self._missing_since is None or now - self._missing_since < 60:
            return False        # give it a minute: it may just be rejoining by itself
        if now - self._last_rescue_try < self._rescue_wait:
            return False
        return any(ap.get("ssid") == name and ap.get("rssi", -100) >= -85 for ap in aps)

    async def rescue(self):
        """Hop onto the Dot's setup network, switch its saved hotspot back on, hop home."""
        from . import wifi as wifimod
        if self.rescuing:
            return "already rescuing"
        self.rescuing, self._last_rescue_try = True, time.time()
        name, back = self.s["setup_network"], self.app.home_ssid
        addr = f"{SETUP_IP}:{PORT}"
        self.state = f"rescuing the Dot from setup mode (via {name})"
        log.info("Dot rescue: joining %s", name)
        self.app._switching = True
        result = "couldn't reach the Dot"
        try:
            if not await asyncio.to_thread(wifimod.ensure_rescue_profile, name):
                result = "couldn't set up the rescue network"
                return result
            ok, msg = await wifimod.connect_profile(wifimod.RESCUE_PROFILE, timeout=30)
            if not ok:
                # (often the Dot restarting, its network gone mid-join: try again soon, once)
                result = f"couldn't join {name}: {msg}"
                self._rescue_wait = RESCUE_RETRY_S if self._rescue_wait != RESCUE_RETRY_S else RESCUE_WAIT_S
                return result
            await asyncio.sleep(2)
            await self._adb("connect", addr, target=False, timeout=10)
            rc, out = await self._adb("-s", addr, "shell", "getprop ro.serialno", target=False, timeout=10)
            serial = out.strip().splitlines()[-1].strip() if rc == 0 and out.strip() else ""
            if not serial or " " in serial:
                # nothing answered on the debug link (adbd stuck or not started yet): not the
                # same as a stranger's Echo. Wait longer each time it gets nowhere.
                self._rescue_wait = min(max(self._rescue_wait, RESCUE_WAIT_S) * 2, RESCUE_WAIT_MAX_S)
                result = (f"the Dot didn't answer on {name}; trying again in {self._rescue_wait // 60} min "
                          "(if it keeps happening, unplug the Dot for 10 seconds)")
                return result
            if serial != self.s["serial"]:
                log.warning("Dot rescue: the Echo on %s isn't the claimed Dot; leaving it alone", name)
                self._rescue_wait = RESCUE_WAIT_MAX_S
                result = "a different Echo answered on that network, so it was left alone"
                return result
            rc, out = await self._adb("-s", addr, "shell",
                                      "wpa_cli -i wlan0 enable_network all; wpa_cli -i wlan0 save_config",
                                      target=False, timeout=15)
            if rc == 0 and "FAIL" not in out:
                result = "ok"
                self._rescue_wait = RESCUE_WAIT_S
                self.store.put("dot_last_rescue", time.time())
                self.app.event("dot", f"{self.app.pet.name} rescued the Echo Dot from setup mode")
                self.app.pet.say("I WOKE THE DOT UP!", "proud", 20)
            return result
        finally:
            await self._adb("disconnect", addr, target=False, timeout=5)
            self.app._switching = False
            # home again: the network he was on, or the best one in range
            nets = [s for s, _ in config_networks(self.app.cfg)]
            if back in nets:
                ok, _ = await wifimod.connect_profile(wifimod.profile_name(nets.index(back)))
                if not ok:
                    await self.app.switch_to_best(reason="back from rescuing the Dot")
            else:
                await self.app.switch_to_best(reason="back from rescuing the Dot")
            self._last_scan = self._last_full = 0.0        # look for the Dot straight away
            self.rescuing = False
            self.state = "rescued the Dot; looking for it on the hotspot" if result == "ok" else f"rescue: {result}"
            log.info("Dot rescue: %s", result)

    async def release(self, restore=False):
        """Stop the player (ring off). With restore, also give the Dot back to Amazon."""
        if self.target:
            services = " ".join(re.sub(r"[^A-Za-z0-9_.-]", "", s) for s in self.cfg["stop_services"])
            if self.mic.proc and self.mic.proc.returncode is None:
                self.mic.proc.kill()
            cmd = (f"touch {H}/quit; tinymix '{AMP}' Off; pkill -f 'micgrab [k]eys'; pkill -f 'micgrab [s]tream'; "
                   f"pkill -f 'harald/[e]ars.py'")
            if restore:   # Amazon's mixer switches the amplifier on and keeps it fed
                cmd += (f"; sleep 1; tinymix 'PCM Playback Volume' 127 127; tinymix '{AMP}' On; "
                        f"for s in mixer ledcontroller {services}; do start $s; done")
            await self.sh(cmd, 15)
        self.connected = self.ready = False
        await self.voice.stop()

    async def forget(self):
        await self.release(restore=True)
        if self.target:
            await self._adb("disconnect", self.target, target=False, timeout=5)
        self.target = None
        self.s.update(serial="", model="", last_ip="")
        self.save()
        self.state = "forgotten; looking for a Dot"
        self._last_scan = self._last_full = 0.0
