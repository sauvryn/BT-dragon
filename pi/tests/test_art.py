"""Your own artwork: pictures per mood (and second frames, and belly variants), checked,
turned into the panel's black and white, used on the screen, and the drawn placeholder
for everything else."""
import io
import os
import tempfile

from PIL import Image

from bt_dragon import art as artmod
from bt_dragon import screen

tmp = tempfile.mkdtemp()
mine, builtin = os.path.join(tmp, "harald-art"), os.path.join(tmp, "builtin")
os.makedirs(builtin)


def png(fill=0, size=(96, 86), mode="1", fmt="PNG"):
    im = Image.new(mode, size, fill)
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


a = artmod.ArtSet(mine, builtin)
a.refresh(force=True)
assert a.frame("happy") is None and a.find("happy", 1, "hungry") is None      # all drawn
drawn = a.preview("happy", scale=1)

# uploads: checked
assert a.save("happy.png", png(0)) is None
assert a.save("happy.png", png(0, (100, 86))).startswith("that picture is 100 x 86")
assert a.save("happy.png", png(0, mode="RGB", fmt="JPEG")).startswith("that's a JPEG file")
assert a.save("grumpy.png", png(0)) == "that isn't one of the mood names"
assert a.save("eating-hungry.png", png(0)) == "that isn't one of the mood names"   # belly variants: everyday moods only
assert a.save("happy.png", b"nonsense") == "that isn't a picture that can be read"
assert a.frame("happy").getpixel((10, 10)) == 0                                    # all black: it's used
assert a.preview("happy", scale=1) != drawn

# which picture for which moment
assert a.save("happy_1.png", png(255)) is None and a.save("happy-hungry.png", png(0)) is None
assert a.find("happy") == "happy.png" and a.find("happy", 1) == "happy_1.png"
assert a.find("happy", 0, "hungry") == "happy-hungry.png"
assert a.find("happy", 1, "hungry") == "happy-hungry.png"        # no second hungry frame: the first one
assert a.find("happy", 1, "stuffed") == "happy_1.png"            # no stuffed picture: the usual one
assert a.find("content") is None

# grey and transparency become ink or paper
grey = Image.new("L", (96, 86), 200)
grey.paste(60, (0, 0, 10, 10))
buf = io.BytesIO(); grey.save(buf, "PNG")
assert a.save("bored.png", buf.getvalue()) is None
f = a.frame("bored")
assert f.getpixel((5, 5)) == 0 and f.getpixel((50, 50)) == 255
assert "grey pixel" in a.problems["bored.png"]
clear = Image.new("RGBA", (96, 86), (0, 0, 0, 0))
clear.paste((0, 0, 0, 255), (40, 40, 50, 50))
buf = io.BytesIO(); clear.save(buf, "PNG")
assert a.save("lonely.png", buf.getvalue()) is None
f = a.frame("lonely")
assert f.getpixel((0, 0)) == 255 and f.getpixel((45, 45)) == 0

# files copied in from Windows, including mistakes
open(os.path.join(mine, "sleepy.png"), "wb").write(png(0, (192, 172)))
open(os.path.join(mine, "Harald big.png"), "wb").write(png(0))
open(os.path.join(builtin, "content.png"), "wb").write(png(0))
open(os.path.join(builtin, "happy.png"), "wb").write(png(255))
a.refresh(force=True)
assert "must be 96 x 86" in a.problems["sleepy.png"] and a.frame("sleepy") is None
assert "not a mood or sleep screen name" in a.problems["Harald big.png"]
assert a.frames["content.png"][1] == "built in" and a.frames["happy.png"][1] == "yours"   # yours win
rows = {r["name"]: r for r in a.table()}
assert rows["happy.png"]["used"] == "yours" and rows["content.png"]["used"] == "built in"
assert rows["eating.png"]["used"] == "" and "eating-hungry.png" not in rows and "happy-stuffed_1.png" in rows
assert rows["sleepy.png"]["problem"] and len([r for r in rows.values() if r["mood"] == "happy"]) == 6

# removing one: back to whatever's next
assert a.remove("happy.png") is None
assert a.frames["happy.png"][1] == "built in"
assert a.remove("happy.png") == "there's no picture of yours by that name"
assert a.drawn_png("happy").startswith(b"\x89PNG")

# on the screen
artmod.ART = a
v = {"name": "Harald", "mood": "lonely", "phase": 0}
img = screen.render(v)
assert img.getpixel((2 + 45, 25 + 45)) == 0 and img.getpixel((2 + 1, 25 + 1)) == 255
artmod.ART = artmod.ArtSet(None, os.path.join(tmp, "none"))
assert screen.render(v).tobytes() != img.tobytes()                # without it: the drawn Harald
print("art ok")
