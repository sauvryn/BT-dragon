"""
The radio stick (untested): an RTL-SDR, a TV-tuner USB stick that can listen to a wide range
of radio, from about 25 MHz to 1.7 GHz. It's one radio, so it can listen to one thing at a
time: planes (1090 MHz, through rtl_adsb) or the little radios around homes (433 and 868 MHz,
or 433 and 915 MHz in the Americas, through rtl_433). With both on, it takes turns, five
minutes each.

It only ever listens: an RTL-SDR can't transmit at all.

Both programs come from Debian (the packages rtl-sdr and rtl-433, which the installer adds).
On a Pi Zero 2 W, rtl_adsb uses a fair share of the processor while it runs.
"""
import asyncio
import logging
import shutil
import time

log = logging.getLogger("rtlsdr")

MODES = ("both", "planes", "sensors", "off")
MODE_NAMES = {"both": "Planes and little radios, taking turns", "planes": "Planes only",
              "sensors": "Little radios only", "off": "Off"}
TURN_S = 300
NO_STICK = ("No supported devices", "usb_open error", "Failed to open rtlsdr", "No RTL-SDR")


def sensor_command(region):
    """rtl_433, hopping between 433.92 MHz and the region's other band every 30 seconds."""
    other = "915M" if region in ("US", "CA", "MX") else "868.3M"
    return ["rtl_433", "-F", "json", "-M", "level", "-f", "433.92M", "-f", other, "-H", "30"]


class RadioStick:
    def __init__(self, store, on_line, region=lambda: ""):
        self.store = store
        self.on_line = on_line              # on_line("planes" | "sensors", text)
        self.region = region                # the Lair's country code (for 868 or 915 MHz)
        self.mode = store.get("radio_mode") or "both"
        self.listening = None               # "planes" / "sensors" / None
        self.status = "Not started yet"
        self.found = None                   # True once a stick has answered; False if none
        self.since = 0.0

    def set_mode(self, mode):
        if mode not in MODES:
            return f"say one of: {', '.join(MODES)}"
        self.mode = mode
        self.store.put("radio_mode", mode)
        return None

    def installed(self):
        return {"planes": bool(shutil.which("rtl_adsb")), "sensors": bool(shutil.which("rtl_433"))}

    async def run(self, stop):
        while not stop.is_set():
            mode = self.mode
            have = self.installed()
            wanted = [w for w in (("planes", "sensors") if mode == "both" else (mode,)) if w in have and have[w]]
            if mode == "off":
                self.status, self.listening = "Off", None
            elif not wanted:
                self.status, self.listening = "The radio stick's programs aren't installed yet (see the README)", None
            for what in wanted:
                if stop.is_set() or self.mode != mode:
                    break
                ok = await self._listen(what, TURN_S if len(wanted) > 1 else 3600, stop, mode)
                if not ok:
                    self.found = False
                    self.status, self.listening = "No radio stick found: plug one in (checked every minute)", None
                    break
            if stop.is_set():
                break
            if self.listening is None:
                try:
                    await asyncio.wait_for(stop.wait(), 60 if mode != "off" else 5)
                except asyncio.TimeoutError:
                    pass

    async def _listen(self, what, seconds, stop, mode):
        """Run one program for a turn. False if there's no stick."""
        cmd = ["rtl_adsb"] if what == "planes" else sensor_command(self.region())
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.PIPE)
        except OSError as e:
            log.warning("couldn't start %s: %s", cmd[0], e)
            return True
        self.listening, self.since = what, time.time()
        self.status = ("Listening for planes on 1090 MHz" if what == "planes"
                       else "Listening for little radios on " + ("433 and 915 MHz" if "915M" in cmd else "433 and 868 MHz"))
        end = time.monotonic() + seconds
        heard = 0
        try:
            while time.monotonic() < end and not stop.is_set() and self.mode == mode:
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), 2)
                except asyncio.TimeoutError:
                    continue
                if not line:
                    break                   # the program stopped
                heard += 1
                self.found = True
                try:
                    self.on_line(what, line.decode(errors="replace").strip())
                except Exception as e:
                    log.warning("radio stick: %s", e)
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), 5)
                except asyncio.TimeoutError:
                    proc.kill()
            err = b""
            try:
                err = await asyncio.wait_for(proc.stderr.read(), 2)
            except Exception:
                pass
            self.listening = None
        text = err.decode(errors="replace")
        if any(x in text for x in NO_STICK) or (not heard and time.monotonic() < end - seconds + 5
                                                and proc.returncode not in (None, 0, -15)):
            return False
        return True

    def lines(self):
        """For the Den."""
        return [f"mode={self.mode}", f"status={self.status}", f"listening={self.listening or ''}",
                f"found={'' if self.found is None else int(self.found)}"]
