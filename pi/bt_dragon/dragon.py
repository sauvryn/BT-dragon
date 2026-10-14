"""
Harald, drawn from simple shapes at 1-bit, facing the viewer so his face can show moods.

Everything is drawn into a 96x86 box. Black is 0, white is 255 (e-ink paper color).
Faces change with the mood; `phase` (0 or 1) alternates small details between refreshes
so he looks alive (chomping, blinking sparkles, drifting Zzz).
"""
import math
from PIL import ImageDraw

W, H = 96, 86
B, P = 0, 255  # black ink, paper

MOODS = ("content", "happy", "eating", "excited", "treat", "stuffed", "hungry", "starving",
         "bored", "lonely", "sleepy", "asleep", "alarmed", "uploading", "proud", "adventure", "riding",
         "ecstatic", "sneezing", "sunglasses")  # new moods go at the end: friends' beacons send the mood's number


def _ell(d, x0, y0, x1, y1, fill=P, outline=B, width=1):
    d.ellipse([x0, y0, x1, y1], fill=fill, outline=outline, width=width)


def _mirror(points, cx=48):
    return [(2 * cx - x, y) for x, y in points]


def _wings(d, flap):
    up = -4 if flap else 0
    left = [(33, 70), (13, 63 + up), (16, 69 + up), (9, 72 + up), (17, 76 + up), (12, 81 + up), (32, 81)]
    for pts in (left, _mirror(left)):
        d.polygon(pts, fill=P, outline=B)


def _tail(d):
    pts = [(64, 80), (76, 82), (85, 78), (89, 71)]
    d.line(pts, fill=B, width=3)
    d.polygon([(85, 71), (93, 62), (94, 73)], fill=B)  # spade tip


def _body(d):
    _ell(d, 30, 60, 66, 85)
    # belly plates
    for y in (73, 77):
        d.arc([48 - 7, y - 3, 48 + 7, y + 3], 20, 160, fill=B)
    # arms
    _ell(d, 29, 69, 36, 76)
    _ell(d, 60, 69, 67, 76)
    # feet
    _ell(d, 30, 79, 43, 85)
    _ell(d, 53, 79, 66, 85)
    for x in (33, 36, 40, 56, 60, 63):
        d.point((x, 82), fill=B)


def _frills(d):
    left = [(17, 46), (8, 48), (16, 51), (9, 55), (19, 56)]
    d.polygon(left, fill=P, outline=B)
    d.polygon(_mirror(left), fill=P, outline=B)


def _horns(d):
    # ivory horns curling up out of the helmet sides, with two growth rings each
    left = [(20, 29), (10, 26), (3, 17), (2, 4), (6, 3), (9, 13), (15, 19), (23, 21)]
    for pts in (left, _mirror(left)):
        d.polygon(pts, fill=P, outline=B)
    for a, b in (((4, 10), (8, 10)), ((7, 18), (11, 16))):
        d.line([a, b], fill=B)
        d.line(_mirror([a, b]), fill=B)


def _helmet(d):
    # dome
    d.chord([18, 8, 78, 54], 180, 360, fill=B, outline=B)
    # rim band with rivets
    d.rectangle([16, 29, 80, 34], fill=P, outline=B)
    for x in range(21, 78, 7):
        d.point((x, 31), fill=B)
        d.point((x, 32), fill=B)
    # ridge highlight down the dome and a nasal guard below the band
    d.line([(48, 10), (48, 28)], fill=P)
    d.line([(36, 13), (31, 22)], fill=P)
    d.rectangle([46, 34, 50, 41], fill=B)


def _head(d):
    _ell(d, 15, 18, 81, 68)


def _snout(d, open_mouth=False):
    _ell(d, 29, 52, 67, 69)
    d.rectangle([40, 56, 41, 57], fill=B)  # nostrils
    d.rectangle([55, 56, 56, 57], fill=B)


# ---------------------------------------------------------------- face pieces

def _eye_open(d, cx, cy, look=0):
    _ell(d, cx - 5, cy - 6, cx + 5, cy + 6, fill=B)
    d.rectangle([cx - 3 + look, cy - 4, cx - 1 + look, cy - 2], fill=P)  # shine


