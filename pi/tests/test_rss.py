"""RSS feeds: RSS 2.0, RSS 1.0 and Atom parsed; adding marks what's there as seen; new items
are queued for his screen ("RSS SOURCE TITLE") and said ("New RSS for Source. Title.") when
the RSS tick box is on; a flood is "and N more"; the list holds 50; the Den has the subsection."""
import asyncio
import os
import tempfile
import time

from bt_dragon import config, rss, tuning
from bt_dragon.app import Dragon
from bt_dragon.store import Store

RSS2 = """<?xml version="1.0"?><rss version="2.0"><channel><title>Example News - Home</title>
<item><title>Storm warning for the coast</title><guid>a1</guid></item>
<item><title>Library opens late on &lt;b&gt;Thursdays&lt;/b&gt;</title><link>https://example.com/2</link></item>
</channel></rss>"""
ATOM = """<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>A Blog</title>
<entry><title>Hello world</title><id>tag:x,2026:1</id><link href="https://blog/1"/></entry></feed>"""
RDF = """<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/">
<channel><title>Old Style</title></channel><item><title>One</title><link>https://o/1</link></item></rdf:RDF>"""
BOMB = """<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><rss><channel><title>&b;</title></channel></rss>"""

t, items = rss.parse(RSS2)
assert t == "Example News - Home" and [i["title"] for i in items] == ["Storm warning for the coast", "Library opens late on Thursdays"]
assert rss.parse(ATOM)[0] == "A Blog" and rss.parse(ATOM)[1][0]["title"] == "Hello world"
assert rss.parse(RDF)[0] == "Old Style" and rss.parse(RDF)[1][0]["title"] == "One"
for bad in (BOMB, "<html><body>hi</body></html>", "not xml at all"):
    try:
        rss.parse(bad)
        raise AssertionError(bad[:20])
    except ValueError:
        pass
assert rss.short_source("Example News - Home of the latest") == "Example News"
assert rss.clean_url("feed://example.com/rss") == "https://example.com/rss"
for bad in ("javascript:alert(1)", "file:///etc/passwd", "example"):
    try:
        rss.clean_url(bad)
        raise AssertionError(bad)
    except ValueError:
        pass

# a feed list
pages = {"https://example.com/rss": RSS2}
tmp = tempfile.mkdtemp()
f = rss.Feeds(Store(os.path.join(tmp, "r.db")), fetch_fn=lambda u, timeout=20: pages[u].encode())
assert f.add("https://example.com/rss") == "Example News - Home"
try:
    f.add("https://example.com/rss")
    raise AssertionError("twice")
except ValueError:
    pass
assert f.check() == []                                       # nothing new: what was there is seen
pages["https://example.com/rss"] = RSS2.replace("<item>", "<item><title>Brand new</title><guid>n1</guid></item><item>", 1)
news = f.check()
assert news == [("Example News - Home", ["Brand new"], 0)], news
assert f.view()[0]["last"] == "Brand new"
assert f.check() == []
# a flood: the newest three, and the rest counted
pages["https://example.com/rss"] = RSS2.replace(
    "<item>", "".join(f"<item><title>Item {k}</title><guid>f{k}</guid></item>" for k in range(10)) + "<item>", 1)
news = f.check()
assert news[0][1] == ["Item 0", "Item 1", "Item 2"] and news[0][2] == 7
# a feed that stops working keeps its place, with the reason
pages["https://example.com/rss"] = "<html>gone</html>"
assert f.check() == [] and "not a feed" in f.view()[0]["error"]
# the limit
for k in range(rss.MAX_FEEDS - 1):
    pages[f"https://e{k}.com/rss"] = ATOM
    f.add(f"https://e{k}.com/rss")
pages["https://full.com/rss"] = ATOM
try:
    f.add("https://full.com/rss")
    raise AssertionError("51")
except ValueError as e:
    assert "full" in str(e)
