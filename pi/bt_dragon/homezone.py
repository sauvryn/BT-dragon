"""
The home zone (Den → Recent treats → "Exclude home zone (extra privacy)"): a circle around
home where wardriving sightings are never recorded, so they're never uploaded to WiGLE or
put in an export either.

Why: every sighting is a network plus where you were when you heard it. Uploaded, they show
the streets you walk, and the place they all start from and end at is home. A circle with
nothing in it hides the streets nearest home.

The hole would give it away, though, if home were in its exact middle: anyone looking at
the map of your sightings could find the empty circle and put a pin in its center. (This
happened with fitness apps' privacy zones.) So the circle isn't centered on home. When you
set it, home is moved a random distance, up to half the circle's radius, in a random
direction, and *that* point becomes the center. The center of the hole is then somewhere
up to half a radius from home, and nobody can tell which way. Home is still well inside:
at least half a radius from the edge in every direction.

Only the moved center is kept. Your home's own position is never stored.

Sizes: Wi-Fi reaches about 50 to 100 meters from a house, up to 200 meters outdoors in the
open, so a circle has to be bigger than that to hide the networks that are heard from your
doorstep. 500 meters (the default) covers a few streets in every direction, and still
leaves at least 250 meters around home after the random move.

Turning it on, changing its size, or moving it all happen where Harald is at that moment,
so do them at home. Sightings already recorded inside the circle that haven't been uploaded
are deleted at the same time; ones already uploaded to WiGLE are on WiGLE.
"""
import math
import random

SIZES = (250, 500, 1000)
DEFAULT = 500
EARTH_R = 6371000.0


def distance_m(lat1, lon1, lat2, lon2):
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def moved(lat, lon, r, rng=random):
    """`lat, lon` moved up to r/2 in a random direction. (sqrt makes every point in that
    smaller circle equally likely, rather than crowding them near the middle.)"""
    d = (r / 2) * math.sqrt(rng.random())
    bearing = rng.random() * 2 * math.pi
    dlat = d * math.cos(bearing) / EARTH_R
    dlon = d * math.sin(bearing) / (EARTH_R * math.cos(math.radians(lat)))
    return round(lat + math.degrees(dlat), 6), round(lon + math.degrees(dlon), 6)


class HomeZone:
    KEY = "home_zone"

    def __init__(self, store):
        self.store = store

    def state(self):
        z = self.store.get(self.KEY) or {}
        return {"on": bool(z.get("on")), "r": z.get("r") or DEFAULT,
                "set": z.get("lat") is not None}

    def inside(self, lat, lon):
        z = self.store.get(self.KEY) or {}
        if not z.get("on") or z.get("lat") is None or lat is None:
            return False
        return distance_m(lat, lon, z["lat"], z["lon"]) <= z["r"]

    def set_here(self, fix, r=None, rng=random):
        """Switch it on around where he is now (home). Returns how many sightings it deleted."""
        r = r or self.state()["r"]
        if r not in SIZES:
            raise ValueError("size")
        lat, lon = moved(fix["lat"], fix["lon"], r, rng)
        self.store.put(self.KEY, {"on": True, "lat": lat, "lon": lon, "r": r})
        return self.store.forget_obs_where(lambda la, lo: self.inside(la, lo))

    def off(self):
        z = self.store.get(self.KEY) or {}
        z["on"] = False
        self.store.put(self.KEY, z)
