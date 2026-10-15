"""Which English he writes in (British, American, Canadian): the conversion (Bookworm's rules),
the Pi's own country, the Den's setting and what moving the Lair offers, his screen, and (with
Playwright) the Den converted in a browser, with names left alone."""
import asyncio
import json
import os
import socket
import tempfile
import threading
import time

from bt_dragon import config, garden as G, lang, server
from bt_dragon.app import Dragon
from bt_dragon.store import Store

C = lang.convert
# spellings, both ways, keeping capitals; Canadian is British spelling with -ize
s = "We walked 2 kilometres and 300 meters; the colour grey is organised. Recognise neighbouring traveled centre"
assert C(s, "us") == "We walked 2 kilometers and 300 meters; the color gray is organized. Recognize neighboring traveled center"
assert C(s, "gb") == "We walked 2 kilometres and 300 metres; the colour grey is organised. Recognise neighbouring travelled centre"
assert C(s, "ca") == "We walked 2 kilometres and 300 metres; the colour grey is organized. Recognize neighbouring travelled centre"
assert C("CLIMBING! 3 METRES UP TODAY", "us") == "CLIMBING! 3 METERS UP TODAY"           # his screen: all capitals
assert C("Colour", "us") == "Color" and C("In autumn", "us") == "In the fall" and C("In the fall", "gb") == "In autumn"
assert C("barometer", "gb") == "barometer" and C("parameters", "gb") == "parameters"    # whole words only
# insect names are never converted, as in Bookworm (all four countries' names)
assert C("AN EGG HATCHED! AN EARLY GREY CATERPILLAR, GREY COLOUR", "us") == "AN EGG HATCHED! AN EARLY GREY CATERPILLAR, GRAY COLOR"
assert C("A Gray Hairstreak and the Multicolored Asian Lady Beetle: colour", "gb") == \
    "A Gray Hairstreak and the Multicolored Asian Lady Beetle: colour"
assert C(s, "xx") == s and C("", "us") == "" and C(None, "us") is None

# the Pi's own country
root = tempfile.mkdtemp()


