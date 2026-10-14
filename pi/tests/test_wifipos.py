"""Finding him by Wi-Fi (no GPS): which networks are asked about, what's sent, what's
believed, how sparingly he asks, and what a Wi-Fi position may and may not do: claim land
(only the square he's in), discover green spaces (never walks), and never reach WiGLE."""
import asyncio
import os
import sqlite3
import tempfile
import time

from bt_dragon import config, greens, tuning, wifipos as wp
from bt_dragon.app import Dragon
from bt_dragon.sky import LAND_M, Lands, grid_cell
from bt_dragon.store import Store

LAT, LON = 51.5000, -0.1200


def ap(bssid, rssi=-60, ssid="Net"):
    return {"bssid": bssid, "rssi": rssi, "ssid": ssid}


# which networks are worth asking about
assert not wp.moves_around("AC:84:C6:00:00:01") and wp.moves_around("DA:A1:19:00:00:01")   # 0xDA: a phone's
assert wp.moves_around("nonsense")
aps = [ap("AC:84:C6:00:00:01", -70), ap("AC:84:C6:00:00:02", -50), ap("DA:A1:19:00:00:03", -40, "Sam's phone"),
       ap("AC:84:C6:00:00:04", -45, "Cafe_nomap"), ap("AC:84:C6:00:00:05", -95), ap("AC:84:C6:00:00:06", -55, "MyHotspot")]
got = wp.usable(aps, {"MyHotspot"})
assert [a["bssid"][-2:] for a in got] == ["02", "01"], got           # loudest first
assert len(wp.usable([ap(f"AC:84:C6:00:01:{i:02X}") for i in range(40)])) == wp.MAX_NETWORKS

# what's sent: only the networks, and never "use my internet address instead"
body = wp.request_body(got)
assert body["considerIp"] is False and body["fallbacks"] == {"ipf": False, "lacf": False}
assert body["wifiAccessPoints"][0] == {"macAddress": "ac:84:c6:00:00:02", "signalStrength": -50}
assert set(body) == {"considerIp", "fallbacks", "wifiAccessPoints"}

# what's believed
assert wp.parse_answer({"location": {"lat": LAT, "lng": LON}, "accuracy": 35.2}) == (LAT, LON, 35.2)
assert wp.parse_answer({"location": {"lat": LAT, "lng": LON}, "accuracy": 5000}) is None   # a city-sized guess
assert wp.parse_answer({"error": {"code": 404}}) is None and wp.parse_answer({"location": {"lat": 99, "lng": 0}, "accuracy": 9}) is None

# when he asks
tmp = tempfile.mkdtemp()
store = Store(os.path.join(tmp, "d.db"))
asked = []


def fake(nets):
    asked.append([a["bssid"] for a in nets])
    return (LAT, LON, 40.0)


w = wp.WifiPosition(store, asker=fake)
here = [ap(f"AC:84:C6:00:00:{i:02X}", -50 - i) for i in range(6)]
T = 1_000_000.0
assert w.wanted(here, False, True, now=T) is None and w.status == "off"           # off by default
w.set_enabled(True)
assert w.wanted(here, True, True, now=T) is None and "GPS" in w.status           # GPS always wins
assert w.wanted(here, False, False, now=T) is None and "hotspot" in w.status     # needs the internet
assert w.wanted(here[:1], False, True, now=T) is None and "enough" in w.status  # one router can't place you
nets = w.wanted(here, False, True, now=T)
assert nets and len(nets) == 6
fix = asyncio.run(w.locate(nets, now=T))
assert fix["via"] == "wifi" and fix["acc"] == 40 and len(asked) == 1 and w.current() is fix
assert "40 m" in w.status
# still in the same place: no need to ask again, and the position stays fresh
w.fix["ts"] = T
assert w.wanted(here[:5] + [ap("AC:84:C6:00:09:99", -80)], False, True, now=T + 600) is None and w.fix["ts"] == T + 600
# somewhere new, but asked too recently: wait
elsewhere = [ap(f"AC:84:C6:00:05:{i:02X}", -55) for i in range(5)]
w.last_try = T + 550
assert w.wanted(elsewhere, False, True, now=T + 600) is None
assert w.wanted(elsewhere, False, True, now=T + 550 + wp.ASK_EVERY_S) is not None
# it doesn't know these networks: no position (and no guessing)
w.asker = lambda nets: None
asyncio.run(w.locate(elsewhere))
assert w.fix is None and "doesn't know" in w.status
w.set_enabled(False)
assert w.fix is None and not store.get("wifi_position")

