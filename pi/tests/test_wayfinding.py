"""Which way is it: distances and directions, the words he says, matching heard names to
landmarks, "that landmark", and the questions themselves."""
import time

from bt_dragon import ask
from bt_dragon import wayfinding as wf
from bt_dragon.dot import DotLink

# directions: 8 points, 45 degrees each
assert [wf.compass(d) for d in (0, 22, 23, 90, 135, 180, 225, 270, 315, 338, 359)] == \
    ["north", "north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest", "north", "north"]
here = (51.5080, -0.1281)
assert abs(wf.distance_m(*here, 51.5080 + 0.009, -0.1281) - 1000) < 5          # 1/111th of a degree north
assert wf.compass(wf.bearing(*here, 51.5017, -0.1185)) == "southeast"
assert abs(wf.distance_m(51.5074, -0.1278, 48.8566, 2.3522) - 343500) < 1500   # London to Paris

# metric first, then miles or feet
S = wf.spoken_distance
assert S(900) == "900 meters, about half a mile", S(900)
assert S(37) == "40 meters, about 120 feet" and S(120) == "100 meters, about 400 feet", (S(37), S(120))
assert S(420) == "400 meters, about a quarter of a mile" and S(1240) == "1.2 kilometers, about three quarters of a mile"
assert S(1609) == "1.6 kilometers, about a mile" and S(2414) == "2.4 kilometers, about 1.5 miles"
assert S(16093) == "16 kilometers, about 10 miles" and S(343500) == "340 kilometers, about 210 miles", S(343500)
assert S(1000) == "1 kilometer, about half a mile" and S(5) == "10 meters, about 20 feet", (S(1000), S(5))
assert wf.where_words("East Harbour Railway", here, (51.5017, -0.1185)).startswith(
    "East Harbour Railway is 950 meters to the southeast, about ")
assert wf.where_words("Kingsbridge Castle", here, here) == "We're right by Kingsbridge Castle!"

# names: heard words against landmark titles
assert wf.name_words("St Mary's Church") == ["saint", "street", "mary's", "church"]
assert wf.name_phrase("St Mary's Church") == "saint mary's church" and wf.name_phrase("Café Nero 2") == "cafe nero"
assert wf.match_score("east harbour railway", "East Harbour Railway") == 1.0
assert wf.match_score("saint marys church", "St Mary's Church") == 1.0
assert wf.match_score("the castle", "Kingsbridge Castle") > 0.5 and wf.match_score("railway", "East Harbour Railway") == 0.5
places = [{"title": "East Harbour Railway", "lat": 51.5017, "lon": -0.1185},
          {"title": "Kingsbridge Castle", "lat": 51.5077, "lon": -0.1305},
          {"title": "Millbrook Canal", "lat": 51.5147, "lon": 0.0185},
          {"title": "Ravenmoor Castle", "lat": 52.2347, "lon": 0.2185}]
assert wf.best_match("harbour railway", places, here)["title"] == "East Harbour Railway"
assert wf.best_match("the castle", places, here)["title"] == "Kingsbridge Castle"            # the nearer castle
assert wf.best_match("ravenmoor castle", places, here)["title"] == "Ravenmoor Castle"
assert wf.best_match("blackpool tower", places, here) is None

# the questions
P = ask.parse
assert P("what direction is east harbour railway in") == {"intent": "where", "name": "east harbour railway"}
assert P("hey dragon where is kingsbridge castle") == {"intent": "where", "name": "kingsbridge castle"}
assert P("which way is the millbrook canal")["name"] == "millbrook canal"
assert P("how far away is ravenmoor castle from here")["name"] == "ravenmoor castle"
for t in ("where is that landmark", "in what direction", "which direction", "how far is it", "where is it",
          "what direction is that in", "how far"):
    assert P(t) == {"intent": "where", "name": None}, (t, P(t))
assert P("go to sleep") == {"intent": "sleep"} and P("hey dragon take a nap") == {"intent": "nap"}
assert P("have a nap")["intent"] == "nap" and P("go to bed")["intent"] == "sleep"
assert P("what time is it")["intent"] == "time" and P("set a timer for ten minutes")["intent"] == "timer_set"
assert ask.is_yes("yes") and ask.is_yes("yeah") and ask.is_yes("yep") and ask.is_yes("yes please")
assert not ask.is_yes("no") and not ask.is_yes("") and not ask.is_yes(None) and not ask.is_yes("[unk]")
assert not ask.is_yes("yes wait") and not ask.is_yes("please")
assert all(w in ask.VOCABULARY for p in ask.PHRASES for w in p.split())


# DotLink's answers
class Obj:
    pass


app = Obj()
app.landmarks = True
app.gps = Obj()
app.gps.fix = {"lat": here[0], "lon": here[1], "ts": time.time()}
app.store = Obj()
app.store.landmarks_list = lambda langs: [dict(p, langs=20) for p in places]
d = Obj()
d._was = DotLink._was
for m in ("known_landmarks", "known_greens", "_way_to", "_here", "answer_where", "answer_nearest", "saw_landmark", "grammar"):
    setattr(d, m, getattr(DotLink, m).__get__(d))
