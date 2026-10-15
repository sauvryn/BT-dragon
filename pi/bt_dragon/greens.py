"""
Green spaces: public parks, woods, nature reserves, commons and gardens.
"Took a walk in Oakfield Country Park!"

Where they come from: OpenStreetMap, the same map the den's map page draws. The green
areas on its tiles are OpenStreetMap's parks (leisure=park), woods (natural=wood,
landuse=forest), nature reserves and so on, and each one is stored there as an outline,
not just a pin. The first time Harald enters a realm (a ~1 km square), he asks
OpenStreetMap's public search service, Overpass, for the named green spaces in it (plus a
margin), and keeps their outlines on the Pi. Each realm is asked about once (and again
after half a year).

Which ones count: named ones (he has to call them something), at least half a hectare
(about 70 x 70 m, so roadside verges don't count), and not marked private.

Being in one: inside its outline, or within a few meters of it (GPS wobbles, and paths
often run along the edge). "Inside" is the classic ray test: from your position, count
how many times a line heading due east crosses the outline. Odd: inside. Even: outside.

Without GPS (finding himself by Wi-Fi, see wifipos.py) green spaces can still be
discovered, but walks, runs and rides need a real GPS.

What counts: while you're in it, time on foot counts towards a walk (10 minutes, and you
have to actually walk a little), running towards a run (5) and cycling towards a ride
(5). Time in a vehicle counts for nothing, though driving through still discovers it.
Stepping out for a few minutes (crossing a road between two halves of a park) doesn't
reset the clock. Each green space gets one walk, run or ride a day.

Privacy: each request tells Overpass roughly which square kilometer you're in. Nothing
else is sent. Switch it off with  greens = false  under [sky] in bt-dragon.toml.
"""
import json
import logging
import math
import time
import urllib.parse
import urllib.request

from . import __version__, tuning
from .sky import METERS_PER_DEG_LAT, REALM_M, cell_bounds, grid_cell

log = logging.getLogger("greens")

OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = f"BTDragon/{__version__} (https://github.com/sauvryn/BT-dragon)"
MARGIN_M = 400              # also look this far past the realm's edges
REFRESH_S = 180 * 86400
MIN_AREA_M2 = 5000          # half a hectare
SIMPLIFY_M = 4              # outlines are simplified to within this many meters
OUT_GRACE_S = 300           # outside this long and a visit's clock starts over
MIN_WALK_M = 150            # a "walk" needs some walking, not just sitting on a bench

KINDS = (("leisure", "park", "park"), ("leisure", "nature_reserve", "nature reserve"),
         ("leisure", "garden", "garden"), ("leisure", "common", "common"),
         ("landuse", "village_green", "green"), ("landuse", "forest", "wood"), ("natural", "wood", "wood"))
PRIVATE = {"private", "no", "customers", "permit"}


def kind_of(tags):
    for key, value, kind in KINDS:
        if tags.get(key) == value:
            return kind
    return None


def query(s, w, n, e):
    box = f"({s:.6f},{w:.6f},{n:.6f},{e:.6f})"
    parts = []
    for key, value, _ in KINDS:
        for t in ("way", "relation"):
            parts.append(f'{t}["{key}"="{value}"]["name"]{box};')
    return "[out:json][timeout:60];(" + "".join(parts) + ");out geom;"


def _post(q, timeout=90):
    req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(),
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------- geometry
def _xy(lat0, lon0):
    """A flat map in meters around (lat0, lon0): plenty accurate across a park."""
    kx = METERS_PER_DEG_LAT * math.cos(math.radians(lat0))
    return (lambda lat, lon: ((lon - lon0) * kx, (lat - lat0) * METERS_PER_DEG_LAT),
            lambda x, y: (lat0 + y / METERS_PER_DEG_LAT, lon0 + x / kx))


