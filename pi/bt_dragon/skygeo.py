"""
Which navigation satellites are in your sky: the Star Chart's rarities, worked out for where
the Lair is.

The worldwide systems (GPS, Galileo, GLONASS and BeiDou's main ring) have satellites spread all
round the Earth about 20,000 km up, so they're Common everywhere. The others sit much higher,
about 36,000 km up, where an orbit takes exactly a day, as long as the Earth takes to turn, so
they stay over one part of the world:

  * geostationary: circling over the equator, so each one hangs still in the sky at one
    longitude (SBAS correction satellites, and some of QZSS, NavIC and BeiDou);
  * inclined geosynchronous: the same one-day orbit tilted, so the satellite swings north and
    south of the equator each day, tracing a tall figure of eight over one longitude (QZSS's
    "quasi-zenith" orbits over Japan and Australia, NavIC's over the Indian Ocean).

For each, the satellite's height above your horizon (its elevation) follows from where it is
and where you are: the angle between "straight up" where you stand and the line to the
satellite. Sampling a whole day of the figure-of-eight orbits gives how much of the day at least
one of a system's satellites is up, and how high the highest gets:

  Common     at least two of them are always at least 15° up (enough to be heard all day
             round, even with one hidden behind a building)
  Uncommon   one of them gets at least 10° above your horizon, at least some of the time
  Rare       none ever rises 10° above your horizon: you'd have to travel to hear one

Positions are approximate (2026), from the operators' published slots; real satellites drift
a little, retire and are replaced. Hills and buildings hide low satellites, too.
"""
import math

RE = 6371.0             # the Earth's radius, km
R_GEO = 42164.0         # the radius of a one-day orbit, km

# (orbit, longitude, inclination): "geo" hangs still; "igso" swings north and south through
# `inclination` degrees each day, crossing the equator at `longitude`. Several in one figure of
# eight are spread evenly round it (`phase` in degrees).
REGIONAL = {
    "QZSS": [("igso", 135.0, 43.0, 0), ("igso", 135.0, 43.0, 120), ("igso", 135.0, 43.0, 240),
             ("geo", 127.0, 0, 0), ("geo", 90.5, 0, 0)],
    "NavIC": [("geo", 32.5, 0, 0), ("geo", 83.0, 0, 0), ("geo", 129.5, 0, 0),
              ("igso", 55.0, 29.0, 0), ("igso", 55.0, 29.0, 180),
              ("igso", 111.75, 29.0, 0), ("igso", 111.75, 29.0, 180)],
    # WAAS (US), EGNOS (Europe), MSAS (Japan, on QZSS's), GAGAN (India), KASS (South Korea),
    # SouthPAN (Australia and New Zealand), BDSBAS (China, on BeiDou's), and the newer African
    # and Pakistani services
    "SBAS": [("geo", lon, 0, 0) for lon in (-117.0, -125.0, -5.0, 5.0, 13.0, 127.0, 90.5, 55.0, 83.0, 93.5,
                                            116.0, 91.5, 143.5, 80.0, 110.5, 140.0, 38.2, -24.8)],
}
GLOBAL = ("GPS", "Galileo", "GLONASS", "BeiDou")
NAMES = {"QZSS": "its satellites", "NavIC": "its satellites", "SBAS": "the correction satellites"}


def _ecef(lat, lon, r):
    la, lo = math.radians(lat), math.radians(lon)
    return (r * math.cos(la) * math.cos(lo), r * math.cos(la) * math.sin(lo), r * math.sin(la))


def elevation(lat, lon, sat_lat, sat_lon, r=R_GEO):
    """Degrees above the horizon of a satellite over (sat_lat, sat_lon) at radius r, seen from
    (lat, lon). Negative: below the horizon."""
    o = _ecef(lat, lon, RE)
    s = _ecef(sat_lat, sat_lon, r)
    d = [s[i] - o[i] for i in range(3)]
    up = [c / RE for c in o]
    return math.degrees(math.asin(sum(d[i] * up[i] for i in range(3)) / math.sqrt(sum(x * x for x in d))))


def track(lon, inc, phase, steps=96):
    """Where an inclined one-day orbit's satellite is overhead through a day: (lat, lon)."""
    out = []
    i = math.radians(inc)
    for k in range(steps):
        u = math.radians(phase + 360.0 * k / steps)           # how far round its orbit it is
        lat = math.degrees(math.asin(math.sin(i) * math.sin(u)))
        # in a tilted orbit, the satellite runs a little ahead of and behind the Earth's turn:
        # the figure of eight's width
        drift = math.degrees(math.atan2(math.cos(i) * math.sin(u), math.cos(u))) - math.degrees(u)
        drift = (drift + 180) % 360 - 180
        out.append((lat, lon + drift))
    return out


def sky(const, lat, lon, steps=96):
    """(rarity, share of the day one is at least 15° up, the highest elevation, the hours a
    day one is at least 10° up) for a regional system; ("Common", 1, 90, 24) for a worldwide one."""
    if const in GLOBAL:
        return "Common", 1.0, 90.0, 24.0
    sats = REGIONAL[const]
    best = [-90.0] * steps
    up15 = [0] * steps                              # how many are at least 15° up, through the day
    for kind, slon, inc, phase in sats:
        pts = [(0.0, slon)] * steps if kind == "geo" else track(slon, inc, phase, steps)
        for k, (sl, so) in enumerate(pts):
            e = elevation(lat, lon, sl, so)
            best[k] = max(best[k], e)
            up15[k] += e >= 15
    share15 = sum(1 for e in best if e >= 15) / steps
    hours10 = 24.0 * sum(1 for e in best if e >= 10) / steps
    top = max(best)
    if min(up15) >= 2:
        r = "Common"
    elif top >= 10:
        r = "Uncommon"
    else:
        r = "Rare"
    return r, share15, top, hours10


def reason(const, rarity, top, hours10, where="the Lair"):
    """Why, in words, for the card."""
    if const in GLOBAL:
        return f"Common everywhere: its satellites circle the whole Earth, so some are always in the sky at {where}."
    what = NAMES[const]
    if rarity == "Common":
        return (f"Common at {where}: at least two of {what} are always well up in your sky, the highest "
                f"{round(top)}° above the horizon.")
    if rarity == "Uncommon":
        if hours10 >= 23.9:
            return (f"Uncommon at {where}: only one of {what} is in your sky all day, at most {round(top)}° above "
                    "the horizon, so a single hill or building in the way hides the whole system.")
        return (f"Uncommon at {where}: one of {what} is above the horizon for about {round(hours10)} hours a day, "
                f"at most {round(top)}° up.")
    if top > 0:
        return (f"Rare at {where}: {what} only ever peep {round(top)}° over your horizon, too low to hear. "
                "You'd have to travel to catch one.")
    return f"Rare at {where}: {what} never rise above your horizon. You'd have to travel to catch one."
