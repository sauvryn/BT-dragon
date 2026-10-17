"""Achievements: Bookworm's five stages (spread over a whole collection, or fixed milestones),
counted from what's been collected; the first count is quiet; new stages go in the diary and on
his screen; stages that no longer count are taken away; the Den's summary and the page."""
import asyncio
import json
import math
import socket
import tempfile
import threading
import time
import urllib.request

from bt_dragon import achievements as ach, config, journal, server
from bt_dragon.app import Dragon

# ---- the stages: Bookworm's rule (thresholds ceil(k*total/5); under 5, the lowest skipped)
assert ach.steps(total=10) == [(0, 2), (1, 4), (2, 6), (3, 8), (4, 10)]
assert ach.steps(total=33) == [(k, math.ceil((k + 1) * 33 / 5)) for k in range(5)]
assert ach.steps(total=2) == [(3, 1), (4, 2)] and ach.steps(total=0) == []
assert ach.steps(fixed=(10, 50, 250, 1000, 5000))[0] == (0, 10)
assert ach.stage(0, ach.steps(total=10)) == -1 and ach.stage(5, ach.steps(total=10)) == 1
assert ach.stage(10, ach.steps(total=10)) == 4

# ---- no two categories share a rune, and every rune is in Harald's font
from bt_dragon.fonts import RUNES
runes = [s[2] for s in ach.SECTIONS]
assert len(set(runes)) == len(runes) and all(r in RUNES for r in runes)
assert dict((s[0], s[3]) for s in ach.SECTIONS)["gadgets"] == "G (the Gebo rune) for Gadgets" and dict((s[0], s[2]) for s in ach.SECTIONS)["gadgets"] == "ᚷ" and dict((s[0], s[2]) for s in ach.SECTIONS)["stars"] == "ᛊ"

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
st = app.store
now = time.time()

# something collected before achievements existed: counted without fuss
for i in range(12):
    st.land_seen(f"c{i}", f"r{i // 6}", now)
fresh = app.check_achievements(now)
assert fresh and all(a["id"] != "l-realms" or m == 0 for a, m in fresh)        # 2 realms: Copper
ev = [r[0] for r in st.db.execute("SELECT text FROM events WHERE kind='achievement'")]
assert len(ev) == 1 and "already been collected" in ev[0], ev
rec = st.get("achievements")
assert rec["l-lands"]["m"] == 0 and "copper" in rec["l-lands"]["dates"]

# a new stage: in the diary and on his screen
for i in range(12, 50):
    st.land_seen(f"c{i}", f"r{i // 6}", now)
fresh = app.check_achievements(now + 10)
ids = {a["id"]: m for a, m in fresh}
assert ids.get("l-lands") == 1, ids                                          # 50 lands: Bronze
ev = [r[0] for r in st.db.execute("SELECT text FROM events WHERE kind='achievement' ORDER BY id")]
assert any("Bronze runestone: Land Claimer (50 lands)" in e for e in ev), ev
assert "RUNESTONE" in app.pet.message or "BRONZE" in app.pet.message or "COPPER" in app.pet.message, app.pet.message
assert app.check_achievements(now + 20) == []                                # nothing new: nothing said

# gadgets: catalogue types by group and rarity, and field finds
lab = journal.CATALOGUE[0][5][0]
st.species_seen("k1", lab, "phone", now)
for i in range(5):
    st.species_seen(f"f{i}", f"Maker {i}", "maker", now)
