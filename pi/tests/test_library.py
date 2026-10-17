"""The library (Bookworm's book tracker): Bookworm's lengths, up to 5 books on the go and 5 frozen,
joy for pages read (capped), rations, points and titles for a finished book, Want To Read,
favourites, editing, nothing during a nap, the diary in order, Open Library through the Pi
(search and covers, kept or only looked at), the web routes and the achievements."""
import asyncio
import io
import json
import os
import socket
import tempfile
import threading
import time
import urllib.request

from bt_dragon import config, library, server, tuning
from bt_dragon.app import Dragon

assert [library.length_of(p) for p in (1, 449, 450, 799, 800, 2000)] == ["short", "short", "medium", "medium", "long", "long"]
assert library.same_book({"title": "The Hobbit", "author": "J. R. R. Tolkien"}, {"title": "the hobbit!", "author": ""})
assert library.same_book({"isbn": "978-0-261-10221-7", "title": "x"}, {"isbn": "9780261102217", "title": "y"})

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
lib = app.library
act = app.library_action

# starting books: up to 5 on the go
for i in range(5):
    r = act({"action": "start", "book": {"title": f"Book {i}", "author": "A", "pages": 300 + i * 300}})
    assert r["ok"], r
assert not act({"action": "start", "book": {"title": "Six", "pages": 100}})["ok"]
assert not act({"action": "start", "book": {"title": "", "pages": 100}})["ok"]
ids = [b["id"] for b in lib.reading()]
assert [b["length"] for b in lib.reading()] == ["short", "medium", "long", "long", "long"]

# logging: joy for pages read (0.5 a page), at most 25 from one log; not backwards
app.pet.joy = 10.0
r = act({"action": "log", "id": ids[0], "value": 20})
assert r["ok"] and r["joy"] == 10 and r["pages"] == 20 and abs(app.pet.joy - 20) < 0.01
r = act({"action": "log", "id": ids[0], "value": 200})
assert r["joy"] == 25                                                         # (180 pages, capped)
assert not act({"action": "log", "id": ids[0], "value": 150})["ok"]
ev = [x[0] for x in app.store.db.execute("SELECT text FROM events WHERE kind='library' ORDER BY id")]
assert "Started reading Book 0 (300 pages)." in ev and any("Read 20 pages of Book 0 (+10 joy)" in e for e in ev)

# finishing: rations (10 for a Short book) and points, and the diary in order
app.pet.rations = 0.0
r = act({"action": "log", "id": ids[0], "value": 300})
assert r["ok"] and r["finished"]["rations"] == 10 and r["finished"]["points"] == 100
assert app.pet.rations == 10 and lib.score() == 100 and len(lib.reading()) == 4
ev = [x[0] for x in app.store.db.execute("SELECT text FROM events WHERE kind='library' ORDER BY id")]
assert ev[-2].startswith("Read 100 pages of Book 0") and ev[-1].startswith("Finished Book 0 (short, 300 pages): +10 rations"), ev[-2:]
assert "BOOK FINISHED" in app.pet.message

# by percentage: pages shared out
r = act({"action": "start", "book": {"title": "E-book", "pages": 1000, "mode": "percent"}})
eb = r and lib.reading()[-1]["id"]
r = act({"action": "log", "id": eb, "value": 2.5})
assert r["pages"] == 25 and r["joy"] == 12.5
# a Long book finished by an edit: 30 rations, 300 points; a new title (500)
r = act({"action": "edit", "id": eb, "book": {"title": "E-book", "pages": 1000, "progress": 100, "mode": "percent"}})
assert r["ok"] and r["finished"]["rations"] == 30 and lib.score() == 400
r = act({"action": "edit", "id": ids[1], "book": {"title": "Book 1", "pages": 600, "progress": 600, "mode": "pages"}})
assert lib.score() == 600 and lib.title() == "Paperback Wyrmling"
assert any("New library title: Paperback Wyrmling" in x[0] for x in app.store.db.execute("SELECT text FROM events"))
assert not act({"action": "edit", "id": ids[2], "book": {"title": "x", "pages": 10, "progress": 50, "mode": "pages"}})["ok"]

# freezing and abandoning
assert act({"action": "freeze", "id": ids[2]})["ok"] and lib.book(ids[2])["status"] == "frozen"
assert not act({"action": "log", "id": ids[2], "value": 5})["ok"]
assert act({"action": "unfreeze", "id": ids[2]})["ok"]
assert act({"action": "abandon", "id": ids[3]})["ok"] and not lib.book(ids[3])

