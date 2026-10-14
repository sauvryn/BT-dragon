"""Green spaces: OpenStreetMap's answer (in its real format) turned into outlines, being
inside one, walks, runs and rides, the database, his words, the map and the questions."""
import asyncio
import os
import tempfile
import time

from bt_dragon import ask, greens, tuning
from bt_dragon.app import Dragon
from bt_dragon.dot import DotLink, build_recap
from bt_dragon.store import Store

LAT, LON = 51.5000, -0.1200
DLAT, DLON = 0.0009, 0.0015          # about 100 m each way


def square(lat, lon, dlat, dlon):
    return [{"lat": lat - dlat, "lon": lon - dlon}, {"lat": lat - dlat, "lon": lon + dlon},
            {"lat": lat + dlat, "lon": lon + dlon}, {"lat": lat + dlat, "lon": lon - dlon},
            {"lat": lat - dlat, "lon": lon - dlon}]


wood = square(LAT + 0.01, LON, DLAT, DLON)
OVERPASS = {"elements": [
    {"type": "way", "id": 1, "tags": {"leisure": "park", "name": "Oakfield Country Park"},
     "geometry": square(LAT, LON, DLAT, DLON)},
    {"type": "way", "id": 2, "tags": {"leisure": "park"}, "geometry": square(LAT, LON, DLAT, DLON)},  # no name
    {"type": "way", "id": 3, "tags": {"leisure": "garden", "name": "Private Garden", "access": "private"},
     "geometry": square(LAT, LON, DLAT, DLON)},
    {"type": "way", "id": 4, "tags": {"leisure": "park", "name": "Pocket Park"},
     "geometry": square(LAT, LON, 0.0002, 0.0003)},                                              # too small
    {"type": "relation", "id": 5, "tags": {"natural": "wood", "name": "Fernhill Vale"},             # in two pieces
     "members": [{"type": "way", "ref": 50, "role": "outer", "geometry": wood[:3]},
                 {"type": "way", "ref": 51, "role": "outer", "geometry": wood[2:][::-1]},
                 {"type": "way", "ref": 52, "role": "inner", "geometry": square(LAT + 0.01, LON, 0.0001, 0.0001)}]},
    {"type": "way", "id": 6, "tags": {"amenity": "parking", "name": "Car Park"}, "geometry": square(LAT, LON, DLAT, DLON)},
]}

# what to ask for
q = greens.query(1, 2, 3, 4)
assert q.startswith("[out:json]") and q.endswith("out geom;") and 'way["leisure"="park"]["name"](1.000000' in q
assert 'relation["natural"="wood"]["name"]' in q and 'way["landuse"="village_green"]["name"]' in q

