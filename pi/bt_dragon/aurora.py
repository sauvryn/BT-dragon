"""
Northern (and southern) lights at the Lair.

What makes them: the Sun keeps blowing out charged particles (the solar wind). When a burst of
it hits the Earth's magnetic field hard, the field is shaken up, and particles pour down along
it into the upper air, around 100 to 300 km up, over a ring around each magnetic pole (the
"auroral oval"). There they hit oxygen and nitrogen, which glow: green (oxygen, about 100 to
250 km up), red (oxygen, higher still) and purple or blue (nitrogen). The harder the shake,
the wider the ring spreads, and the further from the pole the lights can be seen.

How hard the field is being shaken is measured by the Kp index, from 0 (calm) to 9 (an
extreme storm): magnetometers around the world measure how much the field wobbles in each
3-hour stretch. NOAA's Space Weather Prediction Center publishes the Kp measured over the past
week and forecast for the next three days, as a public file. Harald downloads it, the same file
anyone can open; nothing about you or the Lair is sent.

Where you are matters in *magnetic* terms. Picture the Earth's field as a bar magnet inside
it. The magnet's axis is tilted: its north end points up through northern Canada (about
80.6°N, 72.7°W), not the North Pole. And the magnet isn't quite at the Earth's centre either:
it sits about 590 km off it, towards the western Pacific (the "eccentric dipole"). Both are
worked out here from the first few numbers of the International Geomagnetic Reference Field
(IGRF), the model of the field that geophysicists agree on every five years.

Measured from that magnet, every place has a magnetic latitude. The tilt puts North America
magnetically further north than Europe: Toronto, at 43.7°N, is at a magnetic latitude of
about 49°, and London, at 51.5°N, about 50°: closer to the pole than you'd think from the map. That's why the lights reach so much further
south in Canada and the US than in Europe. (This is a simplification of the real field, good
to a few degrees, like the rest of this.)

NOAA's table of how far from the pole the edge of the oval reaches at each Kp (magnetic
latitude of its equatorward edge, overhead):

    Kp  0     1     2     3     4     5     6     7     8     9
        66.5  64.5  62.4  60.4  58.3  56.3  54.2  52.2  50.1  48.1

Aurora is high up, so you can see it low over the horizon from some way further south than
where it's overhead: about 4 degrees of latitude (roughly 450 km) for your eyes, and a phone
camera, with a long exposure, picks up a fainter glow from a couple of degrees further still.
These are rules of thumb: the forecast is for 3-hour stretches, storms come and go within
minutes, and clouds and street lights hide everything.

He only looks when it's dark at the Lair (the Sun more than 6° below the horizon), and says
so once a night, or again if it gets better (from "a camera might catch it" to "low in the
sky" to "overhead").
"""
import calendar
import json
import math
import time
import urllib.request

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
# IGRF-13 (2020), in nanotesla: degree 1 (the tilted bar magnet) and degree 2 (where its
# centre is)
G10, G11, H11 = -29404.8, -1450.9, 4652.5
G20, G21, H21, G22, H22 = -2499.6, 2982.0, -2991.6, 1677.0, -734.6
EDGE = (66.5, 64.5, 62.4, 60.4, 58.3, 56.3, 54.2, 52.2, 50.1, 48.1)
EYE_MARGIN = 4.0           # degrees: low on the horizon, by eye
CAMERA_MARGIN = 6.0        # degrees: a phone camera's long exposure
LEVELS = ("camera", "horizon", "overhead")


def _dipole():
    """The magnet's axis (a unit vector to its north end) and its centre's offset from the
    Earth's (in Earth radii), Fraser-Smith's (1987) formulas."""
    b2 = G10 ** 2 + G11 ** 2 + H11 ** 2
    b = math.sqrt(b2)
    r3 = math.sqrt(3)
    l0 = 2 * G10 * G20 + r3 * (G11 * G21 + H11 * H21)
    l1 = -G11 * G20 + r3 * (G10 * G21 + G11 * G22 + H11 * H22)
    l2 = -H11 * G20 + r3 * (G10 * H21 - H11 * G22 + G11 * H22)
    e = (l0 * G10 + l1 * G11 + l2 * H11) / (4 * b2)
    offset = ((l1 - G11 * e) / (3 * b2), (l2 - H11 * e) / (3 * b2), (l0 - G10 * e) / (3 * b2))
    return (-G11 / b, -H11 / b, -G10 / b), offset


AXIS, OFFSET = _dipole()


def geomagnetic_lat(lat, lon):
    """Magnetic latitude: the angle between the magnet's equator and a line from its centre
    to this place (positive in the north)."""
    la, lo = math.radians(lat), math.radians(lon)
    p = [math.cos(la) * math.cos(lo) - OFFSET[0], math.cos(la) * math.sin(lo) - OFFSET[1], math.sin(la) - OFFSET[2]]
    n = math.sqrt(sum(c * c for c in p))
    return math.degrees(math.asin(max(-1.0, min(1.0, sum(a * c for a, c in zip(AXIS, p)) / n))))


