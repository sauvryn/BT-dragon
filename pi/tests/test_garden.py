"""The Butterfly Garden: unlocking and spots, surplus food, hatching, pupating and emerging,
Bookworm's picking rules (forms, queens and workers, categories unlocking), the den command,
the Collection page build, and (when Playwright is installed) the page itself in a browser."""
import asyncio
import json
import os
import random
import tempfile
import time

from bt_dragon import config, garden as G, garden_page, tuning
from bt_dragon.app import Dragon
from bt_dragon.store import Store

tmp = tempfile.mkdtemp()
store = Store(os.path.join(tmp, "g.db"))
tuning.load(store)
g = G.Garden(store, random.Random(7))
events = []
g.on_event = lambda k, i: events.append((k, i))

# stages: Bookworm's, from a species' own pupation point
assert G.stage_at(0, 90) == 0 and G.stage_at(9, 63) == 63 and G.stage_at(10, 63) == 100 and G.stage_at(3, 90) == 30
assert G.stage_for(62.9, 63) == 8 and G.stage_for(63, 63) == 9 and G.stage_for(100, 63) == 10

# locked until level 5; unlock-now for testing; spots grow with each level after, up to 3
assert not g.unlocked(4) and g.slot_count(4) == 0 and g.unlocked(5) and g.slot_count(5) == 1
assert g.slot_count(6) == 2 and g.slot_count(7) == 3 and g.slot_count(12) == 3
g.unlock_now(2)
assert g.unlocked(2) and g.slot_count(2) == 1 and g.slot_count(3) == 2 and g.slot_count(4) == 3
g.lock_again()
assert not g.unlocked(2)
g.unlock_now(6)                                      # already open by level: nothing to undo later
assert g.s.get("unlocked_at") is None
g.unlock_now(3)

# food while locked does nothing; while open, the first food hatches the egg
g2 = G.Garden(Store(os.path.join(tmp, "g2.db")))
g2.feed(50, 3)
assert not g2.s["slots"]
g.feed(1, 3, "GB")
assert [e[0] for e in events] == ["hatch"] and len(g.s["slots"]) == 1      # unlocked at level 3: one spot
b = g.s["slots"][0]
assert b["country"] == "gb" and b["species"] in G.data()["countries"]["gb"]["by_id"]
assert G.data()["countries"]["gb"]["by_id"][b["species"]]["kind"] == "butterfly"      # butterflies first
assert b["need"] == tuning.get("garden_food_" + b["rarity"].lower())

# rarity: about 60/30/10
r = random.Random(1)
gg = G.Garden(Store(os.path.join(tmp, "g3.db")), r)
counts = {"Common": 0, "Uncommon": 0, "Rare": 0}
for _ in range(5000):
    counts[gg.roll_rarity()] += 1
assert 2800 < counts["Common"] < 3200 and 1300 < counts["Uncommon"] < 1700 and 380 < counts["Rare"] < 620, counts

# grow one to the end: pupates at its species' point, then emerges into the collection
events.clear()
g = G.Garden(Store(os.path.join(tmp, "g4.db")), random.Random(3))
g.on_event = lambda k, i: events.append((k, i))
g.feed(0.001, 5, "GB")
b = g.s["slots"][0]
pup = b["pupAt"]
need = b["need"]
g.feed(need * (pup - 1) / 100, 5, "GB")
assert [e[0] for e in events] == ["hatch"]
g.feed(need * 0.02, 5, "GB")
assert [e[0] for e in events] == ["hatch", "pupate"] and g.s["slots"][0]["stage"] == 9
g.feed(need, 5, "GB")
kinds = [e[0] for e in events]
assert kinds[:3] == ["hatch", "pupate", "emerge"], kinds
em = events[2][1]
assert em["new"] and em["habitat"] and em["name"]
coll = g.cdata("gb")["collection"]
assert len(coll) == 1 and coll[0]["species"] == b["species"] and coll[0]["points"] == G.data()["points"][b["rarity"]]
assert coll[0]["title"] == "Raised in the Butterfly Garden" and coll[0]["pages"] == 0
assert em["habitat"] in g.cdata("gb")["habitats"]
assert g.s["slots"][0].get("egg") and len(g.s["slots"]) == 1            # a new egg in the empty spot
assert g.score() == coll[0]["points"]

