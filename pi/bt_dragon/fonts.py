"""
Harald's two hand-made stroke fonts.

Both fonts are drawn from straight line segments on a small grid, the way runes were
cut into wood and stone: carving across the grain is easy, curves are not, so runes
are all straight strokes. That makes them a natural fit for a 1-bit e-ink panel.

* RUNES: the 24 Elder Futhark runes on a 5x9 grid, plus a transliterator that turns
  Latin text into runes ("Harald" -> ᚺᚨᚱᚨᛚᛞ).
* LATIN: an angular capital alphabet on a 5x7 grid. No curves anywhere, so it reads as
  "carved" while staying legible for numbers and status text.

Each glyph is a list of polylines; each polyline is a list of (x, y) grid points.
A single-point polyline is a dot.
"""
from PIL import ImageDraw

# ---------------------------------------------------------------- Elder Futhark (5x9)

BIND_RUNE = "\ue000"  # private-use code point for Harald's bind rune

RUNES = {
    "ᚠ": [[(0, 0), (0, 8)], [(0, 2), (2, 0)], [(0, 5), (4, 1)]],               # fehu f
    "ᚢ": [[(0, 8), (0, 0), (4, 3), (4, 8)]],                                    # uruz u
    "ᚦ": [[(0, 0), (0, 8)], [(0, 2), (3, 4), (0, 6)]],                         # thurisaz th
    "ᚨ": [[(0, 0), (0, 8)], [(0, 0), (3, 2)], [(0, 3), (3, 5)]],               # ansuz a
    "ᚱ": [[(0, 8), (0, 0), (3, 2), (0, 4), (3, 8)]],                            # raido r
    "ᚲ": [[(3, 1), (0, 4), (3, 7)]],                                            # kaunan k/c
    "ᚷ": [[(0, 0), (4, 8)], [(4, 0), (0, 8)]],                                  # gebo g
    "ᚹ": [[(0, 8), (0, 0), (3, 2), (0, 4)]],                                    # wunjo w
    "ᚺ": [[(0, 0), (0, 8)], [(4, 0), (4, 8)], [(0, 3), (4, 5)]],               # hagalaz h
    "ᚾ": [[(2, 0), (2, 8)], [(0, 3), (4, 5)]],                                  # naudiz n
    "ᛁ": [[(2, 0), (2, 8)]],                                                    # isaz i
    "ᛃ": [[(2, 0), (0, 2), (2, 4)], [(2, 4), (4, 6), (2, 8)]],                 # jera j
    "ᛇ": [[(4, 2), (2, 0), (2, 8), (0, 6)]],                                    # eihwaz ei
    "ᛈ": [[(0, 0), (0, 8)], [(0, 0), (2, 2), (4, 0)], [(0, 8), (2, 6), (4, 8)]],  # perthro p
    "ᛉ": [[(2, 0), (2, 8)], [(0, 0), (2, 3), (4, 0)]],                         # algiz z
    "ᛊ": [[(3, 0), (0, 3), (4, 5), (1, 8)]],                                    # sowilo s
    "ᛏ": [[(2, 0), (2, 8)], [(0, 2), (2, 0), (4, 2)]],                         # tiwaz t
    "ᛒ": [[(0, 0), (0, 8)], [(0, 0), (3, 2), (0, 4), (3, 6), (0, 8)]],         # berkanan b
    "ᛖ": [[(0, 8), (0, 0), (2, 3), (4, 0), (4, 8)]],                            # ehwaz e
    "ᛗ": [[(0, 0), (0, 8)], [(4, 0), (4, 8)], [(0, 0), (4, 4)], [(4, 0), (0, 4)]],  # mannaz m
    "ᛚ": [[(0, 8), (0, 0), (3, 3)]],                                            # laguz l
    "ᛜ": [[(2, 1), (4, 4), (2, 7), (0, 4), (2, 1)]],                            # ingwaz ng
    "ᛞ": [[(0, 0), (0, 8)], [(4, 0), (4, 8)], [(0, 0), (4, 8)], [(4, 0), (0, 8)]],  # dagaz d
    "ᛟ": [[(0, 8), (0, 6), (4, 2), (2, 0), (0, 2), (4, 6), (4, 8)]],            # othala o
    # Harald Bluetooth's bind rune: Younger Futhark hagall (ᚼ) over berkanan (ᛒ).
    # It is the Bluetooth logo, and Harald's personal mark.
    BIND_RUNE: [[(1, 0), (1, 8)], [(1, 0), (4, 2), (1, 4), (4, 6), (1, 8)], [(0, 1), (2, 3)], [(2, 5), (0, 7)]],
    "·": [[(2, 4)]],   # word divider, as on rune stones
    ":": [[(2, 2)], [(2, 6)]],
    " ": [],
}