achs = {a["id"]: a for a in app.achievement_list(fresh=True)}
assert achs["g-journal"]["n"] == 1 and achs["g-journal"]["goal"] == len(journal.CATALOGUE)
assert achs["g-field"]["n"] == 5 and achs["g-phones"]["n"] == 1
# Wi-Fi by kind (a car's network is mobile, not WPA2)
for i, (ssid, auth) in enumerate([("Home", "[WPA2-PSK-CCMP][ESS]"), ("Cafe", "[ESS]"),
                                  ("VW_WLAN_1234", "[WPA2-PSK-CCMP][ESS]"), ("New", "[WPA3-SAE-CCMP][ESS]")]):
    st.db.execute("INSERT INTO aps (bssid, ssid, auth, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                  (f"aa:{i}", ssid, auth, now, now))
achs = {a["id"]: a for a in app.achievement_list(fresh=True)}
assert (achs["w-all"]["n"], achs["w-wpa2"]["n"], achs["w-open"]["n"], achs["w-mobile"]["n"], achs["w-wpa3"]["n"]) == (4, 1, 1, 1, 1)

# the Butterfly Garden: Bookworm's achievements (categories by country name, rarities, sightings, meta)
from bt_dragon.garden import data
sp = data()["countries"]["gb"]["species"]
bfly = [s for s in sp if s["kind"] == "butterfly"]
app.garden.cdata("gb")["collection"].extend({"species": s["id"], "points": 100} for s in bfly[:11])
achs = {a["id"]: a for a in app.achievement_list(fresh=True)}
a = achs["b-gb-all-butterfly"]
assert a["name"] == "Butterfly House" and a["n"] == 11 and a["goal"] == len(bfly)
assert achs["b-meta-gb"]["n"] == 11 and "b-meta-rare" in achs and "b-gb-seen-50" in achs
app.garden.cdata("gb")["seen"] = {bfly[0]["id"]: ["young", "pupa", "adult"]}
achs = {a["id"]: a for a in app.achievement_list(fresh=True)}
assert achs["b-gb-seen-stages-5"]["n"] == 1 and achs["b-gb-seen-50"]["n"] == 1

# stars per constellation, never more than there are
for p in range(1, 40):
    st.db.execute("INSERT INTO stars VALUES (?, 'GPS', ?, ?, ?, 1)", (f"GPS-{p}", p, now, now))
achs = {a["id"]: a for a in app.achievement_list(fresh=True)}
assert achs["s-gps"]["n"] == 31 and achs["s-stars"]["n"] == 39 and achs["s-consts"]["n"] == 1

# forgetting the map: its stages are taken away quietly
app.check_achievements(now + 30)
st.forget_lands()
app.check_achievements(now + 40)
rec = st.get("achievements")
assert "l-lands" not in rec and "l-realms" not in rec

# napping: nothing counted or written
app.napping = True
st.land_seen("zz", "rz", now)
assert app.check_achievements(now + 50) == []
app.napping = False

# the Den's summary
v = app.view()["achievements"]
assert v["earned"] >= 1 and v["latest"] and v["latest"]["rune"] in runes and v["latest"]["tier"] in ach.TIERS

# the page (and its locks before level 5)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
app.cfg["link"]["web_port"] = port
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
html = urllib.request.urlopen(f"http://127.0.0.1:{port}/achievements", timeout=20).read().decode()
assert "__DATA__" not in html and "__RUNEFONT__" not in html
d = json.loads(html.split("const DATA = ", 1)[1].split(";\nconst FONT", 1)[0])
keys = [x["key"] for x in d["sections"]]
assert keys[:2] == ["gadgets", "wifi"] and "garden" in keys and "sky" in keys
lock = {x["key"]: x["locked"] for x in d["sections"]}
assert lock["lands"] and lock["stars"] and lock["garden"] and not lock["gadgets"]
den = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=20).read().decode()
assert 'href="/achievements"' in den and "Open Achievements" in den
print("test_achievements: OK")
# every category's rune is named and explained on the page, and its label names it
names = {r: n for r, n, _ in ach.RUNE_MEANINGS}
assert all(s[2] in names and f"the {names[s[2]]} rune" in s[3] for s in ach.SECTIONS)
assert d["runes"] and len(d["runes"]) == len(ach.SECTIONS)
print("rune names ok")
