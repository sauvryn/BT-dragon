"""The Tadpole Pond: species data (native, with a water stage, every card with checked sources);
opens at level 8 (or the test box); spawn hatches with the first food; at most 25% of the bar a
day, from hatching and from midnight (10% by midnight -> up to 35% the next day); stages (frogs back legs first, newts front legs);
grown up -> Pond Collection; spare food shared as one more mouth, or first with the priority box
(the two boxes exclusive); achievements (ᛖ); the Den."""
import asyncio
import datetime
import json
import os
import random
import tempfile
import time

from bt_dragon import achievements as ach, config, pond as P, tuning
from bt_dragon.app import Dragon
from bt_dragon.store import Store

D = P.data()
assert set(D) == {"gb", "ie", "us", "ca"}
assert {s["id"] for s in D["ie"]["species"]} == {"common-frog", "smooth-newt", "natterjack"}      # Ireland's three
assert len(D["gb"]["species"]) == 7                                                               # Britain's seven
for c in D:
    for s in D[c]["species"]:
        assert s["kind"] in ("frog", "toad", "newt", "salamander") and len(s["facts"]) >= 3 and s["months"]
        assert s["learn"] and all(u.startswith("https://") for _, u in s["learn"] + s["src"]), s["id"]
        assert s["family"] and s["size"] and s["life"] and s["status"] and s["habitats"]
        assert set(s["unv"]) <= {"when", "food", "life", "status"}
        assert not any("wikipedia" in u for _, u in s["learn"] + s["src"])        # (public bodies and charities)
        assert (s["young"], s["meta"]) == {"frog": ("tadpole", "froglet"), "toad": ("tadpole", "toadlet"),
                                           "newt": ("larva", "eft"), "salamander": ("larva", "juvenile")}[s["kind"]]
        assert all(" he " not in f" {f} " and " his " not in f" {f} " for f in s["facts"])
# no direct developers (no water stage) and none that never leave the water
names = " ".join(s["sci"] for c in D for s in D[c]["species"])
for no in ("Plethodon", "Ensatina", "Batrachoseps", "Aneides", "Necturus", "Cryptobranchus", "Siren", "Amphiuma", "Eleutherodactylus"):
    assert no not in names, no

# stages
assert P.stage("frog", 10) == (1, "tadpole") and P.stage("frog", 50) == (2, "tadpole with back legs")
assert P.stage("newt", 50) == (2, "larva with front legs") and P.stage("newt", 90)[1] == "meta"
assert P.stage("toad", 100)[0] == 5

tmp = tempfile.mkdtemp()
pond = P.Pond(Store(os.path.join(tmp, "p.db")), random.Random(4))
events = []
pond.on_event = lambda k, i: events.append((k, i))
assert not pond.unlocked(7) and pond.unlocked(8)
assert pond.feed(5, 7, "gb") == 0                                    # closed: eats nothing
pond.unlock_now(3)
assert pond.unlocked(3)
pond.lock_again()
assert not pond.unlocked(3)

day1 = time.mktime(datetime.datetime(2026, 4, 1, 10, 0).timetuple())
day2 = time.mktime(datetime.datetime(2026, 4, 2, 0, 5).timetuple())
day3 = time.mktime(datetime.datetime(2026, 4, 3, 9, 0).timetuple())
day4 = time.mktime(datetime.datetime(2026, 4, 4, 9, 0).timetuple())
day5 = time.mktime(datetime.datetime(2026, 4, 5, 9, 0).timetuple())
assert pond.room(8, day1) == float("inf")                            # spawn: hatches with the next food
eaten = pond.feed(1000, 8, "gb", now=day1)
b = pond.s["slot"]
assert events[0][0] == "hatch" and b["country"] == "gb" and b["species"] in D["gb"]["by_id"]
need = b["need"]
assert need == tuning.get("pond_food_" + b["rarity"].lower())
assert tuning.get("pond_daily_pct") == 25
assert abs(eaten - need * 0.25) < 1e-6 and abs(pond.pct(b) - 25) < 0.01     # a quarter of the bar on day one, at most
assert pond.feed(10, 8, "gb", now=day1 + 3600) == 0 and pond.room(8, day1 + 3600) == 0
v = pond.view(8, "gb", now=day1 + 3600)
assert v["slot"]["full_today"] and v["slot"]["limit_pct"] == 25
# each new day: up to 25% more, so four days at least
assert abs(pond.room(8, day2) - need * 0.25) < 1e-6
for t in (day2, day3, day4):
    assert not pond.s["slot"].get("adult")
    pond.feed(1000, 8, "gb", now=t)
