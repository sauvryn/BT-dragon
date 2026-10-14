"""
Your physical activity, as Harald sees it.

Two sources, both from your phone over the hotspot:

1. GPS speed (already arriving for wardriving). Every RMC sentence carries "speed over
   ground", which the GPS chip measures from the Doppler shift of the satellite signals
   rather than by comparing positions, so it's fairly accurate even at walking pace. Raw
   readings still wobble by about half a meter per second, so Harald takes the median of
   the last 30 seconds before deciding how you're moving:
       still < 0.5 m/s < walking < 2.5 < running < 4.5 < cycling < 8 < vehicle
   Distance is added up from the positions, and only while you're actually moving, so
   GPS wander while you stand still doesn't count as a walk.

2. Steps, from the phone's step-counter chip via the free "Sensor Server" app. Android's
   step counter is a running total since the phone last restarted, so Harald remembers the
   last total he saw. When he next hears from the phone, any steps in between happened
   without him: that's a story you tell him. Steps counted while he's along are part of
   the adventure (used for distance when there's no GPS fix, e.g. indoors).

Sensor Server speaks WebSocket. Rather than add a library, this file includes a minimal
WebSocket client: an HTTP "Upgrade" handshake, then small binary frames, each with a
2-14 byte header (opcode, length, and a 4-byte mask that clients must apply to what they
send).
"""
import asyncio
import base64
import json
import logging
import math
import os
import statistics
import struct
import time

log = logging.getLogger("activity")

MODES = (("still", 0.5), ("walking", 2.5), ("running", 4.5), ("cycling", 8.0), ("vehicle", 1e9))


def classify(speed):
    for name, upper in MODES:
        if speed < upper:
            return name
    return "vehicle"


