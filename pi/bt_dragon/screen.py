"""
Lays out the 250x122 e-ink screen.

 ┌──────────────────────────────────────────────┐
 │ ᚺᚨᚱᚨᛚᛞ (runes)                  HARALD  LV 4 │  name banner
 │/////////////// carved band ///////////////////│
 │  ┌─────────┐  JOY   [■■■■■■□□□□]              │
 │  │ Harald  │  BELLY [■■■■■■■■□□]              │
 │  │  face   │  PACK  [■■■□□□□□□□]              │
 │  │         │                                  │  (a little breathing room)
 │  │         │  SNACKS 34  TYPES 12 (+2)        │  today's counts only;
 │  │         │  WALK 1.2KM  TREATS 5            │  lifetime totals are in the den
 │  │         │  PALS 2/3  FRIENDS 1             │
 │  │         │  GPS FIX  WIGLE 120  45°C        │
 │  └─────────┘  UP 02:13  CPU 12%  MEM 38%      │
 │───────────────────────────────────────────────│
 │ NOM! 3 NEW SNACKS                    ((  ⚓    │  status line: hotspot + link icons
 └──────────────────────────────────────────────┘
"""
from PIL import Image, ImageDraw

from . import art as artmod
from . import lang as langmod
from .fonts import FONT_LATIN, FONT_RUNES, draw_text, fit_text, text_width, to_runes

WIDTH, HEIGHT = 250, 122
PANEL_X = 102


def _band(d, y):
    """A carved band like the serpent ribbons on rune stones."""
    d.line([(0, y), (WIDTH - 1, y)], fill=0)
    d.line([(0, y + 4), (WIDTH - 1, y + 4)], fill=0)
    for x in range(-4, WIDTH, 5):
        d.line([(x, y + 4), (x + 4, y)], fill=0)


def _bar(d, x, y, w, h, frac, segments=10):
    d.rectangle([x, y, x + w - 1, y + h - 1], outline=0, fill=255)
    seg_w = (w - 2) / segments
    filled = round(max(0.0, min(1.0, frac)) * segments)
    for i in range(filled):
        x0 = int(x + 2 + i * seg_w)
        x1 = int(x + 1 + (i + 1) * seg_w) - 1
        d.rectangle([x0, y + 2, x1, y + h - 3], fill=0)


def _wifi_icon(d, x, y):
    d.rectangle([x + 3, y + 5, x + 4, y + 6], fill=0)
    d.arc([x + 1, y + 2, x + 6, y + 8], 225, 315, fill=0)
    d.arc([x - 1, y, x + 8, y + 10], 225, 315, fill=0)


ANCHOR = ("...#...",
          "..#.#..",
          "...#...",
          ".#####.",
          "...#...",
          "#..#..#",
          ".#.#.#.",
          "..###..")


def _anchor_icon(d, x, y):
    """A tiny ship's anchor (7x8): someone has the den open (or a tool is on the control link)."""
    for row, line in enumerate(ANCHOR):
        for col, c in enumerate(line):
            if c == "#":
                d.point((x + col, y + row), fill=0)


def _first_fit(options, width):
    """The first wording that fits; roomier spacing when the numbers are small."""
    for o in options:
        if text_width(o) <= width:
            return o
    return options[-1]


def _km(m):
    return f"{m / 1000:.1f}KM" if m >= 100 else f"{int(m)}M"


