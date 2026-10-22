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
    """Turns GPS fixes into a movement mode and distance per mode.

    Speed alone can't tell a bus or a tram from a walk: in town they spend much of the
    time pulling away from stops, slowing for them and crawling in traffic, at walking,
    running and cycling speeds. Two things sort that out:

      * Riding: once you've gone at least 9 m/s (32 km/h, faster than nearly anyone cycles
        or runs) for 10 seconds, you're in a vehicle, and everything slower counts as the
        vehicle too, until you're on your feet again. That's when the step counter sees
        steps, or, without one, after 90 seconds at walking pace with nothing faster.
      * The step counter, when it's linked: walking and running make steps, so walking or
        running speed with no steps (fewer than 15 in the last 45 seconds) is a vehicle
        crawling along, not you: but only within 3 minutes of vehicle speed (a bus in
        traffic). With the phone's screen off, many phones send their step count only every
        minute or so, so on a walk the steps can go quiet for a while; that alone isn't a ride.
      * And the other way round: a ride never starts while the step counter says you're
        walking (a burst of speed from GPS glitches between tall buildings, mid-walk).

    Indoors, a phone often can't hear the satellites and finds itself from Wi-Fi and mobile
    masts instead. Those positions jump tens or hundreds of meters at a time, and the phone
    reports the jumps as speed: a run of them looks just like a bus pulling away. So speed
    alone is never enough for the fast modes. Before he decides you're riding (or counts a
    quick burst as cycling), the position has to have really gone somewhere: over those
    seconds, the accurate fixes (better than 30 m) must have gone at least 70% as far as the
    speed says (a bus at 9 m/s goes about 90 m in 10 s), in a fairly straight line (at least
    80% as far in a straight line as along the way: a road bends, but wobble zigzags round the
    same spot), with most steps from one fix to the next about the length the speed says (a bus
    at 11 m/s moves about 11 m a second; wobble jumps 0 m, then 80, then 30). And every bit of
    distance, riding or not, only counts if its step is about the length the speed says.
    Better a little real distance missed than a ride that never happened.
    """

    WINDOW_S = 30
    GOOD_ACC_M = 30           # fixes this accurate (or better) show where you really went
    MOVED_SHARE = 0.7         # ...and must have moved at least this share of what the speed says,
    STRAIGHT = 0.8            # in a line at least this straight (straight-line distance / path length)
    MIN_FIXES = 5             # ...shown by at least this many accurate fixes in the VEHICLE_S,
    PROGRESS = 0.8            # ...nearly all of their steps (this share) the length the speed says,
    STEP_SLACK_M = 10         # ...give or take this much (or half the step, if more)
    VEHICLE_MS = 9.0          # sustained for VEHICLE_S: in a vehicle
    VEHICLE_S = 10
    OFF_AFTER_S = 90          # (no step counter) this long at walking pace: off the vehicle
    HOLD_S = 30               # stretches on foot or bike are held back this long, in case
                              # they turn out to be a vehicle pulling away
    CRAWL_S = 180             # walking pace with no steps is a vehicle only this soon after vehicle speed

    def __init__(self, feet=None):
        self.speeds = []          # (ts, m/s)
        self.mode = "still"
        self.last_pos = None      # (lat, lon, ts)
        self.pending = {}         # mode -> meters not yet handed out
        self.feet = feet          # () -> True/False from the step counter, or None without one
        self.riding = False       # in a vehicle (see above)
        self._held = []           # (ts, mode, meters): stretches on foot or bike, held back HOLD_S
        self._slow_since = None   # (no step counter) when walking pace began, while riding
        self._track = []          # (ts, lat, lon) of accurate fixes, the last VEHICLE_S or so
        self._fast_ts = None      # the last time the speed was a vehicle's (VEHICLE_MS or more)

    def _on_feet(self):
        try:
            return self.feet() if self.feet else None
        except Exception:
            return None

    def _fits(self, d, speed, dt):
        """A step of d meters in dt seconds is about what `speed` says (give or take jitter)."""
        want = speed * dt
        return abs(d - want) <= max(self.STEP_SLACK_M, 0.5 * want)

    def _went_somewhere(self, now, speed):
        """Did the accurate fixes of the last VEHICLE_S really travel at about `speed` (see above)?"""
        pts = [p for p in self._track if now - p[0] <= self.VEHICLE_S]
        if len(pts) < self.MIN_FIXES:          # (outdoors, a phone gives about one good fix a second)
            return False
        span = pts[-1][0] - pts[0][0]
        if span < self.VEHICLE_S / 2:
            return False
        net = _dist(pts[0][1:], pts[-1][1:])
        steps = [(_dist(a[1:], b[1:]), b[0] - a[0]) for a, b in zip(pts, pts[1:])]
        path = sum(d for d, _ in steps)
        if net < self.MOVED_SHARE * speed * span:     # far enough for the speed
            return False
        if net < self.STRAIGHT * path:                 # fairly straight: wobble zigzags
            return False
        fits = sum(1 for d, dt in steps if self._fits(d, speed, dt))
        return fits >= self.PROGRESS * len(steps)      # steady steps: wobble jumps 0 m, then 80, then 30

    def _update_riding(self, now, sp):
        recent = [s for t, s in self.speeds if now - t <= self.VEHICLE_S]
        span = (now - min(t for t, _ in self.speeds if now - t <= self.VEHICLE_S)) if recent else 0
        fast = len(recent) >= 3 and span >= self.VEHICLE_S - 2 and statistics.median(recent) >= self.VEHICLE_MS
        if fast and self.riding:                   # (already riding: keeps the ride going, as before)
            self._slow_since = None
            return
        # starting a ride needs the proof that the phone really went somewhere (see above), and
        # never while the step counter says you're walking
        if fast and self._on_feet() is not True and self._went_somewhere(now, statistics.median(recent)):
            if not self.riding:
                # it was a vehicle pulling away all along: the stretches still held count as the ride
                self.pending["vehicle"] = self.pending.get("vehicle", 0.0) + sum(d for _, _, d in self._held)
                self._held = []
            self.riding, self._slow_since = True, None
            return
        if not self.riding:
            return
        feet = self._on_feet()
        if feet:                                   # steps again: off the bus
            self.riding, self._slow_since = False, None
        elif feet is None and sp is not None:      # no step counter: a while at walking pace
            if 0.5 <= sp < 2.5:
                self._slow_since = self._slow_since or now
                if now - self._slow_since >= self.OFF_AFTER_S:
                    self.riding, self._slow_since = False, None
            elif sp >= 2.5:
                self._slow_since = None

    def _really(self, mode, now=None):
        """A mode from speed, corrected for riding and for the step counter."""
        if mode == "still":
            return mode
        if self.riding:
            return "vehicle"
        if (mode in ("walking", "running") and self._on_feet() is False and now is not None
                and self._fast_ts is not None and now - self._fast_ts <= self.CRAWL_S):
            return "vehicle"                       # (no steps, just after vehicle speed: a bus in traffic)
        return mode

    def feed(self, fix):
        now = fix["ts"]
        sp = fix.get("speed")
        if sp is not None:
            self.speeds.append((now, sp))
            if sp >= self.VEHICLE_MS:
                self._fast_ts = now
        self.speeds = [(t, s) for t, s in self.speeds if now - t <= self.WINDOW_S]
        if fix.get("acc", 10) <= self.GOOD_ACC_M:
            self._track.append((now, fix["lat"], fix["lon"]))
        self._track = [p for p in self._track if now - p[0] <= self.VEHICLE_S + 5]
        self._update_riding(now, sp)
        if len(self.speeds) >= 3:
            self.mode = self._really(classify(statistics.median(s for _, s in self.speeds)), now)
        pos = (fix["lat"], fix["lon"], now)
        if self.last_pos and now - self.last_pos[2] <= 15:
            d = _dist(self.last_pos, pos)
            # Each stretch is credited to how fast you were going right then (the smoothed
            # mode lags ~15 s behind, which would misfile the start of a drive as a walk);
            # readings under 0.5 m/s are GPS wander, not movement.
            raw = classify(sp) if sp is not None else self.mode
            seg_mode = self._really(raw, now)
            dt = now - self.last_pos[2]
            # (and the step has to be about as long as the speed says: indoors the position jumps
            # tens of meters while the phone barely moves, which is wobble, not distance)
            if (seg_mode != "still" and d < 60 * (dt + 1) and fix.get("acc", 10) < 30
                    and (sp is None or self._fits(d, sp, max(dt, 1)))):
                if sp is not None:                 # (and never more than the speed allows: jitter
                    d = min(d, sp * max(dt, 1))    # zigzagging along a road mustn't add distance)
                if raw == "vehicle" and not self.riding and sp is not None:
                    # a moment above cycling speed (a sprint, downhill) isn't a vehicle by itself:
                    # held as cycling, and it becomes the ride if the speed keeps up. Only if
                    # you really went somewhere at a cycling pace, though: a jump of the
                    # position indoors isn't a sprint
                    if self._went_somewhere(now, MODES[2][1]):
                        self._held.append((now, "cycling", d))
                elif seg_mode == "vehicle":
                    self.pending["vehicle"] = self.pending.get("vehicle", 0.0) + d
                else:
                    self._held.append((now, seg_mode, d))
        self.last_pos = pos
        self._release(now)

    def _release(self, now):
        """Hand out held stretches once they're HOLD_S old: by then a vehicle pulling away
        would have shown itself."""
        keep = []
        for t, mode, d in self._held:
            if now - t >= self.HOLD_S:
                self.pending[mode] = self.pending.get(mode, 0.0) + d
            else:
                keep.append((t, mode, d))
        self._held = keep

    def take(self, now=None):
        """Distance per mode since the last call (stretches on foot or by bike HOLD_S late)."""
        if now is not None:
            self._release(now)
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
        self.motion = Motion(feet=self.feet)
        self.trip = {}            # mode -> meters this adventure
        self.trip_start = None
        self.last_moving = 0.0
        self.live_steps = None    # step total at the last reading this session
        self._step_log = []       # (when, steps) this session, for on_foot()
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
        if self.live_steps is not None and total > self.live_steps:
            self._step_log.append((time.time(), total - self.live_steps))
            self._step_log = [(t, n) for t, n in self._step_log if time.time() - t <= self.ON_FOOT_S]
        self.live_steps = total
        now = time.time()
        if out or now - getattr(self, "_steps_saved", 0) > 30:  # don't write on every step
            self.store.put("steps_last", total)
            self._steps_saved = now
        return out

    def link_lost(self):
        self.live_steps = None

    ON_FOOT_S = 120
    ON_FOOT_STEPS = 40
    FEET_S = 45
    FEET_STEPS = 15

    def feet(self, now=None):
        """For telling a walk from a slow bus: True if the step counter saw at least 15
        steps in the last 45 seconds, False if not, None if there's no step counter."""
        if self.live_steps is None:
            return None
        now = now or time.time()
        return sum(n for t, n in self._step_log if now - t <= self.FEET_S) >= self.FEET_STEPS

    def on_foot(self, now=None):
        """Out walking (or running) right now, by the phone's step counter: at least 40 steps
        in the last 2 minutes. Picking the phone up, or a few steps across a room, isn't."""
        now = now or time.time()
        self._step_log = [(t, n) for t, n in self._step_log if now - t <= self.ON_FOOT_S]
        return sum(n for _, n in self._step_log) >= self.ON_FOOT_STEPS

    def moving_mode(self, now=None):
        """How he's moving, for climbing: the GPS's walking, running or cycling, or "walking"
        if the step counter says so; anything else (still, or in a vehicle) isn't climbing."""
        m = self.motion.mode
        if m in ("walking", "running", "cycling", "vehicle"):
            return m
        return "walking" if self.on_foot(now) else "still"

    # -- GPS
    def take_motion(self):
        """Distances since the last call; also tracks when an adventure starts and ends."""
        self._roll_day()
        got = self.motion.take(time.time())
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