def _eye_happy(d, cx, cy):          # ^ shaped
    d.line([(cx - 5, cy + 2), (cx, cy - 3), (cx + 5, cy + 2)], fill=B, width=2)


def _eye_closed(d, cx, cy):         # u shaped, content/asleep
    d.arc([cx - 5, cy - 4, cx + 5, cy + 3], 20, 160, fill=B, width=2)


def _eye_line(d, cx, cy):
    d.line([(cx - 5, cy), (cx + 5, cy)], fill=B, width=2)


def _eye_half(d, cx, cy):           # bored: lid over the top half
    _ell(d, cx - 5, cy - 4, cx + 5, cy + 6, fill=B)
    d.rectangle([cx - 6, cy - 5, cx + 6, cy], fill=P)
    d.line([(cx - 6, cy), (cx + 6, cy)], fill=B, width=2)


def _eye_wide(d, cx, cy):           # alarmed: big white with tiny pupil
    _ell(d, cx - 6, cy - 7, cx + 6, cy + 7, fill=P, width=2)
    d.rectangle([cx - 1, cy - 1, cx + 1, cy + 1], fill=B)


def _eye_star(d, cx, cy, phase):
    r = 6 if phase else 5
    pts = []
    for i in range(8):
        a = math.pi / 4 * i - math.pi / 2
        rr = r if i % 2 == 0 else 2
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=B)


def _eye_big_star(d, cx, cy, phase):
    """Ecstatic: a big five-pointed star, almost filling the eye area."""
    r = 9 if phase else 8
    pts = []
    for i in range(10):
        a = math.pi / 5 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=B)


def _twinkles(d, phase):
    """Little four-point sparkles around his head."""
    spots = ((6, 36), (89, 22), (91, 50)) if phase else ((4, 48), (88, 34), (8, 24))
    for x, y in spots:
        d.line([(x - 2, y), (x + 2, y)], fill=B)
        d.line([(x, y - 2), (x, y + 2)], fill=B)


def _eye_sad(d, cx, cy, side):
    _ell(d, cx - 4, cy - 4, cx + 4, cy + 6, fill=B)
    d.rectangle([cx - 2, cy - 2, cx - 1, cy - 1], fill=P)
    # brows tilt up toward the middle
    inner = cx + (4 if side < 0 else -4)
    outer = cx - (5 if side < 0 else -5)
    d.line([(outer, cy - 6), (inner, cy - 9)], fill=B, width=2)


def _blush(d):
    for x in (19, 69):
        for i in range(3):
            d.line([(x + i * 3, 53), (x + i * 3 + 2, 51)], fill=B)


def _mouth_smile(d):
    d.arc([40, 58, 56, 68], 20, 160, fill=B, width=2)


def _mouth_grin(d, tongue=False):
    d.chord([38, 59, 58, 70], 0, 180, fill=B)
    if tongue:
        d.chord([44, 64, 52, 70], 0, 180, fill=P)
    else:
        # two little fangs
        d.polygon([(41, 63), (44, 63), (42, 66)], fill=P)
        d.polygon([(52, 63), (55, 63), (54, 66)], fill=P)


def _mouth_chomp(d, phase):
    if phase:
        _ell(d, 41, 59, 55, 68, fill=B)
        d.polygon([(43, 60), (46, 60), (44, 63)], fill=P)
        d.polygon([(50, 60), (53, 60), (52, 63)], fill=P)
    else:
        d.line([(40, 63), (44, 61), (48, 64), (52, 61), (56, 63)], fill=B, width=2)


def _mouth_frown(d):
    d.arc([41, 62, 55, 70], 200, 340, fill=B, width=2)


def _mouth_flat(d):
    d.line([(42, 64), (54, 64)], fill=B, width=2)


def _mouth_o(d):
    _ell(d, 45, 60, 51, 67, fill=B)


def _mouth_wavy(d):
    d.line([(40, 64), (43, 62), (46, 64), (49, 62), (52, 64), (55, 62)], fill=B, width=1)


def _eye_squeeze(d, cx, cy, side):    # sneezing: screwed shut, > <
    tip = cx + (3 if side < 0 else -3)
    back = cx - (5 if side < 0 else -5)
    d.line([(back, cy - 4), (tip, cy), (back, cy + 4)], fill=B, width=2)


