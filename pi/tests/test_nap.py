"""Nap mode: as good as switched off (nothing runs, nothing is written), wakeable from the
den, and still napping after a restart."""
import asyncio
import os
import tempfile

from bt_dragon import config
from bt_dragon.app import Dragon

tmp = tempfile.mkdtemp()


def make():
    cfg = config.load(None)
    cfg["data_dir"] = tmp
    cfg["diary"]["files"] = False
    return Dragon(cfg, simulate=True, out_dir=tmp)


def count_events(app):
    return app.store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]


async def main():
    app = make()
    assert not app.napping and app.view()["napping"] is False
    # something that only runs while he's awake (like the Bluetooth scanner)
    runs = []

    async def radio(stop):
        runs.append("on")
        await stop.wait()
        runs.append("off")
    task = asyncio.ensure_future(app._awake_only(radio))
    await asyncio.sleep(0.1)
    assert runs == ["on"]

    assert await app.command("NAP") == ["OK napping"] and app.napping
    assert app.store.get("napping")["since"] > 0 and app.view()["napping"] is True
    for _ in range(40):
        await asyncio.sleep(0.1)
        if runs[-1] == "off":
            break
    assert runs == ["on", "off"], runs                     # the radio is stopped for the nap
    # nothing is written while napping: no diary entries, no meals, the Dot silent
    n, meals = count_events(app), app.pet.total_meals
    app.event("treat", "New Wi-Fi: should not be recorded")
    app.on_advert("C0:11:22:33:44:55", "public", -50, "JBL Flip 5", {0x0057: b"\x01"}, [], {})
    app.on_steps(1000)
    app.dot.say("A TREAT!", force=True)
    assert count_events(app) == n and app.pet.total_meals == meals and not app.dot.queue
    assert app.dot.rescue_wanted([{"ssid": "Amazon-XY7", "rssi": -40}]) is False
    assert await app.command("NAP") == ["OK already napping"]

    # a restart (or power cut) mid-nap: he comes back still napping, without a "woke up" entry
    again = make()
    assert again.napping and again.nap_since == app.nap_since

    assert await app.command("WAKE") == ["OK awake"] and not app.napping
    assert app.store.get("napping") is None and count_events(app) == n + 1
    for _ in range(40):                                      # the radio starts again
        await asyncio.sleep(0.1)
        if runs[-1] == "on" and len(runs) == 3:
            break
    assert runs == ["on", "off", "on"], runs
    assert make().napping is False
    assert await app.command("WAKE") == ["OK already awake"]
    app.stop.set()
    await asyncio.wait_for(task, 20)


asyncio.run(main())
print("nap ok")
