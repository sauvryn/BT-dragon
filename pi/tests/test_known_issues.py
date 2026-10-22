"""Known issues from testing (Oct 21): the home zone, switched on for the first time with the tick
box, asks first (it goes around where he is) and the Den can say whether he's inside it now; the
Den's rations text mentions books; ISBN search survives a slow or empty edition record; nothing
is "fed to the garden" when only pupae (and adults waiting) are there."""
import asyncio
import os
import random
import tempfile
import urllib.error

from bt_dragon import config, garden as G, homezone
from bt_dragon.app import Dragon
from bt_dragon.library import Library
from bt_dragon.store import Store

HERE = os.path.dirname(os.path.abspath(__file__))
den = open(os.path.join(HERE, "..", "bt_dragon", "den.html"), encoding="utf-8").read()

# ---- the home zone: the distances are right (1 km from home is never inside a 500 m zone)
LON0, LAT0 = -0.1276, 51.5072          # (London)
for seed in range(200):
    lat, lon = homezone.moved(LAT0, LON0, 500, random.Random(seed))
    assert homezone.distance_m(LAT0, LON0, lat, lon) <= 250.5
    for bearing_lat, bearing_lon in ((0.009, 0), (-0.009, 0), (0, 0.0144), (0, -0.0144)):   # ~1 km N/S/E/W
        assert homezone.distance_m(LAT0 + bearing_lat, LON0 + bearing_lon, lat, lon) > 500

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
fix = {"lat": LAT0, "lon": LON0, "ts": 0}
app.gps.current = lambda: fix
run = lambda c: asyncio.run(app.command(c))  # noqa: E731
st = dict(l.split("=", 1) for l in run("HOMEZONE") if "=" in l)
assert st["on"] == "0" and st["here"] == "off"
assert run("HOMEZONESET here 500")[0].startswith("OK")
st = dict(l.split("=", 1) for l in run("HOMEZONE") if "=" in l)
assert st["on"] == "1" and st["here"] == "in"
fix = {"lat": LAT0 + 0.009, "lon": LON0, "ts": 0}                  # 1 km north
st = dict(l.split("=", 1) for l in run("HOMEZONE") if "=" in l)
assert st["here"] == "out"
app.gps.current = lambda: None
st = dict(l.split("=", 1) for l in run("HOMEZONE") if "=" in l)
assert st["here"] == "nofix"
# the Den: the first tick asks, and says it goes around where he is
assert "if (!hzSet)" in den and "Switch on the home zone around where" in den
assert "the first time, the circle goes around wherever" in den

# ---- rations: the Den mentions books
assert "and for every book finished in the Library" in den
assert "feasts, new lands and finished books earn them" in den

# ---- ISBN search
tmp = tempfile.mkdtemp()
lib = Library(Store(os.path.join(tmp, "l.db")), tmp)
DOC = {"docs": [{"title": "the hobbit", "author_name": ["J. R. R. Tolkien"], "isbn": ["9780261102217"],
                 "number_of_pages_median": 300, "cover_i": 77, "first_publish_year": 1937, "edition_count": 400}]}


def run(edition, doc=DOC, doc_fails=False):
    calls = []

    def get(url, timeout=12):
        calls.append(url)
        if "/isbn/" in url:
            if isinstance(edition, Exception):
                raise edition
            return edition
        if "/authors/" in url:
            return {"name": "From The Author Record"}
        if doc_fails:
            raise TimeoutError("slow")
        return doc
    lib._get_json = get
    return lib.search("978-0-261-10221-7"), calls


# a slow edition record (a timeout, not a 404): the ISBN search answers instead
r, calls = run(TimeoutError("timed out"))
assert r and r[0]["title"] == "the hobbit" and r[0]["author"] == "J. R. R. Tolkien" and r[0]["pages"] == 300
assert any("isbn=9780261102217" in c for c in calls)
# an edition record with no authors (the work has them): the author comes from the ISBN search
r, _ = run({"title": "The Hobbit", "number_of_pages": 310, "covers": [5], "publish_date": "1995"})
assert r[0]["author"] == "J. R. R. Tolkien" and r[0]["pages"] == 310 and r[0]["edition"] and r[0]["cover"] == 5
# an edition record without a page count: the typical count, not marked as the edition's own
r, _ = run({"title": "The Hobbit", "publish_date": "1995"})
assert r[0]["pages"] == 300 and not r[0]["edition"]
# a 404 and an empty ISBN search: an ordinary search for the number
r, calls = run(urllib.error.HTTPError("u", 404, "nf", {}, None), doc={"docs": []})
assert "q=978" in calls[-1]
# nothing answers at all: an error (the page says it couldn't reach Open Library)
try:
    run(TimeoutError("x"), doc_fails=True)
    raise AssertionError("should fail")
except OSError:
    pass
# no authors in the ISBN search either: the author record
r, _ = run({"title": "The Hobbit", "authors": [{"key": "/authors/OL1A"}], "number_of_pages": 310},
           doc={"docs": [{"title": "the hobbit"}]})
assert r[0]["author"] == "From The Author Record"

# ---- the garden: nothing "fed" when only a pupa is there
g = G.Garden(Store(os.path.join(tmp, "g.db")), random.Random(3))
g.unlock_now(5)
assert g.feed(0.001, 5, "GB") > 0
b = g.s["slots"][0]
need, pup = b["need"], b["pupAt"]
eaten = g.feed(need, 5, "GB")                               # more than it needs: it stops at pupation
assert abs(eaten - (need * pup / 100 - 0.001)) < 0.01 and g.is_pupa(g.s["slots"][0])
today = g.s["fed_today"]
assert g.feed(5, 5, "GB") == 0 and g.s["fed_today"] == today
# and in the app: no message waiting
app.garden.unlock_now(5)
app.pet.level = lambda: 5
app.garden.feed(0.001, 5)
s0 = app.garden.s["slots"][0]
app.garden.feed(s0["need"], 5)
assert app.garden.is_pupa(app.garden.s["slots"][0])
app._garden_fed = 0.0
app._garden_feed(10)
assert app._garden_fed == 0.0
print("known issues ok")
