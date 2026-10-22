"""The offline map: reading a PMTiles file in pieces over HTTP (its header, a root directory
and leaf directories, tiles numbered along a Hilbert curve), choosing the tiles that cover
the lands claimed, fetching them once a day, the map page using them (and Leaflet from the
Pi), the libraries checked against their fingerprints, and "Forget my map" deleting it."""
import asyncio
import base64
import gzip
import hashlib
import io
import json
import os
import socket
import struct
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bt_dragon import offlinemap as om
from bt_dragon.store import Store
from bt_dragon import sky as skymod

# --- tile numbers: PMTiles' own test values
assert om.zxy_to_id(0, 0, 0) == 0
assert [om.zxy_to_id(1, 0, 0), om.zxy_to_id(1, 0, 1), om.zxy_to_id(1, 1, 1), om.zxy_to_id(1, 1, 0)] == [1, 2, 3, 4]
assert om.zxy_to_id(2, 0, 0) == 5 and om.zxy_to_id(12, 3423, 1763) == 19078479
assert om.zxy_to_id(3, 7, 7) == 63 and om.zxy_to_id(3, 7, 0) == 84


# --- a small PMTiles file of our own, with leaf directories
def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def directory(entries):
    out = varint(len(entries))
    last = 0
    for tid, _, _, _ in entries:
        out += varint(tid - last)
        last = tid
    for e in entries:
        out += varint(e[3])
    for e in entries:
        out += varint(e[2])
    for i, (_, off, ln, _) in enumerate(entries):
        prev = entries[i - 1] if i else None
        out += varint(0 if prev and off == prev[1] + prev[2] else off + 1)
    return gzip.compress(out)


def build_pmtiles(tiles, per_leaf=4):
    """tiles: {(z, x, y): bytes}. Gzip directories and tiles, as Protomaps' builds are."""
    items = sorted((om.zxy_to_id(*k), gzip.compress(v)) for k, v in tiles.items())
    data, entries = b"", []
    for tid, blob in items:
        entries.append((tid, len(data), len(blob), 1))
        data += blob
    leaves, root = b"", []
    for i in range(0, len(entries), per_leaf):
        chunk = entries[i:i + per_leaf]
        d = directory(chunk)
        root.append((chunk[0][0], len(leaves), len(d), 0))
        leaves += d
    rootd = directory(root)
    meta = gzip.compress(b"{}")
    root_off = 127
    meta_off = root_off + len(rootd)
    leaf_off = meta_off + len(meta)
    data_off = leaf_off + len(leaves)
    head = b"PMTiles" + bytes([3]) + struct.pack("<11Q", root_off, len(rootd), meta_off, len(meta), leaf_off,
                                                 len(leaves), data_off, len(data), len(items), len(items), len(items))
    head += bytes([1, 2, 2, 1, 0, 15]) + struct.pack("<4i", -1800000000, -850000000, 1800000000, 850000000)
    head += bytes([0]) + struct.pack("<2i", 0, 0)
    assert len(head) == 127
    return head + rootd + meta + leaves + data


# lands around a point in London (the map data itself is made up)
LAT, LON = 51.51, -0.13
bounds = [[LAT, LON, LAT + 0.002, LON + 0.003]]
need = om.tiles_for(bounds)
assert all(om.MIN_Z <= z <= om.MAX_Z for z, _, _ in need)
assert {z for z, _, _ in need} == set(range(om.MIN_Z, om.MAX_Z + 1))
assert sum(1 for z, _, _ in need if z == 15) <= 9 and sum(1 for z, _, _ in need if z <= 10) <= 14
TILES = {t: f"tile {t}".encode() for t in need}
TILES[(0, 0, 0)] = b"world"
blob = build_pmtiles(TILES)

# served with range requests, as build.protomaps.com does (only one day's build exists)
DATE = "20261015"
asked = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        asked.append(self.path)
        if self.path != f"/{DATE}.pmtiles":
            self.send_response(404)
            self.end_headers()
            return
        a, b = self.headers["Range"].split("=")[1].split("-")
        part = blob[int(a): int(b) + 1]
        self.send_response(206)
        self.send_header("Content-Length", str(len(part)))
        self.end_headers()
        self.wfile.write(part)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
om.BUILD_URL = f"http://127.0.0.1:{srv.server_port}/{{date}}.pmtiles"

pm = om.PMTiles(om.BUILD_URL.format(date=DATE))
assert pm.h["tile_compression"] == 2 and pm.h["max_zoom"] == 15
for t, v in list(TILES.items())[:20]:
    assert gzip.decompress(pm.tile(*t)) == v, t
assert pm.tile(15, 0, 0) is None                                  # nothing there
assert len(pm._leaves) > 1                                        # (leaves were used)

