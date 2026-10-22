"""Libraries (treasure troves): parsed from OpenStreetMap; "NEW TROVE!" the first time, "TREASURE
TROVE!" another day; a library that's also a famous place is announced once, in the library's
words, and counts for both; Conquest points, achievements (ᛏ), the Den list and the map."""
import asyncio
import os
import tempfile
import time

from bt_dragon import achievements as ach, config, conquest, libraries, tuning
from bt_dragon.app import Dragon

LAT, LON = 51.5299, -0.1270          # (London)
OSM = {"elements": [
    {"type": "node", "id": 1, "lat": LAT, "lon": LON, "tags": {"amenity": "library", "name": "Ordinary Library"}},
    {"type": "way", "id": 2, "center": {"lat": LAT + 0.01, "lon": LON}, "tags": {"amenity": "library",
     "name": "The Great Library", "wikidata": "Q23308"}},
    {"type": "way", "id": 3, "center": {"lat": LAT, "lon": LON + 0.01}, "tags": {"amenity": "library",
     "name": "Staff Library", "access": "private"}},
    {"type": "node", "id": 4, "lat": LAT, "lon": LON, "tags": {"amenity": "library"}},     # no name
    {"type": "relation", "id": 5, "center": {"lat": LAT - 0.01, "lon": LON}, "tags": {"amenity": "library",
     "name": "Riverside Library"}}]}
libs = libraries.parse(OSM)
assert [b["name"] for b in libs] == ["Ordinary Library", "The Great Library", "Riverside Library"]
assert libs[1]["qid"] == "Q23308" and libs[1]["id"] == "w2" and libs[0]["qid"] == ""
assert 'nwr["amenity"="library"]["name"]' in libraries.query(1, 2, 3, 4)
# matching a landmark
assert libraries.same_place({"name": "X", "lat": 0, "lon": 0, "qid": "Q1"}, {"qid": "Q1", "title": "Other", "lat": 5, "lon": 5})
assert libraries.same_place({"name": "Riverside Library", "lat": LAT, "lon": LON, "qid": ""},
                            {"qid": "Q9", "title": "Riverside Public Library", "lat": LAT + 0.001, "lon": LON})
assert not libraries.same_place({"name": "Riverside Library", "lat": LAT, "lon": LON, "qid": ""},
                                {"qid": "Q9", "title": "Riverside Library", "lat": LAT + 0.01, "lon": LON})   # 1 km away
assert not libraries.same_place({"name": "Riverside Library", "lat": LAT, "lon": LON, "qid": ""},
                                {"qid": "Q9", "title": "Riverside Church", "lat": LAT, "lon": LON})

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
app.store.put("explore_unlocked", True)
app.store.save_libraries("r", libs, time.time())
for realm in ("r",):
    pass
# every realm already asked (no internet here)
app.libraries.wanted = lambda fix: None
app.landmarks.wanted = lambda fix: None
# a famous place that is "The Great Library" (same Wikidata ID), and one that isn't a library
app.store.save_landmarks("r", [{"qid": "Q23308", "title": "Great Library of the City", "lat": LAT + 0.01, "lon": LON,
                                "langs": 40},
                               {"qid": "Q77", "title": "Famous Tower", "lat": LAT - 0.02, "lon": LON, "langs": 40}],
                         time.time())
said, adv = [], []
app.pet.say = lambda text, mood=None, seconds=20, speak=True: said.append(text if isinstance(text, str) else text[0])
app.dot.adventure = lambda kind, **k: adv.append((kind, k))


def at(lat, lon):
    said.clear()
    app._look_around({"lat": lat, "lon": lon, "ts": time.time(), "acc": 8})
    return list(said)


