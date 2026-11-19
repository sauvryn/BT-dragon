"""Rations: earned for new lands and famous places (not feasts, unless that's switched on;
fractions add up, riding earns less, an optional limit), kept apart from his food until you
give one, and then the PACK is filled completely. And scrolls: one per library visited,
studied for joy."""
import asyncio
import tempfile

from bt_dragon import config, tuning
from bt_dragon.app import Dragon
from bt_dragon.pet import Pet
from bt_dragon.store import Store

st = Store(":memory:")
p = Pet(st, "Harald")
p.hunger, p.pack = 20.0, 0.0
assert p.rations == 0 and p.give_ration() == "no rations left"
p.feast("A WATCH")
assert p.rations == 0 and tuning.get("ration_feast") == 0       # feasts earn none, to start with
p.earn_ration(tuning.get("ration_landmark"))    # (a famous place: the app, below)
p.land(False)
p.land(False, riding=True)                      # riding: a quarter (Lands: rewards while riding)
assert abs(p.rations - 2.25) < 1e-9, p.rations
assert p.pack == 0.0                            # he can't touch them himself
p.eat_from_pack()
assert p.pack == 0.0 and abs(p.rations - 2.25) < 1e-9

# giving one fills the PACK completely, whatever was in it
p.pack = 7.0
assert p.give_ration() is None and p.pack == p.pack_cap() and abs(p.rations - 1.25) < 1e-9
assert "RATION" in p.message
assert p.give_ration() == "the PACK is already full" and abs(p.rations - 1.25) < 1e-9
# kept over a restart
p.save()
q = Pet(st, "Harald")
assert abs(q.rations - 1.25) < 1e-9 and q.pack == q.pack_cap()

# fractions, and a limit when one is set
tuning.set_value("ration_land", 0.1)
r = Pet(Store(":memory:"), "Harald")
for _ in range(10):
    r.land(False)
assert abs(r.rations - 1.0) < 1e-6
tuning.set_value("ration_max", 3)
tuning.set_value("ration_feast", 1)
for _ in range(10):
    r.feast("X")
assert r.rations == 3
tuning.reset("all")

# the den: RATION, the view, napping, and setting them in Developer Tools
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())


def cmd(c):
    return asyncio.run(app.command(c))


assert cmd("RATION")[0] == "ERR no rations left"
v = app.view()
assert v["rations"] == 0 and v["ration_room"] == round(app.pet.pack_cap() - app.pet.pack, 1)
assert cmd("METER rations 2")[0] == "OK" and app.view()["rations"] == 2
app.pet.pack = 0.0
out = cmd("RATION")
assert out[0].startswith("OK") and "1 ration left" in out[0], out
assert app.pet.pack == app.pet.pack_cap() and app.view()["rations"] == 1 and app.view()["ration_room"] == 0
assert any("gave Harald a ration" in r[0] for r in app.store.db.execute("SELECT text FROM events").fetchall())
assert cmd("RATION")[0] == "ERR the PACK is already full"
app.pet.pack = 0.0
app.napping = True
assert "napping" in cmd("RATION")[0] and app.pet.pack == 0.0
app.napping = False
app.pet.rations = 1.5
assert app.view()["rations"] == 1 and app.view()["ration_part"] == 0.5
# famous places: a ration each (once per place per day: landmarks.near); libraries: a scroll
app.pet.rations, app.pet.scrolls = 0.0, 0
app._landmark({"qid": "Q1", "title": "Tower Bridge", "lat": 51.5, "lon": -0.07}, True)
assert app.pet.rations == 1 and any("A ration for visiting Tower Bridge" in e["text"] for e in app.store.events(5))
app._trove({"id": "L1", "name": "Central Library"}, True)
assert app.pet.scrolls == 1 and app.pet.rations == 1
app._trove({"id": "L2", "name": "Old Library"}, False, {"qid": "Q2", "title": "Old Library", "lat": 0, "lon": 0}, True)
assert app.pet.scrolls == 2 and app.pet.rations == 2              # a library that's also a famous place: both
# studying a scroll: half the joy bar, at most to full; kept over a restart
app.pet.joy = 0.0
v = app.view()
assert v["scrolls"] == 2 and v["scroll_room"] == round(50 * app.pet.growth())
assert cmd("SCROLL")[0].startswith("OK") and abs(app.pet.joy - 50) < 1e-9 and app.pet.scrolls == 1
assert "SCROLL" in app.pet.message and any("a scroll to study" in e["text"] for e in app.store.events(5))
app.pet.joy = 80.0
assert cmd("SCROLL")[0].startswith("OK") and app.pet.joy == 100.0 and app.pet.scrolls == 0
assert cmd("SCROLL")[0] == "ERR no scrolls left"
assert cmd("METER scrolls 3")[0] == "OK" and app.pet.scrolls == 3
assert cmd("SCROLL")[0] == "ERR the joy bar is already full" and app.pet.scrolls == 3
app.pet.save()
assert Pet(app.store, "Harald").scrolls == 3
print("test_rations: OK")