# Latin -> rune. Two-letter sounds are matched first.
_DIGRAPHS = {"th": "ᚦ", "ng": "ᛜ", "ei": "ᛇ"}
_LETTERS = {
    "a": "ᚨ", "b": "ᛒ", "c": "ᚲ", "d": "ᛞ", "e": "ᛖ", "f": "ᚠ", "g": "ᚷ", "h": "ᚺ",
    "i": "ᛁ", "j": "ᛃ", "k": "ᚲ", "l": "ᛚ", "m": "ᛗ", "n": "ᚾ", "o": "ᛟ", "p": "ᛈ",
    "q": "ᚲ", "r": "ᚱ", "s": "ᛊ", "t": "ᛏ", "u": "ᚢ", "v": "ᚹ", "w": "ᚹ", "x": "ᚲᛊ",
    "y": "ᛃ", "z": "ᛉ", " ": "·", "-": "·", "_": "·",
}


def to_runes(text):
    """Transliterate Latin letters to Elder Futhark. Unknown characters are dropped."""
    out, t, i = [], text.lower(), 0
    while i < len(t):
        pair = t[i:i + 2]
        if pair in _DIGRAPHS:
            out.append(_DIGRAPHS[pair])
            i += 2
            continue
        ch = t[i]
        if ch in _LETTERS:
            out.append(_LETTERS[ch])
        elif ch in RUNES:
            out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- angular Latin (5x7)

_O = [(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]
_P = [(0, 6), (0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]

LATIN = {
    "A": [[(0, 6), (0, 2), (2, 0), (4, 2), (4, 6)], [(0, 4), (4, 4)]],
    "B": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(0, 0), (3, 0), (4, 1), (4, 2), (3, 3)]],
    "C": [[(4, 0), (1, 0), (0, 1), (0, 5), (1, 6), (4, 6)]],
    "D": [[(0, 0), (0, 6), (2, 6), (4, 4), (4, 2), (2, 0), (0, 0)]],
    "E": [[(4, 0), (0, 0), (0, 6), (4, 6)], [(0, 3), (3, 3)]],
    "F": [[(4, 0), (0, 0), (0, 6)], [(0, 3), (3, 3)]],
    "G": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 3), (2, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(1, 0), (3, 0)], [(2, 0), (2, 6)], [(1, 6), (3, 6)]],
    "J": [[(4, 0), (4, 5), (3, 6), (1, 6), (0, 5)]],
    "K": [[(0, 0), (0, 6)], [(4, 0), (0, 4)], [(1, 3), (4, 6)]],
    "L": [[(0, 0), (0, 6), (4, 6)]],
    "M": [[(0, 6), (0, 0), (2, 3), (4, 0), (4, 6)]],
    "N": [[(0, 6), (0, 0), (4, 6), (4, 0)]],
    "O": [_O],
    "P": [_P],
    "Q": [_O, [(2, 4), (4, 6)]],
    "R": [_P, [(2, 3), (4, 6)]],
    "S": [[(4, 0), (1, 0), (0, 1), (0, 2), (1, 3), (3, 3), (4, 4), (4, 5), (3, 6), (0, 6)]],
    "T": [[(0, 0), (4, 0)], [(2, 0), (2, 6)]],
    "U": [[(0, 0), (0, 5), (1, 6), (3, 6), (4, 5), (4, 0)]],
    "V": [[(0, 0), (0, 3), (2, 6), (4, 3), (4, 0)]],
    "W": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    "X": [[(0, 0), (4, 6)], [(4, 0), (0, 6)]],
    "Y": [[(0, 0), (2, 3), (4, 0)], [(2, 3), (2, 6)]],
    "Z": [[(0, 0), (4, 0), (0, 6), (4, 6)]],
    "0": [_O, [(3, 1), (1, 5)]],
    "1": [[(1, 1), (2, 0), (2, 6)], [(1, 6), (3, 6)]],
    "2": [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (0, 6), (4, 6)]],
    "3": [[(0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (1, 3)], [(3, 3), (4, 4), (4, 5), (3, 6), (0, 6)]],
    "4": [[(3, 6), (3, 0), (0, 4), (4, 4)]],
    "5": [[(4, 0), (0, 0), (0, 3), (3, 3), (4, 4), (4, 5), (3, 6), (0, 6)]],
    "6": [[(3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]],
    "7": [[(0, 0), (4, 0), (4, 1), (1, 6)]],
    "8": [[(1, 0), (3, 0), (4, 1), (4, 2), (3, 3), (1, 3), (0, 2), (0, 1), (1, 0)],
          [(1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3)]],
    "9": [[(4, 3), (1, 3), (0, 2), (0, 1), (1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6)]],
    ".": [[(0, 6)]],
    ",": [[(1, 5), (0, 6)]],
    ":": [[(0, 2)], [(0, 5)]],
    ";": [[(1, 2)], [(1, 5), (0, 6)]],
    "!": [[(0, 0), (0, 4)], [(0, 6)]],
    "?": [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (2, 4)], [(2, 6)]],
    "'": [[(0, 0), (0, 1)]],
    '"': [[(0, 0), (0, 1)], [(2, 0), (2, 1)]],
    "-": [[(0, 3), (3, 3)]],
    "+": [[(0, 3), (4, 3)], [(2, 1), (2, 5)]],
    "=": [[(0, 2), (4, 2)], [(0, 4), (4, 4)]],
    "/": [[(4, 0), (0, 6)]],
    "%": [[(0, 6), (4, 0)], [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)], [(3, 5), (4, 5), (4, 6), (3, 6), (3, 5)]],
    "(": [[(2, 0), (0, 2), (0, 4), (2, 6)]],
    ")": [[(0, 0), (2, 2), (2, 4), (0, 6)]],
    "<": [[(3, 0), (0, 3), (3, 6)]],
    ">": [[(0, 0), (3, 3), (0, 6)]],
    "#": [[(1, 0), (1, 6)], [(3, 0), (3, 6)], [(0, 2), (4, 2)], [(0, 4), (4, 4)]],
    "*": [[(0, 1), (4, 5)], [(4, 1), (0, 5)], [(2, 0), (2, 6)]],
    "_": [[(0, 6), (4, 6)]],
    "°": [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]],
    "|": [[(0, 0), (0, 6)]],
    "@": [[(3, 4), (3, 2), (1, 2), (1, 4), (4, 4), (4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (4, 6)]],
    " ": [],
}
# glyph advance = cell width + 1 px gap; narrow punctuation gets a narrow cell
_LATIN_W = {k: 5 for k in LATIN}
_LATIN_W.update({".": 1, ",": 2, ":": 1, ";": 2, "!": 1, "'": 1, '"': 3, "(": 3, ")": 3,
                 "-": 4, "<": 4, ">": 4, "°": 2, "|": 1, " ": 3, "I": 5, "1": 4})