def _fmt_uptime(s):
    """HH:MM, hours zero-padded to two digits and free to grow to three (999:59 max).
    No seconds: the e-ink only redraws about once a minute, so they'd always be stale."""
    s = max(0, int(s))
    h = min(s // 3600, 999)
    m = 59 if s // 3600 > 999 else s // 60 % 60
    return f"{h:02d}:{m:02d}"


def render(v: dict) -> Image.Image:
    """Render one frame from a view dict (see pet.Pet.view())."""
    img = Image.new("1", (WIDTH, HEIGHT), 255)
    d = ImageDraw.Draw(img)

    # ---- banner: runic name, Latin name and level
    # Right-hand block first (Latin name over level + XP bar), then the runes get whatever
    # width is left. Runes are drawn big if they fit, small if not, and trimmed as a last
    # resort, so the two can never overlap.
    name = fit_text(v.get("name", "Harald").upper(), 90)
    lv = f"LV {v.get('level', 1)}"
    xp_w = 30
    right_w = max(text_width(name), xp_w + 4 + text_width(lv))
    draw_text(d, (WIDTH - 2 - text_width(name), 2), name)
    draw_text(d, (WIDTH - 2 - xp_w - 4 - text_width(lv), 11), lv)
    _bar(d, WIDTH - 2 - xp_w, 11, xp_w, 7, v.get("xp_frac", 0.0), segments=5)

    runes = to_runes(v.get("name", "Harald"))
    room = WIDTH - 2 - right_w - 8 - 3  # 8 px clear gap between the two
    if text_width(runes, FONT_RUNES, 2, 2) <= room:
        draw_text(d, (3, 1), runes, FONT_RUNES, scale=2, spacing=2)
    else:
        while runes and text_width(runes, FONT_RUNES, 1, 2) > room:
            runes = runes[:-1]
        draw_text(d, (3, 5), runes, FONT_RUNES, scale=1, spacing=2)
    _band(d, 19)

    # ---- Harald
    artmod.ART.draw(img, 2, 25, v.get("mood", "content"), v.get("phase", 0), v.get("belly"))   # yours, or drawn

    # ---- stats panel: three meters, a little gap, then five rows of text
    x = PANEL_X
    bar_x = x + 32
    meters = (("JOY", v.get("joy", 50) / 100.0),
              ("BELLY", v.get("hunger", 50) / 100.0),
              ("PACK", v.get("pack", 0) / max(1.0, v.get("pack_cap", 50))))
    for i, (label, frac) in enumerate(meters):
        y = 26 + i * 9
        draw_text(d, (x, y), label)
        _bar(d, bar_x, y - 1, WIDTH - 3 - bar_x, 8, frac)
    walked = v.get("walked_today", 0)
    treats = f"TREATS {v.get('session_treats', 0)}"
    walk = _first_fit([f"WALK {_km(walked)}  {treats}" if walked else f"WALK - (GO!)  {treats}",
                       f"WALK {_km(walked)} {treats}" if walked else f"WALK -  {treats}"], WIDTH - 2 - x)
    sn, sp = v.get("session_meals", 0), v.get("species", 0)
    plus = f" (+{v['new_species']})" if v.get("new_species") else ""
    rows = [
        _first_fit([f"SNACKS {sn}  TYPES {sp}{plus}", f"SNACKS {sn} TYPES {sp}{plus}",
                    f"SNACKS {sn} TYPES {sp}"], WIDTH - 2 - x),
        walk,
        (f"PALS {v.get('pals_near', 0)}/{v.get('pals_total', 0)}" if v.get("pals_total") else "PALS -")
        + f"  FRIENDS {v.get('friends', 0)}" + (f" ({v['friends_near']})" if v.get("friends_near") else ""),
        _first_fit([f"GPS {v.get('gps', 'OFF')}  WIGLE {v.get('wigle_pending', 0)}  {v.get('temp', 0):.0f}°C",
                    f"GPS {v.get('gps', 'OFF')} WIGLE {v.get('wigle_pending', 0)} {v.get('temp', 0):.0f}°C"],
                   WIDTH - 2 - x),
        _first_fit([f"UP {_fmt_uptime(v.get('awake', 0))}  CPU {v.get('cpu', 0):.0f}%  MEM {v.get('mem', 0):.0f}%",
                    f"UP {_fmt_uptime(v.get('awake', 0))} CPU {v.get('cpu', 0):.0f}% MEM {v.get('mem', 0):.0f}%",
                    f"UP {_fmt_uptime(v.get('awake', 0))} CPU{v.get('cpu', 0):.0f}% MEM{v.get('mem', 0):.0f}%"],
                   WIDTH - 2 - x),
    ]
    for i, row in enumerate(rows):
        draw_text(d, (x, 58 + i * 10), fit_text(row, WIDTH - 2 - x))

    # ---- status line
    d.line([(0, 111), (WIDTH - 1, 111)], fill=0)
    icons_w = 0
    ix = WIDTH - 2
    if v.get("linked"):
        ix -= 7
        _anchor_icon(d, ix, 113)
        ix -= 3
        icons_w += 10
    if v.get("home"):
        ix -= 8
        _wifi_icon(d, ix, 113)
        icons_w += 10
    msg = langmod.convert(v.get("message", ""), v.get("lang", "gb"))   # in his English (see lang.py)
    if v.get("alert"):
        d.rectangle([0, 112, WIDTH - 1 - icons_w, HEIGHT - 1], fill=0)
        draw_text(d, (3, 114), fit_text(msg, WIDTH - 8 - icons_w), fill=255)
    else:
        draw_text(d, (3, 114), fit_text(msg, WIDTH - 8 - icons_w))
    return img


def render_nap(v: dict) -> Image.Image:
    """Shown while Harald naps: asleep, but the den can wake him."""
    v = dict(v)
    v.update(mood="asleep", phase=1, alert=False, linked=False,
             message="NAPPING. WAKE ME IN MY DEN")
    return render(v)


def render_sleep(v: dict) -> Image.Image:
    """Shown when Harald is shut down. E-ink keeps it with the power off."""
    v = dict(v)
    v.update(mood="asleep", phase=1, alert=False, linked=False, home=False,
             message="ZZZ... SAFE TO UNPLUG")
    return render(v)
