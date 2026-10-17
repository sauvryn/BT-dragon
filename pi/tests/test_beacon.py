"""The friend beacon re-announces a new level or name at once, a new mood alone at most every
10 minutes; and the hungriest everyday message fits the screen ("famished", not "starving")."""
from bt_dragon import friends
from bt_dragon.fonts import text_width
from bt_dragon.pet import STATUS_W, hunger_word
from bt_dragon.store import Store
from bt_dragon.pet import Pet
from bt_dragon.dragon import MOODS

dragon_id = b"\x01\x02\x03\x04"
a = friends.encode(dragon_id, 5, 1, "Fafnir")
assert friends.Beacon._same_but_mood(a, friends.encode(dragon_id, 5, 7, "Fafnir"))
assert not friends.Beacon._same_but_mood(a, friends.encode(dragon_id, 6, 1, "Fafnir"))      # a level up
assert not friends.Beacon._same_but_mood(a, friends.encode(dragon_id, 5, 1, "Harald"))      # a new name
assert not friends.Beacon._same_but_mood(a, friends.encode(b"\x09\x02\x03\x04", 5, 1, "Fafnir"))  # a new day
assert not friends.Beacon._same_but_mood(None, a)

assert hunger_word(5) == "FAMISHED" and "starving" not in MOODS and "famished" in MOODS
p = Pet(Store(":memory:"), "Harald")
p.hunger, p.joy, p.message_ts, p.message_hold = 3.0, 90.0, 0, 0
p.tick([])
assert p.message.startswith("FAMISHED") and text_width(p.message.upper()) <= STATUS_W, p.message
print("beacon ok")

# growing up: baby 1-4, child 5-9, teen 10-19, adult 20+; a new stage is in the diary and on his screen
from bt_dragon.pet import stage, xp_for
assert [stage(l)[0] for l in (1, 4, 5, 9, 10, 19, 20, 40)] == ["baby", "baby", "child", "child", "teen", "teen",
                                                               "adult", "adult"]
assert stage(1)[1] == 5 and stage(12)[1] == 20 and stage(25)[1] is None
st = Store(":memory:")
p = Pet(st, "Fafnir")
p.xp = xp_for(5) - 1
p._gain(0, 2)
assert any("Fafnir is now a child!" in e["text"] for e in st.events(5)) and "CHILD" in p.message
print("stages ok")

# the beacon goes up with scanning paused (a radio may refuse a new random address mid-scan),
# and scanning starts again afterwards; a refusal is retried, and the log doesn't fill up
import asyncio
import logging
from bt_dragon.ble import BleakScanner

log_lines = []
logging.getLogger("friends").addHandler(type("H", (logging.Handler,), {"emit": lambda s, r: log_lines.append(r.getMessage())})())
logging.getLogger("friends").setLevel(logging.INFO)
radio = {"scanning": False, "starts": 0, "refuse": 2, "on_air": []}


class FakeScan:
    def __init__(self, **k):
        pass

    async def __aenter__(self):
        radio["scanning"] = True
        radio["starts"] += 1

    async def __aexit__(self, *a):
        radio["scanning"] = False


class Mgr:
    async def call_register_advertisement(self, path, opts):
        if radio["scanning"]:
            raise RuntimeError("Failed to register advertisement (scanning!)")
        if radio["refuse"]:
            radio["refuse"] -= 1
            raise RuntimeError("Failed to register advertisement")
        radio["on_air"].append(path)

    async def call_unregister_advertisement(self, path):
        radio["on_air"].remove(path)


class Bus:
    def export(self, p, o): pass
    def unexport(self, p): pass
    def disconnect(self): pass


class Adv:
    data = b""


def bus_fn():
    async def connect():
        return Bus(), Mgr()
    return connect, Adv


async def go():
    stop = asyncio.Event()
    sc = BleakScanner(lambda *a: None, bleak_cls=FakeScan)
    b = friends.Beacon(lambda: a, quiet=sc.quiet, bus_fn=bus_fn)
    b.GAP_S = 0
    real_wait_for = asyncio.wait_for

    async def quick(aw, t):          # (minutes go by in moments)
        return await real_wait_for(aw, min(t, 0.05))
    asyncio.wait_for = quick
    try:
        t1 = asyncio.ensure_future(sc.run(stop))
        await asyncio.sleep(0.05)
        assert radio["scanning"]
        t2 = asyncio.ensure_future(b.run(stop))
        for _ in range(100):
            await asyncio.sleep(0.02)
            if radio["on_air"] and radio["scanning"]:
                break
        assert radio["on_air"] == ["/org/btdragon/beacon3"], radio      # two refusals, then up
        assert radio["scanning"] and radio["starts"] >= 2                 # and scanning came back
        stop.set()
        await asyncio.gather(t1, t2)
    finally:
        asyncio.wait_for = real_wait_for
    assert radio["on_air"] == []                                          # taken down on the way out


asyncio.run(go())
assert sum("unavailable" in l for l in log_lines) == 2 and any("beacon on" in l for l in log_lines), log_lines

# without the pause, a scanning radio refuses it (what the Pi 5 did)
radio.update(scanning=True, refuse=0, on_air=[])
b = friends.Beacon(lambda: a, bus_fn=bus_fn)


async def once():
    stop = asyncio.Event()
    t = asyncio.ensure_future(b.run(stop))
    await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(t, 70)


asyncio.run(once())
assert radio["on_air"] == [] and b.failures >= 1
print("beacon pause ok")

# the Den's tick box: off takes the beacon off the air at once (scanning paused for it), on puts it back
radio.update(scanning=False, refuse=0, on_air=[])
state = {"on": True}


async def toggled():
    stop = asyncio.Event()
    sc = BleakScanner(lambda *a: None, bleak_cls=FakeScan)
    b = friends.Beacon(lambda: a, quiet=sc.quiet, bus_fn=bus_fn, enabled_fn=lambda: state["on"])
    b.GAP_S = 0
    t1 = asyncio.ensure_future(sc.run(stop))
    t2 = asyncio.ensure_future(b.run(stop))
    for _ in range(100):
        await asyncio.sleep(0.02)
        if radio["on_air"]:
            break
    assert radio["on_air"], radio
    state["on"] = False
    b.kick.set()                                  # (what the BEACON command does)
    for _ in range(100):
        await asyncio.sleep(0.02)
        if not radio["on_air"]:
            break
    assert radio["on_air"] == [], radio
    state["on"] = True
    b.kick.set()
    for _ in range(100):
        await asyncio.sleep(0.02)
        if radio["on_air"]:
            break
    assert len(radio["on_air"]) == 1 and radio["scanning"], radio
    stop.set()
    await asyncio.gather(t1, t2)


asyncio.run(toggled())
# the app: the tick box wins over the settings file once it's been used
import tempfile
from bt_dragon import config
from bt_dragon.app import Dragon
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
cfg["friends"]["beacon"] = False
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
assert app.beacon_on() is False and app.view()["beacon_on"] is False          # how it starts, from the card
assert asyncio.run(app.command("BEACON on")) == ["OK"] and app.beacon_on() and app.view()["beacon_on"]
asyncio.run(app.command("BEACON off"))
assert not app.beacon_on()
print("beacon switch ok")