def put(p, text):
    p = os.path.join(root, p.lstrip("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


assert lang.os_country(root) is None
put("/etc/default/locale", 'LANG="en_US.UTF-8"\n')
assert lang.os_country(root) == "US"
put("/etc/wpa_supplicant/wpa_supplicant.conf", "ctrl_interface=DIR=/var/run/wpa_supplicant\ncountry=ca\n")
assert lang.os_country(root) == "CA"
put("/boot/firmware/cmdline.txt", "console=tty1 root=PARTUUID=1-02 rootwait cfg80211.ieee80211_regdom=GB\n")
assert lang.os_country(root) == "GB"                                   # Raspberry Pi Imager's setting wins

# the setting
st = Store(os.path.join(tempfile.mkdtemp(), "l.db"))
L = lang.Language(st, "US")
assert L.auto and L.current() == "us" and L.current("CA") == "ca" and L.current("FR") == "us" and L.current("IE") == "gb"
assert lang.Language(st, "FR").current() == "gb" and lang.Language(st, None).current() == "gb"
assert L.set(auto=False, lair_code="CA") is None and L.current("GB") == "ca"     # unticking keeps what was showing
assert L.set(lang="us") is None and L.current("GB") == "us" and L.set(lang="fr")
assert lang.Language(st, "US").current("GB") == "us"                  # kept
L.set(auto=True)
assert L.current("GB") == "gb"

# the app: commands, the garden's starting country, his screen
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
run = lambda c: asyncio.run(app.command(c))                             # noqa: E731


def state():
    return dict(x.split("=", 1) for x in run("LANG")[:-1])


d = state()
assert d["auto"] == "1" and d["lang"] == "gb" and d["garden"] == "gb" and d["lair_lang"] == ""
app.os_country = "US"
app.language.os_code = "US"
assert state()["lang"] == "us"
assert run("LANGSET auto off") == ["OK"] and run("LANGSET ca") == ["OK"] and state()["lang"] == "ca"
assert run("LANGSET fr")[0].startswith("ERR") and run("LANGSET auto maybe")[0].startswith("ERR")
assert run("LANGSET auto on") == ["OK"]
app.pet.say("CLIMBING! 3 METRES UP TODAY")
from bt_dragon import screen  # noqa: E402
v = app.view()
assert v["lang"] == "us"
g = G.Garden(Store(os.path.join(tempfile.mkdtemp(), "g.db")))
g.default_country = "us"
assert g.country("GB") == "us"                                         # the Lair no longer decides by itself
g.set_country("ie")
assert g.country() == "ie"
# the garden page gets his English
assert '"lang": "us"' in app.garden_page("gb")


# moving the Lair: LANG says what to offer
def geo(name, cc, lat, lon):
    def get(url, params, timeout=12):
        return {"results": [{"name": name, "admin1": "", "country_code": cc, "latitude": lat, "longitude": lon}]}
    return get


app.lair.fetch = lambda *a, **k: {}
app.lair.get = geo("Toronto", "CA", 43.7, -79.4)
assert run("LAIRSET Toronto|Canada")[0].startswith("OK")
d = state()
assert d["lair_lang"] == "ca" and d["lair_country"] == "ca" and d["lang"] == "ca" and d["garden"] == "gb"
app.lair.get = geo("Paris", "FR", 48.85, 2.35)
run("LAIRSET Paris|France")
d = state()
assert d["lair_lang"] == "" and d["lang"] == "us"                     # back to the Pi's own country


# the Den in a browser: converted, with names (data-nolang) left alone
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
if sync_playwright:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    app.cfg["link"]["web_port"] = port
    threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
    time.sleep(3)
    with sync_playwright() as p:
        kw = {"executable_path": "/opt/pw-browsers/chromium"} if os.path.exists("/opt/pw-browsers/chromium") else {}
        br = p.chromium.launch(**kw)
        page = br.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/*", lambda rt: rt.continue_() if "127.0.0.1" in rt.request.url else rt.abort())
        page.goto(f"http://127.0.0.1:{port}/")
        page.wait_for_function("window.btLang && window.btLang.lang === 'us'")
        page.wait_for_timeout(1500)
        assert not errors, errors
        body = page.inner_text("body").replace('"metres" or "meters", "colour" or "color"', "")   # the example
        assert "metres" not in body and "colour" not in body, [l for l in body.split("\n") if "metres" in l or "colour" in l]
        # new text is converted as it arrives; names are not
        page.evaluate("""() => { const a = document.createElement('p'); a.id = 't1'; a.textContent = 'Grey metres';
                                 const b = document.createElement('p'); b.id = 't2'; b.setAttribute('data-nolang', '');
                                 b.textContent = 'Grey House'; document.body.append(a, b); }""")
        page.evaluate("() => { const c = document.createElement('p'); c.id = 't3'; c.textContent = 'Early Grey, grey metres'; document.body.append(c); }")
        page.wait_for_timeout(200)
        assert page.text_content("#t3") == "Early Grey, gray meters"
        # the language examples in the Lair section stay as written
        assert '"metres" or "meters", "colour" or "color", "autumn" or "fall"' in page.inner_text("[data-arrange=lair]")
        assert page.text_content("#t1") == "Gray meters" and page.text_content("#t2") == "Grey House"
        assert page.get_attribute("#lairPlace", "placeholder") == "City/state or zip/postcode"
        # the Lair moving to Canada: asks about the language and the garden
        app.lair.get = geo("Toronto", "CA", 43.7, -79.4)
        page.fill("#lairPlace", "Toronto")
        page.fill("#lairCountry", "Canada")
        page.click("#lairSaveBtn")
        page.wait_for_selector("#lairAsk:not([hidden])")
        assert page.is_visible("#laLangRow") and page.is_visible("#laGardenRow")
        assert page.text_content("#laLangName") == "Canadian English"
        page.uncheck("#laLang")                       # keep American English; move the garden
        page.click("text=Continue")
        page.wait_for_timeout(800)
        lines = page.evaluate("fetch('/api/cmd', {method: 'POST', body: 'LANG'}).then(r => r.json()).then(j => j.lines)")
        d = dict(x.split("=", 1) for x in lines[:-1])
        assert d["auto"] == "0" and d["lang"] == "us" and d["garden"] == "ca", d
        br.close()
print("lang ok")
