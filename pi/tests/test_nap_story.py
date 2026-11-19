"""Steps taken while Harald naps are a story you tell him ("You told Harald about your
adventure!"), not a walk with him: the nap forgets the step count it was following, even when
the phone's link is cancelled mid-read rather than lost."""
import asyncio
import tempfile

from bt_dragon import activity as actmod, config
from bt_dragon.app import Dragon

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
app.gps.state = lambda: "NOFIX"
stories, walks = [], []
app.pet.story = lambda meters, n: stories.append(n)
app.activity.add = lambda mode, n: walks.append(n)

# awake, the phone linked: steps with him, indoors (no GPS) are a walk with him
app.on_steps(10000)
app.on_steps(10050)
assert walks and not stories

# a nap; you go out without him (the phone's steps arrive, or don't: either way they're ignored)
walks.clear()
assert asyncio.run(app.nap()).startswith("OK")
app.on_steps(12000)
app.on_steps(14000)
assert not walks and not stories
assert asyncio.run(app.wake_up()).startswith("OK")
app.on_steps(14050)                        # the first reading after waking: a story of the nap's steps
assert stories == [4000] and not walks, (stories, walks)
assert any("You told" in e["text"] and "4,000 steps" in e["text"] for e in app.store.events(5))
app.on_steps(14100)                        # then it's walking with him again
assert walks


# the link itself: cancelled mid-read (as a nap does) still counts as lost
class _Link(actmod.SensorLink):
    async def _session(self, host, port, stop):
        self.connected = True
        await asyncio.sleep(60)


lost = []
link = _Link(lambda v: None, lambda: lost.append(1))


async def go():
    stop = asyncio.Event()
    t = asyncio.ensure_future(link.run(lambda: "127.0.0.1", 1, stop))
    await asyncio.sleep(0.1)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass


asyncio.run(go())
assert lost == [1] and not link.connected
print("nap story ok")
