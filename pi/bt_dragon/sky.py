"""
Things Harald can find with the help of your phone's sensors, besides gadgets and networks:

  * New land (GPS). The world is cut into squares about 250 m across ("lands"), grouped
    into squares about 1 km across ("realms"). He claims the square he's in, and any
    neighboring square you pass close to (about 40 m from its edge), so a square on the
    other side of a fence or wall is claimed from the street: there's never a reason to
    go onto private land. The squares are big for the same reason: nearly every one has a
    public road or path somewhere in it.
    The list of claimed squares stays on the Pi (it's a rough map of where you've taken
    him); the den can forget it.

  * Stars (GPS satellites). Phones report every navigation satellite they can hear in
    NMEA "GSV" lines (satellites in view): its number, height in the sky and signal
    strength. The two letters at the start say which system it belongs to:
      GP GPS (USA)   GL GLONASS (Russia)   GA Galileo (EU)   GB/BD BeiDou (China)
      GQ QZSS (Japan)   GI NavIC (India)   and SBAS helpers (WAAS, EGNOS...) inside GP.
    Only a satellite actually being received (signal strength reported) counts; one the
    phone merely expects to be there doesn't. SensorServer doesn't pass these lines on;
    GPSd Forwarder and GPS2IP do.

  * Weather and climbing (barometer). Air pressure falls about 0.12 hPa for every meter you
    go up, so quick changes over a minute or two are you climbing (stairs, hills), while
    slow changes over hours are the weather: a fall of 3 hPa or more in 3 hours usually
    means wind and rain on the way, a rise that fast means a change to calmer weather.
    To tell the two apart, the weather is only judged over stretches where you've stayed
    in roughly the same place.
"""
import math
import time
from collections import deque

from . import tuning

# ---------------------------------------------------------------- new land

METERS_PER_DEG_LAT = 111320.0


def grid_cell(lat, lon, size_m):
    """The square of about size_m x size_m that a position falls in, as 'row:col'.

    Rows are a fixed slice of latitude. A degree of longitude gets narrower toward the
    poles (it shrinks with the cosine of the latitude), so each row's columns are widened
    by 1/cos(latitude of that row) to keep the squares roughly square."""
    dlat = size_m / METERS_PER_DEG_LAT
    row = math.floor(lat / dlat)
    row_lat = (row + 0.5) * dlat
    dlon = size_m / (METERS_PER_DEG_LAT * max(0.01, math.cos(math.radians(row_lat))))
    col = math.floor(lon / dlon)
    return f"{row}:{col}"


def cell_bounds(cell, size_m):
    """The [south, west, north, east] edges of a grid_cell(), in degrees."""
    row, col = (int(x) for x in cell.split(":"))
    dlat = size_m / METERS_PER_DEG_LAT
    row_lat = (row + 0.5) * dlat
    dlon = size_m / (METERS_PER_DEG_LAT * max(0.01, math.cos(math.radians(row_lat))))
    return [round(row * dlat, 6), round(col * dlon, 6), round((row + 1) * dlat, 6), round((col + 1) * dlon, 6)]


LAND_M = 250
REALM_M = 1000
OLD_LAND_SIZES = (100,)   # earlier versions used smaller squares; see Lands.migrate


def cell_center(cell, size_m):
    s, w, n, e = cell_bounds(cell, size_m)
    return (s + n) / 2, (w + e) / 2


