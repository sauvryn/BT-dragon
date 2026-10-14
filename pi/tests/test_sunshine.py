"""Sunshine from the phone's light sensor: bright enough for long enough, not too often."""
import os
import tempfile

from bt_dragon import activity, config, sky, tuning
from bt_dragon.app import Dragon
from bt_dragon.store import Store

tmp = tempfile.mkdtemp()
store = Store(os.path.join(tmp, "s.db"))
tuning.load(store)
assert activity.LightLink(lambda v: None).sensor == "android.sensor.light"

sun = sky.Sunshine(store)
t = 1_000_000.0
assert sun.feed(400, t) is None                         # indoors
for i in range(29):
    assert sun.feed(45000, t + 1 + i) is None           # bright, but not for 30 s yet
assert sun.feed(45000, t + 31) == 45000                 # 30 s of sunshine: cheer
assert sun.feed(50000, t + 100) is None                 # ...then not again for 3 hours
for i in range(40):
    assert sun.feed(60000, t + 3 * 3600 + i) in (None, 60000)
assert sun.last > t + 3 * 3600                          # again after 3 hours
assert sky.Sunshine(store).last == sun.last             # remembered over a restart

# a brief shadow doesn't reset a sunny spell; a long one does
s2 = sky.Sunshine(Store(os.path.join(tmp, "s2.db")))
s2.feed(40000, 0 + 5e6)
s2.feed(100, 5 + 5e6)
assert s2.feed(40000, 8 + 5e6) is None and s2.bright_since == 5e6
s2.feed(100, 10 + 5e6)
s2.feed(100, 25 + 5e6)                                  # 15 s of shade: the spell is over
assert s2.bright_since is None

# the knobs are in Dev Tools
assert "sunny_joy" in tuning._defaults and "sunny_lux" in tuning._defaults

# the whole dragon: a cheer, a joy boost and a diary entry; none while napping
cfg = config.load(None)
cfg["data_dir"] = os.path.join(tmp, "app")
app = Dragon(cfg, simulate=True, out_dir=cfg["data_dir"])
app.sun.last = 0
app.pet.joy = 50
app.napping = True
for i in range(40):
    app.sun.ts = 0
    app.on_light([60000.0])
assert app.pet.joy == 50 and app.sun.lux is None        # asleep: not even read
app.napping = False
import time as _t  # noqa: E402
start = _t.time()
app.sun.feed(60000, start - 40)                         # it's been bright for 40 s already
app.on_light([60000.0])
assert app.pet.joy == 50 + tuning.get("sunny_joy"), app.pet.joy
assert "SUNNY" in app.pet.message, app.pet.message
assert app.store.events(5)[0]["text"].startswith("Sunshine!")
assert app.view()["lux"] == 60000 and app.view()["light_link"] is False
print("sunshine ok")
