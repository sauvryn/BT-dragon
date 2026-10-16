"""Rations: earned for feasts and land claims (fractions add up, riding earns less, an optional
limit), kept apart from his food until you give one, and then the PACK is filled completely."""
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
print("test_rations: OK")
