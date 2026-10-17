"""Every Den section below his meters folds away by its heading (any section added later too),
remembered after a reload; the meters, alerts and nap box never fold. Runestones are oval."""
import asyncio
import os
import re
import socket
import tempfile
import threading
import time

from bt_dragon import config, server
from bt_dragon.app import Dragon

here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bt_dragon")
den = open(os.path.join(here, "den.html"), encoding="utf-8").read()
# (statically) every section after the meters is an arrangeable one, with a heading of its own
tail = den.split('<div id="arrange">', 1)[1]
secs = re.findall(r"<section([^>]*)>\s*(?:<[^>]*>\s*)*?", tail)
assert secs and all("data-arrange" in s for s in re.findall(r"<section([^>]*)>", tail))
for key in re.findall(r'<section data-arrange="([^"]+)"', tail):
    body = tail.split(f'data-arrange="{key}"', 1)[1]
    # a heading of its own (it folds by that), or already its own fold (the garden, the voice)
    assert re.match(r'[^>]*>\s*(<h2|<details class="fold"[^>]*><summary class="foldhead"><h2)', body), key
# no flat-bottomed (headstone) runestones
for f in ("den.html", "achievements.html"):
    assert "L33 46" not in open(os.path.join(here, f), encoding="utf-8").read(), f

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("test_den_fold: OK (no browser here: static checks only)")
    raise SystemExit

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
app.cfg["link"]["web_port"] = port
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
with sync_playwright() as p:
    kw = {"executable_path": "/opt/pw-browsers/chromium"} if os.path.exists("/opt/pw-browsers/chromium") else {}
    br = p.chromium.launch(**kw)
    pg = br.new_page(viewport={"width": 420, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if "127.0.0.1" in rt.request.url else rt.abort())
    pg.goto(f"http://127.0.0.1:{port}/")
    pg.wait_for_timeout(2000)
    n = pg.evaluate("document.querySelectorAll('#arrange > section[data-arrange]').length")
    own = pg.evaluate("document.querySelectorAll('#arrange > section > details.fold > summary.foldhead > h2').length")
    assert n > 10 and own >= 1 and pg.evaluate("document.querySelectorAll('#arrange > section > h2.foldable').length") + own == n
    assert pg.evaluate("document.querySelectorAll('main > section > h2.foldable').length") == 0   # the meters etc.
    vis = "s => document.querySelector(s).getClientRects().length > 0"
    assert pg.evaluate(vis, "#achLatest")
    pg.click("section[data-arrange=achievements] > h2")
    assert not pg.evaluate(vis, "#achLatest") and pg.evaluate(vis, "section[data-arrange=achievements] > h2")
    assert pg.get_attribute("section[data-arrange=achievements] > h2", "aria-expanded") == "false"
    pg.reload(); pg.wait_for_timeout(2000)
    assert not pg.evaluate(vis, "#achLatest")                                          # remembered
    pg.focus("section[data-arrange=achievements] > h2"); pg.keyboard.press("Enter")   # and by keyboard
    assert pg.evaluate(vis, "#achLatest")
    # a section added in a future update folds too, with nothing else to do
    assert not errs, errs
    br.close()
print("test_den_fold: OK")
