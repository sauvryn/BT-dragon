"""Sharing with the Butterfly Garden: snacks and feasts that don't fit in his belly go straight to
the garden (they don't keep); treats and berries go into the PACK first, and only reach the
garden once the PACK is full."""
import tempfile
import time

from bt_dragon import config, tuning
from bt_dragon.app import Dragon

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
pet = app.pet
tuning.set_value("growth_pct", "0")
fed = []
pet.on_surplus = fed.append

# a snack with a full belly: all of it to the garden, none to the pack
pet.hunger, pet.pack = 100.0, 0.0
pet.snack()
assert fed == [tuning.get("snack_food")] and pet.pack == 0.0 and pet.hunger == 100.0
# with a little room: he eats what fits, the rest is shared
fed.clear()
pet.hunger = 99.0
pet.snack()
assert abs(pet.hunger - 100.0) < 1e-9 and abs(sum(fed) - (tuning.get("snack_food") - 1)) < 1e-9
# a feast, belly full: shared too
fed.clear()
pet.feast("JBL Flip #")
assert fed == [tuning.get("feast_food")] and pet.pack == 0.0
# hungry: he eats it all, nothing shared
fed.clear()
pet.hunger = 50.0
pet.snack()
assert fed == [] and abs(pet.hunger - (50 + tuning.get("snack_food"))) < 1e-9

# treats and berries: into the pack first; the garden only once the pack is full
fed.clear()
pet.hunger, pet.pack = 100.0, 0.0
pet.treat({"ssid": "Cafe", "security": "wpa2"})
assert fed == [] and pet.pack == tuning.get("treat_food_wpa2")
pet.pack = pet.pack_cap()
pet.berries(3.0, 2)
assert fed == [3.0]

# the screen: "fed to the garden" at most every 5 minutes
assert app.GARDEN_FED_EVERY_S == 300
tuning.set_value("growth_pct", "default")
print("share ok")
