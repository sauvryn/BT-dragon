"""Conquest points: counted from what's been claimed, in the diary with each claim, on the Den
and the map, titles along the way, and "Forget my map" taking the map's points back off. And
the Butterfly Garden's adults, collected from the den, with their points in the diary too."""
import asyncio
import tempfile
import time

from bt_dragon import config, conquest, tuning
from bt_dragon.app import Dragon

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
run = lambda c: asyncio.run(app.command(c))                             # noqa: E731
st = app.store
assert conquest.score(st) == 0 and conquest.title(0) == "Fledgling Forager"

# a baby (level 1-4) can't claim land yet: from level 5, or with "Unlock now (prototype testing)"
LAT, LON = 51.5007, -0.1246
t = time.time()
assert not app.explore_open()
app._visit_land({"lat": LAT, "lon": LON, "acc": 5, "ts": t, "speed": 1.4})
assert st.land_counts() == (0, 0) and run("STATUS") and "explore_open=False" in run("STATUS")
assert "locked=" not in str(app.map_data()) and app.map_data()["locked"] == 5
assert run("EXPLOREUNLOCK on") == ["OK"] and app.explore_open() and app.map_data()["locked"] is None
# claims as they happen: walking through new squares of the map
for i in range(12):
    app._visit_land({"lat": LAT, "lon": LON + i * 0.004, "acc": 5, "ts": t + i * 60, "speed": 1.4})
lands, realms = st.land_counts()
assert lands >= 10 and realms >= 1
diary = [e["text"] for e in st.events(200) if e["kind"] == "land"]
assert any(x.endswith("+10 Conquest points.") and "claimed a new land" in x for x in diary), diary
assert any(x.endswith("+60 Conquest points.") and "claimed a new realm" in x for x in diary), diary
s, title = app.conquest_score(fresh=True)
assert s == lands * 10 + realms * 50
assert any(x.startswith("New conquest title: Wandering Wyrmling") for x in diary) == (s >= 250)

# stars and a new constellation
st.star_seen("gps-1", "GPS", 1, t)
st.star_seen("gal-2", "Galileo", 2, t)
assert conquest.counts(st)["star"] == 2 and conquest.counts(st)["constellation"] == 2
assert conquest.score(st) == s + 2 * 20 + 2 * 80

# the knobs change what everything is worth, at once
run("TUNE conquest_land 20")
assert conquest.score(st) == lands * 20 + realms * 50 + 2 * 20 + 2 * 80
tuning.reset("points")

# the Den and the map
app.conquest_score(fresh=True)
v = app.view()
assert v["conquest"] == conquest.score(st) and v["conquest_title"] and "conquest_next" in v
m = app.map_data()
assert m["conquest"] == v["conquest"] and m["conquest_title"] == v["conquest_title"]
with open("bt_dragon/map.html", encoding="utf-8") as f:
    assert 'id="score"' in f.read()
with open("bt_dragon/den.html", encoding="utf-8") as f:
    den = f.read()
assert 'id="cqScore"' in den and 'id="knobs-points"' in den

# forgetting the map takes its points back off (the stars stay)
run("FORGETMAP")
assert app.conquest_score()[0] == 2 * 20 + 2 * 80

# titles: in order, alliterative, and each announced once
assert [n for n, _, _ in conquest.TITLES] == sorted(n for n, _, _ in conquest.TITLES)
from bt_dragon.store import Store  # noqa: E402
st2 = Store(tempfile.mkdtemp() + "/t.db")
assert conquest.new_titles(st2, 100) == []
assert conquest.new_titles(st2, 1600) == ["Wandering Wyrmling", "Scouting Skald", "Roaming Raider"]
assert conquest.new_titles(st2, 1600) == []
assert conquest.next_title(1600) == (3000, "Trailblazing Thane") and conquest.next_title(10 ** 6) is None

# the garden: an adult waits for "tap to add to Collection", then its points go in the diary
app.pet.xp = 900
app.garden.unlock_now(app.pet.level())
app.garden.feed(0.01, app.pet.level())
b = app.garden.s["slots"][0]
b["fed"] = b["need"] * b["pupAt"] / 100 - 0.001
app.garden.feed(0.01, app.pet.level())
app.garden.check_pupae(time.time() + app.garden.pupa_s() + 1)
assert app.garden.s["slots"][0]["adult"] and app.garden.cdata(app.garden.country())["collection"] == []
assert run("GARDENCOLLECT 0") == ["OK"] and run("GARDENCOLLECT 0")[0].startswith("ERR")
app._garden_news = [x for x in app._garden_news if x[0] == "collect"]
app.pet.message_hold, app.pet.message_ts = 0, 0
app._garden_tick()
diary = [e["text"] for e in st.events(20) if e["kind"] == "garden"]
assert any("collection." in x and x.endswith("Butterfly Garden points.") for x in diary), diary
print("conquest ok")