# a new spot stays empty until you put an egg in it (only the first spot fills itself)
g = G.Garden(Store(os.path.join(tmp, "g5.db")), random.Random(5))
g.feed(5, 6, "US")
assert g.s["slots"][1] == {"empty": True} and g.s["slots"][0]["fed"] == 5        # all of it to the one larva
assert g.take_egg(0, 6) and g.take_egg(1, 6) and g.lay_egg(2, 6)               # no such things to do
assert g.lay_egg(1, 6) is None and g.lay_egg(1, 6)                              # (not twice)
assert g.take_egg(1, 6) is None and g.s["slots"][1] == {"empty": True}
assert g.lay_egg(1, 6) is None
# food is shared: two larvae each get half
g.feed(10, 6, "US")
a, c = g.s["slots"]
assert abs(a["fed"] - 5 - 5) < 0.001 and abs(c["fed"] - 5) < 0.001 and a["species"] != c["species"]
assert g.take_egg(1, 6)                                                        # hatched now: stays
v = g.view(6, "US")
assert [x.get("slot") for x in v["larvae"]] == [0, 1] and v["fed_today"] == 15
# when a second-spot adult emerges, its spot is left empty; the first spot gets a new egg
evs = []
g.on_event = lambda k, i: evs.append(k)
c["fed"] = c["need"] - 0.01
g.feed(0.1, 6, "US")
assert "emerge" in evs and g.s["slots"][1] == {"empty": True}
a = g.s["slots"][0]
a["fed"] = a["need"] - 0.01
g.feed(0.1, 6, "US")
assert g.s["slots"][0].get("egg")

# picking: forms count separately; a species with all forms raised isn't picked again while others remain
gb = G.data()["countries"]["gb"]
dimorph = next(s for s in gb["species"] if s["kind"] == "butterfly" and s["forms"] == ["m", "f"])
g = G.Garden(Store(os.path.join(tmp, "g6.db")), random.Random(9))
assert g._missing_forms("gb", dimorph) == ["m", "f"]
g.cdata("gb")["collection"].append({"species": dimorph["id"], "sex": "m", "points": 100})
assert g._missing_forms("gb", dimorph) == ["f"]
g.cdata("gb")["collection"].append({"species": dimorph["id"], "sex": "f", "points": 100})
assert g._missing_forms("gb", dimorph) == []
tier = dimorph["rarity"]
for _ in range(200):
    assert g.pick("gb", tier, 5)["species"] != dimorph["id"]

# categories unlock as butterflies are raised (moths after 2; each one raised counts, as in Bookworm)
assert "moth" in g.unlocked_kinds("gb")
g = G.Garden(Store(os.path.join(tmp, "g6b.db")), random.Random(9))
g.cdata("gb")["collection"].append({"species": dimorph["id"], "sex": "m", "points": 100})
assert g.unlocked_kinds("gb") == {"butterfly"}
g.cdata("gb")["collection"].append({"species": next(s["id"] for s in gb["species"] if s["kind"] == "butterfly" and s["id"] != dimorph["id"]), "points": 100})
assert "moth" in g.unlocked_kinds("gb") and "beewasp" not in g.unlocked_kinds("gb")

# in season: three times as likely
pool = [s for s in gb["species"] if s["kind"] == "butterfly" and s["rarity"] == "Common"]
month = 6
ins = [s for s in pool if month in s["months"]]
outs = [s for s in pool if month not in s["months"]]
if ins and outs:
    rr = G.Garden(Store(os.path.join(tmp, "g7.db")), random.Random(11))
    n_in = sum(1 for _ in range(6000) if month in rr._weighted(pool, month)["months"])
    expect = 3 * len(ins) / (3 * len(ins) + len(outs))
    assert abs(n_in / 6000 - expect) < 0.03, (n_in / 6000, expect)

# queens and workers: a social species' female becomes a worker if his belly ran low while she grew
caste = next(s for s in gb["species"] if s["caste"])
g = G.Garden(Store(os.path.join(tmp, "g8.db")), random.Random(1))
evs = []
g.on_event = lambda k, i: evs.append((k, i))
g.unlock_now(1)
g.s["slots"] = [{"species": caste["id"], "country": "gb", "sex": "f", "rarity": caste["rarity"], "need": 10.0, "fed": 0.0,
                 "pupAt": caste["pupAt"], "hatched": time.time(), "stage": 0, "caste": True, "hungry": False}]
g.note_belly(True, 1)
g.feed(20, 1, "GB")
assert [e for e in evs if e[0] == "emerge"][0][1]["form"] == "w"
assert g.cdata("gb")["collection"][-1]["sex"] == "w"
g.s["slots"] = [{"species": caste["id"], "country": "gb", "sex": "f", "rarity": caste["rarity"], "need": 10.0, "fed": 0.0,
                 "pupAt": caste["pupAt"], "hatched": time.time(), "stage": 0, "caste": True, "hungry": False}]
