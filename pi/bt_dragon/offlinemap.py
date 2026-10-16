"""
The offline map (Den → Conquests → "Offline map"): the map of everywhere he's been, kept on
the Pi, so the map page still shows streets with no mobile signal (your phone's hotspot and
its GPS both work without one; only the map underneath used to need the internet).

Where it comes from. OpenStreetMap's own tile servers don't allow this: their usage policy
forbids downloading ahead of time and offline use (they run on donations). Protomaps instead
publishes the whole of OpenStreetMap as one file every day (build.protomaps.com/YYYYMMDD.pmtiles,
kept for a week), under OpenStreetMap's own licence, for people to take what they need and host
it themselves. So once a day, Harald works out which pieces of the map cover the lands he
claimed since last time (with a margin round them), and fetches just those pieces from that
file. Nothing else is downloaded, and nothing is fetched for places he hasn't been.

How a PMTiles file works. It's one big file, read in pieces over the internet with "range
requests" (give me bytes 1,000,000 to 1,050,000). Every map tile has a number: the zoom
levels are counted in order, and within a zoom level the tiles are numbered along a Hilbert
curve, a line that snakes through the grid so tiles next to each other mostly get numbers
close together. The file starts with a 127-byte header saying where everything is, then a
directory listing which tile numbers are where (packed tightly: each number stored as the
difference from the one before, in as few bytes as it needs). A big file has a root
directory pointing at "leaf" directories, each covering a run of tile numbers.

The tiles are vector tiles: the shapes of roads, buildings, water and parks and the names,
not pictures. Your phone draws them (with protomaps-leaflet, kept on the Pi too, along with
Leaflet itself), so the Pi Zero only hands them over.

Privacy: the tiles asked for show roughly where you've been (to the nearest few hundred
meters, as any online map does while you look at it), so it's off until you switch it on.
They're kept in their own file on the card (offline-map.db), not in his database or backups.
"""
import datetime
import gzip
import hashlib
import base64
import io
import json
import logging
import math
import os
import sqlite3
import struct
import tarfile
import threading
import time
import urllib.request

log = logging.getLogger("offlinemap")

BUILD_URL = "https://build.protomaps.com/{date}.pmtiles"
BUILD_DAYS = 7                    # builds are kept for a week: look back this far for one
MIN_Z, MAX_Z = 4, 15              # the zooms kept (15 is street level, the most detailed there is)
MARGIN_M = 250                    # this much round each land is fetched too
DAILY_MAX = 3000                  # tiles a day at most (the rest come the next day)
UA = "BT-Dragon offline map (a Raspberry Pi pet; github.com/sauvryn/BT-dragon)"

# Leaflet as the map page already loads it, checked against the same fingerprints
LEAFLET = "https://registry.npmjs.org/leaflet/-/leaflet-1.9.4.tgz"
LEAFLET_SHA256 = {"leaflet.js": "20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=",
                  "leaflet.css": "p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="}
PROTOMAPS_LEAFLET = "https://registry.npmjs.org/protomaps-leaflet"
VENDOR_FILES = ("leaflet.js", "leaflet.css", "protomaps-leaflet.js", "images/layers.png", "images/layers-2x.png",
                "images/marker-icon.png", "images/marker-icon-2x.png", "images/marker-shadow.png")


# ---------------------------------------------------------------- the PMTiles format
def zxy_to_id(z, x, y):
    """A tile's number in a PMTiles file: all the tiles of the zoom levels before it, then its
    place along the Hilbert curve through its own zoom level."""
    acc = (4 ** z - 1) // 3
    n = 1 << z
    d, s = 0, n >> 1
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:                       # turn the quarter round so the curve joins up
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s >>= 1
    return acc + d


def _varint(buf, pos):
    out = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        out |= (b & 0x7F) << shift
        if b < 0x80:
            return out, pos
        shift += 7


def _decompress(data, how):
    if how in (0, 1):
        return data
    if how == 2:
        return gzip.decompress(data)
    raise ValueError(f"unsupported compression {how}")


