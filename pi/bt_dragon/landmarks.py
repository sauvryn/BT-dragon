"""
Famous places: "LOOK! LONDON BRIDGE!"

The first time Harald enters a realm (a ~1 km square of the map), he asks Wikipedia which
articles have coordinates inside it (plus a margin, so a landmark just over the border
still counts), using the internet connection of your phone's hotspot. The answer is kept
on the Pi, so each realm is only asked about once (and again after half a year).

Wikipedia has articles about every pub, school and side street, so "famous" needs a test.
This one is simple and works everywhere: how many languages have an article about the
place. Wikidata, Wikipedia's sister project, lists that for every article. The Tower of
London is written about in about a hundred languages, a village war memorial in one.
Whole cities, districts and countries are skipped (they'd make him shout "LOOK! LONDON!"
everywhere in London).

Privacy: each request tells Wikipedia roughly which square kilometer you're in. Nothing
else is sent. Switch it off with  landmarks = false  under [sky] in bt-dragon.toml.
"""
import json
import logging
import math
import time
import urllib.parse
import urllib.request

from . import __version__, tuning
from .sky import METERS_PER_DEG_LAT, REALM_M, cell_bounds, grid_cell

log = logging.getLogger("landmarks")

WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
# Wikimedia asks every program to say who it is and how to reach its author
USER_AGENT = f"BTDragon/{__version__} (https://github.com/sauvryn/BT-dragon)"
SKIP_TYPES = {"country", "adm1st", "adm2nd", "adm3rd", "city", "region", "satellite", "globe"}
NOT_WIKIPEDIAS = {"commonswiki", "specieswiki", "metawiki", "wikidatawiki", "mediawikiwiki",
                  "sourceswiki", "outreachwiki", "wikimaniawiki", "foundationwiki", "wikifunctionswiki"}
MARGIN_M = 400        # also look this far past the realm's edges
REFRESH_S = 180 * 86400


def _get(url, params, timeout=20):
    q = urllib.parse.urlencode(dict(params, format="json", formatversion=2))
    req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def clean_title(title):
    """'Tower Bridge' stays; 'The Shard (London)' loses its bracket."""
    if title.endswith(")") and " (" in title:
        title = title[: title.rindex(" (")]
    return title


def fetch_box(s, w, n, e):
    """Articles with coordinates inside a box: [(qid, title, lat, lon, type)]."""
    out, cont = [], {}
    for _ in range(10):           # follow "continue" a few pages at most
        params = {"action": "query", "generator": "geosearch", "ggsbbox": f"{n}|{w}|{s}|{e}",
                  "ggslimit": 500, "ggsnamespace": 0, "prop": "coordinates|pageprops",
                  "ppprop": "wikibase_item", "coprop": "type", "colimit": "max"}
        params.update(cont)
        data = _get(WIKIPEDIA, params)
        for p in (data.get("query") or {}).get("pages", []):
            qid = (p.get("pageprops") or {}).get("wikibase_item")
            coords = p.get("coordinates") or []
            if not qid or not coords:
                continue
            c = coords[0]
            out.append((qid, clean_title(p["title"]), c["lat"], c["lon"], (c.get("type") or "").lower()))
        if "continue" not in data:
            break
        cont = data["continue"]
    return out


def language_counts(qids):
    """How many Wikipedias (languages) have an article about each item."""
    counts = {}
    qids = list(dict.fromkeys(qids))
    for i in range(0, len(qids), 50):
        data = _get(WIKIDATA, {"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                               "props": "sitelinks"})
        for qid, ent in (data.get("entities") or {}).items():
            links = ent.get("sitelinks") or {}
            counts[qid] = sum(1 for site in links
                              if site.endswith("wiki") and site not in NOT_WIKIPEDIAS)
    return counts


def realm_landmarks(realm):
    """Famous places in and just around one realm (blocking: run it in a thread)."""
    s, w, n, e = cell_bounds(realm, REALM_M)
    lat_m = MARGIN_M / METERS_PER_DEG_LAT
    lon_m = MARGIN_M / (METERS_PER_DEG_LAT * max(0.01, math.cos(math.radians((s + n) / 2))))
    found = [x for x in fetch_box(s - lat_m, w - lon_m, n + lat_m, e + lon_m) if x[4] not in SKIP_TYPES]
    counts = language_counts([x[0] for x in found]) if found else {}
    return [{"qid": q, "title": t, "lat": la, "lon": lo, "langs": counts.get(q, 0)}
            for q, t, la, lo, _ in found]


def distance_m(lat1, lon1, lat2, lon2):
    dy = (lat2 - lat1) * METERS_PER_DEG_LAT
    dx = (lon2 - lon1) * METERS_PER_DEG_LAT * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


class Landmarks:
    def __init__(self, store):
        self.store = store
        self._busy = False
        self._failed = {}         # realm -> when the last attempt failed
        t = store.get("landmarks_today", {}) or {}
        self._day = time.strftime("%Y-%m-%d")
        self.today = set(t.get("qids", [])) if t.get("date") == self._day else set()

    def wanted(self, fix):
        """The realm to ask Wikipedia about next, if this one hasn't been asked yet."""
        realm = grid_cell(fix["lat"], fix["lon"], REALM_M)
        fetched = self.store.realm_fetched(realm)
        if fetched and time.time() - fetched < REFRESH_S:
            return None
        if self._busy or time.time() - self._failed.get(realm, 0) < 600:
            return None
        return realm

    async def fetch(self, realm):
        import asyncio
        self._busy = True
        try:
            places = await asyncio.to_thread(realm_landmarks, realm)
            self.store.save_landmarks(realm, places, time.time())
            famous = [p for p in places if p["langs"] >= tuning.get("landmark_langs")]
            log.info("realm %s: %d places on Wikipedia, %d famous", realm, len(places), len(famous))
        except Exception as e:      # offline, slow hotspot, Wikipedia busy: try again later
            log.info("landmark lookup for realm %s failed: %s", realm, e)
            self._failed[realm] = time.time()
        finally:
            self._busy = False

    def near(self, fix):
        """Famous places within sight that he hasn't pointed out yet today:
        [(landmark dict, first_time_ever)]."""
        day = time.strftime("%Y-%m-%d")
        if day != self._day:
            self._day, self.today = day, set()
        reach = tuning.get("landmark_m")
        out = []
        for lm in self.store.landmarks_near(fix["lat"], fix["lon"], reach, tuning.get("landmark_langs")):
            if lm["qid"] in self.today:
                continue
            if distance_m(fix["lat"], fix["lon"], lm["lat"], lm["lon"]) <= reach:
                self.today.add(lm["qid"])
                first = not lm["seen"]
                self.store.landmark_seen(lm["qid"], time.time())
                out.append((lm, first))
        return out

    def save(self):
        self.store.put("landmarks_today", {"date": self._day, "qids": sorted(self.today)})
