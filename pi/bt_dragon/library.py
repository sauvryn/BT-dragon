"""
The library: Harald's hoard of literary treasures (Den → the library section, and the Library page).

Dragons guard treasure. Harald's is knowledge: the books you read. This is Bookworm's book tracker,
brought over and changed for BT Dragon. Instead of each book raising an insect, reading feeds
Harald:
  - logging your progress ("I'm now on page 120") brings him joy, for the pages read
    (Developer Tools → Joy: "Library: joy for each page read", at most "Library: most joy from
    one log");
  - finishing a book earns rations, by its length (Developer Tools → Food: "Library: rations
    for a Short / Medium / Long book": 10, 20 and 30). A ration fills his PACK when you give it
    (see pet.give_ration), so a finished book is food for the lean days;
  - and points towards the library's titles, as in Bookworm: 100 for a Short book, 200 for a
    Medium one and 300 for a Long one, with Bookworm's thresholds and titles of its own.

As in Bookworm:
  - a book's length is its page count: Short under 450 pages, Medium 450 to 799, Long 800 or more;
  - up to 5 books on the go, and up to 5 frozen (paused, to come back to);
  - progress by page number, or by percentage (for an e-book), switchable when editing;
  - abandoning a book takes it off the shelf (nothing is earned for it);
  - a Want To Read list, with its own order, and Completed Books, with favourites;
  - books are found on Open Library (openlibrary.org), by title, author or ISBN. Here Harald
    looks them up (and fetches their covers, which he keeps), so the Den's pages never talk to
    any other website themselves, and covers still show without the internet.

Everything is kept in Harald's database, so it's in his backups, and the same on every phone or
computer you open the Den on. Nothing changes during a nap (nothing is written to the card).
"""
import json
import logging
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

from . import tuning

log = logging.getLogger("library")

MAX_CURRENT, MAX_FROZEN, MAX_WTR = 5, 5, 200
LENGTHS = (("short", "Short", 0), ("medium", "Medium", 450), ("long", "Long", 800))
POINTS = {"short": 100, "medium": 200, "long": 300}
# Bookworm's points for each title, with names of a dragon and its books
TITLES = [(0, "l0", "Dog-Eared Drakeling"), (500, "l1", "Paperback Wyrmling"),
          (1500, "l2", "Chapter-Chasing Whelp"), (3000, "l3", "Bookmark-Bearing Drake"),
          (5000, "l4", "Hardback Hoarder"), (8000, "l5", "Wyvern of the Written Word"),
          (12000, "l6", "Scroll-Guarding Serpent"), (17000, "l7", "Lindworm of the Library"),
          (23000, "l8", "Beowulf's Bookish Foe"), (30000, "l9", "Grimoire-Guarding Wyrm"),
          (40000, "l10", "Lore-Laden Elder Wyrm"), (55000, "l11", "Dragon of a Thousand Tales"),
          (75000, "l12", "Hoard-Ruler of the Endless Library")]
OL = "https://openlibrary.org"
COVERS = "https://covers.openlibrary.org/b/id/{}-M.jpg"
UA = "BT-Dragon (https://github.com/sauvryn/BT-dragon)"
OL_FIELDS = "key,title,author_name,isbn,number_of_pages_median,cover_i,first_publish_year,edition_count"


def length_of(pages):
    """'short', 'medium' or 'long', by Bookworm's page counts."""
    k = "short"
    for key, _, at in LENGTHS:
        if (pages or 0) >= at:
            k = key
    return k


LENGTH_NAME = {k: n for k, n, _ in LENGTHS}


def rations_for(length):
    return int(round(tuning.get("library_rations_" + length)))


def iso(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t or time.time()))


def _clean(s, n=300):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def same_book(a, b):
    """Bookworm's rule: the same ISBN, or the same title and author (or one author blank)."""
    if a.get("isbn") and b.get("isbn") and norm(a["isbn"]) == norm(b["isbn"]):
        return True
    return norm(a.get("title")) == norm(b.get("title")) and (
        not norm(a.get("author")) or not norm(b.get("author")) or norm(a.get("author")) == norm(b.get("author")))


