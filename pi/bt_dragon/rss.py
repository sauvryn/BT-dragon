"""
RSS feeds: news from websites you choose, on Harald's screen and said out loud.
"RSS BBC NEWS STORM WARNING FOR.."  /  "New RSS for BBC News. Storm warning for the coast."

What a feed is: many websites publish a small file listing their newest articles, podcast
episodes or posts, newest first: a title, a link and an ID for each. It's called a feed (RSS,
or its younger cousin Atom; both are XML). Anything that reads it, a "feed reader", just
fetches that file now and then and shows whatever wasn't there last time. That's all
Harald does: on the clock, each feed every so many minutes (its own number in the Den; 20 to
start with, Developer Tools → Detection), the Pi fetches it over your phone's hotspot like
everything else and compares the items' IDs with the ones it has seen. The minutes are
counted from midnight, so every 20 means 6:00, 6:20, 6:40 and so on, every 30 means on the
hour and half past.

When you add a feed, everything already in it is marked as seen, so the first thing you
hear is the next new one, not the last twenty. If a lot arrive at once (a website catching
up, or the Pi was off for a day), he says the newest few and "and 12 more".

Privacy: each website sees a request for its feed from your phone's internet address, the
same as if your phone's feed reader had asked. Nothing about you is sent. The Pi keeps the
feeds' addresses and names, and the IDs of the items it has seen (not the articles).

Safety: only http:// and https:// addresses; at most 2 MB a feed; an XML file that defines
its own entities (the "billion laughs" trick, which makes a tiny file expand to gigabytes
when read) is refused rather than read.
"""
import hashlib
import html
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import __version__, tuning

log = logging.getLogger("rss")

MAX_FEEDS = 50
EVERY_MIN, EVERY_MAX = 10, 1440        # a feed's own check, in minutes (at most once a day)
MAX_BYTES = 2_000_000
SEEN_KEEP = 300            # item IDs remembered per feed (a feed shows its newest 10 to 100)
SAY_AT_ONCE = 3            # new items said per feed per check; the rest are "and N more"
USER_AGENT = f"BTDragon/{__version__} (https://github.com/sauvryn/BT-dragon; feed reader)"
KEY = "rss"


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el):
    if el is None:
        return ""
    t = "".join(el.itertext())
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))       # (some feeds put HTML in titles)
    return re.sub(r"\s+", " ", t).strip()


def parse(data):
    """(feed title, [items, newest first]) from an RSS 2.0, RSS 1.0 (RDF) or Atom file.
    Each item: {"id", "title"}. Raises ValueError if it isn't a feed."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    head = data[:4096].upper()
    if b"<!ENTITY" in head or b"<!ENTITY" in data.upper():
        raise ValueError("this file defines its own XML entities, so it isn't read (a safety rule)")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise ValueError("not a feed (it isn't XML: is it the website's page rather than its feed?)")
    kind = _local(root.tag)
    if kind == "rss":
        chan = _child(root, "channel")
        if chan is None:
            raise ValueError("an RSS file with no channel")
        title = _text(_child(chan, "title"))
        entries = [e for e in chan if _local(e.tag) == "item"]
    elif kind == "rdf":
        chan = _child(root, "channel")
        title = _text(_child(chan, "title")) if chan is not None else ""
        entries = [e for e in root if _local(e.tag) == "item"]
    elif kind == "feed":
        title = _text(_child(root, "title"))
        entries = [e for e in root if _local(e.tag) == "entry"]
    else:
        raise ValueError("not a feed (no RSS or Atom inside)")
    items = []
    for e in entries:
        t = _text(_child(e, "title"))
        link = _child(e, "link")
        href = (link.get("href") or _text(link)) if link is not None else ""
        ident = _text(_child(e, "guid")) or _text(_child(e, "id")) or href or t
        if not (t or ident):
            continue
        items.append({"id": hashlib.sha1(ident.encode("utf-8")).hexdigest()[:16], "title": t or "(untitled)"})
    return title, items


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("the feed is over 2 MB")
    return data


def clean_url(url):
    url = (url or "").strip()
    if url.lower().startswith("feed:"):              # (feed:https://... and feed://...)
        url = url[5:].lstrip("/") if url[5:].startswith("//") else url[5:]
        if not url.lower().startswith("http"):
            url = "https://" + url
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc or len(url) > 1000:
        raise ValueError("that isn't a web address (it should start with https://)")
    return url


def short_source(name):
    """A feed's own title can be long ("BBC News - Home"): the part before a separator."""
    name = re.sub(r"\s+", " ", name or "").strip()
    for sep in (" - ", " | ", " – ", " — ", ": "):
        if sep in name and len(name) > 24:
            name = name.split(sep)[0].strip()
    return name[:60] or "a feed"


