"""Color Blindness Mode: each set of colours stays readable on the Den's background and keeps its
three meanings (accent, danger, good) apart, for the people it's for (simulated as in Machado,
Oliveira and Fernandes, 2009); the setting, and the style sheet every page loads."""
import asyncio
import itertools
import math
import tempfile

from bt_dragon import access, config
from bt_dragon.app import Dragon

SIM = {"normal": None,
       "protanopia": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
       "deuteranopia": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
       "tritanopia": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]}


def rgb(h):
    return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def seen(h, kind):
    c = [lin(x) for x in rgb(h)]
    m = SIM[kind]
    return [max(0.0, min(1.0, sum(m[i][j] * c[j] for j in range(3)))) for i in range(3)] if m else c


def lab(c):
    X = 0.4124 * c[0] + 0.3576 * c[1] + 0.1805 * c[2]
    Y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    Z = 0.0193 * c[0] + 0.1192 * c[1] + 0.9505 * c[2]
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116      # noqa: E731
    fx, fy, fz = f(X / 0.95047), f(Y), f(Z / 1.08883)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def apart(a, b, kind):
    """How different two colours look (CIE76 colour difference): over 30 is clearly different."""
    return math.dist(lab(seen(a, kind)), lab(seen(b, kind)))


def contrast(a, b="#282623"):
    L = lambda h: 0.2126 * lin(rgb(h)[0]) + 0.7152 * lin(rgb(h)[1]) + 0.0722 * lin(rgb(h)[2])  # noqa: E731
    x, y = L(a), L(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


for mode in access.MODES:
    p = access.PALETTE[mode]
    for role in ("accent", "danger", "good", "rare"):
        for bg in ("#282623", "#1d1c1a"):                       # sections and the page behind them
            assert contrast(p[role], bg) >= 4.5, (mode, role, bg, contrast(p[role], bg))
    who = ["normal"] + ([] if mode == "full" else [mode])
    for kind in who:
        for a, b in itertools.combinations(("accent", "danger", "good"), 2):
            d = apart(p[a], p[b], kind)
            assert d >= 30, (mode, kind, a, b, round(d))
# and the point of it: the full-colour set fails red-green colour blindness, the new one doesn't
assert apart(access.FULL["danger"], access.FULL["good"], "deuteranopia") < 20
assert apart(access.RED_GREEN["danger"], access.RED_GREEN["good"], "deuteranopia") >= 30
assert access.PALETTE["protanopia"] is access.PALETTE["deuteranopia"]     # one set serves both

# the style sheet: nothing for full colour vision; the set, plus a ⚠ on danger buttons, otherwise
assert "--moss" not in access.theme_css("full") and "--moss" not in access.theme_css("nonsense")
css = access.theme_css("tritanopia")
assert "--rune: #c9a2f2" in css and "--moss: #5fd4c8" in css and "button.danger::before" in css and "--rare:" in css
assert access.theme_css("protanopia").split("*/", 1)[1] == access.theme_css("deuteranopia").split("*/", 1)[1]

# the setting
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
run = lambda c: asyncio.run(app.command(c))                             # noqa: E731
assert run("CVD") == ["full"]
assert run("CVD deuteranopia") == ["OK"] and run("CVD") == ["deuteranopia"] and app.cvd_mode() == "deuteranopia"
assert run("CVD purple")[0].startswith("ERR") and run("CVD") == ["deuteranopia"]
for page in ("den", "map", "shopping", "calendar", "art", "collection"):
    with open(f"bt_dragon/{page}.html", encoding="utf-8") as f:
        html = f.read()
    assert '<link rel="stylesheet" href="/theme.css">' in html and "color-scheme: dark" in html, page
    assert "#c8553d" not in html, page                                  # the old red failed contrast
with open("bt_dragon/den.html", encoding="utf-8") as f:
    den = f.read()
assert "<h2>Care and Accessibility</h2>" in den
for m in access.MODES:
    assert f'<option value="{m}">{access.NAMES[m]}</option>' in den
assert '<link rel="stylesheet" href="/theme.css">' in app.garden_page("gb")

# every piece of text on the Den's pages passes contrast (WCAG), in every mode, in a real browser
CONTRAST_JS = r"""
() => {
  const lin = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const L = ([r,g,b]) => 0.2126*lin(r) + 0.7152*lin(g) + 0.0722*lin(b);
  const parse = s => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0],p[1],p[2], p.length > 3 ? p[3] : 1]; };
  const blend = (top, bot) => [0,1,2].map(i => top[i]*top[3] + bot[i]*(1-top[3])).concat([1]);
  function bg(el){
    const layers = [];
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
    }
    let base = [255,255,255,1];
    for (let i = layers.length - 1; i >= 0; i--) base = blend(layers[i], base);
    return base;
  }
  const seen = new Map(), out = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const t = n.nodeValue.trim(); if (!t) continue;
    const el = n.parentElement; if (!el) continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || +cs.opacity === 0) continue;
    if (el.closest('svg')) continue;
    let fg = parse(cs.color); const b = bg(el);
    let op = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) op *= +getComputedStyle(e).opacity;
    fg = blend([fg[0],fg[1],fg[2], fg[3]*op], b);
    const l1 = L(fg), l2 = L(b), ratio = (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
    const size = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    const need = large ? 3 : 4.5;
    const key = fg.slice(0,3).join(',') + '|' + b.slice(0,3).join(',') + '|' + (large ? 'L' : 'N');
    if (!seen.has(key)) { seen.set(key, out.length); out.push({fg: fg.slice(0,3), bg: b.slice(0,3), ratio: +ratio.toFixed(2), need, large, n: 0, sample: t.slice(0, 60), tag: el.tagName + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '')}); }
    out[seen.get(key)].n++;
  }
  // form controls: their own text on their own background
  document.querySelectorAll('input, select, textarea, button').forEach(el => {
    const r = el.getBoundingClientRect(); if (!r.width) return;
    const cs = getComputedStyle(el); const fg = parse(cs.color); const b = bg(el);
    const ratio = (Math.max(L(fg),L(b))+0.05)/(Math.min(L(fg),L(b))+0.05);
    const key = 'ctl|' + el.tagName + '|' + fg.slice(0,3) + '|' + b.slice(0,3);
    if (!seen.has(key)) { seen.set(key, out.length); out.push({fg: fg.slice(0,3), bg: b.slice(0,3), ratio: +ratio.toFixed(2), need: 4.5, n: 0, sample: (el.value || el.placeholder || el.textContent || '').trim().slice(0,40), tag: 'control ' + el.tagName + (el.type ? '[' + el.type + ']' : '')}); }
    out[seen.get(key)].n++;
  });
  return out;
}
"""
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
if sync_playwright:
    import os
    import socket
    import threading
    import time
    from bt_dragon import server
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    app.cfg["link"]["web_port"] = port
    app.pet.xp = 1300
    app.garden.feed(5, app.pet.level())
    threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
    time.sleep(3)
    with sync_playwright() as p:
        kw = {"executable_path": "/opt/pw-browsers/chromium"} if os.path.exists("/opt/pw-browsers/chromium") else {}
        br = p.chromium.launch(**kw)
        for mode in access.MODES:
            app.store.put("cvd", mode)
            for scheme in ("dark", "light"):
                ctx = br.new_context(viewport={"width": 400, "height": 900}, color_scheme=scheme)
                # (the pages are dark whatever the browser prefers; light mode is checked on the two main ones)
                for path in (("/", "/garden", "/art", "/map", "/shopping", "/calendar", "/stars", "/journal", "/sky", "/whispers", "/achievements", "/library") if scheme == "dark"
                             else ("/", "/garden")):
                    page = ctx.new_page()
                    page.route("**/*", lambda rt: rt.continue_() if "127.0.0.1" in rt.request.url else rt.abort())
                    page.goto(f"http://127.0.0.1:{port}{path}")
                    page.wait_for_timeout(1500)
                    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
                    bad = [x for x in page.evaluate(CONTRAST_JS) if x["ratio"] < x["need"]
                           and not x["tag"].startswith(("control INPUT[range]", "control INPUT[checkbox]"))]
                    assert not bad, (mode, scheme, path, bad)
                    if path == "/":
                        moss = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--moss').trim()")
                        assert moss == access.PALETTE[mode]["good"], (mode, moss)
                    page.close()
                ctx.close()
        br.close()
print("access ok")