def _mouth_wide(d):                   # mid-sneeze
    d.chord([39, 58, 57, 72], 0, 180, fill=B)


# ---------------------------------------------------------------- accessories

def _round_shades(d, phase):
    """Sunglasses with round frames (the Pwnagotchi's deauth face has square ones)."""
    for cx in (33, 63):
        d.ellipse([cx - 9, 35, cx + 9, 53], fill=B, outline=B)
        # a glint that moves across the lens between refreshes
        gx = cx - 4 + (3 if phase else 0)
        d.line([(gx, 41), (gx + 3, 38)], fill=P)
    d.line([(42, 43), (54, 43)], fill=B)                      # the bridge, just under his helmet's nose guard
    d.line([(24, 42), (16, 39)], fill=B, width=2)            # the arms, back to his frills
    d.line([(72, 42), (80, 39)], fill=B, width=2)


def _spray(d):
    """Achoo! Droplets flying out either side of his snout."""
    for side in (-1, 1):
        x0 = 48 + side * 21
        for dy, dx, y1 in ((-2, 9, -6), (3, 11, 3), (8, 9, 11)):
            d.line([(x0, 60 + dy), (x0 + side * dx, 60 + y1)], fill=B, width=2)
        for x, y in ((14, 52), (11, 61), (14, 70)):
            px = 48 + side * (48 - x) - (1 if side > 0 else 0)
            d.rectangle([px, y, px + 1, y + 1], fill=B)


def _zzz(d, phase):
    from .fonts import draw_text
    off = 2 if phase else 0
    draw_text(d, (82, 26 - off), "Z", scale=1)
    draw_text(d, (86, 14 - off), "Z", scale=2)


def _drool(d):
    d.line([(55, 66), (55, 71)], fill=B)
    d.rectangle([54, 71, 56, 72], fill=B)


def _sweat(d):
    d.polygon([(78, 38), (75, 44), (78, 47), (81, 44)], fill=P, outline=B)


def _shine_lines(d):
    for (a, b) in (((84, 42), (90, 38)), ((85, 48), (92, 48)), ((84, 54), (90, 58))):
        d.line([a, b], fill=B)


def _exclaim(d):
    from .fonts import draw_text
    draw_text(d, (86, 30), "!", scale=3)


def _cloud(d, phase):
    """Little arrow + cloud for uploading."""
    y = 26 if phase else 28
    _ell(d, 80, y, 89, y + 7, fill=P)
    _ell(d, 85, y - 3, 94, y + 6, fill=P)
    d.rectangle([82, y + 3, 92, y + 7], fill=P)
    d.line([(83, y + 7), (92, y + 7)], fill=B)
    d.line([(87, y + 16), (87, y + 9)], fill=B)
    d.line([(85, y + 11), (87, y + 9), (89, y + 11)], fill=B)


