"""Fixes from a week of testing: Awake counts from power-on (not the wall clock, which jumps when a
Pi without a clock battery finds the time); the stars can be kept off the voice; an unknown tracker's
warning repeats every minute, whatever the chattiness or quiet hours, until it's dismissed; the
Voice and light ring settings wait for Save; the Life list lives in Gadgets nearby; a book tracked by
percentage shows its percentage once."""
import asyncio
import json
import os
import socket
import tempfile
import threading
import time
import urllib.request

from bt_dragon import config, dot as dotmod, server
from bt_dragon.app import Dragon

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())

# ---- Awake: the wall clock jumping (finding the real time after power-on) doesn't move it
real_time = time.time
time.time = lambda: real_time() + 8 * 3600
try:
    assert app.view()["awake"] < 60
finally:
    time.time = real_time

# ---- the stars off the voice (still on the screen)
d = app.dot
said = []
d.say = lambda text, force=False: said.append((text, force))
d.speaks = lambda: True
d.s["chatty"] = "all"
d.on_say("A STAR RISES! GPS 12", "excited")
assert said and said[-1][0].upper().startswith("A STAR RISES")
said.clear()
d.s["say_stars"] = False
for t in ("A STAR RISES! GPS 12", "A NEW STAR! GALILEO", "3 NEW STARS IN THE SKY!", "A NEW CONSTELLATION: QZSS!"):
    d.on_say(t, "excited")
d.s["chatty"] = "adventure"
d.adventure("stars", n=2)
d.adventure("constellation", name="QZSS")
assert said == [], said
d.s["say_stars"] = True
assert "say_stars" in dotmod.SAY_BOOLS and dotmod.DEFAULTS["say_stars"] is True

# ---- an unknown tracker: said at once, then every minute until dismissed, in quiet hours too
said.clear()
rings = []


async def once(name, force=False):
    rings.append((name, force))
d.once = once
d.quiet_now = lambda: True                          # (quiet hours, and Adventure mode, from above)
dotmod.TRACKER_EVERY_S = 0.6                        # (a minute, sped up)
app.trackers.alerts[1] = {"id": 1, "address": "aa", "label": "Find My item (owner away)", "since": time.time() - 125 * 60,
                          "ts": time.time()}
d.on_say("UNKNOWN FIND MY ITEM NEAR YOU FOR 125 MIN", "alarmed")     # (the screen's message isn't said twice)
assert said == []


async def run(seconds):
    t = asyncio.ensure_future(d._timer_loop())
    await asyncio.sleep(seconds)
    t.cancel()
asyncio.run(run(1.9))
warn = [s for s in said if s[0].startswith("Warning! An unknown tracker")]
assert len(warn) >= 2 and all(f for _, f in warn), said
assert "125 minutes: a Find My item. Please check the Den." in warn[0][0], warn[0]
assert ("ev_alert", True) in rings
assert asyncio.run(app.command("DISMISS 1"))[0].startswith("OK") or not app.trackers.alerts
said.clear()
asyncio.run(run(1.5))
assert not [s for s in said if s[0].startswith("Warning!")], said
print("voice ok")

# ---- in a browser: Save settings, the Life list, a book by percentage
app.library_action({"action": "start", "book": {"title": "An E-book", "pages": 300, "mode": "percent"}})
bid = app.library.reading()[0]["id"]
app.library_action({"action": "log", "id": bid, "value": 12.5})
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
app.cfg["link"]["web_port"] = port
app.stop = asyncio.Event()             # (the voice tests above used another event loop)
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    kw = {"executable_path": "/opt/pw-browsers/chromium"} if os.path.exists("/opt/pw-browsers/chromium") else {}
    br = p.chromium.launch(**kw)
    pg = br.new_page(viewport={"width": 420, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if "127.0.0.1" in rt.request.url else rt.abort())
    pg.goto(f"http://127.0.0.1:{port}/")
    pg.wait_for_timeout(2500)
    # the Life list is part of Gadgets nearby now
    assert pg.evaluate("!!document.querySelector('[data-arrange=nearby] #species') && !document.querySelector('[data-arrange=life]')")
    pg.evaluate("document.getElementById('fold-voice').open = true")
    before = app.dot.s["volume"]
    new = 35 if before != 35 else 40
    pg.evaluate(f"(() => {{ const r = document.getElementById('dotVolume'); r.value = {new}; r.dispatchEvent(new Event('change')); }})()")
    pg.wait_for_timeout(300)
    assert app.dot.s["volume"] == before and pg.is_visible("#dotSaveBar")         # nothing sent yet
    pg.wait_for_timeout(3500)                                                      # (the Den refreshes meanwhile...)
    assert pg.evaluate("document.getElementById('dotVolume').value") == str(new)   # (...but keeps what you set)
    pg.click("#dotSaveBar button.primary")
    pg.wait_for_timeout(800)
    assert app.dot.s["volume"] == new and not pg.is_visible("#dotSaveBar")
    # Undo puts it back
    pg.evaluate("(() => { const b = document.getElementById('say_stars'); b.checked = !b.checked; b.dispatchEvent(new Event('change')); })()")
    pg.click("#dotSaveBar button:not(.primary)")
    pg.wait_for_timeout(800)
    assert app.dot.s["say_stars"] is True and pg.is_checked("#say_stars")
    # a book by percentage: its percentage once
    pg.goto(f"http://127.0.0.1:{port}/library")
    pg.wait_for_timeout(1500)
    line = pg.inner_text(f"#bk-{bid} .foot .sub")
    assert line.count("%") == 2 and line.count("12.5%") == 1 and "tracking by %" in line, line   # ("12.5% · tracking by %")
    assert not errs, errs
    br.close()
print("test_batch_oct22: OK")
