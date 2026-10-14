"""
Harald's light ring on an Echo Dot (2nd generation).

The Dot's ring is 12 RGB lights driven by an IS31FL3236 chip (36 brightness channels =
12 lights x red, green, blue). Linux exposes the chip as a text file:

    /sys/devices/soc/11007000.i2c/i2c-0/0-003f/frame

Writing 72 hex digits to it (RRGGBB for each light, light 0 first) shows that picture
at once. Light 0 sits at about half past seven when you look down on the Dot, and the
numbers run clockwise.

This module draws animations as lists of frames and turns them into the text the small
player script on the Dot plays (one frame per line: "<seconds> <72 hex digits>").

Colors here are "how bright it should look", from 0 to 1. Three corrections turn that
into what the chip needs:
  * gamma: our eyes see brightness on a curve, so half-bright-looking is only about a
    quarter of the light. Raising to the power 2.2 makes fades look even.
  * color balance: on this ring the green and blue lights are much brighter than the red
    ones, so equal numbers look greenish-blue. Each color is scaled down by its own
    amount (adjustable in the den, by eye).
  * overall brightness (also in the den).
"""
import math
import random

LEDS = 12
FRAME_S = 0.07          # one frame every 70 ms: about as fast as the Dot's shell keeps up
GAMMA = 2.2
OFF = (0.0, 0.0, 0.0)

# the palette, as it should look
GOLD = (1.0, 0.62, 0.05)
AMBER = (1.0, 0.45, 0.0)
ORANGE = (1.0, 0.32, 0.0)
RED = (1.0, 0.0, 0.0)
GREEN = (0.15, 1.0, 0.1)
LEAF = (0.55, 0.9, 0.0)
CYAN = (0.0, 0.85, 1.0)
BLUE = (0.0, 0.25, 1.0)
NIGHT = (0.05, 0.1, 0.6)
PURPLE = (0.65, 0.1, 1.0)
WHITE = (1.0, 1.0, 1.0)
SILVER = (0.75, 0.8, 1.0)


