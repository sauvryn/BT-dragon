"""The Star Chart and the Gadget Journal: every kind of gadget Harald can name has a card,
every card has its facts and sources, his finds are sorted into them, and the pages are
served safely (names from the air are only ever text)."""
import asyncio
import re
import socket
import tempfile
import threading
import time
import urllib.request

from bt_dragon import ble, config, journal, server, starchart
from bt_dragon.app import Dragon

# every fixed label the gadget classifier can give has a card in the Journal
fixed = {lab for lab, _ in ble.SERVICES.values()} | set(ble.APPLE_PODS.values()) | {
    "Google Find Hub tag", "Eddystone beacon", "Windows PC", "Swift Pair accessory", ble.UNBRANDED, "Mystery morsel",
    "Find My item (owner away)", "Find My device (near owner)", "AirPods / Beats", "AirPlay speaker / TV",
    "Apple Watch", "iPhone / iPad hotspot", "iPhone / iPad / Mac", "Apple device setting up", "Apple device (Handoff)",
    "Apple device (AirDrop)", "iBeacon", "Apple device"}
for data in (bytes([0x12, 0x19]) + bytes(25), bytes([0x12, 2, 0, 0]), bytes([0x07, 3, 0, 0x14, 0x20]), bytes([0x09, 0]),
             bytes([0x0B, 0]), bytes([0x0D, 0]), bytes([0x10, 0]), bytes([0x0F, 0]), bytes([0x0C, 0]), bytes([0x05, 0]),
             bytes([0x02, 0]), bytes([0x55, 0])):
    fixed.add(ble.classify(None, {0x004C: data}, [], {})[1])
missing = sorted(lab for lab in fixed if lab not in journal.CAT_BY_LABEL)
assert not missing, missing
ids = [c[0] for c in journal.CATALOGUE]
assert len(ids) == len(set(ids))
for c in journal.CATALOGUE:
    gid, group, title, rarity, icon, labels, what, how, dyk, sources = c
    assert group in journal.GROUPS and rarity in ("Common", "Uncommon", "Rare") and what and how and dyk, gid
    assert sources and all(u.startswith("https://") for _, u in sources), gid
for c in starchart.CONSTELLATIONS.values():
    assert c["rarity"] in ("Common", "Uncommon", "Rare") and c["text"] and c["dyk"] and c["sources"]
    assert all(u.startswith("https://") for _, u in c["sources"]) and len(c["shape"]) >= 5
assert set(starchart.ORDER) == set(starchart.CONSTELLATIONS)
from bt_dragon.sky import CONSTELLATIONS as SKY                    # noqa: E402
assert set(SKY) == set(starchart.CONSTELLATIONS)                   # every system he can hear has a card

# his finds, sorted into the collection
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
app.pet.name = "Ember"
now = time.time()
for lab, kind in [("iPhone / iPad / Mac", "apple"), ("AirPods Pro 2", "audio"), ("AirPods / Beats", "audio"),
                  ("JBL Flip #", "named"), ("Garmin device", "maker"), ('</script><b id="x">hi</b>', "named")]:
    app.store.db.execute("INSERT INTO species (key, label, kind, first_seen, last_seen, meals) VALUES (?, ?, ?, ?, ?, ?)",
                         (lab.lower(), lab, kind, now - 86400, now, 3))
j = app.journal_data()
items = {i["id"]: i for g in j["groups"] for i in g["items"]}
assert items["apple-nearby"]["found"] and items["airpods"]["count"] == 6 and not items["tile"]["found"]
assert [x["label"] for x in items["airpods"]["card"]["mine"]["list"]] == ["AirPods Pro 2"]   # models found, as forms
extras = {x["id"]: x for x in j["extras"]}
assert extras["named"]["count"] == 2 and extras["maker"]["count"] == 1
assert j["title"] == "Ember's Gadget Journal" and "Ember" in j["intro"] and "Harald" not in str(j["groups"])
for st in [("GPS", 5), ("GPS", 12), ("Galileo", 3), ("SBAS", 123)]:
    app.store.star_seen(f"{st[0]}-{st[1]}", st[0], st[1], now)
app.stars.last_heard = {"GPS-5": now}
s = app.star_chart_data()
cs = {i["id"]: i for i in s["groups"][0]["items"]}
assert cs["GPS"]["count"] == 2 and cs["GPS"]["now"] == 1 and not cs["QZSS"]["found"]
assert [x["bold"] for x in cs["GPS"]["card"]["mine"]["list"]] == [True, False]
assert s["subtitle"].startswith("4 stars in 3 of 7 constellations") and "1 in view now" in s["subtitle"]

# the pages, served: the data is in the page, and a name from the air can't break out of it
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
app.cfg["link"]["web_port"] = port
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
for path in ("/journal", "/stars"):
    html = urllib.request.urlopen(f"http://127.0.0.1:{port}{path}").read().decode()
    assert "__DATA__" not in html and "const DATA = {" in html
    assert html.count("</script>") == 3, path                       # lang.js's, auth.js's and the page's own
with open("bt_dragon/den.html", encoding="utf-8") as f:
    den = f.read()
assert 'href="/journal"' in den and 'href="/stars"' in den
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
if sync_playwright:
    import os
    with sync_playwright() as p:
        kw = {"executable_path": "/opt/pw-browsers/chromium"} if os.path.exists("/opt/pw-browsers/chromium") else {}
        br = p.chromium.launch(**kw)
        for path in ("/journal", "/stars"):
            page = br.new_page(viewport={"width": 360, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("**/*", lambda rt: rt.continue_() if "127.0.0.1" in rt.request.url else rt.abort())
            page.goto(f"http://127.0.0.1:{port}{path}")
            page.wait_for_selector(".card")
            assert not errors, errors
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), path
            assert page.locator("#x").count() == 0                     # shown as text, not made into a page element
            page.locator(".card").first.click()
            page.wait_for_selector("#sheet:not([hidden])")
            assert page.locator("#sheet .sources a").count() >= 1
            page.keyboard.press("Escape")
            assert page.locator("#sheet").is_hidden()
            if path == "/journal":
                page.locator('.card[data-id="named"]').click()
                assert '</script><b id="x">hi</b>' in page.inner_text("#sheet")
            page.close()
        br.close()
print("collections ok")
