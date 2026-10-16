"""Growing up: a bigger appetite each level (belly, joy and pack hold more; each snack fills
a smaller share), up to a limit; a full belly still lasts as long; the garden's needs stay the
same unless its knob is on."""
import asyncio
import tempfile

from bt_dragon import config, tuning
from bt_dragon.app import Dragon
from bt_dragon.pet import xp_for

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
pet = app.pet
run = lambda c: asyncio.run(app.command(c))                             # noqa: E731
at = lambda lv: xp_for(lv)                                              # noqa: E731

assert abs(pet.growth(1) - 1.0) < 1e-9 and abs(pet.growth(5) - 1.2) < 1e-9 and abs(pet.growth(11) - 1.5) < 1e-9
assert pet.growth(40) == 2.0                                            # the limit: twice level 1
pet.xp = at(5)
assert pet.level() == 5 and abs(pet.pack_cap() - 60) < 1e-9

# a snack fills a smaller share of a bigger dragon; joy too
pet.hunger, pet.joy = 50.0, 50.0
pet._gain(12, 0, 12)
assert abs(pet.hunger - 60.0) < 1e-9 and abs(pet.joy - 60.0) < 1e-9      # 12 food = 10% at level 5
pet.xp = at(1)
pet.hunger, pet.joy = 50.0, 50.0
pet._gain(12, 0, 12)
assert abs(pet.hunger - 62.0) < 1e-9                                    # at level 1, 12%

# (a full belly empties in the same time at any level: the drain is a percentage a minute,
# untouched by growing up)
with open("bt_dragon/pet.py", encoding="utf-8") as f:
    assert 'self.hunger - dt * 100 / (tuning.get("food_empty_min") * 60)' in f.read()

# the belly's room, the pack, and eating from the pack, in food
pet.xp = at(5)
pet.hunger, pet.pack = 99.0, 0.0
packed = pet._overflow(4.0)
assert abs(packed - (4.0 - 1.2)) < 1e-9                                 # 1% of a 120-food belly is 1.2 food
pet.hunger, pet.pack = 20.0, 30.0
bite = pet.eat_from_pack()
assert abs(bite - 15.0) < 1e-9 and abs(pet.hunger - (20 + 15 / 1.2)) < 1e-9

# the level-up: a bigger appetite, on his screen and in the diary
pet.xp = at(6) - 1
pet._gain(0, 5, 0)
assert "BIGGER APPETITE" in pet.message and pet.level() == 6
assert any("a bigger appetite" in e["text"] and "25% more" in e["text"] for e in app.store.events(5))
v = app.view()
assert v["belly_holds"] == 125 and abs(v["pack_cap"] - 62.5) < 1e-9

# the garden: the same needs by default, growing with him if its knob is on
common = app.garden.need("Common")
assert common == tuning.get("garden_food_common")
assert run("TUNE garden_grows 1")[0].startswith("OK")
assert abs(app.garden.need("Common") - tuning.get("garden_food_common") * 1.25) < 1e-9
assert run("TUNE garden_grows 2")[0].startswith("ERR") and run("TUNE growth_max 50")[0].startswith("ERR")
run("TUNE garden_grows 0")

# switched off: the same at every level
run("TUNE growth_pct 0")
assert pet.growth() == 1.0 and pet.pack_cap() == tuning.get("pack_cap")
run("TUNERESET food")
assert tuning.get("growth_pct") == 5
print("growth ok")