def parse_header(b):
    if len(b) < 127 or b[:7] != b"PMTiles" or b[7] != 3:
        raise ValueError("not a PMTiles (v3) file")
    q = struct.unpack_from("<11Q", b, 8)
    keys = ("root_offset", "root_length", "meta_offset", "meta_length", "leaf_offset", "leaf_length",
            "data_offset", "data_length", "addressed", "entries", "contents")
    h = dict(zip(keys, q))
    h.update(clustered=b[96], internal_compression=b[97], tile_compression=b[98], tile_type=b[99],
             min_zoom=b[100], max_zoom=b[101])
    return h


def parse_directory(b):
    """[(tile_id, offset, length, run_length)], as stored (see the module's notes)."""
    n, pos = _varint(b, 0)
    ids, runs, lens, offs = [], [], [], []
    last = 0
    for _ in range(n):
        v, pos = _varint(b, pos)
        last += v
        ids.append(last)
    for _ in range(n):
        v, pos = _varint(b, pos)
        runs.append(v)
    for _ in range(n):
        v, pos = _varint(b, pos)
        lens.append(v)
    for i in range(n):
        v, pos = _varint(b, pos)
        offs.append(offs[i - 1] + lens[i - 1] if v == 0 and i > 0 else v - 1)
    return list(zip(ids, offs, lens, runs))


def find(entries, tid):
    """The entry for a tile number: the last one starting at or before it (binary search)."""
    lo, hi = 0, len(entries) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if entries[mid][0] <= tid:
            lo = mid + 1
        else:
            hi = mid - 1
    if hi < 0:
        return None
    e = entries[hi]
    if e[3] == 0:                    # a leaf directory covering it
        return e
    return e if tid < e[0] + e[3] else None


class PMTiles:
    """Reads tiles out of a PMTiles file over the internet, a piece at a time."""

    def __init__(self, url, fetch=None):
        self.url = url
        self.fetch = fetch or http_range
        first = self.fetch(url, 0, 16384)            # the header and root directory are in here
        self.h = parse_header(first)
        h = self.h
        if h["root_offset"] + h["root_length"] <= len(first):
            raw = first[h["root_offset"]: h["root_offset"] + h["root_length"]]
        else:
            raw = self.fetch(url, h["root_offset"], h["root_length"])
        self.root = parse_directory(_decompress(raw, h["internal_compression"]))
        self._leaves = {}

    def _leaf(self, offset, length):
        key = (offset, length)
        if key not in self._leaves:
            raw = self.fetch(self.url, self.h["leaf_offset"] + offset, length)
            self._leaves[key] = parse_directory(_decompress(raw, self.h["internal_compression"]))
            if len(self._leaves) > 64:
                self._leaves.pop(next(iter(self._leaves)))
        return self._leaves[key]

    def locate(self, z, x, y):
        """(offset, length) of a tile in the file, or None if the map has nothing there."""
        tid = zxy_to_id(z, x, y)
        entries = self.root
        for _ in range(4):                           # root, then at most a few levels of leaves
            e = find(entries, tid)
            if e is None:
                return None
            if e[3] > 0:
                return self.h["data_offset"] + e[1], e[2]
            entries = self._leaf(e[1], e[2])
        return None

    def tile(self, z, x, y):
        loc = self.locate(z, x, y)
        return self.fetch(self.url, *loc) if loc else None


