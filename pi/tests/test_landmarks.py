"""Landmarks, with Wikipedia and Wikidata replaced by canned answers in their real formats."""
import asyncio
import os
import tempfile

from bt_dragon import landmarks, sky
from bt_dragon.store import Store

# Two pages of geosearch results (formatversion=2), then Wikidata's sitelinks.
PAGE1 = {"continue": {"ggscontinue": "x", "continue": "ggscontinue||"},
         "query": {"pages": [
             {"pageid": 1, "ns": 0, "title": "Tower Bridge",
              "coordinates": [{"lat": 51.50926, "lon": -0.07441, "primary": True, "type": "landmark"}],
              "pageprops": {"wikibase_item": "Q1"}},
             {"pageid": 2, "ns": 0, "title": "London",
              "coordinates": [{"lat": 51.5094, "lon": -0.0753, "primary": True, "type": "city"}],
              "pageprops": {"wikibase_item": "Q18125"}},
             {"pageid": 3, "ns": 0, "title": "The Corner Pub (London)",
              "coordinates": [{"lat": 51.5095, "lon": -0.0740, "primary": True, "type": "landmark"}],
              "pageprops": {"wikibase_item": "Q3"}},
             {"pageid": 4, "ns": 0, "title": "No Coordinates Here", "pageprops": {"wikibase_item": "Q4"}},
         ]}}
PAGE2 = {"query": {"pages": [
    {"pageid": 5, "ns": 0, "title": "The Shard (London)",
     "coordinates": [{"lat": 51.50606, "lon": -0.08145, "primary": True, "type": "landmark"}],
     "pageprops": {"wikibase_item": "Q5"}}]}}


def sitelinks(n, extra=()):
    links = {f"l{i}wiki": {"site": f"l{i}wiki", "title": "x"} for i in range(n)}
    for e in extra:
        links[e] = {"site": e, "title": "x"}
    return links


WIKIDATA = {"entities": {
    "Q1": {"id": "Q1", "sitelinks": sitelinks(14, ["commonswiki", "enwikivoyage"])},
    "Q3": {"id": "Q3", "sitelinks": sitelinks(1)},
    "Q5": {"id": "Q5", "sitelinks": sitelinks(22)},
}}
calls = []


def fake_get(url, params, timeout=20):
    calls.append((url, dict(params)))
    if url == landmarks.WIKIDATA:
        assert set(params["ids"].split("|")) <= {"Q1", "Q3", "Q5"}, params["ids"]
        return WIKIDATA
    assert params["generator"] == "geosearch" and params["ggsbbox"].count("|") == 3
    return PAGE2 if "ggscontinue" in params else PAGE1


landmarks._get = fake_get
assert landmarks.clean_title("The Shard (London)") == "The Shard"

st = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
lm = landmarks.Landmarks(st)
here = {"lat": 51.5090, "lon": -0.0749, "acc": 10}
realm = lm.wanted(here)
assert realm == sky.grid_cell(51.5090, -0.0749, sky.REALM_M)
asyncio.run(lm.fetch(realm))
assert lm.wanted(here) is None                       # asked once, remembered
n, w, s_, e = (float(x) for x in calls[0][1]["ggsbbox"].split("|"))
assert n > s_ and e > w and (n - s_) * 111320 > 1500  # the realm plus a margin all round

famous = st.landmarks_list(10)
assert [f["title"] for f in famous] == ["Tower Bridge", "The Shard"], famous
assert next(f for f in famous if f["title"] == "Tower Bridge")["langs"] == 14  # Commons etc. not counted

got = lm.near(here)                                  # ~60 m from the Town Hall
assert [(x["title"], first) for x, first in got] == [("Tower Bridge", True)], got
assert lm.near(here) == []                           # once a day
lm.today.clear()                                     # next day
got = lm.near(here)
assert [(x["title"], first) for x, first in got] == [("Tower Bridge", False)]
assert lm.near({"lat": 51.5061, "lon": -0.0812, "acc": 10})[0][0]["title"] == "The Shard"

# offline: the lookup fails quietly and is retried later, not hammered
def offline(*a, **k):
    raise OSError("no internet")
landmarks._get = offline
lm2 = landmarks.Landmarks(st)
far = {"lat": 51.63, "lon": -0.13, "acc": 10}
r2 = lm2.wanted(far)
asyncio.run(lm2.fetch(r2))
assert lm2.wanted(far) is None                       # waits 10 minutes before trying again
print("all good")