def _dist(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class Motion:
    """Turns GPS fixes into a movement mode and distance per mode."""

    WINDOW_S = 30

    def __init__(self):
        self.speeds = []          # (ts, m/s)
        self.mode = "still"
        self.last_pos = None      # (lat, lon, ts)
        self.pending = {}         # mode -> meters not yet handed out

    def feed(self, fix):
        now = fix["ts"]
        sp = fix.get("speed")
        if sp is not None:
            self.speeds.append((now, sp))
        self.speeds = [(t, s) for t, s in self.speeds if now - t <= self.WINDOW_S]
        if len(self.speeds) >= 3:
            self.mode = classify(statistics.median(s for _, s in self.speeds))
        pos = (fix["lat"], fix["lon"], now)
        if self.last_pos and now - self.last_pos[2] <= 15:
            d = _dist(self.last_pos, pos)
            # Each stretch is credited to how fast you were going right then (the smoothed
            # mode lags ~15 s behind, which would misfile the start of a drive as a walk);
            # readings under 0.5 m/s are GPS wander, not movement.
            seg_mode = classify(sp) if sp is not None else self.mode
            if seg_mode != "still" and d < 60 * (now - self.last_pos[2] + 1) and fix.get("acc", 10) < 30:
                self.pending[seg_mode] = self.pending.get(seg_mode, 0.0) + d
        self.last_pos = pos

    def take(self):
        """Distance per mode since the last call."""
        out, self.pending = self.pending, {}
        return out


class SensorLink:
    """Reads one of the phone's sensors from the SensorServer app, over a WebSocket."""

    SENSOR = ""
    NAME = "sensor"

    def __init__(self, on_values, on_lost=None, sensor=None, name=None):
        self.on_values = on_values  # callback(list of floats), once per reading
        self.on_lost = on_lost
        self.sensor = sensor or self.SENSOR
        self.name = name or self.NAME
        self.connected = False

    async def run(self, host_fn, port, stop):
        while not stop.is_set():
            host = host_fn()
            if host:
                try:
                    await self._session(host, port, stop)
                except (OSError, asyncio.TimeoutError, ValueError, ConnectionError,
                        asyncio.IncompleteReadError) as e:
                    log.debug("%s link: %s", self.name, e)
                if self.connected and self.on_lost:
                    self.on_lost()
                self.connected = False
            try:
                await asyncio.wait_for(stop.wait(), 20)
            except asyncio.TimeoutError:
                pass

    async def _session(self, host, port, stop):
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 5)
        try:
            key = base64.b64encode(os.urandom(16)).decode()
            path = f"/sensor/connect?type={self.sensor}"
            writer.write((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                          f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                          f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
            await writer.drain()
            status = await asyncio.wait_for(reader.readline(), 5)
            if b" 101 " not in status:
                raise ValueError(f"no websocket: {status!r}")
            while (await asyncio.wait_for(reader.readline(), 5)) not in (b"\r\n", b""):
                pass
            self.connected = True
            log.info("%s linked via %s:%d", self.name, host, port)
            while not stop.is_set():
                op, payload = await asyncio.wait_for(read_frame(reader), 120)
                if op == 0x8:          # close
                    return
                if op == 0x9:          # ping -> pong
                    writer.write(make_frame(0xA, payload))
                    await writer.drain()
                elif op in (0x1, 0x2):
                    msg = json.loads(payload.decode())
                    vals = msg.get("values") or []
                    if vals:
                        self.on_values(vals)
        finally:
            writer.close()


class StepLink(SensorLink):
    """The phone's step counter (total steps since the phone last booted)."""

    SENSOR = "android.sensor.step_counter"
    NAME = "step counter"

    def __init__(self, on_steps, on_lost=None):
        super().__init__(lambda vals: on_steps(int(vals[0])), on_lost)


class PressureLink(SensorLink):
    """The phone's barometer: air pressure in hPa."""

    SENSOR = "android.sensor.pressure"
    NAME = "barometer"


class LightLink(SensorLink):
    """The phone's light sensor (the one that dims the screen): brightness in lux."""

    SENSOR = "android.sensor.light"
    NAME = "light sensor"


async def read_frame(reader):
    h = await reader.readexactly(2)
    op = h[0] & 0x0F
    masked = h[1] & 0x80
    n = h[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", await reader.readexactly(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", await reader.readexactly(8))[0]
    if n > 1 << 20:
        raise ValueError("frame too large")
    mask = await reader.readexactly(4) if masked else None
    data = await reader.readexactly(n)
    if mask:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return op, data


def make_frame(op, payload=b""):
    """A client-to-server frame (clients must mask)."""
    mask = os.urandom(4)
    n = len(payload)
    head = bytes([0x80 | op])
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class Activity:
    """Keeps the books: adventures (with Harald) and stories (without him)."""

    STRIDE_M = 0.75
    END_AFTER_S = 180     # an adventure ends after 3 minutes of standing still
    MIN_ADVENTURE_M = 200
    MIN_STORY_STEPS = 200
    RESUME_S = 600        # back within 10 minutes: the same walk carries on

    def __init__(self, store, stride_m=STRIDE_M):
        self.store = store
        self.stride = stride_m
        self.motion = Motion()
        self.trip = {}            # mode -> meters this adventure
        self.trip_start = None
        self.last_moving = 0.0
        self.live_steps = None    # step total at the last reading this session
        self.today = store.get("activity_today", {"date": "", "walked": 0.0, "rode": 0.0, "told": 0.0})
        self.last_trip = None     # (start, end) of the trip finished_trip() last handed out
        self._trip_saved = 0.0
        # a walk in progress survives a restart (of him, or of the Pi) if he's back soon
        t = store.get("trip_now") or {}
        if t.get("start") and time.time() - t.get("last_moving", 0) < self.RESUME_S:
            self.trip, self.trip_start, self.last_moving = dict(t.get("trip") or {}), t["start"], t["last_moving"]

    def _roll_day(self):
        d = time.strftime("%Y-%m-%d")
        if self.today.get("date") != d:
            self.today = {"date": d, "walked": 0.0, "rode": 0.0, "told": 0.0}

    def save(self):
        self.store.put("activity_today", self.today)
        if self.live_steps is not None:
            self.store.put("steps_last", self.live_steps)

    # -- steps
    def steps(self, total, gps_fix_live):
        """
        A step-counter reading. Returns ("story", steps) for steps taken without Harald,
        or ("walk", meters) for steps taken with him when GPS can't measure the walk.
        """
        self._roll_day()
        out = None
        if self.live_steps is None:
            # first reading since Harald woke or the phone reconnected
            last = self.store.get("steps_last")
            if last is not None and total >= last and total - last >= self.MIN_STORY_STEPS:
                n = total - last
                self.today["told"] += n * self.stride
                out = ("story", n)
        elif total > self.live_steps and not gps_fix_live:
            out = ("walk", (total - self.live_steps) * self.stride)
        self.live_steps = total
        now = time.time()
        if out or now - getattr(self, "_steps_saved", 0) > 30:  # don't write on every step
            self.store.put("steps_last", total)
            self._steps_saved = now
        return out

    def link_lost(self):
        self.live_steps = None

    # -- GPS
    def take_motion(self):
        """Distances since the last call; also tracks when an adventure starts and ends."""
        self._roll_day()
        got = self.motion.take()
        now = time.time()
        if self.motion.mode != "still":
            self.last_moving = now
            if self.trip_start is None:
                self.trip_start = now
        for mode, m in got.items():
            self.add(mode, m)
        if self.trip_start and now - self._trip_saved > 60:     # once a minute while out
            self._trip_saved = now
            self.store.put("trip_now", {"start": self.trip_start, "last_moving": self.last_moving, "trip": self.trip})
        return got

    def trip_now(self):
        """The walk in progress: {kind, meters (on foot or bike), seconds, start}, or None."""
        if not self.trip_start:
            return None
        return trip_summary(self.trip, self.trip_start, max(self.last_moving, self.trip_start))

    def add(self, mode, meters):
        if self.trip_start is None:
            self.trip_start = time.time()
        self.last_moving = time.time()
        self.trip[mode] = self.trip.get(mode, 0.0) + meters
        if mode in ("walking", "running", "cycling"):
            self.today["walked"] += meters
        else:
            self.today["rode"] += meters

    def finished_trip(self):
        """Returns the trip dict once you've been still for a while after moving."""
        if self.trip_start and time.time() - self.last_moving > self.END_AFTER_S:
            self.last_trip = (self.trip_start, self.last_moving)
            trip, self.trip, self.trip_start = self.trip, {}, None
            self.store.put("trip_now", {})
            return trip
        return None


KINDS = {"walking": ("walk", "Walk"), "running": ("run", "Run"), "cycling": ("ride", "Bike ride")}


def trip_summary(trip, start, end):
    """What kind of outing it was (whichever of walking, running and cycling covered the
    most ground), how far under your own steam, and how long it took."""
    own = {k: trip.get(k, 0.0) for k in KINDS}
    main = max(own, key=own.get)
    return {"kind": KINDS[main][0], "label": KINDS[main][1], "meters": sum(own.values()),
            "seconds": max(0.0, end - start), "start": start, "vehicle": trip.get("vehicle", 0.0)}


def km_mi(m):
    """'4.57 km (2.84 mi)'"""
    return f"{m / 1000:.2f} km ({m / 1609.344:.2f} mi)"


def duration_words(seconds, short=False):
    """'1 h 24 min' (short) or '1 hour and 24 minutes'."""
    mins = int(round(seconds / 60))
    h, m = divmod(mins, 60)
    if short:
        return f"{h} h {m} min" if h else f"{m} min"
    hp = f"{h} hour{'s' if h != 1 else ''}"
    mp = f"{m} minute{'s' if m != 1 else ''}"
    return f"{hp} and {mp}" if h and m else hp if h else mp


def exercise_line(summary):
    """For the diary: 'Walk: 4.57 km (2.84 mi) in 1 h 24 min, from 15:20'."""
    return (f"{summary['label']}: {km_mi(summary['meters'])} in {duration_words(summary['seconds'], True)}, "
            f"from {time.strftime('%H:%M', time.localtime(summary['start']))}")


def describe_km(m):
    return f"{m / 1000:.1f} KM" if m >= 100 else f"{int(m)} M"
