"""The e-book reader's pages line up with the screen, however far into a chapter you are: on a
phone the reading area is often a fraction of a pixel wide (412.3px, say, at a zoom or text
size the phone chose), and a page turn that moved by a whole number of pixels drifted a little
further each time, until half a letter on the right was cut off."""
import ast
import asyncio
import os
import socket
import tempfile
import threading
import time
import zipfile

from bt_dragon import config, server
from bt_dragon.app import Dragon

# make_epub from test_epub.py (its own words and layout), without running that test
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_epub.py")).read()
tree = ast.parse(src)
ns = {"zipfile": zipfile}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "WORDS" for t in node.targets):
        exec(compile(ast.Module([node], []), "test_epub", "exec"), ns)
    if isinstance(node, ast.FunctionDef) and node.name == "make_epub":
        exec(compile(ast.Module([node], []), "test_epub", "exec"), ns)

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
app.cfg["link"]["web_port"] = port
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
base = f"http://127.0.0.1:{port}"
book = os.path.join(tempfile.mkdtemp(), "long.epub")
ns["make_epub"](book, title="A Long Chapter", chapters=2, words=9000)

CHECK = """() => {
  const flow = document.getElementById('rd-flow'), fr = flow.getBoundingClientRect();
  const range = document.createRange(); range.selectNodeContents(flow);
  let worst = 0, seen = 0;
  for (const r of range.getClientRects()) {
    if (r.width < 1 || r.right < fr.left || r.left > fr.right) continue;       // (other pages)
    seen++;
    worst = Math.max(worst, r.right - fr.right, fr.left - r.left);           // past either edge
  }
  return {worst, seen, page: RD.page, pages: RD.pages, width: fr.width};
}"""

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium") if os.path.exists("/opt/pw-browsers/chromium") else p.chromium.launch()
    for vw, dpr, pad in ((412, 2.625, "24.37px"), (390, 3, "24px"), (1280, 1, "23.6px")):
        pg = br.new_page(viewport={"width": vw, "height": 860}, device_scale_factor=dpr)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/*", lambda rt: rt.continue_() if "127.0.0.1" in rt.request.url else rt.abort())
        pg.goto(base + "/library")
        pg.wait_for_timeout(1200)
        if not app.library.reading():
            pg.set_input_files("#epubFile", [book])
            pg.wait_for_selector("[data-startlib]", timeout=20000)
            pg.wait_for_timeout(500)
            pg.click("[data-startlib]")
            pg.wait_for_timeout(1200)
        b = app.library.reading()[-1]
        pg.click(f"#bk-{b['id']} [data-read]")
        pg.wait_for_selector("#reader:not([hidden])")
        pg.wait_for_function("RD && RD.pages > 1 && !RD.loading", timeout=20000)
        # a reading area a fraction of a pixel wide, as on many phones
        pg.add_style_tag(content=f".rd-stage {{ padding-left: {pad} !important; padding-right: {pad} !important; }}")
        pg.evaluate("window.dispatchEvent(new Event('resize'))")
        pg.wait_for_timeout(800)
        # into the long chapter, and far along it
        for _ in range(60):
            if pg.evaluate("RD.pages") >= 18:
                break
            if pg.is_disabled("#rd-next"):
                pg.click("#rd-prev")
            else:
                pg.click("#rd-next")
            pg.wait_for_timeout(150)
        assert pg.evaluate("RD.pages") >= 18, pg.evaluate("[RD.ch, RD.page, RD.pages]")
        far = min(pg.evaluate("RD.pages") - 1, 28)
        for page_no in (0, 1, 7, far):
            pg.evaluate(f"rdSetPage({page_no})")
            pg.wait_for_timeout(120)
            r = pg.evaluate(CHECK)
            assert r["seen"] > 5 and r["worst"] <= 1.0, (vw, dpr, page_no, r)
        assert not errs, errs
        pg.close()
    br.close()
print("reader edges ok")
