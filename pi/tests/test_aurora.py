"""Northern lights at the Lair: magnetic latitude, NOAA's Kp file (both layouts), the chance
by eye or camera, darkness, once a night (again if better), and the Den's line."""
import asyncio
import tempfile
import time

from bt_dragon import aurora as A, config
from bt_dragon.app import Dragon

# the magnet model: its centre ~590 km towards the western Pacific; North America
# magnetically further north than Europe
assert 570 < 6371.2 * sum(c * c for c in A.OFFSET) ** 0.5 < 610
lon_ = A.geomagnetic_lat(53.5, -2.2)                       # Manchester
tor = A.geomagnetic_lat(43.7, -79.4)                       # Toronto
assert 51 < lon_ < 54 and 47 < tor < 51 and A.geomagnetic_lat(-42.9, 147.3) < -50
assert abs(A.geomagnetic_lat(0.0, 0.0)) < 15
# NOAA's table, and what each place needs
assert A.edge(0) == 66.5 and A.edge(9) == 48.1 and abs(A.edge(5.5) - 55.25) < 0.01
assert A.needed_kp(70) == 0 and A.needed_kp(30) is None
m = A.geomagnetic_lat(51.5, -0.13)                         # London
cam, eye, top = A.needed_kp(m, A.CAMERA_MARGIN), A.needed_kp(m, A.EYE_MARGIN), A.needed_kp(m)
assert cam < eye < top and 4 <= cam <= 6 and 5 <= eye <= 7 and top >= 7
assert A.chance(top, m) == "overhead" and A.chance(eye, m) == "horizon" and A.chance(cam, m) == "camera"
assert A.chance(1, m) is None

# NOAA's file: the old layout (a header row) and the new (one object per 3 hours)
t0 = time.time() - time.time() % 10800
iso = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t))   # noqa: E731
old = [["time_tag", "kp", "observed", "noaa_scale"], [iso(t0 - 10800), "2.33", "observed", None],
       [iso(t0), "5.67", "estimated", "G1"], [iso(t0 + 10800), "7.00", "predicted", "G3"]]
new = [{"time_tag": iso(t0 - 10800), "kp": 2.33, "observed": "observed", "noaa_scale": None},
       {"time_tag": iso(t0), "kp": 5.67, "observed": "estimated", "noaa_scale": "G1"},
       {"time_tag": iso(t0 + 10800), "kp": 7.0, "observed": "predicted", "noaa_scale": "G3"}]
for data in (old, new):
    rows = A.parse(data)
    assert [r[1] for r in rows] == [2.33, 5.67, 7.0] and abs(rows[1][0] - t0) < 1
    assert A.kp_now(rows, t0 + 60, ahead_h=0) == (5.67, "estimated")
    assert A.kp_now(rows, t0 + 60) == (7.0, "predicted")
assert A.parse({"oops": 1}) == [] and A.parse([]) == [] and A.kp_now([], t0) == (None, "")

# the Sun: high at noon in June, set at midnight in December (London)
assert A.sun_elevation(51.5, -0.13, time.mktime((2026, 6, 21, 13, 0, 0, 0, 0, -1))) > 55
assert A.dark(51.5, -0.13, time.mktime((2026, 12, 21, 23, 0, 0, 0, 0, -1)))
assert not A.dark(51.5, -0.13, time.mktime((2026, 12, 21, 12, 0, 0, 0, 0, -1)))

# the app: checked at ten to the hour after dark; said once a night, again only if better
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
lair = app.lair
lair.s = {"place": "London", "code": "GB", "lat": 51.5, "lon": -0.1, "label": "London", "country": "United Kingdom",
          "announce": True}
night = time.mktime((2026, 12, 21, 21, 52, 0, 0, 0, -1))
day = time.mktime((2026, 12, 21, 12, 52, 0, 0, 0, -1))
assert "aurora" not in lair.due(day) and "aurora" in lair.due(night)
assert "aurora" not in lair.due(night - 10 * 60)            # (21:42: not yet ten to)
kp = {"v": 3.0}
start = night - night % 10800
lair.fetch_kp = lambda: [{"time_tag": iso(start), "kp": kp["v"], "observed": "estimated"}]
said, cheers = [], []
app.dot.news = lambda text, big=False: said.append(text)
app.pet.cheer = lambda *a, **k: cheers.append(a)
run = lambda t: asyncio.run(app._lair_check(t, ["aurora"]))  # noqa: E731
run(night)
assert not said and lair.s["aurora_last"]["kp"] == 3.0       # too weak for London
kp["v"] = cam + 0.1
run(night + 600)
assert len(said) == 1 and "camera" in said[0] and said[0].startswith("Northern lights alert!")
assert cheers and "TRY A CAMERA" in cheers[-1][2][0]
run(night + 1200)
assert len(said) == 1                                        # once a night...
kp["v"] = top + 0.1
run(night + 1800)
assert len(said) == 2 and "overhead" in said[1]              # ...unless it gets better
assert any("Northern lights possible at the Lair tonight: Kp" in e["text"] for e in app.store.events(10))
app.dot.s["say_lair_aurora"] = False
lair.s["aurora_said"] = {}
run(night + 2400)
assert len(said) == 2 and len(cheers) == 3                   # the tick box: screen only
# the Den's line
lines = asyncio.run(app.command("LAIR"))
d = dict(l.split("=", 1) for l in lines[:-1])
assert d["aurora_south"] == "0" and float(d["aurora_camera"]) == cam and d["aurora_kp"]
with open("bt_dragon/den.html", encoding="utf-8") as f:
    den = f.read()
assert 'id="say_lair_aurora"' in den and "'say_lair_aurora'" in den and 'id="lairAurora"' in den
print("aurora ok")
