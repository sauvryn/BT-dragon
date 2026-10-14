"""Where his words go: a typed question is answered out loud through the phone alone, and
nothing (not even a ringing timer) piles up for a Dot that's away."""
import asyncio
import tempfile

from bt_dragon import config
from bt_dragon.app import Dragon

tmp = tempfile.mkdtemp()
cfg = config.load(None)
cfg["data_dir"] = tmp
app = Dragon(cfg, simulate=True, out_dir=tmp)
d = app.dot
pushed = []
d.phone.push = pushed.append

# the phone only: a typed question is spoken through it
d.s["enabled"], d.s["phone"] = False, True
r = asyncio.run(app.command("ASK what day is it"))
assert r[0].startswith("OK ") and pushed and pushed[-1] == r[0][3:], (r, pushed)

# the Dot switched on but away: forced words (timers, reminders, answers) aren't saved up
d.s["enabled"], d.s["phone"] = True, False
d.connected = d.ready = False
d.queue.clear()
for _ in range(10):
    d.say("Pasta timer is done!", force=True)
assert d.queue == [], d.queue
# and once it's here, they go straight to it
d.connected = d.ready = True
d.say("Pasta timer is done!", force=True)
assert d.queue == ["Pasta timer is done!"]

# Adventure mode through the phone alone: lands, a few at a time, still get announced
import time  # noqa: E402
d.s.update(enabled=False, phone=True, chatty="adventure")
d.connected = d.ready = False
pushed.clear()
d.adventure("land")
d.adventure("land")
d._adv["land_ts"] = time.time() - 20


async def tick():
    task = asyncio.ensure_future(d._timer_loop())
    await asyncio.sleep(0.3)
    app.stop.set()
    await asyncio.sleep(1.2)
    task.cancel()
asyncio.run(tick())
assert "Two new lands! I claim them!" in pushed, pushed
print("speech routes ok")