g.feed(20, 1, "GB")
assert g.cdata("gb")["collection"][-1]["sex"] == "q"

# titles: crossing 500 points
g = G.Garden(Store(os.path.join(tmp, "g9.db")), random.Random(2))
evs = []
g.on_event = lambda k, i: evs.append((k, i))
g.unlock_now(1)
g.cdata("gb")["collection"].extend([{"species": "x", "points": 100}] * 4)
assert g.title() == "Egg Explorer"
g.s["slots"] = [{"species": pool[0]["id"], "country": "gb", "sex": None, "rarity": "Common", "need": 1.0, "fed": 0.0,
                 "pupAt": pool[0]["pupAt"], "hatched": time.time(), "stage": 0, "caste": False, "hungry": False}]
g.feed(5, 1, "GB")
assert ("title", {"name": "Bluetooth Beetle"}) in evs and g.title() == "Bluetooth Beetle"
assert not any(w in " ".join(t[2] for t in G.TITLES).lower() for w in ("book", "chapter", "librar", "manuscript", "paperback"))

# country: the den's choice; to start with, the Pi's own country (set by the app), else the UK
assert g.country("CA") == "gb" and g.country(None) == "gb"
g.default_country = "us"
assert g.country() == "us"
assert g.set_country("ie") is None and g.country("FR") == "ie" and g.country("US") == "ie"
assert g.set_country("fr")

# sightings from the page
assert g.set_seen("gb", {"peacock": ["adult"]}, {"peacock": {"adult": "2026-05-01"}}) is None
assert g.cdata("gb")["seen"] == {"peacock": ["adult"]}
assert g.set_seen("xx", {}, {}) and g.set_seen("gb", [], {})

# names for the screen
assert G.full_name({"name": "Peacock", "noun": "butterfly", "kind": "butterfly"}) == "Peacock butterfly"
assert G.full_name({"name": "Elephant Hawk-moth", "noun": "moth", "kind": "moth"}) == "Elephant Hawk-moth"
assert G.full_name({"name": "Marmalade Fly", "noun": "hoverfly", "kind": "fly"}) == "Marmalade Fly"
assert G.habitat_name("us", "woodland") == "Woodland & Forest"

# the page: Bookworm's own, with the save written in and nothing loaded from the internet
pd = g.page_data("gb")
assert set(pd["saves"]) == {"bookworm-proto-v1", "bookworm-proto-v1-ie", "bookworm-proto-v1-us", "bookworm-proto-v1-ca"}
html = garden_page.build(dict(pd, name="Harald"))
assert "fonts.googleapis" not in html and "fonts.gstatic" not in html
assert html.index("__GARDEN = ") < html.index("<style>") and "window.__garden = {" in html and "gd-to-hab" in html
assert "__GARDEN_DATA__" not in html
evil = garden_page.build({"country": "gb", "lang": "gb", "key": "k", "titles": {}, "name": "</script><b>",
                          "saves": {}}, mode=False)
assert "</script><b>" not in evil
art = garden_page.build(None)
assert "__GARDEN_DATA__" not in art and "bookworm-proto-v1" not in art.split("<script>", 2)[1] and "gd-to-hab" not in art

# the app: surplus food reaches the garden, events become messages, the den command
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
app.pet.xp = 0
app.garden.unlock_now(app.pet.level())
app.pet.hunger, app.pet.pack = 100.0, tuning.get("pack_cap")
app.pet.treat({"ssid": "Cafe", "security": "open"})
assert app.garden.s["slots"] and not app.garden.s["slots"][0].get("egg"), "a full belly and pack: the treat fed the garden"
assert app._garden_news and app._garden_news[0][0] == "hatch"
app.pet.message_hold = 0
app.pet.message_ts = time.time() - 10              # (the treat's own message has been read)
app._garden_tick()
assert "HATCHED" in app.pet.message, app.pet.message
app.pet.hunger, app.pet.pack = 10.0, 0.0
before = app.garden.s["slots"][0]["fed"]
app.pet.treat({"ssid": "Cafe2", "security": "open"})
assert app.garden.s["slots"][0]["fed"] == before, "room in his belly: nothing spare"
v = json.loads(asyncio.run(app.command("GARDEN"))[0])
assert v["mood"] == "hungry"                              # his belly is at 10: the larvae are hungry with him
assert v["unlocked"] and v["forced"] and len(v["larvae"]) == 1 and v["larvae"][0]["pct"] > 0
assert asyncio.run(app.command("GARDENCOUNTRY ie")) == ["OK"] and asyncio.run(app.command("GARDENCOUNTRY xx"))[0].startswith("ERR")
assert asyncio.run(app.command("GARDENUNLOCK off")) == ["OK"] and not app.garden.unlocked(app.pet.level())
assert "Harald" in app.garden_page("us") or app.pet.name in app.garden_page("us")