def stitch(lines):
    """Join way pieces end to end into closed rings (OpenStreetMap often splits a big
    outline into several ways)."""
    lines = [list(x) for x in lines if len(x) >= 2]
    rings = []
    while lines:
        ring = lines.pop(0)
        while ring[0] != ring[-1]:
            for i, ln in enumerate(lines):
                if ln[0] == ring[-1]:
                    ring += ln[1:]
                elif ln[-1] == ring[-1]:
                    ring += ln[::-1][1:]
                elif ln[-1] == ring[0]:
                    ring = ln[:-1] + ring
                elif ln[0] == ring[0]:
                    ring = ln[::-1][:-1] + ring
                else:
                    continue
                lines.pop(i)
                break
            else:
                break             # can't close it: the rest is outside what was asked for
        if ring[0] != ring[-1] and len(ring) >= 3:
            ring.append(ring[0])
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def simplify(points, tol_m):
    """Douglas-Peucker: drop points that lie within tol_m of the line between their
    neighbors, keeping the shape."""
    if len(points) < 4:
        return points
    to_xy, _ = _xy(*points[0])
    xy = [to_xy(*p) for p in points]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = xy[a], xy[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, idx = -1.0, None
        for i in range(a + 1, b):
            px, py = xy[i]
            d = abs(dx * (ay - py) - dy * (ax - px)) / L if L else math.hypot(px - ax, py - ay)
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol_m:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    out = [p for p, k in zip(points, keep) if k]
    return out if len(out) >= 4 else points


def area_m2(ring):
    to_xy, _ = _xy(*ring[0])
    xy = [to_xy(*p) for p in ring]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:]))) / 2


def _inside(ring_xy, x, y):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring_xy, ring_xy[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _nearest_on(ring_xy, x, y):
    """The nearest point on a ring's edge to (x, y), and how far it is."""
    best = (None, float("inf"))
    for (x1, y1), (x2, y2) in zip(ring_xy, ring_xy[1:]):
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2)) if L2 else 0.0
        px, py = x1 + t * dx, y1 + t * dy
        d = math.hypot(px - x, py - y)
        if d < best[1]:
            best = ((px, py), d)
    return best


def locate(green, lat, lon):
    """(distance in meters, (lat, lon) of the nearest edge point). 0 when inside."""
    to_xy, to_ll = _xy(lat, lon)
    best = (float("inf"), None)
    for ring in green["rings"]:
        xy = [to_xy(*p) for p in ring]
        if _inside(xy, 0.0, 0.0):
            return 0.0, (lat, lon)
        (px, py), d = _nearest_on(xy, 0.0, 0.0)
        if d < best[0]:
            best = (d, to_ll(px, py))
    return best