# the first time: NEW TROVE, points, XP
xp0 = app.pet.xp
s0 = conquest.score(app.store, tuning.get("landmark_langs"))
assert at(LAT, LON + 30 / 69300) == ["NEW TROVE! ORDINARY LIBRARY!"]          # 30 m away
assert app.pet.xp - xp0 == tuning.get("trove_xp")
assert conquest.score(app.store, tuning.get("landmark_langs")) - s0 == tuning.get("conquest_trove") == 75
assert adv[-1] == ("trove", {"name": "Ordinary Library", "first": True})
assert at(LAT, LON) == []                                                      # once a day
assert at(LAT, LON + 120 / 69300) == []                                       # (120 m: too far anyway)
# another day: TREASURE TROVE
app.libraries.today = set()
app.libraries._day = "2000-01-01"
assert at(LAT, LON) == ["TREASURE TROVE! ORDINARY LIBRARY!"]
ev = [e for e in app.store.events(20) if e["kind"] == "trove"] if hasattr(app.store, "events") else []

# the famous library: announced once, from the landmark's distance (200 m away here), in the library's words
s1 = conquest.score(app.store, tuning.get("landmark_langs"))
got = at(LAT + 0.01 - 200 / 111320, LON)
assert got[0] == "NEW TROVE! THE GREAT LIBRARY!" and not any(g.startswith("LOOK!") for g in got), got
assert conquest.score(app.store, tuning.get("landmark_langs")) - s1 == 75 + tuning.get("conquest_landmark")
assert app.dot.last_landmark[0]["qid"] == "Q23308"
assert at(LAT + 0.01, LON) == []                                               # right outside: nothing more today
lm = {x["qid"]: x for x in app.store.landmarks_list(0)}
assert lm["Q23308"]["first_seen"] and [b for b in app.store.libraries_list() if b["id"] == "w2"][0]["first_seen"]
# an ordinary landmark is still "LOOK!"
assert at(LAT - 0.02, LON) == ["LOOK! FAMOUS TOWER!"]
# a famous library reached first by its own 60 m (landmark not yet in range is impossible: the landmark
# reach is larger), and a library matched by name
app.store.save_libraries("r", [{"id": "n9", "name": "Hilltop Library", "lat": LAT + 0.03, "lon": LON, "qid": ""}], time.time())
app.store.save_landmarks("r", [{"qid": "Q99", "title": "Hilltop Library", "lat": LAT + 0.03 + 50 / 111320, "lon": LON,
                                "langs": 40}], time.time())
got = at(LAT + 0.03, LON)
assert got == ["NEW TROVE! HILLTOP LIBRARY!"], got

# the commands, the map, achievements, the recap
lines = asyncio.run(app.command("TROVES"))
assert any(l.split("|")[1] == "Ordinary Library" and int(l.split("|")[2]) > 0 for l in lines if "|" in l)
assert any(l.split("|")[1] == "Riverside Library" and l.split("|")[2] == "0" for l in lines if "|" in l)
m = app.map_data()
assert {b["name"]: b["seen"] for b in m["troves"]}["Ordinary Library"] is True
achs = {a["id"]: a for a in app.achievement_list(fresh=True)}
assert achs["t-all"]["n"] == 3 and achs["t-all"]["section"] == "troves" and achs["t-again"]["n"] == 1
assert dict((s[0], s[2]) for s in ach.SECTIONS)["troves"] == "ᛏ"
from bt_dragon import dot as dotmod
events = [{"kind": "trove", "text": f"{app.pet.name} found a new treasure trove: Ordinary Library! +75 Conquest points.", "ts": 0},
          {"kind": "trove", "text": f"{app.pet.name} visited a treasure trove: Riverside Library", "ts": 0}]
rec = dotmod.build_recap(app.pet.name, events, 0, 0, 3600)
assert "We found treasure troves: Ordinary Library and Riverside Library!" in rec, rec
# forgetting the map forgets them too
asyncio.run(app.command("FORGETMAP"))
assert not any(b["first_seen"] for b in app.store.libraries_list())
den = open(os.path.join(os.path.dirname(__file__), "..", "bt_dragon", "den.html"), encoding="utf-8").read()
assert "cmd('TROVES')" in den and 'id="tvList"' in den
print("troves ok")
