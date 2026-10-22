"""
Your own artwork for Harald, in place of the drawn placeholder.

Pictures are 96 x 86 pixels, black and white, PNG, one per mood, named after it:
    happy.png            the happy face
    happy_1.png          (optional) a second frame: he alternates the two on screen updates,
                         for blinking, chomping, drifting Zzz...
    happy-hungry.png     (optional, the everyday moods) when his belly is empty
    happy-stuffed.png    (optional, the everyday moods) when it's full
Any mood without a picture keeps the drawn version, so they can be replaced one at a time.

The sleep screens are whole-screen pictures, 250 x 122: nap-screen.png (while he naps) and
sleep-screen.png (left on the e-ink when he's put to sleep). Without yours, a drawn one: his
sleeping face alone in a white circle on black, with NAP or SLEEP in the corner.

Where they go: the folder "bt-dragon-art" (once "harald-art") on the card's boot partition (the one Windows can
open), next to bt-dragon.toml, or uploaded from the den's art page, which saves them there.
Pictures shipped with the program (bt_dragon/art/) are used for moods you haven't drawn.

On the panel every pixel is ink or paper, so each picture is turned into exactly that:
transparent counts as paper, and anything grey becomes black if it's darker than half way
and white if it's lighter. The den's art page shows the result and points out grey pixels
and wrong sizes, so there are no surprises.
"""
import io
import logging
import os
import re
import time

from PIL import Image, ImageDraw

from .dragon import MOODS, draw_dragon, draw_sleeping_face
from .fonts import draw_text, text_width

log = logging.getLogger("art")

W, H = 96, 86
EVERYDAY = ("happy", "content", "bored", "sleepy")
BELLIES = ("hungry", "stuffed")
NAME_RE = re.compile(r"^(?P<mood>[a-z]+)(?:-(?P<belly>hungry|stuffed))?(?:_(?P<frame>1))?\.png$")
HERE = os.path.dirname(os.path.abspath(__file__))
MAX_BYTES = 200 * 1024
SW, SH = 250, 122                    # the whole screen
SCREENS = {"nap-screen.png": "nap", "sleep-screen.png": "sleep"}


def size_for(name):
    return (SW, SH) if name in SCREENS else (W, H)


def drawn_screen(kind, phase=1):
    """The placeholder sleep screen: flat black, a white circle in the middle with his
    sleeping face, and NAP or SLEEP in bold white at the bottom right."""
    img = Image.new("1", (SW, SH), 0)
    d = ImageDraw.Draw(img)
    cx, cy, r = SW // 2, SH // 2, 58
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    # the face's drawing fills about x 2-96, y 3-69 of its box: centre that in the circle
    draw_sleeping_face(d, cx - 49, cy - 36, phase)
    word = "NAP" if kind == "nap" else "SLEEP"
    x, y = SW - 5 - text_width(word), SH - 4 - 7
    for dx in (0, 1):                    # drawn twice, a pixel apart: bold
        draw_text(d, (x + dx, y), word, fill=255)
    return img

MOOD_NOTES = {
    "content": "the everyday face", "happy": "good mood", "bored": "nothing happening for a while",
    "sleepy": "late, or tired", "asleep": "sleeping and napping",
    "eating": "a Bluetooth snack", "treat": "a Wi-Fi treat", "stuffed": "belly full", "hungry": "belly low",
    "famished": "belly empty", "excited": "something new", "ecstatic": "a big joy boost",
    "proud": "level up", "alarmed": "an unknown tracker following you", "uploading": "sending to WiGLE",
    "adventure": "out walking together", "riding": "in a vehicle",
    "sneezing": "high pollen or poor air at the Lair", "sunglasses": "sunshine",
    "dazzled": "high UV at the Lair",
}


def valid_name(name):
    if name in SCREENS:
        return True
    m = NAME_RE.match(name or "")
    if not m or m.group("mood") not in MOODS:
        return None
    if m.group("belly") and m.group("mood") not in EVERYDAY:
        return None
    return m