def draw_dragon(d: ImageDraw.ImageDraw, ox, oy, mood="content", phase=0, belly=None):
    """Draw Harald with his top-left corner at (ox, oy).

    For everyday moods (happy, content, bored, lonely, sleepy) the eyes show his JOY and
    `belly` ("hungry" or "stuffed") swaps the mouth, so he can look happy-but-hungry.
    """
    # Draw on a translated proxy so all coordinates above stay local.
    class T:
        def __getattr__(self, name):
            fn = getattr(d, name)

            def call(xy, *a, **k):
                return fn(_shift(xy, ox, oy), *a, **k)
            return call
    t = T()

    flap = phase and mood in ("excited", "treat", "happy", "proud", "uploading", "adventure", "ecstatic")
    _tail(t)
    _wings(t, flap)
    _body(t)
    _frills(t)
    _head(t)
    _horns(t)
    _helmet(t)
    _snout(t)

    L, R, EY = 33, 63, 44  # eye centers
    m = mood
    everyday = {
        "happy": (lambda: (_eye_happy(t, L, EY), _eye_happy(t, R, EY)), lambda: (_mouth_grin(t), _blush(t))),
        "content": (lambda: (_eye_open(t, L, EY, phase), _eye_open(t, R, EY, phase)), lambda: _mouth_smile(t)),
        "bored": (lambda: (_eye_half(t, L, EY), _eye_half(t, R, EY)), lambda: _mouth_flat(t)),
        "lonely": (lambda: (_eye_sad(t, L, EY, -1), _eye_sad(t, R, EY, 1)), lambda: _mouth_frown(t)),
        "sleepy": (lambda: (_eye_half(t, L, EY), _eye_half(t, R, EY)), lambda: _mouth_o(t)),
    }
    if m in everyday:
        eyes, mouth = everyday[m]
        eyes()
        if belly == "hungry":
            _mouth_o(t); _drool(t)
        elif belly == "stuffed":
            _mouth_wavy(t); _blush(t)
        else:
            mouth()
    elif m == "proud":  # leveled up
        _eye_closed(t, L, EY); _eye_closed(t, R, EY); _mouth_grin(t); _shine_lines(t)
    elif m == "eating":
        _eye_closed(t, L, EY); _eye_closed(t, R, EY); _mouth_chomp(t, phase)
    elif m == "excited":
        _eye_star(t, L, EY, phase); _eye_star(t, R, EY, phase); _mouth_grin(t, tongue=True); _shine_lines(t)
    elif m == "ecstatic":   # a big joy boost: huge starry eyes, sparkles all around
        _eye_big_star(t, L, EY, phase); _eye_big_star(t, R, EY, phase)
        _mouth_grin(t, tongue=True); _blush(t); _twinkles(t, phase)
    elif m == "treat":
        _eye_happy(t, L, EY); _eye_happy(t, R, EY); _mouth_grin(t, tongue=True); _blush(t)
    elif m == "stuffed":
        _eye_closed(t, L, EY); _eye_closed(t, R, EY); _mouth_wavy(t); _blush(t)
    elif m == "hungry":
        _eye_sad(t, L, EY, -1); _eye_sad(t, R, EY, 1); _mouth_o(t); _drool(t)
    elif m == "starving":
        _eye_sad(t, L, EY, -1); _eye_sad(t, R, EY, 1); _mouth_frown(t); _sweat(t)
    elif m == "adventure":  # out walking together
        _eye_happy(t, L, EY); _eye_happy(t, R, EY); _mouth_grin(t, tongue=True); _speed_lines(t, phase)
    elif m == "riding":     # in a vehicle: wind in his face
        _eye_open(t, L, EY, 1); _eye_open(t, R, EY, 1); _mouth_o(t); _speed_lines(t, phase)
    elif m == "asleep":
        _eye_closed(t, L, EY); _eye_closed(t, R, EY); _mouth_smile(t); _zzz(t, phase)
    elif m == "alarmed":
        _eye_wide(t, L, EY); _eye_wide(t, R, EY); _mouth_o(t); _sweat(t); _exclaim(t)
    elif m == "sneezing":   # high pollen: "ah..." then "CHOO!"
        if phase:
            _eye_squeeze(t, L, EY, -1); _eye_squeeze(t, R, EY, 1); _mouth_wide(t); _spray(t)
        else:
            _eye_half(t, L, EY); _eye_half(t, R, EY); _mouth_o(t)
    elif m == "sunglasses":  # sunshine, or high UV
        _round_shades(t, phase); _mouth_grin(t)
    elif m == "uploading":
        _eye_open(t, L, EY, 1); _eye_open(t, R, EY, 1); _mouth_smile(t); _cloud(t, phase)
    else:
        _eye_open(t, L, EY, phase); _eye_open(t, R, EY, phase); _mouth_smile(t)


def _speed_lines(d, phase):
    """Whoosh lines streaming past on his left, as if he's moving."""
    off = 2 if phase else 0
    for y, x0, x1 in ((40, 0, 8), (50, 2 + off, 10 + off), (60, 0, 7)):
        d.line([(x0, y), (x1, y)], fill=B)


def _shift(xy, ox, oy):
    """Offset any PIL coordinate form: (x, y), [x0, y0, x1, y1], or a list of points."""
    if isinstance(xy, tuple) and len(xy) == 2 and not isinstance(xy[0], (tuple, list)):
        return (xy[0] + ox, xy[1] + oy)
    if isinstance(xy, list) and len(xy) == 4 and all(isinstance(v, (int, float)) for v in xy):
        return [xy[0] + ox, xy[1] + oy, xy[2] + ox, xy[3] + oy]
    return [(x + ox, y + oy) for x, y in xy]