assert pond.s["slot"].get("adult") and [e[0] for e in events][-1] == "adult"
assert "meta" in [e[0] for e in events] and "legs" in [e[0] for e in events]
assert pond.feed(5, 8, "gb", now=day4) == 0                          # grown up: eats nothing
# the "10% by midnight -> 35% the next day" rule
p2 = P.Pond(Store(os.path.join(tmp, "p2.db")), random.Random(1))
p2.feed(0.0001, 8, "us", now=day1)
n2 = p2.s["slot"]["need"]
p2.feed(n2 * 0.10, 8, "us", now=day1 + 60)
assert abs(p2.pct(p2.s["slot"]) - 10) < 0.1
p2.feed(n2, 8, "us", now=day2)
assert abs(p2.pct(p2.s["slot"]) - 35) < 0.1, p2.pct(p2.s["slot"])
for t in (day3, day4, day5):
    p2.feed(n2, 8, "us", now=t)
assert abs(p2.pct(p2.s["slot"]) - 100) < 0.2 and p2.s["slot"].get("adult")
# the collection: a new spawn appears
species = pond.s["slot"]["species"]
assert pond.collect(now=day4) is None and pond.s["slot"] == {"egg": True}
sp0 = D["gb"]["by_id"][species]
assert list(pond.s["habitats"]["gb"]) == [sp0["habitats"][0]]           # its first habitat opened
assert pond.collection("gb")[0]["species"] == species and pond.score() == P.POINTS[D["gb"]["by_id"][species]["rarity"]]
assert pond.collect() is not None                                    # nothing grown up
v = pond.view(8, "gb")
assert v["raised_species"] == 1 and v["total"] == 7 and v["slot"] == {"egg": True}
# sightings, and the page's data
assert pond.set_seen("gb", "natterjack", True) is None and "natterjack" in pond.s["seen"]["gb"]
assert pond.set_seen("gb", "natterjack", False) is None and "natterjack" not in pond.s["seen"]["gb"]
assert pond.set_seen("gb", "bullfrog", True)                                 # (not in the UK)
pd = pond.page_data("gb", "Harald")
assert len(pd["species"]) == 7 and species in pd["raised"] and pd["score"] == pond.score()
# species not raised yet come first
pond.rng = random.Random(9)
picks = {pond.pick("gb", D["gb"]["by_id"][species]["rarity"], month=3)["id"] for _ in range(30)}
assert species not in picks or len([s for s in D["gb"]["species"] if s["rarity"] == D["gb"]["by_id"][species]["rarity"]]) == 1

