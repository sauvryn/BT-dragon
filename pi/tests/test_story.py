"""'Read me a story': the reader gathers the words (this page / this chapter / the whole book, from the
first sentence on this page; leaving out note markers, notes, page numbers, and for the whole book the
index and notes sections), the Pi reads them through the phone's voice (the Termux helper's own
protocol) or the Echo Dot (sentence by sentence, made ahead), stops on Stop, at the time limit or a nap,
keeps where it stopped, and the reader can go back there."""
import asyncio
import json
import os
import socket
import tempfile
import threading
import time
import urllib.request
import zipfile

from bt_dragon import config, server
from bt_dragon.app import Dragon
from bt_dragon import story as storymod

LONG = ("The dragon counted its books by firelight while the river ran below the cave. " * 6).strip()


def page(body):
    return ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
            f'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>x</title></head><body>{body}</body></html>')


def make_book(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        files = {
            "cover": '<section epub:type="cover"><p>Cover words here.</p></section>',
            "ch1": ('<section epub:type="chapter"><h1 id="c1">Chapter One</h1>'
                    '<p>Alpha begins the tale. Alpha has a note<a epub:type="noteref" href="#n1">1</a> in it.</p>'
                    + "".join(f"<p>Alpha paragraph {i}. {LONG}</p>" for i in range(12))
                    + '<span epub:type="pagebreak" id="page7" title="7">7</span>'
                    + '<p>Alpha ends here<sup>2</sup>.</p>'
                    '<h1 id="c2">Chapter Two</h1><p>Bravo starts the second chapter.</p>'
                    + "".join(f"<p>Bravo paragraph {i}. {LONG}</p>" for i in range(3))
                    + '<aside epub:type="footnote" id="n1"><p>FOOTNOTE WORDS that are never read.</p></aside>'
                    '<table><tr><td>TABLE WORDS</td></tr></table></section>'),
            "ch3": '<section epub:type="chapter"><h1>Chapter Three</h1><p>Charlie closes the book. The end.</p></section>',
            "notes": '<section epub:type="endnotes"><p>ENDNOTE WORDS.</p></section>',
            "index": '<section epub:type="index"><p>INDEX WORDS, 1, 2, 3.</p></section>'}
        items, spine = [], []
        for name, body in files.items():
            z.writestr(f"OEBPS/{name}.xhtml", page(body), zipfile.ZIP_DEFLATED)
            items.append(f'<item id="{name}" href="{name}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="{name}"/>')
        nav = ('<nav epub:type="toc"><ol><li><a href="ch1.xhtml#c1">Chapter One</a></li><li><a href="ch1.xhtml#c2">Chapter Two</a></li>'
               '<li><a href="ch3.xhtml">Chapter Three</a></li><li><a href="notes.xhtml">Notes</a></li><li><a href="index.xhtml">Index</a></li></ol></nav>'
               '<nav epub:type="landmarks"><ol><li><a epub:type="bodymatter" href="ch1.xhtml">Start</a></li>'
               '<li><a epub:type="index" href="index.xhtml">Index</a></li><li><a epub:type="endnotes" href="notes.xhtml">Notes</a></li></ol></nav>')
        z.writestr("OEBPS/nav.xhtml", page(nav))
        items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
        z.writestr("OEBPS/content.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">x</dc:identifier><dc:title>Story Time</dc:title>'
                   '<dc:creator>A. Wyrm</dc:creator><dc:language>en</dc:language></metadata>'
                   f'<manifest>{"".join(items)}</manifest><spine>{"".join(spine)}</spine></package>')


cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
app.cfg["link"]["web_port"] = port
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
base = f"http://127.0.0.1:{port}"

# a stand-in for the phone's Termux helper: the same requests, "speaking" each remark at once
heard = []
phone_on = threading.Event()


def phone():
    after = -1
    while True:
        if not phone_on.is_set():
            time.sleep(0.2)
            continue
        try:
            with urllib.request.urlopen(f"{base}/api/phone?after={after}", timeout=75) as r:
                reply = json.load(r)
            for it in reply.get("items", []):
                heard.append(it["text"])
                time.sleep(0.05)
            after = reply.get("seq", after)
        except Exception:
            time.sleep(0.5)


threading.Thread(target=phone, daemon=True).start()
phone_on.set()
time.sleep(1.5)
assert app.story.voices()["phone"]


def post(d):
    req = urllib.request.Request(base + "/api/library/story", data=json.dumps(d).encode(),
                                 headers={"Origin": base}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def wait_done(t=30):
    end = time.time() + t
    while time.time() < end:
        if not app.story.active:
            return True
        time.sleep(0.2)
    return False


# ---- the Pi's side, with words sent straight
items = [{"t": f"Sentence {i}.", "p": i % 3 == 2, "h": False, "ch": 2, "k": 2 + i // 4} for i in range(10)]
assert not post({"action": "start", "voice": "dot", "items": items})["ok"]          # no Dot here
r = post({"action": "start", "book": "b1", "title": "T", "label": "this chapter", "voice": "phone", "items": items})
assert r["ok"], r
assert wait_done()
text = " ".join(heard)
assert all(f"Sentence {i}." in text for i in range(10)), heard
last = app.store.get("story_last")["b1"]
assert last["k"] == 4 and last["end"]
assert any(e["kind"] == "library" and "read T out loud" in e["text"] for e in app.store.events(10))
# the time limit: stops at the end of a sentence
heard.clear()
many = [{"t": f"Word {i}.", "p": False, "h": False, "ch": 2, "k": 3} for i in range(400)]
assert post({"action": "start", "book": "b2", "title": "T2", "voice": "phone", "minutes": 5, "items": many})["ok"]
time.sleep(0.5)
app.story.cur["ends_at"] = time.time()                       # (five minutes later)
assert wait_done()
assert len(heard) < 400 // 2 and not app.story.active
# Stop
heard.clear()
assert post({"action": "start", "book": "b3", "title": "T3", "voice": "phone", "items": many})["ok"]
time.sleep(0.3)
r = post({"action": "stop"})
assert r["stopped"] and not r["story"]["active"]
assert "b3" in app.store.get("story_last")
# bad input
assert not post({"action": "start", "voice": "phone", "items": []})["ok"]
assert not post({"action": "start", "voice": "smoke", "items": items})["ok"]

# ---- the Echo Dot's side: sentence by sentence, each made while the one before plays
dot = app.dot
made, played = [], []


async def fake_make(text, name):
    made.append(text)
    return 0.01, "Pi"


async def fake_play(name, s):
    played.append(name)


dot._make_speech, dot._play = fake_make, fake_play
dot.connected = dot.ready = True
parts = [("One.", 0.0, {}), ("Two.", 0.0, {}), ("Three.", 0.0, {})]
it = iter(parts)
said = []
res = asyncio.run(dot.speak_stream(lambda: next(it, None), said.append))
assert res == "done" and made == ["One.", "Two.", "Three."] and len(played) == 3 and [p[0] for p in said] == made
dot.connected = dot.ready = False

# ---- news waits while a story is read
app.story.active, app.story.voice = True, "phone"
n0 = app.dot.phone.seq
app.dot.s["phone"] = True
app.dot.say("A NEW GADGET!")
assert app.dot.phone.seq == n0                                # held back
app.dot.say("Tracker warning!", force=True)
assert app.dot.phone.seq == n0 + 1                            # a warning still goes through
app.story.active = False

# ---- in a browser: what the reader gathers
work = tempfile.mkdtemp()
book = os.path.join(work, "story.epub")
make_book(book)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium") if os.path.exists("/opt/pw-browsers/chromium") else p.chromium.launch()
    pg = br.new_page(viewport={"width": 420, "height": 800})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if "127.0.0.1" in rt.request.url else rt.abort())
    pg.goto(base + "/library")
    pg.wait_for_timeout(1500)
    pg.set_input_files("#epubFile", [book])
    pg.wait_for_function("document.querySelectorAll('[data-read], [data-startlib]').length >= 1", timeout=20000)
    pg.wait_for_timeout(800)
    eid = app.library.view(full=True)["shelf"][0]["id"]
    pg.evaluate(f"openReader('{eid}')")
    pg.wait_for_selector("#reader:not([hidden])")
    pg.wait_for_timeout(1500)
    assert pg.evaluate("RD.m.chapters[RD.ch].href").endswith("ch1.xhtml")

    def gather(scope):
        return pg.evaluate(f"stGather('{scope}').then(x => x)")

    ch = gather("chapter")
    t = " ".join(x["t"] for x in ch)
    assert t.startswith("Chapter One Alpha begins the tale.") or t.startswith("Chapter One. Alpha") or t.startswith("Chapter One"), t[:80]
    assert "Alpha has a note in it." in t and "Alpha ends here." in t, t[-200:]
    assert "Bravo" not in t and "FOOTNOTE" not in t and "TABLE" not in t and " 7 " not in t
    assert ch[0]["h"] and all(x["ch"] == ch[0]["ch"] for x in ch)
    bk = " ".join(x["t"] for x in gather("book"))
    assert "Bravo starts the second chapter." in bk and "Charlie closes the book." in bk
    assert "ENDNOTE" not in bk and "INDEX" not in bk and "FOOTNOTE" not in bk and "Cover words" not in bk
    pg1 = gather("page")
    assert 0 < len(pg1) < len(ch) and pg1[0]["t"] == ch[0]["t"]
    # from the next page: starts with a sentence that starts there
    pg.click("#rd-next"); pg.wait_for_timeout(500)
    pg2 = gather("page")
    t1, t2 = [x["t"] for x in pg1], [x["t"] for x in pg2]
    nxt = next(x for x in t2 if x.startswith("Alpha paragraph"))
    assert nxt not in t1 and nxt == "Alpha paragraph " + str(int(t1[[i for i, x in enumerate(t1) if x.startswith("Alpha paragraph")][-1]].split()[-1].rstrip(".")) + 1) + "."
    assert len(t1) + len(t2) <= len([x for x in ch if x["t"]]) + 1
    # the panel: start through the phone, then go back to where it stopped
    heard.clear()
    pg.click("#rd-story"); pg.wait_for_timeout(800)
    assert pg.is_enabled("input[name=st-voice][value=phone]") and not pg.is_enabled("input[name=st-voice][value=dot]")
    if os.environ.get("SHOT"):
        pg.screenshot(path=os.environ["SHOT"])
    pg.check("input[name=st-scope][value=page]")
    pg.click("#st-start")
    pg.wait_for_timeout(1500)
    assert wait_done()
    assert any(nxt in h for h in heard), heard[:5]
    last = app.store.get("story_last")[eid]
    assert pg.is_visible("#rd-story-panel")
    pg.click("#st-close"); pg.wait_for_timeout(300)
    pg.click("#rd-prev"); pg.wait_for_timeout(500)
    pg.click("#rd-story"); pg.wait_for_timeout(800)
    assert pg.is_visible("#st-goto")
    pg.click("#st-goto"); pg.wait_for_timeout(1000)
    assert pg.evaluate("RD.ch") == last["ch"]
    pg.click("#rd-close"); pg.wait_for_timeout(500)
    assert not errs, errs
    br.close()
print("story ok")
