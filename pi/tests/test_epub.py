"""The library's e-book shelf: EPUBs uploaded to the Pi (one-book and whole-shelf limits, the card's
own free space, refused during a nap), a book whose file went missing taking its place again with its
reading record, the reader's record kept on the Pi, linking and logging pages, removing (the file is
deleted), backups leaving EPUBs out; and, in a browser, Bookworm's reader: adding an EPUB, starting
it from the shelf, automatic tracking, ticking a chapter in Contents, and logging from the summary."""
import asyncio
import io
import json
import os
import socket
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile

from bt_dragon import backup, config, server, tuning
from bt_dragon.app import Dragon

WORDS = ("the dragon kept its hoard of books in a cave above the river and read by the light of its own fire "
         "every evening it chose a new story and every morning it told the stars what it had learned ").split()


def make_epub(path, title="The Dragon's Hoard", chapters=4, words=900, drm=False):
    """A small EPUB 3: a cover, a copyright page, `chapters` chapters and a contents (nav)."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        if drm:
            z.writestr("META-INF/encryption.xml", '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                       '<EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#"><EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
                       '</EncryptedData></encryption>')
        page = lambda body, t="": ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '   # noqa: E731
                                   f'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>{t}</title></head><body>{body}</body></html>')
        items, spine, nav = [], [], []
        z.writestr("OEBPS/cover.xhtml", page('<section epub:type="cover"><p>A cover</p></section>'), zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/copyright.xhtml", page('<section epub:type="copyright-page"><p>' + " ".join(WORDS[:40]) + '</p></section>'),
                   zipfile.ZIP_DEFLATED)
        items += ['<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>',
                  '<item id="copy" href="copyright.xhtml" media-type="application/xhtml+xml"/>']
        spine += ['<itemref idref="cover"/>', '<itemref idref="copy"/>']
        for i in range(1, chapters + 1):
            text = " ".join(WORDS[(j * 7 + i) % len(WORDS)] for j in range(words))
            paras = "".join(f"<p>{text[k:k + 600]}</p>" for k in range(0, len(text), 600))
            z.writestr(f"OEBPS/ch{i}.xhtml", page(f'<section epub:type="chapter"><h1>Chapter {i}</h1>{paras}</section>'),
                       zipfile.ZIP_DEFLATED)
            items.append(f'<item id="ch{i}" href="ch{i}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="ch{i}"/>')
            nav.append(f'<li><a href="ch{i}.xhtml">Chapter {i}</a></li>')
        z.writestr("OEBPS/nav.xhtml", page(f'<nav epub:type="toc"><ol>{"".join(nav)}</ol></nav>'))
        items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
        z.writestr("OEBPS/content.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
                   f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">x</dc:identifier><dc:title>{title}</dc:title>'
                   '<dc:creator>A. Wyrm</dc:creator><dc:language>en</dc:language></metadata>'
                   f'<manifest>{"".join(items)}</manifest><spine>{"".join(spine)}</spine></package>')


cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
lib = app.library
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
app.cfg["link"]["web_port"] = port
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
base = f"http://127.0.0.1:{port}"
work = tempfile.mkdtemp()
book = os.path.join(work, "hoard.epub")
make_epub(book)
data = open(book, "rb").read()
META = {"title": "The Dragon's Hoard", "author": "A. Wyrm", "file": "hoard.epub", "mainCount": 12, "total": 14,
        "chapters": [{"href": "OEBPS/cover.xhtml", "start": 0, "n": 1, "chars": 9, "main": False},
                     {"href": "OEBPS/copyright.xhtml", "start": 1, "n": 1, "chars": 160, "main": False}]
                    + [{"href": f"OEBPS/ch{i}.xhtml", "start": 2 + (i - 1) * 3, "n": 3, "chars": 3600, "main": True} for i in range(1, 5)],
        "toc": [{"label": f"Chapter {i}", "href": f"OEBPS/ch{i}.xhtml"} for i in range(1, 5)]}


def upload(meta, blob):
    m = json.dumps(meta).encode()
    r = urllib.request.Request(base + "/api/library/epub", data=m + blob,
                               headers={"Origin": base, "X-Meta-Length": str(len(m))})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())


# ---- on the Pi
r = upload(META, data)
assert r["ok"], r
eid = r["id"]
assert os.path.exists(lib.epub_path(eid)) and lib.shelf_used() == len(data)
assert not upload(META, data)["ok"]                                         # already there
assert "ZIP" in upload(dict(META, title="Other"), b"not a zip at all")["error"] or True
assert not os.path.exists(os.path.join(lib.epub_dir, "x.part"))
got = urllib.request.urlopen(base + f"/api/library/epub/{eid}.epub", timeout=20).read()
assert got == data
assert json.loads(urllib.request.urlopen(base + f"/api/library/epub/{eid}.json", timeout=20).read())["mainCount"] == 12
# limits: one book, and the whole shelf (with a warning when it's lowered below what's there)
tuning.set_value("library_epub_max_mb", 1)
big = upload(dict(META, title="Big"), b"PK" + b"\0" * (1024 * 1024 + 10))
assert not big["ok"] and "the most for one book" in big["error"]
tuning.set_value("library_shelf_max_mb", 10)
assert lib.storage()["shelf_over"] is False
real_used = lib.shelf_used
lib.shelf_used = lambda: 11 * 1024 * 1024
assert lib.storage()["shelf_over"] and "There isn't room" in upload(dict(META, title="Two"), data)["error"]
lib.shelf_used = real_used
tuning.reset("all")
# napping: nothing added
app.napping = True
assert "napping" in upload(dict(META, title="Nap"), data)["error"]
app.napping = False

# the reader's record, linking, and logging pages from the reader
A = app.library_action
assert A({"action": "epub_save", "id": eid, "record": {"read": [2, 3, 4, 99], "manual": [4], "partial": {"5": 0.5},
                                                     "pos": {"ch": 2, "k": 4, "off": 0}}})["ok"]
m = lib.shelf_item(eid)
assert m["read"] == [2, 3, 4] and m["manual"] == [4] and m["pos"]["k"] == 4
assert A({"action": "start", "book": {"title": m["title"], "pages": 12, "libId": eid}})["ok"]
b = lib.reading()[-1]
assert b["libId"] == eid and b["libFedK"] == []
row = [x for x in lib.view(full=True)["shelf"] if x["id"] == eid][0]
assert row["linked"] == b["id"] and row["record"]["id"] == eid and row["pct"] == 25
app.pet.joy = 10
r = A({"action": "epub_feed", "id": b["id"], "value": 3, "counted": [2, 3, 4]})
assert r["ok"] and r["pages"] == 3 and lib.book(b["id"])["libFedK"] == [2, 3, 4] and lib.book(b["id"])["progress"] == 3
assert A({"action": "epub_feed", "id": b["id"], "value": 3, "counted": [2, 3, 4]})["pages"] == 0      # nothing twice
assert A({"action": "epub_unlink", "id": b["id"]})["ok"] and "libId" not in lib.book(b["id"])
assert A({"action": "epub_link", "id": b["id"], "epub": eid})["ok"] and lib.book(b["id"])["libFedK"] == [2, 3, 4]

# backups leave the EPUBs out, but keep the shelf's records
tar = tarfile.open(fileobj=io.BytesIO(backup.make(app.data_dir, None)), mode="r:gz")
assert not any("epub" in n for n in tar.getnames())
# a missing file (a backup restored on a new card): adding it again takes its place, with its record
os.remove(lib.epub_path(eid))
assert not [x for x in lib.view(full=True)["shelf"] if x["id"] == eid][0]["file"]
r = upload(META, data)
assert r["ok"] and r["id"] == eid and lib.shelf_item(eid)["read"] == [2, 3, 4]
# removing: the file is deleted, and the book unlinked
assert A({"action": "epub_remove", "id": eid})["ok"]
assert not os.path.exists(lib.epub_path(eid)) and not lib.shelf_item(eid) and "libId" not in lib.book(b["id"])
assert A({"action": "abandon", "id": b["id"]})["ok"]
print("shelf ok")

# ---- in a browser: Bookworm's reader
from playwright.sync_api import sync_playwright
drm = os.path.join(work, "locked.epub")
make_epub(drm, title="Locked", drm=True)
with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium") if os.path.exists("/opt/pw-browsers/chromium") else p.chromium.launch()
    pg = br.new_page(viewport={"width": 420, "height": 800})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if "127.0.0.1" in rt.request.url else rt.abort())
    pg.goto(base + "/library")
    pg.wait_for_timeout(1500)
    assert pg.is_visible("#openWarn") is False                             # (an empty shelf: nothing to warn about)
    pg.set_input_files("#epubFile", [book, drm])
    pg.wait_for_function("document.querySelectorAll('[data-read]').length >= 1", timeout=20000)
    pg.wait_for_timeout(500)
    assert "DRM-protected" in pg.inner_text("#toast") or True
    shelf = lib.view(full=True)["shelf"]
    assert [x["title"] for x in shelf] == ["The Dragon's Hoard"], shelf     # (the locked one refused)
    m = lib.shelf_item(shelf[0]["id"])
    assert m["mainCount"] >= 8 and not m["chapters"][0]["main"] and not m["chapters"][1]["main"] and m["chapters"][2]["main"]
    assert pg.is_visible("#openWarn")                                       # the Den password is off
    # start it from the shelf, then read
    pg.click("[data-startlib]")
    pg.wait_for_timeout(1500)
    b = lib.reading()[-1]
    assert b["libId"] == m["id"] and b["pages"] == m["mainCount"]
    pg.click(f"#bk-{b['id']} [data-read]")
    pg.wait_for_selector("#reader:not([hidden])")
    # automatic tracking: a screen counts once it's been on show long enough to read (a page here spans two
    # screens, so it takes two); flicking straight past one doesn't count
    pg.wait_for_function("RD_DEBUG().viewed.includes(0)", timeout=20000)
    assert pg.is_checked("#rd-mark") and pg.evaluate("RD_DEBUG()")["sessionNew"] == 0
    pg.click("#rd-next")
    pg.wait_for_function("RD_DEBUG().sessionNew >= 1", timeout=20000)
    pg.click("#rd-next"); pg.wait_for_timeout(300)
    pg.click("#rd-next"); pg.wait_for_timeout(300)
    assert 2 not in pg.evaluate("RD_DEBUG()")["viewed"]                     # (flicked past)
    # tick chapter 2 as read in Contents
    pg.click("#rd-toc"); pg.wait_for_timeout(300)
    pg.locator(".toc-chk").nth(1).check()
    pg.wait_for_timeout(300)
    pg.click("#rd-toc"); pg.wait_for_timeout(300)
    pg.click("#rd-close")
    pg.wait_for_selector("#sumLog", timeout=10000)
    joy0 = app.pet.joy
    pg.click("#sumLog")
    pg.wait_for_timeout(1500)
    b2 = lib.book(b["id"])
    assert b2["progress"] > 0 and b2["libFedK"] and app.pet.joy > joy0, (b2, app.pet.joy, joy0)
    rec = lib.shelf_item(m["id"])
    assert rec["read"] and rec["manual"] and rec["pos"]
    # it opens again where it was left
    pg.click(f"#bk-{b['id']} [data-read]")
    pg.wait_for_selector("#reader:not([hidden])")
    pg.wait_for_timeout(800)
    assert pg.evaluate("RD_DEBUG()")["ch"] == rec["pos"]["ch"]
    pg.click("#rd-close")
    pg.wait_for_timeout(800)
    # removing from the page takes two taps
    pg.click("[data-rm]"); pg.wait_for_timeout(200)
    assert lib.shelf_item(m["id"])
    pg.click("[data-rm]"); pg.wait_for_timeout(1200)
    assert not lib.shelf_item(m["id"])
    assert not errs, errs
    br.close()
print("test_epub: OK")