assert f.remove("https://e0.com/rss") and not f.remove("https://e0.com/rss") and len(f.view()) == rss.MAX_FEEDS - 1
# when it's due: on the clock, each feed at its own interval (20 minutes to start with)
import datetime
assert tuning.get("rss_minutes") == 20
at = lambda h, m, sec=0: time.mktime(datetime.datetime(2026, 10, 22, h, m, sec).timetuple())   # noqa: E731
g = rss.Feeds(Store(os.path.join(tmp, "r2.db")), fetch_fn=lambda u, timeout=20: pages[u].encode())
pages["https://a.com/rss"] = pages["https://b.com/rss"] = ATOM
g.add("https://a.com/rss"); g.add("https://b.com/rss")
assert [x["every"] for x in g.view()] == [20, 20]
g._slots = {}
assert g.due(at(6, 1)) == []                                      # (after a restart: wait for the next)
assert g.due(at(6, 5)) == [] and g.due(at(6, 19, 59)) == []
assert [f["url"] for f in g.due(at(6, 20, 3))] == ["https://a.com/rss", "https://b.com/rss"]
assert g.due(at(6, 20, 30)) == []                                 # once per stretch
assert len(g.due(at(6, 40))) == 2 and len(g.due(at(7, 0))) == 2
# its own number: every 30 minutes -> on the hour and half past; every 90 -> 7:30, 9:00...
assert g.set_every("https://b.com/rss", 30) is None and g.view()[1]["every"] == 30
assert g.set_every("https://b.com/rss", 5) and g.set_every("https://b.com/rss", 2000) and g.set_every("https://x.com", 30)
due = lambda h, m: [f["url"][8] for f in g.due(at(h, m))]          # noqa: E731
assert due(7, 20) == ["a"] and due(7, 30) == ["b"] and due(7, 40) == ["a"] and due(8, 0) == ["a", "b"]
assert g.set_every("https://a.com/rss", 90) is None
assert due(8, 30) == ["b"] and due(9, 0) == ["a", "b"]
# only the due ones are fetched
fetched = []
g.fetch = lambda u, timeout=20: (fetched.append(u), pages[u].encode())[1]
g.check(feeds=[g.s["feeds"][1]])
assert fetched == ["https://b.com/rss"]
assert tuning.set_value("rss_minutes", 5) and tuning.set_value("rss_minutes", 45) is None
tuning.reset()

# in the app: queued, shown and said
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
said = []
bigs = []
app.dot.news = lambda text, big=False: (said.append(text), bigs.append(big))
app.rss_news([("Example News", ["Brand new", "Older one"], 2)])
shown = []
for _ in range(10):
    app.pet.message_ts = 0
    app._garden_tick()
    if app.pet.message and (not shown or shown[-1] != app.pet.message):
        shown.append(app.pet.message)
assert shown[0].startswith("RSS EXAMPLE NEWS OLDER ONE") and shown[1].startswith("RSS EXAMPLE NEWS BRAND NEW"), shown
assert "+2 MORE" in shown[2], shown
assert said == ["New RSS for Example News. Older one.", "New RSS for Example News. Brand new.",
                "And 2 more new from Example News."], said
assert all(bigs)                                                  # (said with "Big moments" too)
# a long title: as much as fits
from bt_dragon.fonts import text_width
from bt_dragon.pet import STATUS_W
app.rss_news([("Example News", ["A very long headline about the council meeting that went on for hours and hours"], 0)])
app.pet.message_ts = 0
app._garden_tick()
assert app.pet.message.startswith("RSS EXAMPLE NEWS A VERY") and text_width(app.pet.message) <= STATUS_W
# the tick box off: on screen, not said
said.clear()
app.dot.s["say_rss"] = False
app.rss_news([("Example News", ["Quiet one"], 0)])
app.pet.message_ts = 0
app._garden_tick()
assert "QUIET ONE" in app.pet.message and not said
# the commands
app.rss.fetch = lambda u, timeout=20: RSS2.encode()
run = lambda c: asyncio.run(app.command(c))  # noqa: E731
assert run("RSSADD https://example.com/rss")[0] == "OK Example News - Home"
assert run("RSSADD nonsense")[0].startswith("ERR")
lines = run("RSS")
assert lines[0].startswith("feeds=") and "example.com" in lines[0] and "max=50" in lines
assert run("RSSEVERY 45 https://example.com/rss") == ["OK"] and app.rss.view()[-1]["every"] == 45
assert run("RSSEVERY 3 https://example.com/rss")[0].startswith("ERR")
assert run("RSSDEL https://example.com/rss") == ["OK"]

den = open(os.path.join(os.path.dirname(__file__), "..", "bt_dragon", "den.html"), encoding="utf-8").read()
assert 'id="rssBox"' in den and 'id="say_rss"' in den and "rssAdd()" in den and "data-every" in den and "RSSEVERY" in den
print("rss ok")