class Library:
    def __init__(self, store, data_dir=None):
        self.store = store
        self.s = store.get("library") or {}
        for k, v in (("books", []), ("wtr", []), ("done", []), ("titles", {}), ("favs", []), ("shelf", [])):
            self.s.setdefault(k, v)
        self.cover_dir = os.path.join(data_dir, "covers") if data_dir else None
        self.epub_dir = os.path.join(data_dir, "epubs") if data_dir else None
        self.on_event = None        # (kind, info) -> the app: "finish", "title"

    def save(self):
        self.store.put("library", self.s)

    # ---- looking things up
    def book(self, bid):
        return next((b for b in self.s["books"] if b["id"] == bid), None)

    def reading(self):
        return [b for b in self.s["books"] if b["status"] == "reading"]

    def frozen(self):
        return [b for b in self.s["books"] if b["status"] == "frozen"]

    @staticmethod
    def pct(b):
        if b["mode"] == "pages":
            return min(100.0, b["progress"] / max(1, b["pages"]) * 100)
        return min(100.0, float(b["progress"]))

    def score(self):
        return sum(d.get("points", 0) for d in self.s["done"])

    def title(self):
        s = self.score()
        return [t for t in TITLES if s >= t[0]][-1][2]

    def next_title(self):
        s = self.score()
        return next(((n, name) for n, _, name in TITLES if n > s), None)

    def counts(self):
        """Books finished, by length (for the achievements)."""
        out = {"short": 0, "medium": 0, "long": 0}
        for d in self.s["done"]:
            out[d.get("length") or length_of(d.get("pages"))] += 1
        return out

    def where(self, book):
        """Where a book already is (re-reading is allowed: the Library page only asks)."""
        if any(same_book(b, book) for b in self.s["books"]):
            return "shelf"
        if any(same_book(d, book) for d in self.s["done"]):
            return "done"
        if any(same_book(w, book) for w in self.s["wtr"]):
            return "wtr"
        return None

    # ---- changes (each returns (error or None, result))
    @staticmethod
    def _book_in(d):
        title, pages = _clean(d.get("title")), d.get("pages")
        try:
            pages = int(round(float(pages)))
        except (TypeError, ValueError):
            pages = 0
        if not title or pages <= 0 or pages > 20000:
            return None
        cover = d.get("cover")
        cover = int(cover) if str(cover or "").isdigit() else None
        return {"title": title, "author": _clean(d.get("author"), 200), "isbn": _clean(d.get("isbn"), 20),
                "pages": pages, "cover": cover}

    def start(self, d, now=None):
        """Starts a book (from the search, typed in, or from Want To Read with `wtr`)."""
        now = now or time.time()
        if len(self.reading()) >= MAX_CURRENT:
            return f"You're reading {MAX_CURRENT} books. Finish, freeze or abandon one first.", None
        bk = self._book_in(d)
        if not bk:
            return "Add a title and the number of pages", None
        mode = "percent" if d.get("mode") == "percent" else "pages"
        b = dict(bk, id="b%x%04x" % (int(now * 1000), len(self.s["books"]) + len(self.s["done"])), mode=mode,
                 progress=0, started=now, status="reading", length=length_of(bk["pages"]))
        if d.get("wtr"):
            self.s["wtr"] = [w for w in self.s["wtr"] if w["id"] != d["wtr"]]
        m = self.shelf_item(d.get("libId"))
        if m and not self.linked_book(m["id"]):
            b["libId"], b["libFedK"] = m["id"], []        # (pages read before count when you Log: see the reader)
        self.s["books"].append(b)
        self.save()
        return None, b

    def log_progress(self, bid, value, now=None):
        """'I'm now on page N' (or at N%). Returns (error, {"joy", "pages", "finished"})."""
        now = now or time.time()
        b = self.book(bid)
        if not b or b["status"] != "reading":
            return "That book isn't being read", None
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "Enter the page you're on" if b["mode"] == "pages" else "Enter how far through you are", None
        top = b["pages"] if b["mode"] == "pages" else 100
        v = min(top, round(v) if b["mode"] == "pages" else round(v, 1))
        if v <= b["progress"]:
            where = f"page {b['progress']:g}" if b["mode"] == "pages" else f"{b['progress']:g}%"
            return f"That's not past where you are ({where})", None
        before = b["progress"]
        pages = (v - before) if b["mode"] == "pages" else (v - before) / 100 * b["pages"]
        b["progress"], b["loggedAt"] = v, now
        joy = min(tuning.get("library_joy_max"), pages * tuning.get("library_joy_page"))
        res = {"joy": round(joy, 1), "pages": round(pages, 1), "finished": None}
        if v >= top:
            res["finished"] = self._finish(b, now)
        self.save()
        return None, res

    def _finish(self, b, now):
        length = length_of(b["pages"])
        entry = {k: b.get(k) for k in ("title", "author", "isbn", "pages", "cover")}
        entry.update(length=length, points=POINTS[length], rations=rations_for(length),
                     started=iso(b.get("started")), date=iso(now), id=b["id"])
        self.s["done"].append(entry)
        self.s["books"] = [x for x in self.s["books"] if x["id"] != b["id"]]
        self._tell("finish", entry)
        for n, tid, name in TITLES:
            if n > 0 and self.score() >= n and tid not in self.s["titles"]:
                self.s["titles"][tid] = iso(now)
                self._tell("title", {"name": name, "points": n})
        return entry

    def edit(self, bid, d, now=None):
        """Corrections, not reading: no joy. Reaching 100% by an edit still finishes the book."""
        now = now or time.time()
        b = self.book(bid)
        if not b:
            return "There's no such book", None
        bk = self._book_in(dict(d, cover=b.get("cover"), isbn=d.get("isbn", b.get("isbn"))))
        if not bk:
            return "Add a title and the number of pages", None
        mode = "percent" if d.get("mode") == "percent" else "pages"
        try:
            prog = float(d.get("progress", b["progress"]))
        except (TypeError, ValueError):
            return "Enter how far through you are", None
        prog = round(prog) if mode == "pages" else round(prog, 1)
        top = bk["pages"] if mode == "pages" else 100
        if prog < 0 or prog > top:
            return (f"The book only has {bk['pages']} pages" if mode == "pages" else "Progress can't be more than 100%"), None
        b.update(bk, mode=mode, progress=prog, length=length_of(bk["pages"]))
        fin = self._finish(b, now) if prog >= top and b["status"] == "reading" else None
        self.save()
        return None, {"finished": fin}

    def freeze(self, bid, on, now=None):
        b = self.book(bid)
        if not b:
            return "There's no such book", None
        if on and b["status"] == "reading":
            if len(self.frozen()) >= MAX_FROZEN:
                return f"You already have {MAX_FROZEN} frozen books. Unfreeze or abandon one of them first.", None
            b["status"], b["frozenAt"] = "frozen", now or time.time()
        elif not on and b["status"] == "frozen":
            if len(self.reading()) >= MAX_CURRENT:
                return f"You're already reading {MAX_CURRENT} books. Finish, freeze or abandon one of them first.", None
            b["status"] = "reading"
            b.pop("frozenAt", None)
        self.save()
        return None, b

    def abandon(self, bid):
        if not self.book(bid):
            return "There's no such book", None
        self.s["books"] = [b for b in self.s["books"] if b["id"] != bid]
        self.save()
        return None, True

    def wtr_add(self, d, now=None):
        bk = self._book_in(d)
        if not bk:
            return "Add a title and the number of pages", None
        if any(same_book(w, bk) for w in self.s["wtr"]):
            return "That book is already on your Want To Read list.", None
        if len(self.s["wtr"]) >= MAX_WTR:
            return f"Your Want To Read list is full ({MAX_WTR} books).", None
        now = now or time.time()
        w = dict(bk, id="w%x%03x" % (int(now * 1000), len(self.s["wtr"])), added=iso(now))
        self.s["wtr"].append(w)
        self.save()
        return None, w

    def wtr_remove(self, wid):
        self.s["wtr"] = [w for w in self.s["wtr"] if w["id"] != wid]
        self.save()
        return None, True

    def wtr_move(self, wid, step):
        """The list is kept oldest first; the page shows it newest first, so 'up' there is +1 here."""
        lst = self.s["wtr"]
        i = next((n for n, w in enumerate(lst) if w["id"] == wid), None)
        if i is None:
            return "There's no such book", None
        j = i + (1 if step < 0 else -1)
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
            self.save()
        return None, True

    def favourite(self, did):
        favs = set(self.s["favs"])
        favs.symmetric_difference_update({did})
        self.s["favs"] = sorted(favs)
        self.save()
        return None, did in favs

    def _tell(self, kind, info):
        if self.on_event:
            try:
                self.on_event(kind, info)
            except Exception:
                log.exception("library event")

    # ---- for the Den and the Library page
    def _row(self, b):
        p = self.pct(b)
        return dict(b, pct=round(p, 1), length_name=LENGTH_NAME[length_of(b["pages"])],
                    rations=rations_for(length_of(b["pages"])))

    def view(self, full=False):
        out = {"reading": [self._row(b) for b in self.reading()],
               "frozen": [self._row(b) for b in self.frozen()],
               "max": MAX_CURRENT, "max_frozen": MAX_FROZEN, "score": self.score(), "title": self.title(),
               "next_title": self.next_title(), "done_count": len(self.s["done"]), "wtr_count": len(self.s["wtr"]),
               "rations": {k: rations_for(k) for k, _, _ in LENGTHS},
               "joy_page": tuning.get("library_joy_page"), "joy_max": tuning.get("library_joy_max"),
               "shelf_count": len(self.s["shelf"]), **self.storage()}
        if full:
            out.update(wtr=list(reversed(self.s["wtr"])),
                       done=sorted(self.s["done"], key=lambda d: d["date"], reverse=True),
                       favs=self.s["favs"], points=POINTS,
                       titles=[{"n": n, "id": tid, "name": name, "at": self.s["titles"].get(tid)} for n, tid, name in TITLES],
                       lengths=[{"key": k, "name": n, "from": at} for k, n, at in LENGTHS],
                       shelf=[self._shelf_row(m) for m in sorted(self.s["shelf"], key=lambda m: -m.get("added", 0))])
        return out

    # ---- e-books: EPUBs kept on the Pi, read in the Library page's reader (Bookworm's)
    # Harald only stores them: the reader in your browser opens each one, works out its pages
    # (about 250 words each), and tracks what you read. What's read, where you are and which
    # pages have been logged are kept here (in his database, so in his backups); the EPUB files
    # themselves are not in backups.
    def epub_path(self, eid):
        if not self.epub_dir or not re.fullmatch(r"e[0-9a-f]{6,20}", str(eid or "")):
            return None
        return os.path.join(self.epub_dir, eid + ".epub")

    def shelf_item(self, eid):
        return next((m for m in self.s["shelf"] if m["id"] == eid), None)

    def has_file(self, m):
        p = self.epub_path(m["id"])
        return bool(p and os.path.exists(p))

    def linked_book(self, eid):
        return next((b for b in self.s["books"] if b.get("libId") == eid and b["status"] in ("reading", "frozen")), None)

    def shelf_used(self):
        if not self.epub_dir or not os.path.isdir(self.epub_dir):
            return 0
        return sum(os.path.getsize(os.path.join(self.epub_dir, f)) for f in os.listdir(self.epub_dir) if f.endswith(".epub"))

    def storage(self):
        mb = 1024 * 1024
        used, cap = self.shelf_used(), int(tuning.get("library_shelf_max_mb") * mb)
        return {"shelf_used": used, "shelf_cap": cap, "epub_cap": int(tuning.get("library_epub_max_mb") * mb),
                "shelf_over": used > cap}

    FREE_MARGIN = 300 * 1024 * 1024      # always leave this much of the card free

    def can_add(self, size):
        """Why an EPUB of `size` bytes can't be added (None if it can)."""
        st = self.storage()
        mb = lambda n: f"{n / 1048576:,.0f} MB"          # noqa: E731
        if size > st["epub_cap"]:
            return f"That EPUB is {mb(size)}: the most for one book is {mb(st['epub_cap'])} (Developer Tools → Library)."
        if st["shelf_used"] + size > st["shelf_cap"]:
            return (f"There isn't room on the shelf: {mb(st['shelf_used'])} of {mb(st['shelf_cap'])} is used. Remove some "
                    "EPUBs, or raise the limit in Developer Tools → Library.")
        try:
            os.makedirs(self.epub_dir, exist_ok=True)
            if shutil.disk_usage(self.epub_dir).free - size < self.FREE_MARGIN:
                return "The memory card is nearly full, so the EPUB can't be added."
        except OSError:
            return "The EPUB can't be stored."
        return None

    @staticmethod
    def _info_in(d):
        """The reader's index of an EPUB (made in your browser), checked."""
        if not isinstance(d, dict):
            return None
        try:
            ch = [{"href": _clean(c["href"], 500), "start": int(c["start"]), "n": int(c["n"]), "chars": int(c["chars"]),
                   "main": bool(c["main"])} for c in d.get("chapters") or []][:20000]
            toc = [{"label": _clean(t.get("label"), 300), "href": _clean(t.get("href"), 500)} for t in d.get("toc") or []][:20000]
            main = int(d.get("mainCount") or 0)
            total = int(d.get("total") or 0)
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
        if not ch or main <= 0 or total <= 0 or total > 500000:
            return None
        return {"title": _clean(d.get("title")) or "Untitled", "author": _clean(d.get("author"), 200),
                "file": _clean(d.get("file"), 200), "chapters": ch, "toc": toc, "mainCount": main, "total": total}

    def epub_add(self, meta, tmp, size, now=None):
        """A new EPUB (already written to `tmp`, `size` bytes). One that was on the shelf before,
        but whose file is missing (after restoring a backup on a new card), takes its place again,
        with its reading record."""
        now = now or time.time()
        info = self._info_in(meta)

        def drop():
            try:
                os.remove(tmp)
            except OSError:
                pass
        if not info:
            drop()
            return "That file couldn't be read as an EPUB.", None
        same = [m for m in self.s["shelf"] if norm(m["title"]) == norm(info["title"]) and norm(m["author"]) == norm(info["author"])]
        if any(m.get("size") == size and self.has_file(m) for m in same):
            drop()
            return f"{info['title']} is already on the shelf.", None
        m = next((x for x in same if not self.has_file(x)), None)
        if m:
            if m.get("total") != info["total"]:          # another edition: its old record doesn't fit
                m.update(read=[], manual=[], partial={}, pos=None)
            m.update(info, size=size, back=now)
        else:
            m = dict(info, id="e%x" % int(now * 1000), size=size, added=now, read=[], manual=[], partial={}, pos=None)
            while self.shelf_item(m["id"]):
                m["id"] = "e%x" % (int(m["id"][1:], 16) + 1)
            self.s["shelf"].append(m)
        os.replace(tmp, self.epub_path(m["id"]))
        self.save()
        return None, m

    def epub_save(self, eid, d, now=None):
        """The reader's record: pages read (and which were marked by hand), part-read pages, and where you are."""
        m = self.shelf_item(eid)
        if not m or not isinstance(d, dict):
            return "There's no such e-book", None
        tot = m["total"]
        try:
            read = sorted({int(k) for k in d.get("read") or [] if 0 <= int(k) < tot})
            manual = sorted({int(k) for k in d.get("manual") or []} & set(read))
            partial = {str(int(k)): min(1.0, max(0.0, float(v))) for k, v in (d.get("partial") or {}).items()
                       if 0 <= int(k) < tot}
            pos = d.get("pos")
            pos = {"ch": int(pos["ch"]), "k": None if pos.get("k") is None else int(pos["k"]),
                   "off": int(pos.get("off") or 0)} if isinstance(pos, dict) else None
        except (TypeError, ValueError, KeyError):
            return "That reading record didn't make sense", None
        m.update(read=read, manual=manual, partial=partial, pos=pos, lastOpened=now or time.time())
        self.save()
        return None, True

    def epub_remove(self, eid):
        m = self.shelf_item(eid)
        if not m:
            return "There's no such e-book", None
        p = self.epub_path(eid)
        if p and os.path.exists(p):
            os.remove(p)
        self.s["shelf"] = [x for x in self.s["shelf"] if x["id"] != eid]
        for b in self.s["books"]:
            if b.get("libId") == eid:
                b.pop("libId", None)
                b.pop("libFedK", None)
        self.save()
        return None, True

    def is_main(self, m, k):
        c = next((c for c in m["chapters"] if c["start"] <= k < c["start"] + c["n"]), None)
        return bool(c and c["main"])

    def epub_pct(self, m):
        return int(sum(1 for k in m.get("read", []) if self.is_main(m, k)) / max(1, m["mainCount"]) * 100)

    def epub_link(self, bid, eid):
        """Bookworm's linking: pages already read in the reader are treated like hand-marked ones."""
        b, m = self.book(bid), self.shelf_item(eid)
        if not b or not m:
            return "There's no such book", None
        if self.linked_book(eid) and self.linked_book(eid) is not b:
            return "That e-book is already linked to another book.", None
        main = sorted(k for k in m.get("read", []) if self.is_main(m, k))
        b["libId"], b["libFedK"] = eid, main
        m["manual"] = sorted(set(m.get("manual") or []) | set(main))
        self.save()
        return None, True

    def epub_unlink(self, bid):
        b = self.book(bid)
        if not b:
            return "There's no such book", None
        b.pop("libId", None)
        b.pop("libFedK", None)
        self.save()
        return None, True

    def epub_counted(self, bid, ks):
        """Reader pages that have now counted towards a book's progress (they never count twice)."""
        b = self.book(bid)
        m = b and self.shelf_item(b.get("libId"))
        if not m:
            return "That book isn't linked to an e-book", None
        try:
            ks = {int(k) for k in ks or [] if 0 <= int(k) < m["total"]}
        except (TypeError, ValueError):
            return "Those pages didn't make sense", None
        b["libFedK"] = sorted(set(b.get("libFedK") or []) | ks)
        self.save()
        return None, True

    def _shelf_row(self, m):
        linked = self.linked_book(m["id"])
        row = {k: m.get(k) for k in ("id", "title", "author", "mainCount", "size", "added", "lastOpened")}
        row.update(file=self.has_file(m), pct=self.epub_pct(m), started=bool(m.get("read") or m.get("pos")),
                   linked=linked["id"] if linked else None, linked_title=linked["title"] if linked else None)
        if linked:                   # (a linked book's page needs the whole record, to work out what to log)
            row["record"] = m
        return row

    def epub_record(self, eid):
        return self.shelf_item(eid)

    # ---- Open Library, through Harald
    @staticmethod
    def _get_json(url, timeout=12):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    @staticmethod
    def isbn_of(q):
        d = re.sub(r"[^0-9Xx]", "", q or "")
        return d.upper() if len(d) in (10, 13) and re.fullmatch(r"\d{9,12}[\dXx]", d) else None

    def _by_isbn(self, isbn):
        """An ISBN: that exact edition (its own page count), from Open Library's edition record,
        with its ISBN search to fill in what the record lacks (many editions don't name their
        authors: the work does). The edition record can be slow (Open Library may try to import
        a book it hasn't got), so it has its own short time limit, and if it fails in any way
        the ISBN search alone is used. [] if neither knows it; an error only if neither answered."""
        ed = doc = None
        errors = 0
        try:
            ed = self._get_json(f"{OL}/isbn/{isbn}.json", timeout=8)
            if not isinstance(ed, dict) or not ed.get("title"):
                ed = None
        except urllib.error.HTTPError as e:
            errors += e.code != 404
        except Exception:
            errors += 1
        try:
            docs = self._get_json(f"{OL}/search.json?" + urllib.parse.urlencode(
                {"isbn": isbn, "fields": OL_FIELDS, "limit": 1}), timeout=10).get("docs") or []
            doc = docs[0] if docs else None
        except Exception:
            errors += 1
        if not ed and not doc:
            if errors >= 2:
                raise OSError("Open Library didn't answer")
            return []
        doc = doc or {}
        names = list(doc.get("author_name") or [])
        for a in ([] if names else ((ed or {}).get("authors") or [])[:2]):
            try:                                     # (only if the ISBN search didn't name them)
                names.append(self._get_json(f"{OL}{a['key']}.json", timeout=5).get("name"))
            except Exception:
                pass
        names = [n for n in names if n]
        if ed:
            year = re.search(r"\d{4}", ed.get("publish_date") or "")
            pages = ed.get("number_of_pages")
            return [{"title": ed.get("title") or doc.get("title") or "Untitled", "author": _authors(names),
                     "isbn": isbn, "pages": pages or doc.get("number_of_pages_median"),
                     "cover": next((c for c in ed.get("covers") or [] if c and c > 0), None) or doc.get("cover_i"),
                     "year": year.group(0) if year else (doc.get("first_publish_year") or ""),
                     "edition": bool(pages)}]
        return [{"title": doc.get("title") or "Untitled", "author": _authors(names), "isbn": isbn,
                 "pages": doc.get("number_of_pages_median"), "cover": doc.get("cover_i"),
                 "year": doc.get("first_publish_year") or "", "editions": doc.get("edition_count") or 0}]

    def search(self, q):
        """Bookworm's search: an ISBN asks for that exact edition (its own page count); anything
        else is a search with one result per work (the typical page count across editions)."""
        q = _clean(q, 200)
        if not q:
            return []
        isbn = self.isbn_of(q)
        if isbn:
            found = self._by_isbn(isbn)
            if found:
                return found
            # (Open Library doesn't know that ISBN: an ordinary search for it, below, sometimes does)
        data = self._get_json(f"{OL}/search.json?" + urllib.parse.urlencode(
            {"q": q, "fields": OL_FIELDS, "limit": 10}))
        return [{"title": d.get("title") or "Untitled", "author": _authors(d.get("author_name")),
                 "isbn": isbn or _pick_isbn(d.get("isbn")), "pages": d.get("number_of_pages_median"),
                 "cover": d.get("cover_i"), "year": d.get("first_publish_year") or "",
                 "editions": d.get("edition_count") or 0} for d in data.get("docs") or []]

    def cover(self, cid, keep=True):
        """A cover picture (Open Library's medium size), kept once fetched (unless `keep` is False:
        a search result's, only looked at). None if there isn't one."""
        if not str(cid).isdigit() or not self.cover_dir:
            return None
        path = os.path.join(self.cover_dir, f"{int(cid)}.jpg")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        try:
            req = urllib.request.Request(COVERS.format(int(cid)) + "?default=false", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = r.read(400_000)
        except Exception:
            return None
        if not data.startswith(b"\xff\xd8"):          # (a JPEG, or nothing)
            return None
        if not keep:
            return data
        os.makedirs(self.cover_dir, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return data


def _authors(lst):
    lst = [a for a in (lst or []) if a]
    if not lst:
        return ""
    return " & ".join(lst) if len(lst) <= 2 else f"{lst[0]} and {len(lst) - 1} others"


def _pick_isbn(lst):
    lst = lst or []
    return next((x for x in lst if re.fullmatch(r"97[89]\d{10}", x)), lst[0] if lst else "")
