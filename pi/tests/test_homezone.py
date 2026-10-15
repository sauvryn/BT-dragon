"""The home zone, the 90-day limit on wardriving sightings, daily friend-beacon IDs, and gadget
names kept as broadcast."""
import asyncio
import os
import random
import statistics
import tempfile
import time

from bt_dragon import ble, config, friends, homezone as hz
from bt_dragon.app import Dragon
from bt_dragon.store import Store

HOME = (51.5010, -0.1416)          # (London)

# the moved center: always within half a radius of home, every direction, and spread out
rng = random.Random(7)
for r in hz.SIZES:
    pts = [hz.moved(*HOME, r, rng) for _ in range(2000)]
    d = [hz.distance_m(*HOME, *p) for p in pts]
    assert max(d) <= r / 2 + 0.5 and statistics.mean(d) > r / 4, (r, max(d), statistics.mean(d))
    north = sum(1 for p in pts if p[0] > HOME[0]) / len(pts)
    east = sum(1 for p in pts if p[1] > HOME[1]) / len(pts)
    assert 0.45 < north < 0.55 and 0.45 < east < 0.55
assert abs(hz.distance_m(51.5, -0.14, 51.5, -0.1256) - 1000) < 15

# the zone itself, and sightings inside it being deleted
st = Store(os.path.join(tempfile.mkdtemp(), "h.db"))
z = hz.HomeZone(st)
assert z.state() == {"on": False, "r": 500, "set": False} and not z.inside(*HOME)
st.ap_observe("AA", time.time(), -50, {"lat": HOME[0], "lon": HOME[1]})
st.ap_observe("BB", time.time(), -50, {"lat": HOME[0] + 0.05, "lon": HOME[1]})     # 5.5 km north
assert z.set_here({"lat": HOME[0], "lon": HOME[1]}, 500) == 1
saved = st.get("home_zone")
assert saved["on"] and saved["r"] == 500 and (saved["lat"], saved["lon"]) != HOME     # home itself isn't stored
assert z.inside(*HOME) and not z.inside(HOME[0] + 0.05, HOME[1])
assert [r[0] for r in st.db.execute("SELECT bssid FROM ap_obs")] == ["BB"]
z.off()
assert not z.inside(*HOME) and z.state()["set"]

# the 90-day limit, uploaded or not
now = time.time()
st.ap_observe("CC", now - 91 * 86400, -60, {"lat": 0, "lon": 0})
st.ap_observe("DD", now - 89 * 86400, -60, {"lat": 0, "lon": 0})
assert st.prune_obs(now) == 1
assert {r[0] for r in st.db.execute("SELECT bssid FROM ap_obs")} == {"BB", "DD"}

# the app: sightings inside the zone are never recorded; the commands
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
run = lambda c: asyncio.run(app.command(c))                             # noqa: E731
fix = {"lat": HOME[0], "lon": HOME[1], "acc": 5}
app.gps.current = lambda: dict(fix)
app.clock_ok = lambda: True


def ap(b):
    return {"bssid": b, "ssid": "Net " + b, "auth": "[WPA2-PSK-CCMP][ESS]", "security": "wpa2",
            "channel": 6, "freq": 2437, "rssi": -60}


def sightings():
    return app.store.db.execute("SELECT COUNT(*) FROM ap_obs").fetchone()[0]


app.handle_aps([ap("01:00:00:00:00:01")])
assert sightings() == 1
assert run("HOMEZONE")[:3] == ["on=0", "r=500", "set=0"]
assert run("HOMEZONESET on") == ["OK 1"] and sightings() == 0          # the one at home went
app.handle_aps([ap("01:00:00:00:00:02")])
assert sightings() == 0                                                  # at home: not recorded
assert app.store.ap_count() == 2                                         # (but still eaten)
fix.update(lat=HOME[0] + 0.05)                                           # out for a walk
app._obs_last.clear()
app.handle_aps([ap("01:00:00:00:00:03")])
assert sightings() == 1
assert run("HOMEZONESET here 300")[0].startswith("ERR") and run("HOMEZONESET sideways")[0].startswith("ERR")
assert run("HOMEZONESET off") == ["OK"] and run("HOMEZONE")[0] == "on=0"
assert run("HOMEZONESET on") == ["OK 0"] and run("HOMEZONE")[:3] == ["on=1", "r=500", "set=1"]   # the old place
app.gps.current = lambda: None
assert run("HOMEZONESET here 1000")[0].startswith("ERR")                # no GPS: no new home
assert not any("home zone" in str(e).lower() and "off" not in str(e).lower() for e in app.store.events(50))

# daily friend IDs: the same all day, different the next, unrelated without the key
ids = friends.DragonId(Store(os.path.join(tempfile.mkdtemp(), "f.db")))
t = time.mktime((2026, 10, 15, 9, 0, 0, 0, 0, -1))
assert ids.today(t) == ids.today(t + 3600 * 10) and ids.today(t) != ids.today(t + 86400)
assert len(ids.today(t)) == 4 and ids.is_mine(ids.today(t).hex(), t) and not ids.is_mine("00000000", t)
other = friends.DragonId(Store(os.path.join(tempfile.mkdtemp(), "g.db")))
assert other.today(t) != ids.today(t)
# a friend with a new day's ID is still the same friend (same name, level the same or higher)
book = friends.FriendBook(Store(os.path.join(tempfile.mkdtemp(), "b.db")), ids)
assert book.heard({"id": "aaaa0001", "name": "Ember", "level": 4, "mood": 0}, -60, t) == "new"
assert book.heard({"id": "bbbb0002", "name": "Ember", "level": 5, "mood": 0}, -60, t + 86400) == "again"
assert book.count() == 1 and book.all()[0]["id"] == "bbbb0002" and book.all()[0]["meetings"] == 2
assert book.heard({"id": "cccc0003", "name": "Ember", "level": 2, "mood": 0}, -60, t + 2 * 86400) == "new"
assert book.heard({"id": ids.today(t).hex(), "name": "Me", "level": 1, "mood": 0}, -60, t) is None   # himself
assert app.beacon_payload()[3:7] == app.dragon_id.today()

# gadget names are kept as broadcast (only numbers hidden)
assert ble.species_from_name("Sam's AirPods") == "Sam's AirPods"
assert ble.species_from_name("AirPods de Marie") == "AirPods de Marie"
assert ble.species_from_name("JBL Flip 5") == "JBL Flip #" and ble.species_from_name("A1:B2:C3:D4:E5:F6") is None
print("homezone ok")