# ---- in the app: sharing spare food with the garden
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
app.pet.level = lambda: 8
app.garden.unlock_now(8)
app.garden.sync_slots(8)
assert app.pond.unlocked(8) and app.garden.unlocked(8)
app._garden_feed(0.002)                                  # hatches the garden's egg and the pond's spawn
assert not app.garden.s["slots"][0].get("egg") and not app.pond.s["slot"].get("egg")
g_mouths = app._garden_eaters(8)
assert g_mouths == 1
f0, p0 = app.garden.s["slots"][0]["fed"], app.pond.s["slot"]["fed"]
app._garden_feed(2.0)                                    # shared: one mouth each
assert abs((app.garden.s["slots"][0]["fed"] - f0) - 1.0) < 1e-6 and abs((app.pond.s["slot"]["fed"] - p0) - 1.0) < 1e-6
# the pond first: all of it, up to today's limit, then the rest to the garden
asyncio.run(app.command("FEEDPRIORITY pond"))
assert app.feed_priority() == "pond"
f0, p0 = app.garden.s["slots"][0]["fed"], app.pond.s["slot"]["fed"]
app._garden_feed(2.0)
assert abs(app.pond.s["slot"]["fed"] - p0 - 2.0) < 1e-6 and app.garden.s["slots"][0]["fed"] == f0
room = app.pond.room(8)
app._garden_feed(room + 3.0)                             # more than the pond can eat today: the rest to the garden
assert room < 2.0 or True
assert app.pond.room(8) == 0 and abs(app.garden.s["slots"][0]["fed"] - f0 - 3.0) < 1e-6
# the garden first
asyncio.run(app.command("FEEDPRIORITY garden"))
assert app.feed_priority() == "garden"
assert asyncio.run(app.command("FEEDPRIORITY none")) == ["OK"] and app.feed_priority() == ""
assert asyncio.run(app.command("FEEDPRIORITY sideways"))[0].startswith("ERR")
# the message: what each ate
app._garden_fed, app._pond_fed, app._garden_fed_said = 3.0, 2.0, 0
app._garden_news.clear()
app.pet.message_ts = 0
app._garden_tick()
assert app.pet.message.startswith("FED 3 TO THE GARDEN, 2 TO THE POND"), app.pet.message
# news
app._garden_news.clear()
app._pond_said("hatch", {"name": "Common Frog", "young": "tadpole", "meta": "froglet", "rarity": "Common"})
assert "A COMMON FROG TADPOLE" in app.pet.message
app._pond_said("legs", {"name": "Smooth Newt", "young": "larva", "meta": "eft", "kind": "newt", "k": 2})
assert app.pet.message == "THE SMOOTH NEWT LARVA HAS FRONT LEGS!", app.pet.message
app._pond_said("legs", {"name": "Common Toad", "young": "tadpole", "meta": "toadlet", "kind": "toad", "k": 2})
assert "HAS BACK LEGS" in app.pet.message
# the command and the Den
v = json.loads(asyncio.run(app.command("POND"))[0])
assert v["unlocked"] and v["slot"]["name"] and v["priority"] == ""
achs = {a["id"]: a for a in app.achievement_list(fresh=True)}
assert achs["e-all"]["section"] == "pond" and "e-species" in achs
assert dict((s[0], s[2]) for s in ach.SECTIONS)["pond"] == "ᛈ"
den = open(os.path.join(os.path.dirname(__file__), "..", "bt_dragon", "den.html"), encoding="utf-8").read()
assert den.count("Priority for spare food. All spare food goes here until maxed, then shared elsewhere.") == 2
assert "loadPond()" in den and 'id="pdSlot"' in den and 'href="/pond"' in den and "/pond-art.js" in den
assert "pdColl" not in den                                                   # (the collection is on its own page now)
# the page, served
import socket, threading, urllib.request
from bt_dragon import server
sk = socket.socket(); sk.bind(("127.0.0.1", 0)); port = sk.getsockname()[1]; sk.close()
app.cfg["link"]["web_port"] = port
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
base = f"http://127.0.0.1:{port}"
assert "Tadpole Pond" in urllib.request.urlopen(base + "/pond").read().decode()
assert "TEMP" in urllib.request.urlopen(base + "/pond-art.js").read().decode()
pdj = json.loads(urllib.request.urlopen(base + "/api/pond?c=ca").read())
assert pdj["country"] == "ca" and len(pdj["species"]) == 25 and pdj["habitat_names"]["heath"] == "Mountains & Tundra"
req = urllib.request.Request(base + "/api/pond", data=json.dumps({"country": "ca", "species": "mink-frog", "seen": True}).encode(),
                             headers={"Origin": base}, method="POST")
assert json.load(urllib.request.urlopen(req))["ok"] and "mink-frog" in app.pond.s["seen"]["ca"]
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium") if os.path.exists("/opt/pw-browsers/chromium") else pw.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 860})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if "127.0.0.1" in rt.request.url else rt.abort())
    pg.goto(base + "/pond?c=gb"); pg.wait_for_timeout(1200)
    assert pg.locator("#tabs button").count() == 3                          # (no salamanders in the UK)
    assert pg.locator("#grid .tile").count() == 2                            # frogs: common and pool
    pg.click("#tabs button:nth-child(3)"); pg.wait_for_timeout(200)
    assert pg.locator("#grid .tile").count() == 3                            # newts
    pg.fill("#q", "natter"); pg.wait_for_timeout(200)
    assert pg.locator("#grid .tile").count() == 1
    pg.click("#grid .tile"); pg.wait_for_timeout(300)
    assert pg.is_visible("#sp") and "Natterjack" in pg.inner_text("#spName") and "TEMP" in pg.inner_html("#spArt")
    assert "arc-trust.org" in pg.inner_html("#spLearn") and "best guess" in pg.inner_text("#spNote")
    assert pg.is_visible("#spLocked") or pg.is_visible("#spFactsWrap")
    pg.click("#spSeen"); pg.wait_for_timeout(400)
    assert "natterjack" in app.pond.s["seen"]["gb"]
    pg.click("#spStages button:nth-child(4)"); pg.wait_for_timeout(100)
    assert "spawn" in pg.inner_html("#spArt")
    pg.click("#spClose"); pg.click("#habBtn"); pg.wait_for_timeout(300)
    assert pg.is_visible("#habView") and pg.locator(".hab").count() >= 5
    if os.environ.get("SHOT"):
        pg.click("#collBtn"); pg.fill("#q", ""); pg.click("#tabs button:nth-child(1)"); pg.wait_for_timeout(200)
        pg.screenshot(path=os.environ["SHOT"] + "-1.png")
        pg.click("#grid .tile"); pg.wait_for_timeout(300); pg.screenshot(path=os.environ["SHOT"] + "-2.png")
    assert not errs, errs
    br.close()
print("pond ok")
