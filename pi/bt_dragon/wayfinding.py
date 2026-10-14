"""
"Which way is East Harbour Railway?" Straight-line distance and compass direction from
where your phone says you are to a landmark (or a big city).

How it works:
- Distance: the haversine formula, which measures along the curve of the Earth (treated
  as a ball with a radius of 6,371 km). Across a town it gives the same answer as a flat
  map; across an ocean it gives the real shortest distance.
- Direction: the "initial bearing", the compass angle you'd set off along on that
  shortest path (0 = north, 90 = east), rounded to the nearest of 8 points, 45 degrees
  apart. So "southeast" means anywhere from 112.5 to 157.5 degrees.
- Units: metric first, then the US/imperial version, the way he gives temperatures:
  "900 meters, about half a mile".
- Names: the speech recognizer only knows a fixed word list, so the words in the names of
  the landmarks he knows are added to it, and what it hears is matched to the closest name
  by the words they share.
"""
import math
import re
import unicodedata

EARTH_R = 6371000.0
POINTS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
STOP = {"the", "of", "a", "an", "in", "at", "and", "to", "is", "on", "for", "unk"}
SAINT_OR_STREET = {"st": ("saint", "street")}


def distance_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def bearing(lat1, lon1, lat2, lon2):
    """Degrees clockwise from north, 0 to 360."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(deg):
    return POINTS[int((deg + 22.5) // 45) % 8]


def _num(x):
    """1 decimal under 10, whole numbers above, big ones to two significant figures."""
    if x < 9.95:
        r = round(x, 1)
        return str(int(r)) if r == int(r) else f"{r:.1f}"
    if x < 100:
        return str(round(x))
    digits = len(str(int(x))) - 2
    return f"{int(round(x, -digits)):,}"


def _unit(n, word):
    return f"{n} {word}" + ("" if n == "1" else "s")


def metric(m):
    if m < 1000:
        n = int(round(m, -1)) if m < 100 else int(round(m / 50) * 50)
        if n >= 1000:
            return "1 kilometer"
        return _unit(str(max(10, n)), "meter")
    return _unit(_num(m / 1000), "kilometer")


def imperial(m):
    miles = m / 1609.344
    if miles < 0.2:
        feet = m * 3.28084
        n = int(round(feet, -1)) if feet < 300 else int(round(feet / 50) * 50)
        return _unit(str(max(10, n)), "foot").replace("foots", "feet")
    if miles < 0.875:
        q = round(miles * 4) / 4
        return {0.25: "a quarter of a mile", 0.5: "half a mile", 0.75: "three quarters of a mile"}[min(0.75, max(0.25, q))]
    if miles < 1.25:
        return "a mile"
    return _unit(_num(miles), "mile")


def spoken_distance(m):
    """'900 meters, about half a mile'."""
    return f"{metric(m)}, about {imperial(m)}"


def where_words(title, here, there):
    """'East Harbour Railway is 900 meters to the southeast, about half a mile.'"""
    d = distance_m(here[0], here[1], there[0], there[1])
    if d < 25:
        return f"We're right by {title}!"
    way = compass(bearing(here[0], here[1], there[0], there[1]))
    return f"{title} is {metric(d)} to the {way}, about {imperial(d)}."


def nearest_words(title, here, there, what="landmark I know of"):
    """'The nearest landmark I know of is East Harbour Railway, 900 meters to the
    southeast, about half a mile.'"""
    d = distance_m(here[0], here[1], there[0], there[1])
    if d < 25:
        return f"We're right by one: {title}!"
    way = compass(bearing(here[0], here[1], there[0], there[1]))
    return f"The nearest {what} is {title}, {metric(d)} to the {way}, about {imperial(d)}."


def seen_words(last_seen, now=None, did="saw", done="seen"):
    """'I haven't seen it yet.' / 'I last saw it today.' / '... on the 3rd of October.'
    (For a park: did="explored", done="explored".)"""
    import datetime as dt
    if not last_seen:
        return f"I haven't {done} it yet."
    today = dt.date.fromtimestamp(now or __import__("time").time())
    day = dt.date.fromtimestamp(last_seen)
    if day >= today:
        return f"I last {did} it today."
    if day == today - dt.timedelta(days=1):
        return f"I last {did} it yesterday."
    n = day.day
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    year = f", {day.year}" if day.year != today.year else ""
    return f"I last {did} it on the {n}{suffix} of {day.strftime('%B')}{year}."


# ---------------------------------------------------------------- names
def _plain(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", s.replace("&", " and "))).strip()


def name_words(title):
    """The words to add to the recognizer's list for one name (St -> saint and street)."""
    out = []
    for w in _plain(title).split():
        out.extend(SAINT_OR_STREET.get(w, (w,)))
    return [w for w in out if not w.isdigit()]


def name_phrase(title):
    """The whole name as the recognizer would say it, so it's an easy path through its list."""
    words = [SAINT_OR_STREET.get(w, (w,))[0] for w in _plain(title).split()]
    return " ".join(w for w in words if not w.isdigit())


def _tokens(s):
    out = set()
    for w in _plain(s).replace("'", "").split():
        if w in STOP:
            continue
        w = {"saint": "st", "street": "st"}.get(w, w)
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return out


def match_score(heard, title):
    """How alike two names are, 0 to 1: the share of words they have in common (Dice)."""
    h, t = _tokens(heard), _tokens(title)
    if not h or not t:
        return 0.0
    return 2 * len(h & t) / (len(h) + len(t))


def best_match(heard, places, here=None, threshold=0.5):
    """The place (dict with title, lat, lon) whose name fits `heard` best; on a tie, the
    nearest. None if nothing fits well enough."""
    best, key = None, None
    for p in places:
        s = match_score(heard, p["title"])
        if s < threshold:
            continue
        d = distance_m(here[0], here[1], p["lat"], p["lon"]) if here else 0
        k = (-s, d)
        if key is None or k < key:
            best, key = p, k
    return best
