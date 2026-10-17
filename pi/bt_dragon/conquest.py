"""
Conquest points: a score for everything claimed and collected out in the world, with titles
along the way, like the Butterfly Garden's.

  a land (a square of the map about 250 m across)        10
  a realm (about 1 km across)                             50
  a green space discovered                                50
  a famous place (landmark) seen for the first time      100
  a star (a navigation satellite) never seen before       20
  the first star of a new constellation                 +80 (100 with its star)

How they compare: the garden's insects are worth 100, 200 or 300 points, each one many walks'
worth of spare food. A landmark or a new constellation is as rare as a Common insect, so it's
worth as much; a realm or a park takes a good walk; lands come by the dozen on a walk and stars
by the dozen on a clear day, so each is worth a little.

The score is counted from what's been claimed (so it's always right, after a restore too, and
claims made before scoring existed count), and "Forget my map" takes the lands, realms,
landmarks and green spaces back off it. Every number is a Developer Tools knob.
"""
from . import tuning

KINDS = ("land", "realm", "green", "landmark", "star", "constellation")

TITLES = [(0, "c0", "Fledgling Forager"), (250, "c1", "Wandering Wyrmling"), (750, "c2", "Scouting Skald"),
          (1500, "c3", "Roaming Raider"), (3000, "c4", "Trailblazing Thane"), (5000, "c5", "Boundary-Breaking Berserker"),
          (8000, "c6", "Longship Lookout"), (12000, "c7", "Realm-Raiding Rover"), (17500, "c8", "Jarl of the Journey"),
          (25000, "c9", "Conquering Cartographer"), (35000, "c10", "Hoard-Hunting Herald"),
          (50000, "c11", "Saga-Sung Sea-Sovereign"), (75000, "c12", "Wyrm-Ruler of the Wilds")]


def points(kind):
    return int(round(tuning.get(f"conquest_{kind}")))


def counts(store, min_langs=0):
    lands, realms = store.land_counts()
    stars = store.stars()
    return {"land": lands, "realm": realms,
            "green": sum(1 for g in store.greens_list() if g.get("first_seen")),
            "landmark": sum(1 for x in store.landmarks_list(min_langs) if x.get("first_seen")),
            "star": len(stars), "constellation": len({s["const"] for s in stars})}


def score(store, min_langs=0):
    c = counts(store, min_langs)
    return sum(c[k] * points(k) for k in KINDS)


def title(s):
    return [t for t in TITLES if s >= t[0]][-1][2]


def next_title(s):
    return next(((n, name) for n, _, name in TITLES if n > s), None)


def new_titles(store, s):
    """Titles reached since last time (each announced once)."""
    got = store.get("conquest_titles") or {}
    fresh = [(tid, name) for n, tid, name in TITLES if n > 0 and s >= n and tid not in got]
    if fresh:
        got.update({tid: True for tid, _ in fresh})
        store.put("conquest_titles", got)
    return [name for _, name in fresh]