# land: a Wi-Fi position claims only the square he's in, if it's precise enough
lands = Lands(store)
wf = {"lat": LAT, "lon": LON, "acc": 60, "ts": T, "via": "wifi"}
assert lands.visit(dict(wf, acc=tuning.get("land_wifi_accuracy_m") + 1)) is None
assert lands.visit(wf) == [True] and store.land_counts() == (1, 1)
edge = grid_cell(LAT, LON, LAND_M)
assert all(c == edge for c, _ in store.lands_all())
assert lands.visit({"lat": LAT, "lon": LON, "acc": 60, "ts": T}) is None          # GPS keeps its own, stricter limit

# green spaces: discovered by Wi-Fi, never walked
store.save_greens("R1", [g for g in greens.parse({"elements": [
    {"type": "way", "id": 1, "tags": {"leisure": "park", "name": "Oakfield Country Park"},
     "geometry": [{"lat": LAT - .0009, "lon": LON - .0015}, {"lat": LAT - .0009, "lon": LON + .0015},
                  {"lat": LAT + .0009, "lon": LON + .0015}, {"lat": LAT + .0009, "lon": LON - .0015},
                  {"lat": LAT - .0009, "lon": LON - .0015}]}]})], T)
gs = greens.Greens(store)
got = gs.update(wf, "walking")
assert [(w_, g["name"]) for w_, g in got] == [("found", "Oakfield Country Park")]
for i in range(1, 200):                                      # sitting in it for well over half an hour
    assert gs.update(dict(wf, ts=T + i * 15, lon=LON + (i % 3) * 0.0001), "walking") == []
park = store.greens_list()[0]
assert park["visits"] == 1 and park["walks"] == 0 and park["seen"]
assert gs.update(dict(wf, acc=150), "walking") == []

# older databases get the new columns
old = os.path.join(tmp, "old.db")
db = sqlite3.connect(old)
db.execute("CREATE TABLE greens (id TEXT PRIMARY KEY, name TEXT, kind TEXT, lat REAL, lon REAL, minlat REAL, "
           "minlon REAL, maxlat REAL, maxlon REAL, area REAL, rings TEXT, realm TEXT, first_seen REAL, "
           "last_seen REAL, visits INT DEFAULT 0)")
db.commit()
db.close()
s2 = Store(old)
assert {"walks", "runs", "rides"} <= {r[1] for r in s2.db.execute("PRAGMA table_info(greens)")}
Store(old)                                                   # and opening it again is fine

# the whole dragon: nothing found by Wi-Fi goes towards WiGLE
cfg = config.load(None)
cfg["data_dir"] = tmp2 = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tmp2)
app.wifipos.fix = {"lat": LAT, "lon": LON, "acc": 40, "alt": 0.0, "ts": time.time(), "via": "wifi"}
assert app.gps.current() is None and app.where_now()["via"] == "wifi"
app.handle_aps([dict(ap("AC:84:C6:00:07:01", -50, "Corner Cafe"), auth="[WPA2-PSK-CCMP][ESS]", security="wpa2",
                     channel=6, freq=2437)])
assert app.store.ap_count() == 1                                            # a treat all the same
assert app.store.db.execute("SELECT COUNT(*) FROM ap_obs").fetchone()[0] == 0  # but no WiGLE sighting
assert app.map_data()["here"]["wifi"] is True


async def den():
    r = await app.command("WIFIPOS")
    assert r[0] == "on=0", r
    assert await app.command("WIFIPOSSET on") == ["OK"] and app.wifipos.enabled
    r = await app.command("WIFIPOS")
    assert r[0] == "on=1"
    assert (await app.command("GREENS"))[-1] == "END"
    await app.command("WIFIPOSSET off")
    assert not app.wifipos.enabled
asyncio.run(den())
print("wifipos ok")