def offset(lat, lon, dist_m, bearing_deg):
    """A point dist_m away from (lat, lon) in the given compass direction (flat-earth
    approximation, which is plenty over a few dozen meters)."""
    b = math.radians(bearing_deg)
    dlat = dist_m * math.cos(b) / METERS_PER_DEG_LAT
    dlon = dist_m * math.sin(b) / (METERS_PER_DEG_LAT * max(0.01, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


class Lands:
    def __init__(self, store):
        self.store = store
        self.migrate()

    def migrate(self):
        """Squares claimed with an older, smaller grid become the new square their center
        falls in, so nothing already explored is lost."""
        size = self.store.get("land_grid", None)
        if size == LAND_M:
            return
        rows = self.store.lands_all()
        if rows and size is None:
            size = OLD_LAND_SIZES[0]
        if rows:
            old = [(c, size) for c, _ in rows]
            self.store.forget_lands()
            for cell, sz in old:
                lat, lon = cell_center(cell, sz)
                self.store.land_seen(grid_cell(lat, lon, LAND_M), grid_cell(lat, lon, REALM_M), time.time())
        self.store.put("land_grid", LAND_M)

    def visit(self, fix):
        """A GPS fix. Returns a list of (new_realm,) for every square newly claimed (often
        empty), or None if the fix isn't precise enough to count."""
        wifi = fix.get("via") == "wifi"
        if fix.get("acc", 99) > tuning.get("land_wifi_accuracy_m" if wifi else "land_accuracy_m"):
            return None
        lat, lon = fix["lat"], fix["lon"]
        here = grid_cell(lat, lon, LAND_M)
        cells = {here}
        # a Wi-Fi position is too rough to tell you're passing a square's edge: just the one you're in
        reach = 0 if wifi else tuning.get("land_reach_m")
        if reach > 0:
            # Look a reach's distance away in 16 directions: any other square those points
            # land in is one whose edge you're passing close to.
            for i in range(16):
                cells.add(grid_cell(*offset(lat, lon, reach, i * 22.5), LAND_M))
        claimed = []
        for cell in sorted(cells, key=lambda c: c != here):
            clat, clon = cell_center(cell, LAND_M)
            new_land, new_realm = self.store.land_seen(cell, grid_cell(clat, clon, REALM_M), time.time())
            if new_land:
                claimed.append(new_realm)
        return claimed


# ---------------------------------------------------------------- stars

TALKERS = {"GP": "GPS", "GL": "GLONASS", "GA": "Galileo", "GB": "BeiDou", "BD": "BeiDou",
           "GQ": "QZSS", "QZ": "QZSS", "GI": "NavIC", "IR": "NavIC"}
CONSTELLATIONS = ("GPS", "GLONASS", "Galileo", "BeiDou", "QZSS", "NavIC", "SBAS")


def constellation(talker, prn):
    """Which system a satellite belongs to, from the sentence's talker ID and its number."""
    if talker == "GP" and (33 <= prn <= 64 or 120 <= prn <= 158):
        return "SBAS"     # WAAS, EGNOS & co: correction satellites, reported alongside GPS
    if talker == "GN":    # "any system": fall back on the usual NMEA number ranges
        if 1 <= prn <= 32:
            return "GPS"
        if 33 <= prn <= 64 or 120 <= prn <= 158:
            return "SBAS"
        if 65 <= prn <= 96:
            return "GLONASS"
        if 193 <= prn <= 200:
            return "QZSS"
        if 201 <= prn <= 263 or 401 <= prn <= 463:
            return "BeiDou"
        if 301 <= prn <= 336:
            return "Galileo"
        return None
    return TALKERS.get(talker)


class Stars:
    """
    The first time he hears a satellite, it's a new star for his chart. After that, a
    satellite only cheers him up when it *rises*: when it's heard again low in the sky
    (near the horizon) after being out of earshot for a while. Coming back outdoors after
    hours inside doesn't count: those satellites reappear at whatever height they happen
    to be, not down by the horizon.
    """

    def __init__(self, store):
        self.store = store
        self.known = {r["key"]: r["const"] for r in store.stars()}
        self.consts = set(self.known.values())
        t = store.get("stars_today", {}) or {}
        self._day = time.strftime("%Y-%m-%d")
        self.today = set(t.get("keys", [])) if t.get("date") == self._day else set()
        self.last_heard = {k: float(v) for k, v in (store.get("stars_last_heard", {}) or {}).items()}
        self.new = []           # (key, const) heard for the first time ever
        self.new_consts = []    # constellations seen for the first time ever
        self.risen = []         # known stars coming back over the horizon

    def gsv(self, talker, f, now=None):
        """One NMEA GSV sentence, already split on commas (f[0] is '$xxGSV'). Each
        satellite takes four fields: number, elevation (degrees above the horizon),
        azimuth (compass direction) and signal strength."""
        now = now or time.time()
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        if day != self._day:
            self._day, self.today = day, set()
        i = 4
        while i + 3 < len(f):
            prn, elev, snr = f[i], f[i + 1], f[i + 3]
            i += 4
            try:
                prn, snr = int(prn), int(snr or 0)
                elev = int(elev) if elev else None
            except ValueError:
                continue
            if snr < tuning.get("star_min_snr"):
                continue      # predicted to be there, but not actually being heard
            const = constellation(talker, prn)
            if not const:
                continue
            key = f"{const}-{prn}"
            last = self.last_heard.get(key)
            self.last_heard[key] = now
            if key not in self.today:
                self.today.add(key)
                self.store.star_seen(key, const, prn, now)
            if key not in self.known:
                self.known[key] = const
                self.new.append((key, const))
                if const not in self.consts:
                    self.consts.add(const)
                    self.new_consts.append(const)
            elif (last is not None and now - last >= tuning.get("star_away_min") * 60
                  and elev is not None and elev <= tuning.get("star_rise_elev")):
                self.risen.append(key)

    def take(self):
        out = (self.new, self.new_consts, self.risen)
        self.new, self.new_consts, self.risen = [], [], []
        return out

    def save(self):
        self.store.put("stars_today", {"date": self._day, "keys": sorted(self.today)})
        week = time.time() - 7 * 86400
        self.store.put("stars_last_heard", {k: round(v) for k, v in self.last_heard.items() if v > week})


# ---------------------------------------------------------------- barometer

def pressure_altitude(hpa):
    """Height in meters from air pressure (the standard atmosphere formula). Only the
    changes matter here: they're what you climbed."""
    return 44330.0 * (1.0 - (hpa / 1013.25) ** 0.1903)


class Sunshine:
    """Sunshine, from the phone's light sensor: bright enough (tuning sunny_lux) for long
    enough (sunny_hold_s), at most once every sunny_every_h hours."""

    DIP_S = 10           # a shadow this brief doesn't end a sunny spell

    def __init__(self, store):
        self.store = store
        self.lux = None
        self.ts = 0.0
        self.bright_since = None
        self._dark_since = None
        self.last = store.get("sunny_last", 0) or 0

    def feed(self, lux, now=None):
        """One reading. Returns the brightness to cheer about, when it's time to; else None."""
        now = now or time.time()
        if lux is None or lux < 0:
            return None
        self.lux, self.ts = lux, now
        if lux >= tuning.get("sunny_lux"):
            self._dark_since = None
            if self.bright_since is None:
                self.bright_since = now
        elif self.bright_since is not None:
            if self._dark_since is None:
                self._dark_since = now
            if now - self._dark_since > self.DIP_S:
                self.bright_since = self._dark_since = None
        if self.bright_since is None or self._dark_since is not None:
            return None
        if now - self.bright_since < tuning.get("sunny_hold_s"):
            return None
        if now - self.last < tuning.get("sunny_every_h") * 3600:
            return None
        self.last = now
        self.bright_since = None
        self.store.put("sunny_last", now)
        return lux


class Barometer:
    BUCKET_S = 5        # average readings over 5 s (phones send several a second)
    CLIMB_WINDOW_S = 180
    LOG_EVERY_S = 300   # one weather sample every 5 minutes, kept for 4 hours
    LOG_KEEP_S = 4 * 3600
    SPAN_S = 3 * 3600   # the weather is judged over 3 hours, as forecasters do
    JUMP_HPA = 0.3      # a change this big within 5 s is you moving up or down (~2.5 m)

    def __init__(self, store):
        self.store = store
        self.hpa = None
        self.ts = 0.0
        self._bucket, self._bucket_t = [], 0.0
        self._alts = deque()                 # (t, meters), recent 5-s averages
        self._prev5 = None
        self._log_vals, self._log_t, self._log_jumpy = [], 0.0, False
        self.log = [tuple(x) for x in (store.get("pressure_log", []) or [])]
        self.armed = store.get("weather_armed", {"fall": True, "rise": True}) or {"fall": True, "rise": True}
        self.climbed = 0.0                   # meters climbed, not yet handed out

    def feed(self, hpa, fix=None, mode="still", now=None):
        now = now or time.time()
        if not 300 <= hpa <= 1100:
            return
        self.hpa, self.ts = hpa, now
        if not self._bucket:
            self._bucket_t = now
        self._bucket.append(hpa)
        if now - self._bucket_t < self.BUCKET_S:
            return
        p = sum(self._bucket) / len(self._bucket)
        self._bucket = []
        self._five_seconds(p, fix, mode, now)

    def _five_seconds(self, p, fix, mode, now):
        if self._prev5 is not None and abs(p - self._prev5) > self.JUMP_HPA:
            self._log_jumpy = True
        self._prev5 = p
        # -- climbing: the lowest point of the last 3 minutes is the "floor"; rising a
        # step above it is a climb. Weather is far too slow to do that (even a fast
        # change is ~1 hPa an hour, about 0.4 m in 3 minutes).
        alt = pressure_altitude(p)
        if mode == "vehicle":
            self._alts.clear()               # driving over hills isn't climbing
        self._alts.append((now, alt))
        while self._alts and now - self._alts[0][0] > self.CLIMB_WINDOW_S:
            self._alts.popleft()
        floor = min(a for _, a in self._alts)
        if alt - floor >= tuning.get("climb_step_m"):
            self.climbed += alt - floor
            self._alts.clear()
            self._alts.append((now, alt))
        # -- weather log
        if not self._log_vals:
            self._log_t = now
        self._log_vals.append(p)
        if now - self._log_t >= self.LOG_EVERY_S:
            lat = lon = None
            if fix and fix.get("acc", 99) <= 100:
                lat, lon = round(fix["lat"], 5), round(fix["lon"], 5)
            self.log.append((round(now), round(sum(self._log_vals) / len(self._log_vals), 2),
                             lat, lon, 1 if self._log_jumpy else 0))
            self._log_vals, self._log_jumpy = [], False
            self.log = [x for x in self.log if now - x[0] <= self.LOG_KEEP_S]

    def take_climb(self):
        m, self.climbed = self.climbed, 0.0
        return m

    def tendency(self, now=None):
        """Pressure change over the last ~3 hours in hPa, or None if it can't be trusted
        (not enough history, or you moved up/down or across town in between)."""
        now = now or time.time()
        if len(self.log) < 2:
            return None
        end = self.log[-1]
        if now - end[0] > 900:
            return None
        start = None
        for x in self.log:
            if abs((end[0] - x[0]) - self.SPAN_S) <= 900:
                start = x
                break
        if start is None:
            return None
        span = [x for x in self.log if start[0] <= x[0] <= end[0]]
        if any(x[4] for x in span[1:]):
            return None          # sudden jumps in between: you went up or down
        fixes = [x for x in span if x[2] is not None]
        if len(fixes) >= 2:
            lat0, lon0 = fixes[0][2], fixes[0][3]
            for x in fixes[1:]:
                dy = (x[2] - lat0) * METERS_PER_DEG_LAT
                dx = (x[3] - lon0) * METERS_PER_DEG_LAT * math.cos(math.radians(lat0))
                if math.hypot(dx, dy) > 300:
                    return None  # you went somewhere else: a hill or valley changes pressure
        return end[1] - start[1]

    def weather(self, now=None):
        """'storm', 'rise' or None, once per change of weather (it has to settle back
        before the same kind can be announced again)."""
        d = self.tendency(now)
        if d is None:
            return None, None
        storm, rise = tuning.get("storm_hpa"), tuning.get("rise_hpa")
        event = None
        if d <= -storm and self.armed.get("fall", True):
            self.armed["fall"], event = False, "storm"
        elif d > -storm / 3:
            self.armed["fall"] = True
        if d >= rise and self.armed.get("rise", True):
            self.armed["rise"], event = False, event or "rise"
        elif d < rise / 3:
            self.armed["rise"] = True
        return event, d

    def save(self):
        self.store.put("pressure_log", self.log)
        self.store.put("weather_armed", self.armed)