def http_range(url, offset, length, timeout=30):
    req = urllib.request.Request(url, headers={"Range": f"bytes={offset}-{offset + length - 1}", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.status == 200 and len(data) > length:  # the server ignored the range: take our piece
            data = data[offset: offset + length]
        return data


# ---------------------------------------------------------------- which tiles
def tile_xy(lat, lon, z):
    lat = max(-85.0511, min(85.0511, lat))
    n = 1 << z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(n - 1, max(0, x)), min(n - 1, max(0, y))


def tiles_for(bounds_list, margin_m=MARGIN_M, min_z=MIN_Z, max_z=MAX_Z):
    """Every tile, zoom min_z to max_z, that covers any of these [south, west, north, east] boxes
    (each widened by margin_m)."""
    out = set()
    for s, w, n, e in bounds_list:
        dlat = margin_m / 111320.0
        dlon = margin_m / (111320.0 * max(0.01, math.cos(math.radians((s + n) / 2))))
        s, w, n, e = s - dlat, w - dlon, n + dlat, e + dlon
        for z in range(min_z, max_z + 1):
            x0, y0 = tile_xy(n, w, z)
            x1, y1 = tile_xy(s, e, z)
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    out.add((z, x, y))
    return out


# ---------------------------------------------------------------- the kept map
class OfflineMap:
    def __init__(self, store, data_dir, vendor_dir=None):
        self.store = store
        self.path = os.path.join(data_dir, "offline-map.db")
        self.vendor = vendor_dir or os.path.join(data_dir, "vendor")
        self.s = store.get("offline_map") or {"on": False}
        self.busy = False
        self.state = ""
        self._lock = threading.Lock()
        self._db = None

    def _save(self):
        self.store.put("offline_map", self.s)

    def db(self):
        if self._db is None:
            self._db = sqlite3.connect(self.path, check_same_thread=False)
            self._db.execute("CREATE TABLE IF NOT EXISTS tiles (z INTEGER, x INTEGER, y INTEGER, data BLOB, "
                             "gz INTEGER, PRIMARY KEY (z, x, y))")
            self._db.commit()
        return self._db

    # ---- settings
    def set_on(self, on):
        self.s["on"] = bool(on)
        self._save()

    def lines(self):
        n, size = self.counts()
        return [f"on={int(bool(self.s.get('on')))}", f"tiles={n}", f"bytes={size}",
                f"last={int(self.s.get('last_run', 0))}", f"build={self.s.get('build', '')}",
                f"busy={int(self.busy)}", f"state={self.state or self.s.get('result', '')}",
                f"ready={int(self.ready())}"]

    def counts(self):
        if not os.path.exists(self.path):
            return 0, 0
        with self._lock:
            r = self.db().execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(data)), 0) FROM tiles").fetchone()
        return r[0], r[1]

    def ready(self):
        """Can the map page draw it: tiles kept, and its two libraries here."""
        return self.counts()[0] > 0 and self.have_vendor()

    def have_vendor(self):
        return all(os.path.exists(os.path.join(self.vendor, f)) for f in ("leaflet.js", "leaflet.css",
                                                                          "protomaps-leaflet.js"))

    def forget(self):
        """"Forget my map": the offline map goes too (it shows where he's been)."""
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
            for p in (self.path, self.path + "-journal", self.path + "-wal"):
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.s.pop("last_day", None)
        self.s.pop("result", None)
        self._save()

    # ---- serving
    def get(self, z, x, y):
        """(data, gzipped) for the map page, or None."""
        if not os.path.exists(self.path):
            return None
        with self._lock:
            r = self.db().execute("SELECT data, gz FROM tiles WHERE z=? AND x=? AND y=?", (z, x, y)).fetchone()
        return (r[0], bool(r[1])) if r else None

    def vendor_file(self, name):
        if name not in VENDOR_FILES:
            return None
        p = os.path.join(self.vendor, name)
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            return f.read()

    # ---- the daily fetch
    def due(self, now=None):
        if not self.s.get("on") or self.busy:
            return False
        now = now or time.time()
        if self.s.get("last_day") == time.strftime("%Y-%m-%d", time.localtime(now)):
            return False
        return now - self.s.get("last_try", 0) >= 1800      # (offline: again in half an hour)

    def wanted(self, bounds_list):
        have = set()
        if os.path.exists(self.path):
            with self._lock:
                have = {tuple(r) for r in self.db().execute("SELECT z, x, y FROM tiles")}
        want = tiles_for(bounds_list) - have
        # low zooms first: a few big tiles give the overview
        return sorted(want, key=lambda t: t[0])

    def find_build(self, fetch=None, today=None):
        """The newest daily build that answers."""
        fetch = fetch or http_range
        day = today or datetime.datetime.now(datetime.timezone.utc).date()
        last = None
        for back in range(BUILD_DAYS):
            date = (day - datetime.timedelta(days=back)).strftime("%Y%m%d")
            url = BUILD_URL.format(date=date)
            try:
                return date, PMTiles(url, fetch)
            except Exception as e:
                last = e
        raise ConnectionError(f"no map build reachable ({last})")

    def run(self, bounds_list, fetch=None, today=None, now=None):
        """Fetch what's missing (up to DAILY_MAX tiles). Returns a few words for the den."""
        now = now or time.time()
        self.busy = True
        self.s["last_try"] = now
        try:
            if not self.have_vendor():
                self.state = "fetching the map's libraries"
                self.fetch_vendor(fetch)
            want = self.wanted(bounds_list)
            if not want:
                result = "up to date"
            else:
                self.state = "finding today's map"
                date, pm = self.find_build(fetch, today)
                gz = pm.h["tile_compression"] == 2
                got, size = [], 0
                for i, (z, x, y) in enumerate(want[:DAILY_MAX]):
                    if i % 25 == 0:
                        self.state = f"fetching map tiles: {i} of {min(len(want), DAILY_MAX)}"
                    data = pm.tile(z, x, y)
                    if data:
                        got.append((z, x, y, data, int(gz)))
                        size += len(data)
                    else:
                        got.append((z, x, y, b"", 0))       # nothing there (sea): don't ask again
                with self._lock:
                    db = self.db()
                    db.executemany("INSERT OR REPLACE INTO tiles VALUES (?, ?, ?, ?, ?)", got)
                    db.commit()
                self.s["build"] = date
                left = len(want) - len(got)
                result = (f"{len(got):,} new map tiles ({size / 1e6:.1f} MB)"
                          + (f"; {left:,} more tomorrow" if left > 0 else ""))
            self.s["last_day"] = time.strftime("%Y-%m-%d", time.localtime(now))
            self.s["last_run"] = now
            self.s["result"] = result
            return result
        except Exception as e:
            log.info("offline map: %s", e)
            self.s["result"] = f"couldn't fetch the map ({type(e).__name__}); trying again later"
            return self.s["result"]
        finally:
            self.busy = False
            self.state = ""
            self._save()

    # ---- the libraries the map page draws it with
    def fetch_vendor(self, fetch=None):
        """Leaflet (checked against the fingerprints the map page already pins) and protomaps-
        leaflet (checked against the fingerprint npm publishes for it), from npm's registry."""
        get = fetch_url if fetch is None else (lambda url: fetch(url, 0, 0))
        os.makedirs(os.path.join(self.vendor, "images"), exist_ok=True)
        files = _untar(get(LEAFLET))
        for name, want in LEAFLET_SHA256.items():
            data = files.get("package/dist/" + name)
            if data is None or base64.b64encode(hashlib.sha256(data).digest()).decode() != want:
                raise ValueError(f"{name} didn't match its fingerprint")
            _write(os.path.join(self.vendor, name), data)
        for name, data in files.items():
            if name.startswith("package/dist/images/") and name.endswith(".png"):
                _write(os.path.join(self.vendor, "images", os.path.basename(name)), data)
        meta = json.loads(get(PROTOMAPS_LEAFLET))
        version = meta["dist-tags"]["latest"]
        dist = meta["versions"][version]["dist"]
        tgz = get(dist["tarball"])
        algo, _, want = dist["integrity"].partition("-")
        if base64.b64encode(hashlib.new(algo, tgz).digest()).decode() != want:
            raise ValueError("protomaps-leaflet didn't match its fingerprint")
        files = _untar(tgz)
        js = next((files[n] for n in ("package/dist/protomaps-leaflet.js", "package/dist/protomaps-leaflet.min.js",
                                      "package/dist/protomaps-leaflet.umd.js") if n in files), None)
        if js is None:
            raise ValueError("protomaps-leaflet: no browser build in the package")
        _write(os.path.join(self.vendor, "protomaps-leaflet.js"), js)
        self.s["vendor"] = {"leaflet": "1.9.4", "protomaps-leaflet": version}


def fetch_url(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _untar(tgz):
    out = {}
    with tarfile.open(fileobj=io.BytesIO(tgz), mode="r:gz") as t:
        for m in t.getmembers():
            if m.isfile() and m.size < 5_000_000:
                out[m.name] = t.extractfile(m).read()
    return out


def _write(path, data):
    tmp = path + ".new"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