# Want To Read: no duplicates, order, start from it
assert act({"action": "wtr_add", "book": {"title": "Dune", "author": "Frank Herbert", "pages": 600}})["ok"]
assert not act({"action": "wtr_add", "book": {"title": "dune", "author": "", "pages": 610}})["ok"]
assert act({"action": "wtr_add", "book": {"title": "Emma", "pages": 400}})["ok"]
w = {x["title"]: x["id"] for x in lib.s["wtr"]}
assert [x["title"] for x in lib.view(full=True)["wtr"]] == ["Emma", "Dune"]          # newest first
act({"action": "wtr_move", "id": w["Dune"], "dir": "up"})
assert [x["title"] for x in lib.view(full=True)["wtr"]] == ["Dune", "Emma"]
assert act({"action": "start", "book": {"title": "Dune", "pages": 600, "wtr": w["Dune"]}})["ok"]
assert [x["title"] for x in lib.s["wtr"]] == ["Emma"]
# favourites
did = lib.s["done"][0]["id"]
assert act({"action": "fav", "id": did})["ok"] and did in lib.s["favs"]
act({"action": "fav", "id": did})
assert did not in lib.s["favs"]

# napping: nothing changes
app.napping = True
assert "napping" in act({"action": "log", "id": ids[2], "value": 5})["error"]
app.napping = False

# knobs
tuning.set_value("library_rations_short", 4)
assert lib.view()["rations"]["short"] == 4
tuning.reset("all")

# achievements: books by length
achs = {a["id"]: a for a in app.achievement_list(fresh=True)}
assert achs["k-all"]["n"] == 3 and achs["k-long"]["n"] == 1 and achs["k-medium"]["n"] == 1 and achs["k-short"]["n"] == 1

# Open Library through the Pi (no real internet here)
calls = []


def fake_get(url, timeout=12):
    calls.append(url)
    if "/isbn/" in url:
        return {"title": "The Hobbit", "authors": [{"key": "/authors/OL1A"}], "number_of_pages": 310,
                "covers": [-1, 123], "publish_date": "1995"}
    if "/authors/" in url:
        return {"name": "J. R. R. Tolkien"}
    return {"docs": [{"title": "the hobbit", "author_name": ["J. R. R. Tolkien"], "isbn": ["123", "9780261102217"],
                      "number_of_pages_median": 300, "cover_i": 77, "first_publish_year": 1937, "edition_count": 400}]}


lib._get_json = fake_get
r = lib.search("9780261102217")
assert r[0]["pages"] == 310 and r[0]["cover"] == 123 and r[0]["author"] == "J. R. R. Tolkien" and r[0]["edition"]
r = lib.search("hobbit")
assert r[0]["isbn"] == "9780261102217" and r[0]["cover"] == 77 and "search.json" in calls[-1]

JPEG = b"\xff\xd8\xff\xe0 a picture"
real_open = urllib.request.urlopen
urllib.request.urlopen = lambda req, timeout=12: io.BytesIO(JPEG)
try:
    assert lib.cover("77", keep=False) == JPEG and not os.path.exists(os.path.join(lib.cover_dir, "77.jpg"))
    assert lib.cover("77") == JPEG and os.path.exists(os.path.join(lib.cover_dir, "77.jpg"))
    assert lib.cover("../x") is None
finally:
    urllib.request.urlopen = real_open

# the web routes
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
app.cfg["link"]["web_port"] = port
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
base = f"http://127.0.0.1:{port}"
page = urllib.request.urlopen(base + "/library", timeout=20).read().decode()
assert "Open Library" in page and "Want To Read" in page
d = json.loads(urllib.request.urlopen(base + "/api/library", timeout=20).read())
assert d["name"] == "Harald" and d["done"] and d["titles"][0]["name"] == "Dog-Eared Drakeling"
req = urllib.request.Request(base + "/api/library", data=json.dumps({"action": "log", "id": ids[2], "value": 10}).encode(),
                             headers={"Origin": base, "Content-Type": "application/json"})
assert json.loads(urllib.request.urlopen(req, timeout=20).read())["ok"]
img = urllib.request.urlopen(base + "/api/library/cover/77.jpg", timeout=20)
assert img.read() == JPEG and img.headers["Content-Type"] == "image/jpeg"
den = urllib.request.urlopen(base + "/", timeout=20).read().decode()
assert "Open the Library" in den and "Literary Treasures" in den
st = json.loads(urllib.request.urlopen(base + "/api/status", timeout=20).read())
assert st["library"]["reading"] and st["library"]["rations"]["long"] == 30
print("test_library: OK")
