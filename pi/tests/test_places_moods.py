"""Adventures today: "places seen" counts landmarks, green spaces and libraries seen today, new or
known (a library that's also a landmark once). Moods: at worst bored, never sad (no "lonely" face,
no sad eyes when hungry or famished)."""
import os
import tempfile
import time

from PIL import Image, ImageDraw

from bt_dragon import config, dragon, pet as petmod
from bt_dragon.app import Dragon

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
st = app.store
now = time.time()
st.save_landmarks("r", [{"qid": "Q1", "title": "Tower", "lat": 51.5, "lon": -0.1, "langs": 40},
                        {"qid": "Q2", "title": "Big Library", "lat": 51.51, "lon": -0.1, "langs": 40},
                        {"qid": "Q3", "title": "Old Bridge", "lat": 51.52, "lon": -0.1, "langs": 40}], now)
st.save_libraries("r", [{"id": "n1", "name": "Big Library", "lat": 51.51, "lon": -0.1, "qid": "Q2"},
                        {"id": "n2", "name": "Branch Library", "lat": 51.53, "lon": -0.1, "qid": ""}], now)
st.save_greens("r", [{"id": "w1", "name": "Park", "kind": "park", "rings": [[(51.5, -0.1), (51.6, -0.1), (51.6, 0), (51.5, -0.1)]],
                      "area": 10000, "bbox": (51.5, -0.1, 51.6, 0), "lat": 51.55, "lon": -0.05}], now)
assert app.view()["places_today"] == 0
st.landmark_seen("Q1", now)                       # a new one
st.landmark_seen("Q3", now - 3 * 86400)           # seen days ago...
st.landmark_seen("Q3", now)                       # ...and again today: known ones count too
st.landmark_seen("Q2", now); st.library_seen("n1", now)     # the library that is a landmark: once
st.library_seen("n2", now)
st.green_seen("w1", now - 2 * 86400)              # not today
assert app.view()["places_today"] == 4, app.view()["places_today"]
den = open(os.path.join(os.path.dirname(__file__), "..", "bt_dragon", "den.html"), encoding="utf-8").read()
assert "places seen" in den and "stars seen" not in den

# moods: never sad
assert petmod.joy_word(0) == "BORED" and petmod.joy_word(14) == "BORED" and "SAD" not in [petmod.joy_word(j) for j in range(101)]
p = app.pet
p.joy, p.hunger, p.reaction = 0, 50, None
p.sleeping = p.alarm = p.uploading = False
import datetime
real = time.localtime
time.localtime = lambda t=None: real(time.mktime(datetime.datetime(2026, 10, 22, 12, 0).timetuple()))
try:
    assert p.mood() == "bored"
    p.hunger = 0
    assert p.mood() == "famished"
finally:
    time.localtime = real
assert not hasattr(dragon, "_eye_sad")
img = Image.new("1", (96, 86), 1)
for m in ("famished", "hungry", "lonely", "bored"):
    dragon.draw_dragon(ImageDraw.Draw(img), 0, 0, m, 0)
from bt_dragon import art
assert "lonely" not in art.EVERYDAY
print("places and moods ok")
