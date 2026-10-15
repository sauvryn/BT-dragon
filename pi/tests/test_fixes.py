"""Fixes from testing: a nap's catch-up counts the nap (not the time since the last
shutdown), *YAWN* isn't read out as "asterisk", the "safe to unplug" picture isn't drawn
over, and poor air quality at the Lair is announced."""
import asyncio
import tempfile
import time

from bt_dragon import config, tuning
from bt_dragon.app import Dragon
from bt_dragon.voice import speakable

assert speakable("*YAWN* HELLO!") == "Yawn hello!", speakable("*YAWN* HELLO!")

tmp = tempfile.mkdtemp()
cfg = config.load(None)
cfg["data_dir"] = tmp
app = Dragon(cfg, simulate=True, out_dir=tmp)
pet = app.pet
pet.saved_at = time.time() - 3 * 3600          # his last shutdown was three hours ago
app._caught_up = True                           # (and that was caught up at start-up)


async def nap_test():
    pet.hunger, pet.joy = 80.0, 80.0
    await app.nap()
    assert abs(pet.saved_at - time.time()) < 5   # the save before the nap counts now
    app.nap_since -= 600                         # a ten-minute nap
    pet.saved_at -= 600
    await app.wake_up()
    events = len(app.store.events(500))
    app._catch_up()
    lost = 80.0 - pet.hunger
    per_min = 100 / tuning.get("food_empty_min") * tuning.get("food_off_drain") / 100
    assert 0 < lost < per_min * 12, (lost, per_min)           # ten minutes' worth, not three hours'
    texts = [e["text"] for e in app.store.events(500)][: len(app.store.events(500)) - events]
    assert not any("switched off" in t for t in texts), texts  # the wake-up line says it
    assert not pet.message.startswith("YOU'RE BACK! I WAS ASLEEP FOR 3")

asyncio.run(nap_test())


# nothing is drawn after the "safe to unplug" picture
drawn = []
app.display.show = lambda img, *a, **k: drawn.append("show")
app.display.sleep = lambda img, *a, **k: drawn.append("sleep")


async def shutdown_test():
    loop = asyncio.ensure_future(app.display_loop())
    await asyncio.sleep(0.1)
    await app.shutdown("RESTART")
    await asyncio.sleep(0.1)
    loop.cancel()
    assert drawn[-1] == "sleep", drawn

app._sleep = lambda s: asyncio.sleep(0.01)
asyncio.run(shutdown_test())

# poor air quality at the Lair: the sneezing face, and said when it's gone up
app2 = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
L = app2.lair
L.s = {"place": "x", "code": "GB", "lat": 51.5, "lon": -0.1, "announce": True, "done": {}}
pushed = []
app2.dot.phone.push = pushed.append
app2.dot.s.update(enabled=False, phone=True, chatty="big", quiet_from="00:00", quiet_to="00:00")
AIR = {"current": {"european_aqi": 45, "grass_pollen": 0.0}}
L.get = lambda url, params, timeout=12: AIR


async def air_test():
    await app2._lair_check(time.time(), ["pollen"])
    assert pushed == []                                      # fair: nothing to say
    AIR["current"]["european_aqi"] = 72
    L.s["done"]["pollen"] = ""
    await app2._lair_check(time.time() + 3600, ["pollen"])
    assert pushed == ["The air quality at the Lair is poor, with a European air quality index of 72."], pushed
    assert app2.pet.reaction[0] == "sneezing"
    AIR["current"]["european_aqi"] = 85
    await app2._lair_check(time.time() + 7200, ["pollen"])
    assert pushed[-1].startswith("The air quality at the Lair is getting worse! It's very poor now"), pushed
    # the temperature counts as a big moment when its box is ticked
    pushed.clear()
    L.cond = {"current": {"temperature_2m": 12.0}, "hourly": {}, "daily": {}}
    L.cond_ts = time.time() + 99999
    await app2._lair_check(time.time(), ["temp"])
    assert pushed and pushed[0].startswith("At the Lair, the current temperature is"), pushed
    d = dict(x.split("=", 1) for x in await app2.command("LAIR") if "=" in x)
    assert d["temp_said"].startswith("12°C (54°F) at "), d

asyncio.run(air_test())
print("fixes ok")