# through the den's web server: the page, and sightings sent back
import socket
import urllib.request
from bt_dragon import server
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
app.cfg["link"]["web_port"] = port


async def web_check():
    task = asyncio.create_task(server.web_server(app))
    await asyncio.sleep(0.3)
    get = lambda: urllib.request.urlopen(f"http://127.0.0.1:{port}/garden?c=ca", timeout=10).read().decode()  # noqa: E731
    html = await asyncio.to_thread(get)
    for _ in range(100):                                     # the art copy is built in the background at start
        if app.garden_art_version():
            break
        await asyncio.sleep(0.1)
    req = urllib.request.Request(f"http://127.0.0.1:{port}/garden/art?v=1", headers={"Accept-Encoding": "gzip"})
    resp = await asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=10))
    assert resp.headers["Content-Encoding"] == "gzip" and "immutable" in resp.headers["Cache-Control"]
    import gzip as gz
    assert "window.__garden" in gz.decompress(resp.read()).decode()
    assert json.loads((await app.command("GARDEN"))[0])["art"] == app.garden_art_version()
    assert "bookworm-proto-v1-ca" in html and "gd-to-hab" in html
    big = {"sp%d" % i: ["adult"] for i in range(400)}           # bigger than a den command may be
    body = json.dumps({"country": "ca", "seen": big, "seenDates": {}}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/garden/seen", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    r = json.loads(await asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=10).read()))
    assert r["ok"] and len(app.garden.cdata("ca")["seen"]) == 400
    app.stop.set()
    await asyncio.wait_for(task, 5)

asyncio.run(web_check())
app.stop.clear()

# the page in a browser, if Playwright is here
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
if sync_playwright:
    g.cdata("gb")["collection"] = [{"species": pool[0]["id"], "country": "gb", "points": 100,
                                    "title": "Raised in the Butterfly Garden", "author": "", "isbn": "", "pages": 0,
                                    "started": "2026-05-01T10:00:00Z", "date": "2026-05-09T10:00:00Z"}]
    path = os.path.join(tmp, "garden.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(garden_page.build(dict(g.page_data("gb"), name="Harald")))
    with sync_playwright() as p:
        kw = {"executable_path": "/opt/pw-browsers/chromium"} if os.path.exists("/opt/pw-browsers/chromium") else {}
        br = p.chromium.launch(**kw)
        page = br.new_page()
        errors, outside = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/*", lambda rt: (outside.append(rt.request.url), rt.abort()) if not rt.request.url.startswith("file:")
                   else rt.continue_())
        page.goto("file://" + path + "?notes=" + pool[1]["id"])
        page.wait_for_selector("#gd-to-hab")
        assert not errors, errors
        assert not outside, outside
        assert page.title() == "Harald's Butterfly Garden"
        assert page.is_visible("#species-view") and not page.is_visible("#hab-view") and not page.is_visible("nav.tabs")
        assert page.is_visible("#m-notes") and page.text_content("#mn-h") == pool[1]["name"]
        page.evaluate("document.getElementById('m-notes').hidden = true")
        assert "100" in page.inner_text("#score-pts")
        page.click("#gd-to-hab")
        page.wait_for_function("location.hash === '#habitats'")
        assert page.is_visible("#hab-view") and not page.is_visible("#species-view")
        page.click("#gd-back")
        page.wait_for_function("!document.getElementById('species-view').hidden")
        assert page.text_content("#score-title") == "Egg Explorer"
        assert "<image" in page.evaluate("window.__garden.art('red-admiral', 5, 'hungry')")     # her hand-drawn larva
        assert "sway" in page.evaluate("window.__garden.art('red-admiral', 9)")                 # its chrysalis
        assert "flutter" in page.evaluate("window.__garden.art('%s', 10)" % pool[2]["id"])
        page.goto("file://" + path + "?notes=red-admiral&stage=4&mood=content")
        page.wait_for_selector("#gd-notes-art svg")
        assert "crawl" in page.get_attribute("#gd-notes-art", "class")
        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert bg == "rgb(29, 28, 26)", bg
        page.screenshot(path=os.path.join(tmp, "coll.png"), full_page=False)
        br.close()
print("garden ok")