d.app, d.last_landmark = app, None
d.shopping = Obj()
d.shopping.words = lambda: []
A = lambda text, alt=None: d.answer_where(ask.parse(text), alt)  # noqa: E731
assert A("where is the east harbour railway").startswith("East Harbour Railway is 950 meters to the southeast")
assert A("what direction is that landmark in").startswith("I haven't pointed out a landmark")
d.saw_landmark(places[1])
assert A("how far is it").startswith("Kingsbridge Castle is ") and "to the west" in A("in what direction")
d.last_landmark = (places[1], time.time() - 200)                       # over three minutes ago
assert A("where is that landmark").startswith("I haven't")
# the open second listen caught the name the word list couldn't
assert A("where is the [unk] canal", "where is the millbrook canal").startswith("Millbrook Canal is ")
assert A("where is paris").startswith("Paris is ") and "to the southeast" in A("where is paris")
assert A("where is blackpool tower").startswith("I don't know a place called blackpool tower")
app.gps.fix["ts"] = time.time() - 5 * 60
assert A("where is kingsbridge castle").startswith("From where we were 5 minutes ago, Kingsbridge Castle is")
app.gps.fix["ts"] = time.time() - 3600
assert A("where is kingsbridge castle").startswith("I don't know where we are right now")
# the nearest one, and whether (and when) he's seen it
for t in ("where is the closest landmark", "what's the nearest landmark", "what is the closest landmark",
          "where is the nearest famous place", "where's the nearest landmark"):
    assert P(t) == {"intent": "where", "name": None, "nearest": True, "unseen": False}, (t, P(t))
assert P("what is the nearest timer")["intent"] != "where"
import datetime as dt  # noqa: E402
now = time.mktime(dt.datetime(2026, 10, 13, 15, 0).timetuple())
at = lambda *a: time.mktime(dt.datetime(*a).timetuple())  # noqa: E731
assert wf.seen_words(None, now) == "I haven't seen it yet."
assert wf.seen_words(at(2026, 10, 13, 9, 0), now) == "I last saw it today."
assert wf.seen_words(at(2026, 10, 12, 23, 0), now) == "I last saw it yesterday."
assert wf.seen_words(at(2026, 10, 3, 12, 0), now) == "I last saw it on the 3rd of October."
assert wf.seen_words(at(2025, 12, 22, 12, 0), now) == "I last saw it on the 22nd of December, 2025."
app.gps.fix["ts"] = time.time()
r = A("where is the closest landmark")
assert r == "The nearest landmark I know of is Kingsbridge Castle, 150 meters to the west, about 550 feet. I haven't seen it yet.", r
assert A("in what direction").startswith("Kingsbridge Castle is ")                 # "that landmark" is now this one
app.store.landmarks_list = lambda langs: [dict(p, langs=20, last_seen=time.time() - 86400 if i == 1 else None)
                                          for i, p in enumerate(places)]
assert A("what's the nearest landmark").endswith("I last saw it yesterday.")
# the nearest one he hasn't seen yet (Kingsbridge Castle has been seen; East Harbour Railway is next)
for t in ("what is the closest unseen landmark", "what's the nearest undiscovered landmark",
          "where is the closest unknown landmark", "what is the nearest landmark i haven't seen",
          "which is the closest landmark we haven't visited"):
    assert P(t)["unseen"] is True, (t, P(t))
assert P("what is the closest landmark")["unseen"] is False
r = A("what is the closest unseen landmark")
assert r.startswith("The nearest landmark I haven't seen yet is East Harbour Railway, 950 meters to the southeast") \
    and r.endswith("."), r
assert A("how far is it").startswith("East Harbour Railway is")
app.store.landmarks_list = lambda langs: [dict(p, langs=20, last_seen=time.time()) for p in places]
assert A("what's the nearest undiscovered landmark").startswith("I've seen every landmark I know of around here")
app.store.landmarks_list = lambda langs: [dict(p, langs=20, last_seen=time.time() - 86400 if i == 1 else None)
                                          for i, p in enumerate(places)]
app.gps.fix["ts"] = time.time() - 3 * 60
assert A("what's the nearest landmark").startswith("From where we were 3 minutes ago: the nearest landmark")
app.gps.fix = None
assert A("where is the nearest landmark").startswith("I don't know where we are")
app.gps.fix = {"lat": here[0], "lon": here[1], "ts": time.time()}
app.store.landmarks_list = lambda langs: []
assert A("where is the nearest landmark") == "I don't know any landmarks around here yet. Let's go exploring!"
app.store.landmarks_list = lambda langs: [dict(p, langs=20) for p in places]
g = d.grammar()
assert "harbour" in g and "east harbour railway" in g and "millbrook canal" in g
print("wayfinding ok")