def to_panel(img):
    """Any picture -> the panel's black and white: transparent is paper, grey is cut at
    half way. Returns (1-bit image, how many pixels weren't pure black or white)."""
    img.load()
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        paper = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        paper.alpha_composite(rgba)
        img = paper
    grey = img.convert("L")
    hist = grey.histogram()
    in_between = sum(hist[1:255])
    return grey.point(lambda p: 255 if p >= 128 else 0).convert("1"), in_between


class ArtSet:
    def __init__(self, user_dir=None, builtin_dir=os.path.join(HERE, "art")):
        self.user_dir = user_dir
        self.builtin_dir = builtin_dir
        self.frames = {}          # file name -> (1-bit image, where: "yours"/"built in")
        self.problems = {}        # file name -> what's wrong with it
        self._stamp = None
        self._checked = 0.0

    def _listing(self):
        out = []
        for where, folder in (("built in", self.builtin_dir), ("yours", self.user_dir)):
            if folder and os.path.isdir(folder):
                for fn in sorted(os.listdir(folder)):
                    if where == "yours" and fn.startswith("starving"):
                        # the "starving" face is called "famished" now: your picture keeps working
                        new = "famished" + fn[len("starving"):]
                        try:
                            if not os.path.exists(os.path.join(folder, new)):
                                os.rename(os.path.join(folder, fn), os.path.join(folder, new))
                                fn = new
                        except OSError:
                            pass
                    p = os.path.join(folder, fn)
                    if fn.lower().endswith(".png") and os.path.isfile(p):
                        out.append((where, fn, p, os.path.getmtime(p), os.path.getsize(p)))
        return out

    def refresh(self, force=False):
        """Look at the folders again (at most every 10 s): new, changed or removed pictures
        are used without a restart."""
        now = time.monotonic()
        if not force and now - self._checked < 10:
            return
        self._checked = now
        listing = self._listing()
        stamp = [(w, f, m, s) for w, f, _, m, s in listing]
        if stamp == self._stamp:
            return
        self._stamp = stamp
        frames, problems = {}, {}
        for where, fn, path, _, size in listing:        # yours come last, so they win
            name = fn.lower()
            if not valid_name(name):
                problems[fn] = "not a mood or sleep screen name, so it isn't used (see the list of names)"
                continue
            w, h = size_for(name)
            if size > MAX_BYTES:
                problems[fn] = f"too big a file for a {w} x {h} picture"
                continue
            try:
                with Image.open(path) as im:
                    if im.size != (w, h):
                        problems[fn] = f"{im.size[0]} x {im.size[1]} pixels: it must be {w} x {h}, so it isn't used"
                        continue
                    img, grey = to_panel(im)
            except Exception as e:
                problems[fn] = f"can't be read as a picture ({e})"
                continue
            frames[name] = (img, where)
            problems.pop(fn, None)
            if grey and where == "yours":
                problems[fn] = (f"{grey} grey pixel{'s' if grey != 1 else ''}: used, but each becomes black or "
                                "white (the preview shows how)")
        self.frames, self.problems = frames, problems
        log.info("artwork: %d pictures (%d yours)", len(frames), sum(1 for _, w in frames.values() if w == "yours"))

    def find(self, mood, phase=0, belly=None):
        """The file name of the picture for this moment, or None (the drawn one)."""
        tries = []
        if belly in BELLIES and mood in EVERYDAY:
            if phase:
                tries.append(f"{mood}-{belly}_1.png")
            tries.append(f"{mood}-{belly}.png")
        if phase:
            tries.append(f"{mood}_1.png")
        tries.append(f"{mood}.png")
        return next((t for t in tries if t in self.frames), None)

    def frame(self, mood, phase=0, belly=None):
        """The picture to show, or None to draw him as before."""
        self.refresh()
        name = self.find(mood, phase, belly)
        return self.frames[name][0] if name else None

    def draw(self, img, x, y, mood="content", phase=0, belly=None):
        """Harald at (x, y) on a screen image: a picture if there is one, else drawn."""
        pic = self.frame(mood, phase, belly)
        if pic is not None:
            img.paste(pic, (x, y))
        else:
            draw_dragon(ImageDraw.Draw(img), x, y, mood, phase, belly)

    def screen(self, kind):
        """The nap or sleep screen: yours if there is one, else the drawn one."""
        self.refresh()
        got = self.frames.get(f"{kind}-screen.png")
        return got[0].copy() if got else drawn_screen(kind)

    def screen_rows(self):
        self.refresh()
        return [{"name": n, "kind": k, "used": (self.frames.get(n) or (None, ""))[1],
                 "problem": self.problems.get(n, "")} for n, k in SCREENS.items()]

    def screen_png(self, kind, drawn=False, scale=1):
        img = drawn_screen(kind) if drawn else self.screen(kind)
        if scale > 1:
            img = img.resize((SW * scale, SH * scale), Image.NEAREST)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    # ---------------------------------------------------------------- for the den
    def preview(self, mood, phase=0, belly=None, scale=3):
        """A PNG of what the panel shows for this moment, enlarged with crisp pixels."""
        self.refresh()
        img = Image.new("1", (W, H), 255)
        self.draw(img, 0, 0, mood, phase, belly)
        if scale > 1:
            img = img.resize((W * scale, H * scale), Image.NEAREST)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def drawn_png(self, mood, phase=0, belly=None):
        """The drawn placeholder at actual size: a template to draw over."""
        img = Image.new("1", (W, H), 255)
        draw_dragon(ImageDraw.Draw(img), 0, 0, mood, phase, belly)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def table(self):
        """Every picture he can use: [{name, mood, frame, belly, used ("yours"/"built in"/"drawn"), problem}]."""
        self.refresh()
        rows = []
        for mood in MOODS:
            if mood == "lonely":         # (no longer shown: at worst he's bored, never sad)
                continue
            for belly in (None,) + (BELLIES if mood in EVERYDAY else ()):
                for frame in (0, 1):
                    name = f"{mood}{'-' + belly if belly else ''}{'_1' if frame else ''}.png"
                    got = self.frames.get(name)
                    rows.append({"name": name, "mood": mood, "frame": frame, "belly": belly or "",
                                 "used": got[1] if got else "", "shown": self.find(mood, frame, belly) or "",
                                 "problem": self.problems.get(name, "")})
        return rows

    def save(self, name, data):
        """A picture uploaded from the den. Returns an error, or None."""
        if not self.user_dir:
            return "there's nowhere to keep pictures (no settings file found)"
        if not valid_name(name):
            return "that isn't one of the mood names"
        w, h = size_for(name)
        if len(data) > MAX_BYTES:
            return f"that file is too big for a {w} x {h} picture"
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.format != "PNG":
                    return f"that's a {im.format} file: save it as PNG (JPEG blurs the edges into grey)"
                if im.size != (w, h):
                    return f"that picture is {im.size[0]} x {im.size[1]} pixels: it must be {w} x {h}"
        except Exception:
            return "that isn't a picture that can be read"
        os.makedirs(self.user_dir, exist_ok=True)
        path = os.path.join(self.user_dir, name)
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(path + ".tmp", path)
        self.refresh(force=True)
        return None

    def remove(self, name):
        if not self.user_dir or not valid_name(name):
            return "that isn't one of the mood names"
        try:
            os.remove(os.path.join(self.user_dir, name))
        except FileNotFoundError:
            return "there's no picture of yours by that name"
        self.refresh(force=True)
        return None


ART = ArtSet()


def configure(user_dir):
    global ART
    ART = ArtSet(user_dir)
    ART.refresh(force=True)
    return ART