def scale(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


# ------------------------------------------------------------------ animations
# Each returns a list of (seconds, [12 colors]).

def solid(c, hold=1.0):
    return [(hold, [c] * LEDS)]


def breathe(c, period=3.0, lo=0.25, hi=1.0):
    n = max(2, round(period / FRAME_S))
    out = []
    for i in range(n):
        k = lo + (hi - lo) * (0.5 - 0.5 * math.cos(2 * math.pi * i / n))
        out.append((FRAME_S, [scale(c, k)] * LEDS))
    return out


def spin(c, period=1.2, tail=4, bg=OFF, turns=1):
    """A comet running clockwise round the ring."""
    n = max(LEDS, round(period / FRAME_S))
    out = []
    for i in range(n * turns):
        head = (i % n) * LEDS / n
        leds = []
        for j in range(LEDS):
            behind = (head - j) % LEDS
            k = max(0.0, 1 - behind / tail) if behind < tail else 0.0
            leds.append(mix(bg, c, k))
        out.append((FRAME_S, leds))
    return out


def pulse(c, on=0.25, off=0.25, times=1, bg=OFF):
    out = []
    for _ in range(times):
        out.append((on, [c] * LEDS))
        out.append((off, [bg] * LEDS))
    return out


def lightning(seed=3, seconds=6.0):
    """A storm: deep blue sky with lightning flicking across parts of the ring."""
    rnd = random.Random(seed)
    sky = scale(NIGHT, 0.5)
    out = []
    t = 0.0
    while t < seconds:
        if rnd.random() < 0.12:
            start, width = rnd.randrange(LEDS), rnd.randint(2, 6)
            lit = {(start + j) % LEDS for j in range(width)}
            for k in (1.0, 0.3, 0.9, 0.0):
                out.append((FRAME_S, [mix(sky, WHITE, k) if j in lit else sky for j in range(LEDS)]))
                t += FRAME_S
        else:
            out.append((0.14, [sky] * LEDS))
            t += 0.14
    return out


def twinkle(c=WHITE, seed=5, seconds=3.0, bg=OFF):
    rnd = random.Random(seed)
    level = [0.0] * LEDS
    out = []
    for _ in range(round(seconds / FRAME_S)):
        level = [v * 0.75 for v in level]
        if rnd.random() < 0.5:
            level[rnd.randrange(LEDS)] = 1.0
        out.append((FRAME_S, [mix(bg, c, v) for v in level]))
    return out


def fill(c, seconds=1.0, hold=0.6):
    """Lights come on one by one, clockwise, then all flash."""
    out = []
    step = seconds / LEDS
    for i in range(1, LEDS + 1):
        out.append((step, [c if j < i else OFF for j in range(LEDS)]))
    out.append((hold, [c] * LEDS))
    out += pulse(WHITE, 0.1, 0.1, 2, bg=c)
    out.append((hold, [c] * LEDS))
    return out


def portion(c, lit, hold=3.0, bg=OFF):
    """`lit` (0..1) of the ring shown, as a block of lights: the moon's lit part."""
    n = round(lit * LEDS)
    return [(hold, [c if j < n else bg for j in range(LEDS)])]


def flicker(c, seconds=30.0, seed=9):
    """Speaking: a lively glow that wobbles like a voice."""
    rnd = random.Random(seed)
    out = []
    k = 0.6
    for _ in range(round(seconds / FRAME_S)):
        k = max(0.35, min(1.0, k + rnd.uniform(-0.25, 0.25)))
        out.append((FRAME_S, [scale(c, k)] * LEDS))
    return out


def fade_out(c, seconds=0.4):
    n = max(2, round(seconds / FRAME_S))
    return [(FRAME_S, [scale(c, 1 - (i + 1) / n)] * LEDS) for i in range(n)]


# The resting look for each of Harald's moods (these loop)
MOOD_ANIM = {
    "content": lambda: breathe(GOLD, 4.0, 0.25, 0.6),
    "happy": lambda: breathe(GOLD, 3.0, 0.35, 1.0),
    "ecstatic": lambda: spin(GOLD, 1.0, tail=6, bg=scale(AMBER, 0.3)),
    "excited": lambda: breathe(AMBER, 1.2, 0.3, 1.0),
    "eating": lambda: breathe(LEAF, 1.5, 0.3, 0.9),
    "treat": lambda: breathe(LEAF, 1.5, 0.3, 0.9),
    "stuffed": lambda: breathe(AMBER, 5.0, 0.4, 0.7),
    "hungry": lambda: breathe(ORANGE, 3.0, 0.1, 0.6),
    "starving": lambda: breathe(RED, 2.5, 0.05, 0.7),
    "bored": lambda: breathe(scale(SILVER, 0.6), 6.0, 0.15, 0.4),
    "lonely": lambda: breathe(BLUE, 6.0, 0.1, 0.4),
    "sleepy": lambda: breathe(NIGHT, 7.0, 0.1, 0.35),
    "asleep": lambda: breathe(NIGHT, 8.0, 0.05, 0.2),
    "alarmed": lambda: pulse(RED, 0.3, 0.3),
    "uploading": lambda: spin(CYAN, 1.0, tail=4),
    "proud": lambda: breathe(PURPLE, 3.0, 0.3, 1.0),
    "adventure": lambda: spin(GREEN, 1.6, tail=5, bg=scale(GREEN, 0.1)),
    "riding": lambda: spin(GREEN, 0.8, tail=5, bg=scale(GREEN, 0.1)),
}

# One-off displays for things that happen (these play once, then the mood comes back)
EVENT_ANIM = {
    "nom": lambda: pulse(LEAF, 0.15, 0.1, 2),
    "treat": lambda: spin(LEAF, 0.8, tail=5) + fade_out(LEAF),
    "species": lambda: spin(GREEN, 0.9, tail=6, turns=3) + fade_out(GREEN),
    "level": lambda: fill(GOLD) + fade_out(GOLD, 0.8),
    "landmark": lambda: spin(WHITE, 1.2, tail=8, turns=2) + fade_out(WHITE),
    "storm": lambda: lightning(),
    "weather": lambda: breathe(CYAN, 2.0, 0.1, 0.8) * 2,
    "star": lambda: twinkle(),
    "realm": lambda: fill(GREEN) + fade_out(GREEN, 0.8),
    "land": lambda: spin(LEAF, 0.7, tail=4),
    "friend": lambda: twinkle(GOLD, seconds=2.5) + fade_out(GOLD),
    "alert": lambda: pulse(RED, 0.2, 0.2, 6),
    "talk": lambda: flicker(GOLD),
    "hush": lambda: fade_out(GOLD, 0.3),
    "listen": lambda: breathe(CYAN, 1.2, 0.35, 1.0) * 7,           # recording a question (~8 s)
    "think": lambda: spin(CYAN, 0.6, tail=5) * 6,                  # working out the answer
    "alarm": lambda: (pulse(ORANGE, 0.25, 0.15, 6) + pulse(GOLD, 0.25, 0.15, 6)) * 4,
    "test": lambda: [(6.0, [RED, RED, ORANGE, ORANGE, GOLD, GOLD, GREEN, GREEN, BLUE, BLUE, WHITE, WHITE])],
}


def moon_anim(lit):
    return portion(SILVER, lit, 3.0) + fade_out(SILVER)


# ------------------------------------------------------------------ to the chip
def hex_frame(leds, balance=(1.0, 0.5, 0.65), brightness=0.6, gamma=GAMMA):
    """12 colors -> the 72 hex digits the chip takes."""
    out = []
    for c in leds:
        for i in range(3):
            v = max(0.0, min(1.0, c[i])) ** gamma * balance[i] * brightness
            out.append(f"{min(255, round(v * 255)):02X}")
    return "".join(out)


def to_text(frames, **kw):
    """Frames -> the player's file format: one '<seconds> <hex>' line per frame. Repeated
    identical frames are merged into one longer one."""
    lines = []
    last_hex, last_s = None, 0.0
    for s, leds in frames:
        h = hex_frame(leds, **kw)
        if h == last_hex:
            last_s += s
            continue
        if last_hex is not None:
            lines.append(f"{last_s:.2f} {last_hex}")
        last_hex, last_s = h, s
    if last_hex is not None:
        lines.append(f"{last_s:.2f} {last_hex}")
    return "\n".join(lines) + "\n"


def all_animations(night=False):
    """{file name: frames} for everything the player needs."""
    anims = {"off": solid(OFF, 1.0), "night": breathe(NIGHT, 8.0, 0.1, 0.3)}
    for k, f in MOOD_ANIM.items():
        anims["mood_" + k] = f()
    for k, f in EVENT_ANIM.items():
        anims["ev_" + k] = f()
    for i in range(LEDS + 1):           # the moon, from new (0 lit) to full (12 lit)
        anims[f"moon_{i}"] = moon_anim(i / LEDS)
        # a kitchen timer counting down: i lights left, gently breathing
        anims[f"timer_{i}"] = [(f, [c if j < max(1, i) else OFF for j, c in enumerate(leds)])
                               for f, leds in breathe(AMBER, 3.0, 0.45, 0.9)]
        anims[f"vol_{i}"] = portion(WHITE, i / LEDS, 1.2) + fade_out(WHITE, 0.3)
    anims["muted"] = breathe(RED, 6.0, 0.25, 0.45)
    return anims