# --- the daily fetch: finds the newest build that answers, takes only what's missing
import datetime
tmp = tempfile.mkdtemp()
st = Store(os.path.join(tmp, "d.db"))
m = om.OfflineMap(st, tmp, vendor_dir=os.path.join(tmp, "vendor"))
assert not m.due() and not m.ready()                              # off until switched on
m.set_on(True)
assert m.due()
m.have_vendor = lambda: True                                      # (libraries: tested below)
r = m.run(bounds, today=datetime.date(2026, 10, 17))
assert "new map tiles" in r and m.s["build"] == DATE, r
assert f"/20261017.pmtiles" in asked and f"/20261016.pmtiles" in asked   # (looked back for a build)
n, size = m.counts()
assert n == len(need) and size > 0
data, gz = m.get(15, *om.tile_xy(LAT, LON, 15))
assert gz and gzip.decompress(data).startswith(b"tile (15")
assert not m.due()                                                # once a day
asked.clear()
m.s.pop("last_day")
assert "up to date" in m.run(bounds, today=datetime.date(2026, 10, 17)) and not asked                # nothing new: nothing asked for
m.s.pop("last_day")
more = bounds + [[LAT + 0.01, LON, LAT + 0.012, LON + 0.003]]     # a new land a kilometer north
r = m.run(more, today=datetime.date(2026, 10, 17))
assert "new map tiles" in r and m.counts()[0] > n and "/{}.pmtiles".format(DATE) in asked
# no internet: says so, and tries again in half an hour (not the next day)
m.s.pop("last_day")
om.BUILD_URL = "http://127.0.0.1:1/{date}.pmtiles"
r = m.run(more + [[LAT + 0.05, LON, LAT + 0.052, LON + 0.003]])
assert "couldn't fetch" in r and "last_day" not in m.s
assert not m.due(time.time() + 60) and m.due(time.time() + 1900)

# --- the libraries: Leaflet must match the page's own fingerprints; protomaps-leaflet npm's
def tgz(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


b64 = lambda algo, d: base64.b64encode(hashlib.new(algo, d).digest()).decode()
LJS, LCSS, PJS = b"/* leaflet */", b"/* css */", b"/* protomaps-leaflet */"
leaflet_tgz = tgz({"package/dist/leaflet.js": LJS, "package/dist/leaflet.css": LCSS,
                   "package/dist/images/layers.png": b"png"})
pl_tgz = tgz({"package/dist/protomaps-leaflet.js": PJS, "package/dist/esm/index.mjs": b"x"})
meta = json.dumps({"dist-tags": {"latest": "5.0.1"}, "versions": {"5.0.1": {"dist": {
    "tarball": "https://registry.npmjs.org/protomaps-leaflet/-/protomaps-leaflet-5.0.1.tgz",
    "integrity": "sha512-" + b64("sha512", pl_tgz)}}}}).encode()
web = {om.LEAFLET: leaflet_tgz, om.PROTOMAPS_LEAFLET: meta,
       "https://registry.npmjs.org/protomaps-leaflet/-/protomaps-leaflet-5.0.1.tgz": pl_tgz}
fake = lambda url, a, b: web[url]
m2 = om.OfflineMap(st, tmp, vendor_dir=os.path.join(tmp, "v2"))
try:
    m2.fetch_vendor(fake)
    raise AssertionError("a Leaflet that doesn't match the pinned fingerprint was accepted")
except ValueError:
    pass
assert not m2.have_vendor()
om.LEAFLET_SHA256 = {"leaflet.js": b64("sha256", LJS), "leaflet.css": b64("sha256", LCSS)}
m2.fetch_vendor(fake)
assert m2.have_vendor() and m2.vendor_file("protomaps-leaflet.js") == PJS
assert m2.vendor_file("images/layers.png") == b"png" and m2.vendor_file("../d.db") is None
web["https://registry.npmjs.org/protomaps-leaflet/-/protomaps-leaflet-5.0.1.tgz"] = tgz(
    {"package/dist/protomaps-leaflet.js": b"/* tampered */"})
try:
    om.OfflineMap(st, tmp, vendor_dir=os.path.join(tmp, "v3")).fetch_vendor(fake)
    raise AssertionError("a tampered protomaps-leaflet was accepted")
except ValueError:
    pass

# --- the Den: the map page uses them, the tiles are served, and Forget my map deletes it
from bt_dragon import config, server
from bt_dragon.app import Dragon

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


app.cfg["link"]["web_port"], app.cfg["link"]["port"] = web_port, ctl = free_port(), free_port()
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(2)


def get(path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{web_port}{path}", timeout=10) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


code, page, _ = get("/map")
assert code == 200 and b"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" in page and b"const OFFLINE = null" in page
assert b"<!--OFFLINE-->" not in page
# with the libraries and some tiles: everything from the Pi
app.offline_map = m
m.vendor = m2.vendor
del m.have_vendor
code, page, _ = get("/map")
assert b'src="/vendor/leaflet.js"' in page and b"unpkg.com" not in page and b"/vendor/protomaps-leaflet.js" in page
assert b'integrity="sha256-' in page                               # (still checked: the same bytes)
assert b"const OFFLINE = {" in page
x, y = om.tile_xy(LAT, LON, 15)
code, body, h = get(f"/offline/15/{x}/{y}.mvt")
assert code == 200 and h["Content-Encoding"] == "gzip" and gzip.decompress(body).startswith(b"tile (15")
assert get("/offline/15/0/0.mvt")[0] == 404 and get("/offline/a/b/c.mvt")[0] == 404
assert get("/vendor/protomaps-leaflet.js")[1] == PJS and get("/vendor/secret.txt")[0] == 404
lines = asyncio.run(app.command("OFFLINEMAP"))
assert "on=1" in lines and any(l.startswith("tiles=") and l != "tiles=0" for l in lines)
assert asyncio.run(app.command("FORGETMAP")) == ["OK"]
assert m.counts() == (0, 0) and not os.path.exists(m.path) and get(f"/offline/15/{x}/{y}.mvt")[0] == 404
assert b"const OFFLINE = null" in get("/map")[1]
assert asyncio.run(app.command("OFFLINEMAPSET off")) == ["OK"] and not m.s["on"]
assert asyncio.run(app.command("OFFLINEMAPNOW"))[0].startswith("ERR")
srv.shutdown()
print("offline map ok")