FONT_LATIN = ("latin", LATIN, _LATIN_W, 7)
FONT_RUNES = ("runes", RUNES, {k: 5 for k in RUNES}, 9)


def _glyph(font, ch):
    _, table, _, _ = font
    if font is FONT_LATIN:
        ch = ch.upper()
        if ch not in table:
            ch = "?"
    return table.get(ch, [])


def _adv(font, ch, scale):
    _, table, widths, _ = font
    if font is FONT_LATIN:
        ch = ch.upper()
    return (widths.get(ch, 5) + 1) * scale


def text_width(text, font=FONT_LATIN, scale=1, spacing=0):
    if not text:
        return 0
    w = sum(_adv(font, c, scale) + spacing for c in text)
    return w - scale - spacing  # no gap after the last glyph


def text_height(font=FONT_LATIN, scale=1):
    return font[3] * scale


def draw_text(draw: ImageDraw.ImageDraw, xy, text, font=FONT_LATIN, scale=1, fill=0, spacing=0):
    """Draw stroke text with its top-left corner at xy. Returns the x after the text."""
    x0, y0 = xy
    x = x0
    for ch in text:
        for stroke in _glyph(font, ch):
            pts = [(x + px * scale + (scale - 1) // 2, y0 + py * scale + (scale - 1) // 2) for px, py in stroke]
            if len(pts) == 1:
                px, py = pts[0]
                o = (scale - 1) // 2
                draw.rectangle([px - o, py - o, px - o + scale - 1, py - o + scale - 1], fill=fill)
            else:
                draw.line(pts, fill=fill, width=scale, joint=None)
                if scale > 1:  # square the joints so thick strokes look chiselled
                    o = (scale - 1) // 2
                    for px, py in pts:
                        draw.rectangle([px - o, py - o, px - o + scale - 1, py - o + scale - 1], fill=fill)
        x += _adv(font, ch, scale) + spacing
    return x


def fit_text(text, max_width, font=FONT_LATIN, scale=1):
    """Trim text to fit max_width, adding '..' when it is cut."""
    if text_width(text, font, scale) <= max_width:
        return text
    while text and text_width(text + "..", font, scale) > max_width:
        text = text[:-1]
    return text + ".."