def edge(kp):
    """Magnetic latitude of the oval's equatorward edge at this Kp (NOAA's table, in between
    by straight lines)."""
    kp = max(0.0, min(9.0, kp))
    i = min(8, int(kp))
    return EDGE[i] + (EDGE[i + 1] - EDGE[i]) * (kp - i)


def needed_kp(mlat, margin=0.0):
    """The Kp at which the oval's edge reaches |mlat| + margin (None if never, even at 9)."""
    target = abs(mlat) + margin
    if target >= EDGE[0]:
        return 0.0
    if target < EDGE[9]:
        return None
    for i in range(9):
        if EDGE[i + 1] <= target:
            # rounded up to a tenth, so that Kp is really enough
            return math.ceil((i + (EDGE[i] - target) / (EDGE[i] - EDGE[i + 1])) * 10 - 1e-9) / 10
    return None


def chance(kp, mlat):
    """'overhead', 'horizon' (low in the sky, by eye), 'camera' (a phone camera might catch
    it), or None."""
    e, m = edge(kp), abs(mlat)
    if e <= m:
        return "overhead"
    if e <= m + EYE_MARGIN:
        return "horizon"
    if e <= m + CAMERA_MARGIN:
        return "camera"
    return None


def parse(data):
    """NOAA's file -> [(start time, kp, 'observed' | 'estimated' | 'predicted')], oldest first.
    Two layouts are read: rows of values under a header row (until March 2026), and one
    object per 3-hour stretch (since)."""
    out = []
    if not isinstance(data, list) or not data:
        return out
    rows = data
    if isinstance(data[0], list):
        head = [str(h).lower() for h in data[0]]
        rows = [dict(zip(head, r)) for r in data[1:] if isinstance(r, list)]
    for r in rows:
        if not isinstance(r, dict):
            continue
        r = {str(k).lower(): v for k, v in r.items()}
        try:
            t = calendar.timegm(time.strptime(str(r["time_tag"])[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S"))
            kp = float(r["kp"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append((t, kp, str(r.get("observed") or "").lower()))
    return sorted(out)


def fetch(timeout=15):
    req = urllib.request.Request(KP_URL, headers={"User-Agent": "BT-Dragon (https://github.com/sauvryn/BT-dragon)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def kp_now(rows, now=None, ahead_h=3):
    """The highest Kp for the 3-hour stretch we're in and the next `ahead_h` hours (a forecast
    for the rest of the evening), with whether it's measured or forecast. (None, '') if the
    file doesn't cover now."""
    now = now or time.time()
    best = (None, "")
    for t, kp, kind in rows:
        if t + 3 * 3600 > now and t < now + ahead_h * 3600:
            if best[0] is None or kp > best[0]:
                best = (kp, kind)
    return best


# ---------------------------------------------------------------- is it dark?
def sun_elevation(lat, lon, ts):
    """The Sun's height above the horizon in degrees (accurate to about a degree, plenty for
    "is it dark yet"). From the Sun's position along its yearly path and the Earth's turning."""
    d = ts / 86400.0 - 10957.5                                 # days since noon, 1 January 2000 (UTC)
    g = math.radians((357.529 + 0.98560028 * d) % 360)          # how far round its orbit the Earth is
    q = (280.459 + 0.98564736 * d) % 360
    L = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)   # the Sun's longitude
    e = math.radians(23.439 - 0.00000036 * d)                   # the Earth's tilt
    ra = math.atan2(math.cos(e) * math.sin(L), math.cos(L))
    dec = math.asin(math.sin(e) * math.sin(L))
    gmst = (18.697374558 + 24.06570982441908 * d) % 24          # the Earth's turn, in hours
    ha = math.radians(gmst * 15 + lon) - ra                     # how far past the meridian the Sun is
    la = math.radians(lat)
    return math.degrees(math.asin(math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(ha)))


def dark(lat, lon, ts=None):
    return sun_elevation(lat, lon, ts or time.time()) < -6


def words(level, south=False):
    """What he says, by how good the chance is."""
    lights = "southern lights" if south else "northern lights"
    look = "south" if south else "north"
    return {"overhead": f"The {lights} could be overhead at the Lair tonight! Go outside and look up.",
            "horizon": f"The {lights} might be seen low in the {look}ern sky at the Lair tonight. "
                       f"Look {look}, away from street lights.",
            "camera": f"A phone camera might catch the {lights} low in the {look} at the Lair tonight, "
                      f"even if your eyes can't. Try a long exposure, pointed {look}."}[level]
