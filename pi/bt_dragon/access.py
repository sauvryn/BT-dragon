"""
Color Blindness Mode (Den → Care and Accessibility): colours for each kind of colour blindness.

Your eyes have three kinds of cone cell, most sensitive to long (red), medium (green) and short
(blue) wavelengths. In each kind of colour blindness one of them is missing or shifted:

  protanopia     the long-wavelength (red) cones: reds look darker, and red, orange, yellow and
                 green drift towards the same muddy yellow-brown.
  deuteranopia   the medium-wavelength (green) cones: much the same confusion between red and
                 green, without reds looking dark. The most common kind: red-green colour
                 blindness of some degree affects about 1 in 12 men and 1 in 200 women.
  tritanopia     the short-wavelength (blue) cones: blue and green, and yellow and pink, are
                 confused instead. Rare: about 1 in 10,000 people.

The Den has three colours that mean something: gold (its accent: headings, buttons), red
(danger: alerts, "Put to sleep", "Forget...") and green (good: meters, progress, raised).
The two red-green kinds lose the red-green difference but keep blue-yellow, so one set of
colours serves both: gold stays, green becomes blue, red becomes pink. Tritanopia keeps red-
green but loses blue-yellow, so there gold becomes lavender and green becomes teal, and red
stays red. Each set was chosen by simulating the colour blindness (the matrices of Machado,
Oliveira and Fernandes, 2009) and checking that every pair of these colours still stays well
apart, and that each is readable on the Den's dark background (WCAG contrast of 4.5:1 or more).
The tests check both.

With any of the three on, danger buttons also get a ⚠, so they never depend on colour alone.
"""

MODES = ("full", "protanopia", "deuteranopia", "tritanopia")
NAMES = {"full": "Full color vision", "protanopia": "Protanopia", "deuteranopia": "Deuteranopia",
         "tritanopia": "Tritanopia"}
STONE = "#1d1c1a"

# accent (gold), danger (red), good (green), rare (Bookworm's purple)
FULL = {"accent": "#d9a441", "danger": "#e8735c", "good": "#7fa36b", "rare": "#c9a8f0"}
RED_GREEN = {"accent": "#d9a441", "danger": "#ff9ec4", "good": "#4aa3f0", "rare": "#e6e1d6"}
TRITAN = {"accent": "#c9a2f2", "danger": "#e8735c", "good": "#5fd4c8", "rare": "#e6e1d6"}
PALETTE = {"full": FULL, "protanopia": RED_GREEN, "deuteranopia": RED_GREEN, "tritanopia": TRITAN}


def _mix(a, b, t):
    """`t` of colour a over colour b (for the dark tints behind Bookworm's chips)."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x * t + y * (1 - t)) for x, y in zip(pa, pb))


def theme_css(mode):
    """The style sheet every Den page loads last (/theme.css). Nothing for full colour vision."""
    if mode not in PALETTE or mode == "full":
        return "/* Color Blindness Mode: full color vision (the pages' own colours) */\n"
    p = PALETTE[mode]
    a, d, g, r = p["accent"], p["danger"], p["good"], p["rare"]
    return f"""/* Color Blindness Mode: {NAMES[mode]} (see access.py) */
:root {{ --rune: {a}; --blood: {d}; --ember: {d}; --moss: {g}; }}
/* the Garden Collection (Bookworm's own colours) */
:root, :root[data-theme="dark"], :root:not([data-theme="light"]) {{
  --accent: {a} !important; --accent-ink: {a} !important; --link: {a} !important; --warn: {a} !important;
  --accent-soft: {_mix(a, STONE, .2)} !important; --warn-soft: {_mix(a, STONE, .2)} !important;
  --ok: {g} !important; --ok-soft: {_mix(g, STONE, .2)} !important;
  --danger: {d} !important; --danger-soft: {_mix(d, STONE, .2)} !important;
  --rare: {r} !important; --rare-soft: {_mix(r, STONE, .2)} !important;
}}
/* never colour alone: a warning sign on anything dangerous, and a heavier alert border */
button.danger::before {{ content: "\\26A0\\FE0E  "; }}
.alert {{ border-width: 2px; }}
"""
