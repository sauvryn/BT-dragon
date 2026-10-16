"""Developer Tools knobs apply at once: a smaller PACK spills what no longer fits (and its meter
is full), spare food reaches the garden and is announced, and belly and joy knobs are read live."""
import asyncio
import tempfile
import time

from bt_dragon import config, tuning
from bt_dragon.app import Dragon

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
run = lambda c: asyncio.run(app.command(c))                             # noqa: E731
try:
    run("TUNE pack_cap 200")
    app.pet.pack = 169
    run("TUNE pack_cap 100")
    assert app.pet.pack == 100                                          # spilled down to the new size
    v = app.view()
    assert v["pack"] / v["pack_cap"] == 1.0
    run("TUNERESET food")
    assert tuning.get("pack_cap") == 50 and app.pet.pack == 50

    # spare food: to the garden, and said on his screen (not over the treat's own message)
    run("TUNE growth_pct 0")                    # (growing up has its own test: test_growth)
    app.pet.xp = 900
    app.garden.unlock_now(app.pet.level())
    app.pet.hunger, app.pet.pack = 99.0, tuning.get("pack_cap")
    app.pet.treat({"ssid": "Cafe", "security": "wpa2"})
    assert app._garden_fed == 3.0 and app.garden.s["slots"][0]["fed"] == 3.0
    app._garden_news.clear()
    app._garden_tick()
    assert "TREAT" in app.pet.message                                   # still the treat's message
    app.pet.message_ts = time.time() - 10
    app._garden_tick()
    assert app.pet.message == "FED 3 FOOD TO THE BUTTERFLY GARDEN", app.pet.message

    # belly and joy knobs are read when they're needed, so a change applies straight away
    run("TUNE food_empty_min 150")
    assert tuning.get("food_empty_min") == 150 and tuning.get("joy_empty_min") == 1000
    run("TUNE snack_food 5")
    app.pet.hunger = 50.0
    app.pet.snack()
    assert app.pet.hunger == 55.0
finally:
    tuning.reset("all")
print("pack ok")