# reading the answer
found = greens.parse(OVERPASS)
assert [(g["id"], g["name"], g["kind"]) for g in found] == [("w1", "Oakfield Country Park", "park"), ("r5", "Fernhill Vale", "wood")]
park, vale = found
assert 38000 < park["area"] < 42000 and len(vale["rings"]) == 1 and len(vale["rings"][0]) == 5, vale
assert greens.stitch([[(0, 0), (0, 1)], [(1, 1), (0, 1)], [(1, 1), (1, 0), (0, 0)]]) == [[(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]]
line = [(51.5, -0.12 + i * 0.0001) for i in range(20)] + [(51.501, -0.118), (51.5, -0.12)]
assert len(greens.simplify(line, 4)) < 8

# inside, near, outside
assert greens.locate(park, LAT, LON) == (0.0, (LAT, LON))
d, pt = greens.locate(park, LAT, LON + DLON + 0.0003)          # ~20 m east of the east edge
assert 15 < d < 25 and abs(pt[1] - (LON + DLON)) < 1e-6, (d, pt)
assert 900 < greens.locate(vale, LAT, LON)[0] < 1100

# kept on the Pi
tmp = tempfile.mkdtemp()
store = Store(os.path.join(tmp, "dragon.db"))
store.save_greens("R1", found, 1000.0)
assert store.greens_fetched("R1") == 1000.0 and store.greens_fetched("R2") is None
assert [g["name"] for g in store.greens_near(LAT, LON, 20)] == ["Oakfield Country Park"]
assert [g["name"] for g in store.greens_list()] == ["Fernhill Vale", "Oakfield Country Park"]
PARK = lambda: next(g for g in store.greens_list() if g["id"] == "w1")  # noqa: E731
assert PARK()["rings"] == park["rings"] and not PARK()["seen"]


# being there
def walk(gs, minutes, mode, start, lat=LAT, lon=LON, step_s=5, east_m_per_step=6):
    """Fixes every few seconds, moving back and forth inside the park."""
    out, t = [], start
    for i in range(int(minutes * 60 / step_s)):
        wobble = (i % 20 - 10) * east_m_per_step / 111320 / 0.6225
        out += gs.update({"lat": lat, "lon": lon + wobble, "ts": t, "acc": 8}, mode)
        t += step_s
    return out, t


T0 = time.mktime(time.localtime()[:3] + (10, 0, 0, 0, 0, -1))   # 10am today, so saving and reloading stays on one day
gs = greens.Greens(store)
got, t = walk(gs, 9.5, "walking", T0)
assert [(w, g["name"]) for w, g in got] == [("found", "Oakfield Country Park")], got
assert PARK()["seen"]
got, t = walk(gs, 1, "walking", t)
assert [w for w, _ in got] == ["walk"], got
got, t = walk(gs, 20, "walking", t)                             # once a day
assert got == [] and "w1" in gs.today

# a ride: 5 minutes; a vehicle never counts; a short trip out doesn't reset the clock
store.db.execute("UPDATE greens SET first_seen=NULL")
gs = greens.Greens(store)
gs.today = set()
got, t = walk(gs, 10, "vehicle", T0, east_m_per_step=9)
assert [w for w, _ in got] == ["found"], got                    # driving through still discovers it
got, t = walk(gs, 3, "cycling", t, east_m_per_step=8)
assert got == []
got, t = walk(gs, 3, "cycling", t, lat=LAT + 0.005)             # out of the park for 3 minutes
got, t = walk(gs, 2.1, "cycling", t, east_m_per_step=8)
assert [w for w, _ in got] == ["bike"], got
# a run, after a long time away (the clock started again)
gs = greens.Greens(store)
gs.today = set()
got, t = walk(gs, 3, "running", T0)
got, t = walk(gs, 6, "walking", t, lat=LAT + 0.005)
got, t = walk(gs, 4.9, "running", t)
assert got == [], got
got, t = walk(gs, 0.2, "running", t)
assert [w for w, _ in got] == ["run"], got
# sitting on a bench for 10 minutes isn't a walk
gs = greens.Greens(store)
gs.today = set()
got, t = walk(gs, 12, "still", T0, east_m_per_step=0)
assert got == [], got
# the knobs
tuning._over["green_walk_min"] = 2
gs = greens.Greens(store)
gs.today = set()
got, t = walk(gs, 2.2, "walking", T0)
assert [w for w, _ in got] == ["walk"]
del tuning._over["green_walk_min"]
gs.save()
assert greens.Greens(store).today == {"w1"}
assert PARK()["walks"] >= 1 and PARK()["runs"] >= 1 and PARK()["visits"] >= 1, PARK()   # counted per green space

# fetching (OpenStreetMap replaced by the canned answer)
gs2 = greens.Greens(Store(os.path.join(tmp, "fetch.db")), fetcher=lambda realm: greens.parse(OVERPASS))
realm = gs2.wanted({"lat": LAT, "lon": LON})
assert realm
asyncio.run(gs2.fetch(realm))
assert gs2.wanted({"lat": LAT, "lon": LON}) is None and len(gs2.store.greens_list()) == 2


def boom(realm):
    raise OSError("no internet")


gs3 = greens.Greens(Store(os.path.join(tmp, "fail.db")), fetcher=boom)
r3 = gs3.wanted({"lat": LAT, "lon": LON})
asyncio.run(gs3.fetch(r3))
assert gs3.wanted({"lat": LAT, "lon": LON}) is None                 # not again for 10 minutes

# his words, and the app putting it together
assert greens.visit_words("walk", "Oakfield Country Park") == "Took a walk in Oakfield Country Park!"
assert greens.visit_words("run", "Oakfield Country Park") == "Went for a run in Oakfield Country Park!"
assert greens.visit_words("bike", "Fernhill Vale") == "Biked through Fernhill Vale!"


class Obj:
    pass


said, spoken, events = [], [], []
app = Obj()
app.greens = greens.Greens(store)
app.greens.today = set()
store.db.execute("UPDATE greens SET first_seen=NULL")
app.home_ssid, app.simulate = "Home", False
app.activity = Obj()
app.activity.motion = Obj()
app.activity.motion.mode = "walking"
app.pet = Obj()
app.pet.name = "Harald"
app.pet.green_found = lambda name: said.append(("found", name))
app.pet.green_visit = lambda words: said.append(("visit", words))
app.dot = Obj()
app.dot.adventure = lambda kind, **k: spoken.append((kind, k))
app.event = lambda kind, text: events.append((kind, text))
app.greens.wanted = lambda fix: None
t = T0
for i in range(130):
    Dragon._green_tick(app, {"lat": LAT, "lon": LON + (i % 20 - 10) * 6 / 69300, "ts": t, "acc": 8})
    t += 5
assert said == [("found", "Oakfield Country Park"), ("visit", "Took a walk in Oakfield Country Park!")], said
assert spoken == [("green_found", {"name": "Oakfield Country Park"}),
                  ("green_visit", {"text": "Took a walk in Oakfield Country Park!"})], spoken
assert events == [("green", "Harald found a new green space: Oakfield Country Park"),
                  ("green", "Harald: Took a walk in Oakfield Country Park!")], events
recap = build_recap("Harald", [{"kind": k, "text": x} for k, x in events], 0, 0, 3600)
assert "We went to Oakfield Country Park!" in recap, recap

# the pet: joy, XP and his screen
from bt_dragon.pet import Pet  # noqa: E402
pet = Pet(Store(os.path.join(tmp, "pet.db")), "Harald")
pet.on_say = None
xp, joy = pet.xp, pet.joy
pet.green_found("Fernhill Vale")
assert pet.xp == xp + tuning.get("green_xp") and pet.joy >= joy
pet.green_visit("Biked through Fernhill Vale!")
assert pet.xp == xp + tuning.get("green_xp") + tuning.get("green_visit_xp")

# the questions
P = ask.parse
assert P("where is the closest park") == {"intent": "where", "name": None, "nearest": True, "unseen": False, "green": True}
assert P("what's the nearest green space")["green"] and P("where are the nearest woods")["green"]
assert P("what is the closest unexplored park")["unseen"] and P("closest park i haven't been to")["unseen"]
assert P("what is the nearest park i haven't explored")["unseen"]
assert "green" not in P("what is the closest landmark")
assert P("where is oakfield country park") == {"intent": "where", "name": "oakfield country park"}
assert all(w in ask.VOCABULARY for p in ask.PHRASES for w in p.split())

d = Obj()
d._was = DotLink._was
for m in ("known_landmarks", "known_greens", "_way_to", "_here", "answer_where", "answer_nearest", "saw_landmark",
          "grammar"):
    setattr(d, m, getattr(DotLink, m).__get__(d))
dapp = Obj()
dapp.landmarks, dapp.greens, dapp.store = None, True, store
dapp.gps = Obj()
dapp.gps.fix = {"lat": LAT + 0.0045, "lon": LON, "ts": time.time()}     # 400 m north of the park
d.app, d.last_landmark = dapp, None
d.shopping = Obj()
d.shopping.words = lambda: []
A = lambda text: d.answer_where(ask.parse(text))  # noqa: E731
store.db.execute("UPDATE greens SET first_seen=?, last_seen=? WHERE id='w1'", (time.time(), time.time()))
store.db.execute("UPDATE greens SET first_seen=NULL, last_seen=NULL WHERE id='r5'")
r = A("where is the closest park")
assert r == ("The nearest green space I know of is Oakfield Country Park, 400 meters to the south, about a quarter "
             "of a mile. I last explored it today."), r
r = A("what is the closest unexplored park")
assert r.startswith("The nearest green space I haven't explored yet is Fernhill Vale, ") and "to the north" in r, r
assert A("how far is it").startswith("Fernhill Vale is ")
assert A("where is oakfield country park").startswith("Oakfield Country Park is 400 meters to the south")
assert A("which way is fernhill vale").startswith("Fernhill Vale is ")
dapp.gps.fix = {"lat": LAT, "lon": LON, "ts": time.time()}
assert A("where is the nearest park") == "We're in Oakfield Country Park right now!"
assert A("where is oakfield country park") == "We're in Oakfield Country Park right now!"
store.db.execute("UPDATE greens SET first_seen=1, last_seen=1")
assert A("closest unexplored park").startswith("I've explored every green space I know of around here")
g = d.grammar()
assert "oakfield country park" in g and "fernhill vale" in g and "oakfield" in g
print("greens ok")
