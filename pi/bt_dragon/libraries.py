"""
Libraries: treasure troves. "NEW TROVE! CENTRAL LIBRARY!"  /  "TREASURE TROVE! CENTRAL LIBRARY!"

Where they come from: OpenStreetMap, like the green spaces (greens.py). The first time
Harald enters a realm (a ~1 km square), he asks OpenStreetMap's public search service,
Overpass, for the libraries in it (plus a margin): everything tagged amenity=library with a
name, as a point (its middle, if it's drawn as a building). Each realm is asked about once
(and again after half a year).

Which count: named ones (he has to call them something), not marked private (a school's or
a company's own library usually is). Little free libraries (a box of books on a post) are a
different tag in OpenStreetMap (public bookcases) and aren't included.

Being there: within 60 m of its point (Developer Tools → Detection: "Libraries: count a visit within"), roughly the size of a
library building plus GPS wobble. The first time ever: "NEW TROVE!", Conquest points and
XP. Each later day you pass: "TREASURE TROVE!" (once a day, like landmarks).

Libraries that are also famous places: a library with a Wikipedia article in enough
languages (the British Library, say) is a landmark too. It's only announced once, in the
library's words: the landmark side stays quiet for it and the library's announcement counts
for both (both are recorded as seen, and both earn their Conquest points). The two are
matched by the Wikidata ID OpenStreetMap often records (wikidata=Q...), or failing that by
the same name within 200 m.

Privacy: each request tells Overpass roughly which square kilometer you're in. Nothing else
is sent. Switch it off with  libraries = false  under [sky] in bt-dragon.toml.
"""
import logging
import math
import re
import time

from . import tuning
from .greens import _post
from .sky import METERS_PER_DEG_LAT, REALM_M, cell_bounds, grid_cell

log = logging.getLogger("libraries")

MARGIN_M = 400
REFRESH_S = 180 * 86400
PRIVATE = {"private", "no", "customers", "permit", "students", "members"}
MATCH_M = 200              # a landmark with the same name this close is the same library


def query(s, w, n, e):
    box = f"({s:.6f},{w:.6f},{n:.6f},{e:.6f})"
    return f'[out:json][timeout:60];nwr["amenity"="library"]["name"]{box};out center tags;'


def parse(data):
    """Overpass's answer -> [{id, name, lat, lon, qid}]."""
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name or tags.get("access") in PRIVATE:
            continue
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        qid = (tags.get("wikidata") or "").strip()
        out.append({"id": f"{el['type'][0]}{el['id']}", "name": name, "lat": round(lat, 6), "lon": round(lon, 6),
                    "qid": qid if re.fullmatch(r"Q\d+", qid) else ""})
    return out


def realm_libraries(realm):
    """Libraries in and just around one realm (blocking: run it in a thread)."""
    s, w, n, e = cell_bounds(realm, REALM_M)
    lat_m = MARGIN_M / METERS_PER_DEG_LAT
    lon_m = MARGIN_M / (METERS_PER_DEG_LAT * max(0.01, math.cos(math.radians((s + n) / 2))))
    return parse(_post(query(s - lat_m, w - lon_m, n + lat_m, e + lon_m)))


def distance_m(lat1, lon1, lat2, lon2):
    dy = (lat2 - lat1) * METERS_PER_DEG_LAT
    dx = (lon2 - lon1) * METERS_PER_DEG_LAT * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def _norm(name):
    n = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    n = re.sub(r"\b(the|public|library|libraries|branch)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def same_place(lib, lm):
    """Is this landmark (a Wikipedia place) this library?"""
    if lib.get("qid") and lib["qid"] == lm.get("qid"):
        return True
    if distance_m(lib["lat"], lib["lon"], lm["lat"], lm["lon"]) > MATCH_M:
        return False
    a, b = _norm(lib["name"]), _norm(lm.get("title"))
    return bool(a) and a == b and "librar" in (lm.get("title") or "").lower() + (lib["name"] or "").lower()


class Libraries:
    def __init__(self, store, fetcher=realm_libraries):
        self.store = store
        self.fetcher = fetcher
        self._busy = False
        self._failed = {}
        t = store.get("libraries_today", {}) or {}
        self._day = time.strftime("%Y-%m-%d")
        self.today = set(t.get("ids", [])) if t.get("date") == self._day else set()

    def wanted(self, fix):
        realm = grid_cell(fix["lat"], fix["lon"], REALM_M)
        fetched = self.store.libraries_fetched(realm)
        if fetched and time.time() - fetched < REFRESH_S:
            return None
        if self._busy or time.time() - self._failed.get(realm, 0) < 600:
            return None
        return realm

    async def fetch(self, realm):
        import asyncio
        self._busy = True
        try:
            found = await asyncio.to_thread(self.fetcher, realm)
            self.store.save_libraries(realm, found, time.time())
            log.info("a new realm: %d libraries", len(found))      # (not which realm: the log is no map)
        except Exception as e:      # offline, slow hotspot, Overpass busy: try again later
            log.info("library lookup failed: %s", e)
            self._failed[realm] = time.time()
        finally:
            self._busy = False

    def _new_day(self):
        day = time.strftime("%Y-%m-%d")
        if day != self._day:
            self._day, self.today = day, set()

    def near(self, fix):
        """Libraries in reach that haven't been visited today (nothing is marked: see visit)."""
        self._new_day()
        reach = tuning.get("trove_m")
        return [lib for lib in self.store.libraries_near(fix["lat"], fix["lon"], reach)
                if lib["id"] not in self.today and distance_m(fix["lat"], fix["lon"], lib["lat"], lib["lon"]) <= reach]

    def visited_today(self, lib):
        self._new_day()
        return lib["id"] in self.today

    def visit(self, lib):
        """Count a visit (once a day). Returns (library, first_time_ever)."""
        self._new_day()
        first = not lib["seen"]
        if lib["id"] not in self.today:
            self.today.add(lib["id"])
            self.store.library_seen(lib["id"], time.time())
        return lib, first

    def famous(self, lib, min_langs):
        """The famous place (landmark) this library is, if it's one."""
        for lm in self.store.landmarks_near(lib["lat"], lib["lon"], MATCH_M, min_langs):
            if same_place(lib, lm):
                return lm
        return None

    def matching(self, lm):
        """The library this landmark is, if it is one."""
        for lib in self.store.libraries_near(lm["lat"], lm["lon"], MATCH_M):
            if same_place(lib, lm):
                return lib
        if lm.get("qid"):
            return self.store.library_by_qid(lm["qid"])
        return None

    def save(self):
        self.store.put("libraries_today", {"date": self._day, "ids": sorted(self.today)})
