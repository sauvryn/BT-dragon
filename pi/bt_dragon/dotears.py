"""
Listening on the Echo Dot itself: the Pi's side.

When the Dot has its own small Debian (dot_debian/build.sh and push.sh put it there), a
little program on the Dot (dot_debian/ears.py) reads the buttons, records questions and
turns them into words with Vosk. Sound never leaves the Dot; only words come over the
hotspot, on a plain network connection (port 5577) that needs a key only the Pi and the
Dot have. The fragile debug connection (adb) is only used to start it.

Without that Debian, nothing changes: the Pi records through adb and listens itself.
"""
import asyncio
import json
import logging
import os
import secrets
import shutil
import time

log = logging.getLogger("dotears")

PORT = 5577
LOCAL_PORT = 15577                   # on the Pi, when going through adb instead
LOST_KEEP_S = 30 * 60                # how long to keep trying the ears after the debug link is lost
D = "/data/local/tmp/deb"            # the Dot's Debian and its tools
HERE = os.path.dirname(os.path.abspath(__file__))


class DotEars:
    def __init__(self, dot):
        self.dot = dot
        self.installed = False       # the Dot has its Debian
        self.connected = False       # talking to the ears on the Dot right now
        self.ready = False           # ...and its speech model is loaded
        self.state = ""              # a few words for the den
        self.last_up = 0.0           # when they were last connected (or started)
        self.task = None
        self.ip = ""                 # the Dot's address on the hotspot, for the ears' own line
        self._writer = None
        self._pending = {}
        self._seq = 0
        self.via_adb = False         # the direct connection is blocked: going through adb
        self.voice = False           # the Dot can make Harald's speech itself (Piper is there)
        self.wake_state = {}         # the wake word on the Dot: active, heard, cpu, error
        self._wake_sent = None
        key = dot.store.get("dot_ears_key")
        if not key:
            key = secrets.token_hex(16)
            dot.store.put("dot_ears_key", key)
        self.key = key

    @property
    def handles_keys(self):
        """The Dot's ears read the buttons (or will again in a moment)."""
        return self.installed and (self.connected or time.time() - self.last_up < 45)

    def stage(self, stage_dir):
        """Put the Dot's half (and the key) with the files copied to the Dot."""
        shutil.copyfile(os.path.join(HERE, "dot_debian", "ears.py"), os.path.join(stage_dir, "ears.py"))
        with open(os.path.join(stage_dir, "ears.key"), "w", newline="\n") as f:
            f.write(self.key + "\n")

    # ------------------------------------------------------------ starting
    async def start(self):
        """When the Dot is set up: start its ears if it has the Debian. True if they're in use."""
        d = self.dot
        out = await d.sh(f"[ -x {D}/root/usr/bin/python3 ] && [ -x {D}/busybox ] && echo YES", 10)
        self.installed = bool(out and "YES" in out)
        if not self.installed:
            self.state = ""
            return False
        await d._adb("push", os.path.join(HERE, "dot_debian", "enter.sh"), f"{D}/enter.sh", timeout=20)
        # the speaker model (13 MB, for voice profiles): copied over once, if the Pi has it
        spk = "/opt/bt-dragon/vosk-spk"
        if os.path.isdir(spk):
            have = await d.sh(f"[ -d {D}/root/opt/vosk-spk ] && echo YES", 10)
            if not (have and "YES" in have):
                log.info("copying the speaker model to the Dot")
                rc, out = await d._adb("push", spk, f"{D}/root/opt/vosk-spk.new", timeout=300)
                if rc == 0:
                    await d.sh(f"rm -rf {D}/root/opt/vosk-spk; mv {D}/root/opt/vosk-spk.new {D}/root/opt/vosk-spk", 20)
        self.via_adb = False
        self.ip = (d.target or "").split(":")[0]
        await self.restart()
        if self.task is None or self.task.done():
            self.task = asyncio.ensure_future(self.run())
        return True

    async def restart(self):
        """(Re)start the ears on the Dot, fresh, so the newest version runs."""
        self.state = "starting on the Dot"
        self.last_up = time.time()
        # Stopping the old one has to be a command of its own: `pkill -f` matches whole
        # command lines, and the shell starting the new one has "harald/ears.py" in its own,
        # so it would stop itself before getting that far.
        await self.dot.sh(f"sed -i 's/\\r$//' {D}/enter.sh; pkill -f 'harald/[e]ars.py'; sleep 1", 15)
        # Fire OS has a firewall: let the Pi (only the Pi) reach the ears' port. The rule is
        # forgotten when the Dot restarts, and put back each time Harald sets it up.
        me = await asyncio.to_thread(self.dot._my_network)
        src = f"-s {me.ip} " if me else ""
        for chain, rule in (("INPUT", f"-p tcp {src}--dport {PORT} -j ACCEPT"),
                            ("OUTPUT", f"-p tcp {src.replace('-s', '-d')}--sport {PORT} -j ACCEPT")):
            await self.dot.sh(f"iptables -C {chain} {rule} 2>/dev/null || iptables -I {chain} {rule}", 10)
        from . import voice as voicemod
        model = voicemod.find_voice(self.dot.cfg["voice"])          # the same voice as on the Pi
        name = os.path.basename(model)[:-5] if model else ""
        name = "".join(c for c in name if c.isalnum() or c in "_-.")
        run = f"sh {D}/enter.sh python3 -u /harald/ears.py --port {PORT}" + (f" --voice {name}" if name else "")
        await self.dot.sh(
            f"cd /; if command -v setsid >/dev/null; then setsid {run}; else nohup {run}; fi "
            f"</dev/null >{D}/ears.log 2>&1 &", 15)

    async def stop(self):
        if self.installed:
            await self.dot.sh("pkill -f 'harald/[e]ars.py'", 10)
        if self.via_adb:
            await self.dot._adb("forward", "--remove", f"tcp:{LOCAL_PORT}", timeout=10)
        if self._writer:
            self._writer.close()

    # ------------------------------------------------------------ the connection
    def keep_going(self):
        """Keep (re)connecting to the ears? While the Dot is connected, and also for a while
        after the debug link (adb) is lost: the ears have a line of their own, so they may
        well still be there, and they can mend the debug link (fix_adb)."""
        d = self.dot
        if d.app.stop.is_set() or getattr(d.app, "napping", False) or not d.s["enabled"]:
            return False
        if d.connected:
            return True
        return bool(self.ip) and not self.via_adb and d._lost_at is not None \
            and time.time() - d._lost_at < LOST_KEEP_S

    async def fix_adb(self):
        """Ask the ears to restart the Dot's adbd. The reply, or None."""
        return await self._request({"cmd": "fix_adb"}, 15)

    async def run(self):
        d = self.dot
        fails = 0
        while self.keep_going():
            ip, port = self.ip or (d.target or "").split(":")[0], PORT
            if not self.via_adb and fails >= 3:
                # can't get through directly (a firewall?): the same connection can go
                # through adb instead, which already reaches the Dot. Only words travel on it.
                rc, out = await d._adb("forward", f"tcp:{LOCAL_PORT}", f"tcp:{PORT}", timeout=10)
                if rc == 0:
                    log.info("the Dot's ears: going through adb")
                    self.via_adb = True
            if self.via_adb:
                await d._adb("forward", f"tcp:{LOCAL_PORT}", f"tcp:{PORT}", timeout=10)
                ip, port = "127.0.0.1", LOCAL_PORT
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), 5)
            except (OSError, asyncio.TimeoutError):
                fails += 1
                if fails >= 6:
                    self.state = "the ears on the Dot aren't answering; trying again"
                if fails % 12 == 0 and d.connected:   # about a minute: start them again (needs adb)
                    await self.restart()
                await d.app._sleep(5)
                continue
            pinger = None
            try:
                writer.write((json.dumps({"hello": self.key}) + "\n").encode())
                from . import ask
                writer.write((json.dumps({"cmd": "vocab", "words": ask.GRAMMAR}) + "\n").encode())
                await writer.drain()
                first = json.loads(await asyncio.wait_for(reader.readline(), 10) or b"{}")
                if first.get("hello") != "ok":
                    raise ConnectionError("no answer from the ears" if not first else "the Dot turned the key down")
                fails = 0
                self.connected, self._writer = True, writer
                self._wake_sent = None           # tell it again what's wanted
                self.ready = bool(first.get("ready"))
                self.voice = bool(first.get("voice"))
                self._message({})
                self.last_up = time.time()
                log.info("talking to the ears on the Dot")
                pinger = asyncio.ensure_future(self._ping(writer))
                while True:
                    line = await asyncio.wait_for(reader.readline(), 60)
                    if not line or not self.keep_going():
                        break
                    self.last_up = time.time()
                    try:
                        self._message(json.loads(line))
                    except ValueError:
                        pass
            except (OSError, asyncio.TimeoutError, ValueError, ConnectionError) as e:
                log.info("the Dot's ears: %s", e or type(e).__name__)
                if not self.connected:          # never got as far as hello
                    fails += 1
                    if fails % 12 == 0 and d.connected:
                        await self.restart()
            finally:
                if pinger:
                    pinger.cancel()
                self.connected, self.ready, self._writer, self.voice = False, False, None, False
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_result(None)
                self._pending.clear()
                writer.close()
            await d.app._sleep(3)
        self.connected = False

    async def _ping(self, writer):
        while True:
            await asyncio.sleep(20)
            writer.write(b'{"cmd": "ping"}\n')
            await writer.drain()

    def _message(self, msg):
        if "line" in msg:
            self.dot.on_key(str(msg["line"]))
        if "wake_state" in msg:
            self.wake_state = msg["wake_state"] or {}
        if msg.get("wake"):
            self.dot.on_wake()
        if "ready" in msg:
            self.ready = bool(msg["ready"])
        if msg.get("id") in self._pending:
            fut = self._pending.pop(msg["id"])
            if not fut.done():
                fut.set_result(msg)
        self.state = ("listening on the Dot" if self.ready else "loading the speech model on the Dot") \
            + (" (through the debug link: the Dot's firewall blocks the direct way)" if self.via_adb else "")

    async def _send(self, msg):
        if self.connected and self._writer:
            try:
                self._writer.write((json.dumps(msg) + "\n").encode())
                await asyncio.wait_for(self._writer.drain(), 5)
            except asyncio.TimeoutError:          # the Dot's gone without saying goodbye
                log.info("the Dot's ears stopped taking messages; reconnecting")
                self._writer.close()
            except OSError:
                pass

    async def set_wake(self, on, strict=50):
        """Listen for "hey dragon" on the Dot, or stop, and how strict to be about it
        (only tells it when something changed)."""
        if self.connected and (on, strict) != self._wake_sent:
            self._wake_sent = (on, strict)
            await self._send({"cmd": "wake", "on": on, "strict": strict})

    async def busy(self, on):
        """He's talking (so the Dot doesn't hear him say "dragon"), or finished."""
        await self._send({"cmd": "busy", "on": on})

    async def _request(self, req, timeout):
        """Send a request; wait for the reply with the same id. None if it never came."""
        if not (self.connected and self._writer):
            return None
        self._seq += 1
        n = req["id"] = self._seq
        fut = asyncio.get_running_loop().create_future()
        self._pending[n] = fut
        try:
            self._writer.write((json.dumps(req) + "\n").encode())
            await self._writer.drain()
            return await asyncio.wait_for(fut, timeout)
        except (OSError, asyncio.TimeoutError):
            return None
        finally:
            self._pending.pop(n, None)

    # ------------------------------------------------------------ speaking
    async def say(self, text, speed=1.0, pitch=0.0, volume=0.9, lead=0.0, tail=0.0, file="say.wav"):
        """Have the Dot make `text` into speech, ready to play as /data/local/tmp/harald/<file>.
        Returns {"ok": True, "speech_s": .., "tts_s": ..}, or None/ok False if it couldn't."""
        if not self.voice:
            return None
        return await self._request({"cmd": "say", "text": text, "speed": speed, "pitch": pitch,
                                    "volume": volume, "lead": lead, "tail": tail, "file": file}, 90)

    # ------------------------------------------------------------ questions
    async def hear(self, max_s=8, words=None, free_if=None, free=False, pre_s=0.0):
        """Record on the Dot until the speaker stops, and recognize it there. Returns
        {"speech": bool, "text": str, "rec_s": .., "stt_s": ..}, or None if the Dot's ears
        dropped out."""
        req = {"cmd": "hear", "max_s": max_s}
        if words:
            req["words"] = list(words)
        if free_if:
            req["free_if"] = free_if
        if free:
            req["free"] = True          # every word Vosk knows (a name, say), not the list
        if pre_s:
            req["pre_s"] = pre_s        # after the wake word: include the moment before
        return await self._request(req, max_s + 60)
