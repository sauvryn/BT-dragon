"""Walks in the diary: what, how far (km, with miles), how long and when; "How far have we
gone?"; a walk surviving a restart; and WiGLE uploads spaced out across restarts."""
import os
import tempfile
import time

from bt_dragon import activity as act
from bt_dragon import ask
from bt_dragon.app import Dragon
from bt_dragon.dot import DotLink
from bt_dragon.store import Store

tmp = tempfile.mkdtemp()
store = Store(os.path.join(tmp, "dragon.db"))

# the words
assert act.km_mi(4570.5) == "4.57 km (2.84 mi)" and act.km_mi(2060) == "2.06 km (1.28 mi)"
assert act.duration_words(84 * 60, True) == "1 h 24 min" and act.duration_words(47 * 60, True) == "47 min"
assert act.duration_words(84 * 60) == "1 hour and 24 minutes" and act.duration_words(3600) == "1 hour"
assert act.duration_words(61) == "1 minute"
start = time.mktime((2026, 10, 13, 15, 20, 0, 0, 0, -1))
s = act.trip_summary({"walking": 4400, "running": 170, "vehicle": 3000}, start, start + 84 * 60)
assert s["kind"] == "walk" and abs(s["meters"] - 4570) < 1 and s["vehicle"] == 3000
assert act.exercise_line(s) == "Walk: 4.57 km (2.84 mi) in 1 h 24 min, from 15:20", act.exercise_line(s)
assert act.trip_summary({"cycling": 9000, "walking": 300}, start, start + 1800)["label"] == "Bike ride"
assert act.trip_summary({"running": 5000, "walking": 1000}, start, start + 1800)["kind"] == "run"

# a walk: in progress, kept across a restart, then finished
a = act.Activity(store)
a.add("walking", 1200)
a.trip_start = time.time() - 20 * 60
a._trip_saved = 0
a.take_motion()
t = a.trip_now()
assert t["kind"] == "walk" and t["meters"] == 1200 and 19 * 60 < t["seconds"] < 21 * 60
b = act.Activity(store)                                   # he restarted mid-walk
assert b.trip == {"walking": 1200} and b.trip_start == a.trip_start
b.last_moving = time.time() - 400
trip = b.finished_trip()
assert trip == {"walking": 1200} and b.last_trip[0] == a.trip_start and not b.trip_start
assert act.Activity(store).trip_start is None              # finished: not resumed again
store.put("trip_now", {"start": time.time() - 9000, "last_moving": time.time() - 3600, "trip": {"walking": 50}})
assert act.Activity(store).trip_start is None              # an hour ago: a new walk, not that one

# kept for good, and listed in the den
store.exercise_add(start, start + 84 * 60, "walk", 4570)
store.exercise_add(start + 7140, start + 7140 + 47 * 60, "walk", 2060)
assert [r["meters"] for r in store.exercise_since(start)] == [4570, 2060]


class Obj:
    pass


app = Obj()
app.store = store = Store(os.path.join(tmp, "den.db"))
lt = time.localtime()
today0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 9, 0, 0, 0, 0, -1))
store.exercise_add(today0, today0 + 1800, "run", 5000)
assert Dragon._exercise_today(app) == ["Run: 5.00 km (3.11 mi) in 30 min, from 09:00"]
app.activity = act.Activity(store)
app.activity.trip, app.activity.trip_start = {"walking": 2414}, time.time() - 52 * 60
app.activity.last_moving = time.time()
v = Dragon._trip_view(app)
assert v["label"] == "Walk" and v["dist"] == "2.41 km (1.50 mi)" and v["time"] == "52 min", v

# "How far have we gone?"
P = ask.parse
for q in ("how far have we gone on this walk", "how far have we traveled", "how far have we walked",
          "how long have we been walking", "how far have we come"):
    assert P(q) == {"intent": "trip", "today": False}, (q, P(q))
assert P("how far have i walked today") == {"intent": "trip", "today": True}
assert P("how far is it")["intent"] == "where" and P("how long is left on the pasta timer")["intent"] == "timer_left"
assert all(w in ask.VOCABULARY for p in ask.PHRASES for w in p.split())
d = Obj()
d.app = app
app.activity.today = {"date": time.strftime("%Y-%m-%d"), "walked": 5300.0, "rode": 0.0, "told": 0.0}
r = DotLink.answer_trip(d)
assert r == "We've gone 2.4 kilometers on this walk, about 1.5 miles, in 52 minutes.", r
assert DotLink.answer_trip(d, today=True) == ("Today we've gone 5.3 kilometers together under our own steam, "
                                               "about 3.3 miles.")
app.activity.trip, app.activity.trip_start = {}, None
assert DotLink.answer_trip(d).startswith("We're not out on a walk right now. Today we've gone 5.3 kilometers")
app.activity.today["walked"] = 0
assert DotLink.answer_trip(d) == "We haven't been anywhere together today yet. Let's go for a walk!"

# WiGLE: every 4 hours, remembered across restarts
w = Obj()
w.store = Store(os.path.join(tmp, "w.db"))
w.cfg = {"wigle": {"upload_every_minutes": 240}}
w._quota_wait = lambda: 0.0
assert Dragon._next_upload_in(w) == 0                       # never tried: go ahead
w.store.put("wigle_last_try", time.time() - 3600)
assert 3 * 3600 - 5 < Dragon._next_upload_in(w) <= 3 * 3600   # tried an hour ago: 3 hours to go
w.cfg["wigle"]["upload_every_minutes"] = 10
w.store.put("wigle_last_try", time.time() - 120)
assert 3470 < Dragon._next_upload_in(w) <= 3480             # never more often than hourly
w._quota_wait = lambda: 20000.0
assert Dragon._next_upload_in(w) == 20000.0                 # WiGLE's daily limit hit: wait for it
print("exercise ok")
