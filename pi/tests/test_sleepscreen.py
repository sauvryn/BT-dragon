"""Sleep screens: the drawn ones (his sleeping face in a white circle on black, NAP or SLEEP in
the corner), your own pictures in their place, the den's two tick boxes, and which picture is
left on the e-ink for a nap and for sleep."""
import asyncio
import io
import os
import tempfile

from PIL import Image

from bt_dragon import art, config
from bt_dragon.app import Dragon

# the drawn screens
for kind in ("nap", "sleep"):
    img = art.drawn_screen(kind)
    assert img.size == (250, 122) and img.mode == "1"
    px = img.load()
    assert px[0, 0] == 0 and px[249, 0] == 0 and px[0, 121] == 0 and px[20, 61] == 0     # black outside the circle
    assert px[125, 3] == 255 and px[70, 61] == 255                                          # white inside it
    corner = img.crop((200, 105, 250, 122))
    assert 0 < corner.histogram()[255] < 200                                  # the word, in white
nap, sleep = art.drawn_screen("nap"), art.drawn_screen("sleep")
assert nap.crop((0, 0, 200, 122)).tobytes() == sleep.crop((0, 0, 200, 122)).tobytes()   # only the word differs
assert nap.tobytes() != sleep.tobytes()

# your own
tmp = tempfile.mkdtemp()
a = art.ArtSet(os.path.join(tmp, "harald-art"))


def png(w, h, colour=0):
    b = io.BytesIO()
    Image.new("L", (w, h), colour).save(b, "PNG")
    return b.getvalue()


assert "250 x 122" in a.save("nap-screen.png", png(96, 86))
assert a.save("nap-screen.png", png(250, 122, 0)) is None
assert a.screen("nap").histogram()[255] == 0 and a.screen("sleep").getpixel((125, 3)) == 255
rows = {r["kind"]: r for r in a.screen_rows()}
assert rows["nap"]["used"] == "yours" and rows["sleep"]["used"] == ""
assert a.remove("nap-screen.png") is None and a.screen("nap").getpixel((125, 3)) == 255
assert "96 x 86" in a.save("happy.png", png(250, 122))                # moods are still 96 x 86

# the den's tick boxes: both on unless unticked
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
run = lambda c: asyncio.run(app.command(c))                             # noqa: E731
assert run("SLEEPSCREEN") == ["nap=1", "sleep=1", "END"]
assert app._nap_picture().tobytes() == art.drawn_screen("nap").tobytes()
assert run("SLEEPSCREENSET nap off") == ["OK"] and run("SLEEPSCREEN")[:2] == ["nap=0", "sleep=1"]
assert app._nap_picture().getpixel((0, 0)) == 255                      # the old nap picture: white paper
assert run("SLEEPSCREENSET bed on")[0].startswith("ERR") and run("SLEEPSCREENSET nap maybe")[0].startswith("ERR")
app.napping = True
run("SLEEPSCREENSET nap on")
assert app._nap_redraw                                                  # napping now: redrawn


# put to sleep: the sleep screen stays on the e-ink
async def go(a, how):
    a.dot.release = lambda: asyncio.sleep(0)
    await a.shutdown(how)

asyncio.run(go(app, "SLEEP"))
shown = Image.open(io.BytesIO(app.display.png)).convert("1")
assert shown.tobytes() == art.drawn_screen("sleep").tobytes()

cfg["data_dir"] = tempfile.mkdtemp()
app2 = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
asyncio.run(app2.command("SLEEPSCREENSET sleep off"))
asyncio.run(go(app2, "SLEEP"))
assert Image.open(io.BytesIO(app2.display.png)).convert("1").getpixel((0, 0)) == 255     # the old picture
print("sleep screens ok")