def parse(data):
    """Overpass's answer -> green spaces: [{id, name, kind, rings, area, bbox, lat, lon}]."""
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        kind, name = kind_of(tags), (tags.get("name") or "").strip()
        if not kind or not name or tags.get("access") in PRIVATE:
            continue
        if kind == "garden" and tags.get("garden:type") in ("residential", "private"):
            continue
        if el["type"] == "way":
            lines = [[(p["lat"], p["lon"]) for p in el.get("geometry") or []]]
        else:
            lines = [[(p["lat"], p["lon"]) for p in m.get("geometry") or []]
                     for m in el.get("members", []) if m.get("role") in ("outer", "") and m.get("type") == "way"]
        rings = [simplify(r, SIMPLIFY_M) for r in stitch(lines)]
        rings = [[(round(a, 6), round(b, 6)) for a, b in r] for r in rings]
        if not rings:
            continue
        area = sum(area_m2(r) for r in rings)
        if area < MIN_AREA_M2:
            continue
        pts = [p for r in rings for p in r]
        lats, lons = [p[0] for p in pts], [p[1] for p in pts]
        out.append({"id": f"{el['type'][0]}{el['id']}", "name": name, "kind": kind, "rings": rings,
                    "area": round(area), "bbox": (min(lats), min(lons), max(lats), max(lons)),
                    "lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons)})
    return out


def realm_greens(realm):
    """Green spaces in and just around one realm (blocking: run it in a thread)."""
    s, w, n, e = cell_bounds(realm, REALM_M)
    lat_m = MARGIN_M / METERS_PER_DEG_LAT
    lon_m = MARGIN_M / (METERS_PER_DEG_LAT * max(0.01, math.cos(math.radians((s + n) / 2))))
    return parse(_post(query(s - lat_m, w - lon_m, n + lat_m, e + lon_m)))


# ---------------------------------------------------------------- being there
class Greens:
    def __init__(self, store, fetcher=realm_greens):
        self.store = store
        self.fetcher = fetcher
        self._busy = False
        self._failed = {}
        self.visits = {}          # id -> {"foot": s, "run": s, "bike": s, "walked": m, "out": ts or None}
        self._last = None         # (lat, lon, ts) of the last fix
        self._wifi_in = set()     # green spaces the last Wi-Fi position was in
        t = store.get("greens_today", {}) or {}
        self._day = time.strftime("%Y-%m-%d")
        self.today = set(t.get("ids", [])) if t.get("date") == self._day else set()

    def wanted(self, fix):
        realm = grid_cell(fix["lat"], fix["lon"], REALM_M)
        fetched = self.store.greens_fetched(realm)
        if fetched and time.time() - fetched < REFRESH_S:
            return None
        if self._busy or time.time() - self._failed.get(realm, 0) < 600:
            return None
        return realm

    async def fetch(self, realm):
        import asyncio
        self._busy = True
        try:
            found = await asyncio.to_thread(self.fetcher, realm)
            self.store.save_greens(realm, found, time.time())
            log.info("a new realm: %d green spaces", len(found))   # (not which realm: the log is no map)
        except Exception as e:      # offline, slow hotspot, Overpass busy: try again later
            log.info("green space lookup failed: %s", e)
            self._failed[realm] = time.time()
        finally:
            self._busy = False

    def here(self, lat, lon, margin_m=None):
        """The green spaces we're in (or within the margin of) right now."""
        margin = tuning.get("green_margin_m") if margin_m is None else margin_m
        return [g for g in self.store.greens_near(lat, lon, margin) if locate(g, lat, lon)[0] <= margin]

    def update(self, fix, mode):
        """One GPS fix. Returns what happened: [("found", green)] for a green space he's
        never been in, [("walk" | "run" | "bike", green)] when a visit has gone on long
        enough."""
        if fix.get("via") == "wifi":
            return self._discover(fix)
        now, lat, lon = fix["ts"], fix["lat"], fix["lon"]
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        if day != self._day:
            self._day, self.today = day, set()
        dt, moved = 0.0, 0.0
        if self._last and 0 < now - self._last[2]:
            dt = min(15.0, now - self._last[2])
            to_xy, _ = _xy(self._last[0], self._last[1])
            moved = math.hypot(*to_xy(lat, lon))
        self._last = (lat, lon, now)
        out = []
        inside = self.here(lat, lon) if fix.get("acc", 10) <= 50 else []
        ids = set()
        for g in inside:
            ids.add(g["id"])
            v = self.visits.get(g["id"])
            if v is None:                         # just came in
                v = self.visits[g["id"]] = {"foot": 0.0, "run": 0.0, "bike": 0.0, "walked": 0.0, "out": None}
                first = not g["first_seen"]
                self.store.green_seen(g["id"], now)
                if first:
                    out.append(("found", g))
            v["out"] = None
            if g["id"] in self.today:
                continue
            if mode in ("still", "walking", "running"):
                v["foot"] += dt
                if mode != "still":
                    v["walked"] += min(moved, 10 * dt)
            if mode == "running":
                v["run"] += dt
            elif mode == "cycling":
                v["bike"] += dt
            how = ("run" if v["run"] >= tuning.get("green_run_min") * 60 else
                   "bike" if v["bike"] >= tuning.get("green_bike_min") * 60 else
                   "walk" if v["foot"] >= tuning.get("green_walk_min") * 60 and v["walked"] >= MIN_WALK_M else None)
            if how:
                self.today.add(g["id"])
                self.store.green_exercise(g["id"], how, now)
                self.save()
                out.append((how, g))
        for gid, v in list(self.visits.items()):
            if gid in ids:
                continue
            if v["out"] is None:
                v["out"] = now
            elif now - v["out"] > OUT_GRACE_S:
                del self.visits[gid]
        return out

    def _discover(self, fix):
        """A Wi-Fi position (no GPS): green spaces can be discovered and visited, but never
        walked, run or ridden in. A Wi-Fi position wanders by tens of meters while you sit
        still, so it can't tell a walk from a bench."""
        if fix.get("acc", 99) > tuning.get("land_wifi_accuracy_m"):
            return []
        out, inside = [], set()
        for g in self.here(fix["lat"], fix["lon"]):
            inside.add(g["id"])
            if g["id"] in self._wifi_in:
                continue                   # still in it: one visit, not one per lookup
            first = not g["first_seen"]
            self.store.green_seen(g["id"], fix["ts"])
            if first:
                out.append(("found", g))
        self._wifi_in = inside
        return out

    def save(self):
        self.store.put("greens_today", {"date": self._day, "ids": sorted(self.today)})


def visit_words(how, name):
    """What he says (and shows) after a walk, run or ride in a green space."""
    return {"walk": f"Took a walk in {name}!", "run": f"Went for a run in {name}!",
            "bike": f"Biked through {name}!"}[how]
