"""Adventure mode: only adventure news out loud (never Bluetooth or Wi-Fi), milestones for
walking and climbing, lands a few at a time, a full pack, and its own volume."""
import os
import tempfile
import time

from bt_dragon import config, tuning
from bt_dragon.app import Dragon

tmp = tempfile.mkdtemp()
cfg = config.load(None)
cfg["data_dir"] = tmp
app = Dragon(cfg, simulate=True, out_dir=tmp)
d = app.dot
d.connected = d.ready = True                     # pretend the Dot is here
d.s["quiet_from"] = d.s["quiet_to"] = "00:00"
assert d.set("chatty", "adventure") is None and d.set("chatty", "loud")
said = lambda: [t for t in d.queue]               # noqa: E731

# ordinary messages, and anything about gadgets or Wi-Fi, stay quiet
d.on_say("NOM! 3 NEW SNACKS", "eating")
d.on_say("TREAT! CoffeeShop_Guest (WPA2)", "excited")
d.on_say("A NEW SPECIES! APPLE WATCH", "ecstatic")
app.pet.berries(5, 2)
assert said() == [], said()

# the first tick only notes where things stand (nothing already done is announced)
app.activity.today["walked"] = 1200
app.pet.climbed_today = 25
d._adventure_tick()
assert said() == []
app.activity.today["walked"] = 1550               # passed 1.5 km
d._adventure_tick()
assert said() == ["We've walked 1.5 kilometres today!"], said()
d.queue.clear()
app.activity.today["walked"] = 1700               # not the next half yet
d._adventure_tick()
assert said() == []
app.pet.climbed_today = 41                        # passed 40 m
d._adventure_tick()
assert said() == ["We've climbed 40 metres today!"], said()
d.queue.clear()
assert d._km_words(0.5) == "half a kilometre" and d._km_words(1) == "1 kilometre" and d._km_words(2.5) == "2.5 kilometres"

# lands come out a few at a time, after a quiet spell; realms straight away
for _ in range(3):
    d.adventure("land")
d._adventure_tick()
assert said() == []                               # still claiming
d._adv["land_ts"] = time.time() - 20
d._adventure_tick()
assert said() == ["Three new lands! I claim them!"], said()
d.queue.clear()
d.adventure("realm")
d.adventure("landmark", title="Kingsbridge Castle", first=True)
d.adventure("landmark", title="Kingsbridge Castle", first=False)
d.adventure("sunny")
d.adventure("constellation", name="Galileo")
d.adventure("stars", n=3)
d.on_event("level", "Harald reached level 7", time.time())
assert said()[-4:] == ["Wow! It's sunny out today!", "A new constellation in the sky: Galileo!",
                       "I spotted 3 new stars in the sky!", "Level up! I'm level 7 now!"], said()
assert "Look! It's Kingsbridge Castle! I've never seen it before!" in said() and "A new realm! I claim it for us!" in said()
d.queue.clear()

# a full pack, once, until it's been used and filled again
cap = tuning.get("pack_cap")
app.pet.pack = cap - 5
d._adventure_tick()
app.pet.pack = cap
d._adventure_tick()
d._adventure_tick()
assert said() == ["Smashing! My pack is full up!"], said()
d.queue.clear()
app.pet.pack = cap * 0.5
d._adventure_tick()
app.pet.pack = cap
d._adventure_tick()
assert said() == ["Smashing! My pack is full up!"]
d.queue.clear()

# the whole dragon: the sunshine cheer reaches the Dot
app.sun.last = 0
app.sun.feed(60000, time.time() - 40)
app.on_light([60000.0])
assert said() == ["Wow! It's sunny out today!"], said()
d.queue.clear()

# no welcome-home recap in Adventure mode (it would list snacks and treats); other modes:
# adventure news isn't doubled up
d.recap_pending = "I'm home! I ate 30 snacks."
d._deliver_recap()
assert said() == []
d.set("chatty", "all")
d.adventure("sunny")
assert said() == [] and d._adv["walk"] is not None
d._adventure_tick()
assert d._adv["walk"] is None                     # starts fresh next time it's switched on
assert d.set("adv_volume", "20") is None and d.s["adv_volume"] == 20 and "adv_volume" in d.status()
print("adventure ok")