class Feeds:
    def __init__(self, store, fetch_fn=None):
        self.store = store
        self.fetch = fetch_fn or fetch
        self.s = store.get(KEY) or {}
        self.s.setdefault("feeds", [])
        self.last_check = 0.0
        self._slots = {}                  # url -> the stretch of the clock it was last checked in

    def save(self):
        self.store.put(KEY, self.s)

    def view(self):
        return [{"url": f["url"], "name": f.get("name") or "", "last": f.get("last_title") or "",
                 "last_ts": f.get("last_ts"), "error": f.get("error") or "", "every": self.every(f)}
                for f in self.s["feeds"]]

    @staticmethod
    def every(f):
        return int(f.get("every") or tuning.get("rss_minutes") or 20)

    def set_every(self, url, minutes):
        """A feed's own check, every `minutes` (10 to 1,440). Returns an error, or None."""
        try:
            m = int(float(minutes))
        except (TypeError, ValueError):
            return "a number of minutes"
        if not EVERY_MIN <= m <= EVERY_MAX:
            return f"{EVERY_MIN} to {EVERY_MAX} minutes"
        for f in self.s["feeds"]:
            if f["url"] == url:
                f["every"] = m
                self._slots.pop(url, None)               # (counted afresh: it waits for its next stretch)
                self.save()
                return None
        return "not on the list"

    def add(self, url):
        """Fetches it once (so a wrong address is caught now) and marks everything in it as seen.
        Returns the feed's name. Raises ValueError with a reason to show."""
        url = clean_url(url)
        if any(f["url"] == url for f in self.s["feeds"]):
            raise ValueError("that feed is already on the list")
        if len(self.s["feeds"]) >= MAX_FEEDS:
            raise ValueError(f"the list is full ({MAX_FEEDS} feeds): remove one first")
        try:
            title, items = parse(self.fetch(url))
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"couldn't fetch it ({_why(e)})")
        name = short_source(title or urllib.parse.urlparse(url).netloc)
        self.s["feeds"].append({"url": url, "name": name, "added": time.time(), "every": int(tuning.get("rss_minutes") or 20),
                                "seen": [i["id"] for i in items][:SEEN_KEEP],
                                "last_title": items[0]["title"] if items else "", "last_ts": None, "error": ""})
        self.save()
        return name

    def remove(self, url):
        n = len(self.s["feeds"])
        self.s["feeds"] = [f for f in self.s["feeds"] if f["url"] != url]
        if len(self.s["feeds"]) != n:
            self.save()
            return True
        return False

    @staticmethod
    def slot(every, now=None):
        """Which stretch of the clock it is, counted from midnight on the Pi's own clock: every 20
        minutes, 6:00-6:19 is one stretch and 6:20-6:39 the next, so checks fall on 6:00, 6:20, 6:40."""
        t = time.localtime(now or time.time())
        return (t.tm_year, t.tm_yday, (t.tm_hour * 60 + t.tm_min) // max(1, every))

    def due(self, now=None):
        """The feeds whose next stretch of the clock has started since they were last checked.
        (After a restart, each one waits for its next: 6:20, say.)"""
        out = []
        for f in self.s["feeds"]:
            sl = self.slot(self.every(f), now)
            if f["url"] not in self._slots:
                self._slots[f["url"]] = sl
            elif self._slots[f["url"]] != sl:
                self._slots[f["url"]] = sl
                out.append(f)
        return out

    def check(self, now=None, feeds=None):
        """Fetches the feeds (all of them, or `feeds`; blocking: run it in a thread). Returns
        [(name, [new titles, newest first], how many more)] for the ones with something new."""
        now = now or time.time()
        self.last_check = now
        news = []
        for f in list(feeds if feeds is not None else self.s["feeds"]):
            try:
                _, items = parse(self.fetch(f["url"]))
                f["error"] = ""
            except Exception as e:
                f["error"] = _why(e)
                continue
            seen = set(f.get("seen") or [])
            new = [i for i in items if i["id"] not in seen]
            if new:
                f["seen"] = ([i["id"] for i in new] + (f.get("seen") or []))[:SEEN_KEEP]
                f["last_title"], f["last_ts"] = new[0]["title"], now
                news.append((f["name"], [i["title"] for i in new[:SAY_AT_ONCE]], max(0, len(new) - SAY_AT_ONCE)))
        self.save()
        return news


def _why(e):
    if isinstance(e, urllib.error.HTTPError):
        return f"the website said {e.code}"
    if isinstance(e, ValueError):
        return str(e)
    return "no answer: no internet, or the website is down" if "timed out" in str(e) or isinstance(
        e, (urllib.error.URLError, OSError)) else str(e)[:80]
