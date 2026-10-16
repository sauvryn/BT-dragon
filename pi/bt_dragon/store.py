"""
Harald's memory: one SQLite file.

SQLite writes through a journal, so if the power is cut mid-write the database rolls back
to the last complete transaction instead of being left half-written. That matters on a Pi
that may be unplugged without warning.

Gentle on the memory card: changes are gathered in memory and written to the card together,
every few minutes (store.flush()), rather than one at a time as they happen. A memory card
wears out with writing, and it writes in whole blocks: changing one number in the database
rewrites at least a 4 KB page, and a busy street can change hundreds of numbers a minute
(every gadget eaten updates its type's meal count). Gathered up, the same page changed a
hundred times is written once. Napping, going to sleep, restarting, making a backup and
reading the diary files all write everything first; only pulling the plug without a nap
or sleep loses anything, and then only the last few minutes.

What is kept, and what deliberately isn't:
  * Wi-Fi networks: kept (they are public broadcasts, and that's what WiGLE maps).
  * Bluetooth: only *species* (kinds of device) and counts are kept. Individual addresses
    are held in RAM for the current session and forgotten, except devices you mark as
    your own ("pals").
"""
import json
import sqlite3
import time

from .mobilewifi import is_mobile

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS aps (
    bssid TEXT PRIMARY KEY, ssid TEXT, auth TEXT, channel INT, freq INT,
    first_seen REAL, last_seen REAL, best_rssi INT, times_seen INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS ap_obs (
    id INTEGER PRIMARY KEY, bssid TEXT, ts REAL, rssi INT,
    lat REAL, lon REAL, alt REAL, acc REAL, uploaded INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ap_obs_pending ON ap_obs(uploaded);
CREATE TABLE IF NOT EXISTS species (
    key TEXT PRIMARY KEY, label TEXT, kind TEXT, first_seen REAL, last_seen REAL,
    meals INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS pals (
    mac TEXT PRIMARY KEY, name TEXT, added REAL, last_seen REAL, best_rssi INT);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, ts REAL, kind TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY, ts REAL, rows INT, ok INT, message TEXT);
CREATE TABLE IF NOT EXISTS lands (cell TEXT PRIMARY KEY, realm TEXT, first_seen REAL);
CREATE INDEX IF NOT EXISTS lands_realm ON lands(realm);
CREATE TABLE IF NOT EXISTS landmarks (
    qid TEXT PRIMARY KEY, title TEXT, lat REAL, lon REAL, langs INT, realm TEXT,
    first_seen REAL, last_seen REAL, visits INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS landmarks_lat ON landmarks(lat);
CREATE TABLE IF NOT EXISTS realms_asked (realm TEXT PRIMARY KEY, ts REAL);
CREATE TABLE IF NOT EXISTS greens (
    id TEXT PRIMARY KEY, name TEXT, kind TEXT, lat REAL, lon REAL, minlat REAL, minlon REAL,
    maxlat REAL, maxlon REAL, area REAL, rings TEXT, realm TEXT,
    first_seen REAL, last_seen REAL, visits INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS greens_lat ON greens(minlat);
CREATE TABLE IF NOT EXISTS greens_asked (realm TEXT PRIMARY KEY, ts REAL);
CREATE TABLE IF NOT EXISTS exercise (start REAL PRIMARY KEY, end REAL, kind TEXT, meters REAL);
CREATE TABLE IF NOT EXISTS finds (
    coll TEXT, key TEXT, label TEXT, kind TEXT, first_seen REAL, last_seen REAL, count INT DEFAULT 1,
    PRIMARY KEY (coll, key));
CREATE TABLE IF NOT EXISTS stars (
    key TEXT PRIMARY KEY, const TEXT, prn INT, first_seen REAL, last_seen REAL, nights INT DEFAULT 1);
"""

MAX_EVENTS = 500


def _maker_label(label_for, code):
    if isinstance(label_for, dict):          # a plain list of company names
        name = label_for.get(code)
        return f"{name} device" if name else None
    return label_for(code)


class Store:
    def __init__(self, path):
        # "DEFERRED": the first change opens a transaction, and nothing reaches the card
        # until flush() commits it
        self.db = sqlite3.connect(path, isolation_level="DEFERRED", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self._add_columns("greens", (("walks", "INT DEFAULT 0"), ("runs", "INT DEFAULT 0"), ("rides", "INT DEFAULT 0")))
        self.db.commit()
        self.flushes = 0             # how many times changes have gone to the card (for the Den)
        self.flushed_at = time.time()
        self.before_flush = []       # callables run first (the diary files' waiting lines)

    def flush(self):
        """Write everything waiting onto the card, as one transaction."""
        for f in self.before_flush:
            try:
                f()
            except Exception:
                pass
        if self.db.in_transaction:
            self.db.commit()
            self.flushes += 1
        self.flushed_at = time.time()

    def pending(self):
        return self.db.in_transaction

    def close(self):
        self.flush()
        self.db.close()

    def _add_columns(self, table, cols):
        """Older databases (and restored backups) get columns added since they were made."""
        have = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
        for name, kind in cols:
            if name not in have:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")

    # ---------------------------------------------------------------- key/value
    def get(self, key, default=None):
        r = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def put(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value)))

    # ---------------------------------------------------------------- events
    diary = None   # a DiaryFiles, if the daily spreadsheet files are switched on
    listeners = ()  # callables(kind, text, ts) told about every diary entry (the Echo Dot)

    def event(self, kind, text, ts=None):
        ts = ts or time.time()
        if self.diary:
            self.diary.write(ts, kind, text)
        for f in self.listeners:
            try:
                f(kind, text, ts)
            except Exception:
                pass
        self.db.execute("INSERT INTO events (ts, kind, text) VALUES (?, ?, ?)", (ts, kind, text))
        self.db.execute("DELETE FROM events WHERE id <= (SELECT MAX(id) FROM events) - ?", (MAX_EVENTS,))
        return ts

    def exercise_add(self, start, end, kind, meters):
        """A walk, run or bike ride, kept for good (the diary list only keeps recent things)."""
        self.db.execute("INSERT OR REPLACE INTO exercise VALUES (?, ?, ?, ?)", (start, end, kind, meters))

    def exercise_since(self, ts):
        return [dict(r) for r in self.db.execute(
            "SELECT start, end, kind, meters FROM exercise WHERE start >= ? ORDER BY start", (ts,))]

    def events(self, n=30):
        return [dict(r) for r in self.db.execute(
            "SELECT ts, kind, text FROM events ORDER BY id DESC LIMIT ?", (n,))]

    # ---------------------------------------------------------------- Wi-Fi
    def ap_seen(self, ap, now, touch=True):
        """
        Record an access point. Returns (is_new, previous_last_seen).
        touch=False leaves last_seen alone (used while the clock isn't trustworthy yet, so
        a wrong date can't reset the berry bushes).
        """
        r = self.db.execute("SELECT last_seen FROM aps WHERE bssid=?", (ap["bssid"],)).fetchone()
        if r is None:
            self.db.execute(
                "INSERT INTO aps (bssid, ssid, auth, channel, freq, first_seen, last_seen, best_rssi) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ap["bssid"], ap["ssid"], ap["auth"], ap["channel"], ap["freq"], now, now, ap["rssi"]))
            return True, None
        self.db.execute(
            "UPDATE aps SET ssid=?, auth=?, channel=?, freq=?, last_seen=CASE WHEN ? THEN ? ELSE last_seen END, "
            "best_rssi=MAX(best_rssi, ?), times_seen=times_seen+1 WHERE bssid=?",
            (ap["ssid"], ap["auth"], ap["channel"], ap["freq"], 1 if touch else 0, now, ap["rssi"], ap["bssid"]))
        return False, r[0]

    def ap_observe(self, bssid, ts, rssi, fix):
        self.db.execute(
            "INSERT INTO ap_obs (bssid, ts, rssi, lat, lon, alt, acc) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bssid, ts, rssi, fix["lat"], fix["lon"], fix.get("alt") or 0.0, fix.get("acc") or 0.0))

    def ap_count(self):
        return self.db.execute("SELECT COUNT(*) FROM aps").fetchone()[0]

    def recent_aps(self, n=20):
        return [dict(r) for r in self.db.execute(
            "SELECT bssid, ssid, auth, channel, best_rssi, first_seen, last_seen FROM aps "
            "ORDER BY first_seen DESC LIMIT ?", (n,))]

    def forget_network(self, ssid):
        """Forget a network entirely (sightings too), e.g. your own Echo Dot's setup network,
        so it's never uploaded. Returns how many networks were removed."""
        bssids = [r[0] for r in self.db.execute("SELECT bssid FROM aps WHERE ssid = ?", (ssid,))]
        for b in bssids:
            self.db.execute("DELETE FROM ap_obs WHERE bssid = ?", (b,))
            self.db.execute("DELETE FROM aps WHERE bssid = ?", (b,))
        return len(bssids)

    def pending_obs(self, skip_nomap=True, upload_hidden=False):
        q = ("SELECT o.id, o.bssid, a.ssid, a.auth, a.first_seen, a.channel, a.freq, o.rssi, o.lat, o.lon, "
             "o.alt, o.acc, o.ts FROM ap_obs o JOIN aps a ON a.bssid = o.bssid WHERE o.uploaded = 0")
        rows = [dict(r) for r in self.db.execute(q)]
        out = []
        for r in rows:
            ssid = r["ssid"] or ""
            if skip_nomap and ssid.lower().endswith("_nomap"):
                continue
            if is_mobile(ssid):               # never uploaded: it doesn't stay put (mobilewifi.py)
                continue
            if not upload_hidden and not ssid:
                continue
            out.append(r)
        return out

    def pending_count(self, skip_nomap=True, upload_hidden=False):
        return len(self.pending_obs(skip_nomap, upload_hidden))

    def mark_uploaded(self, ids):
        self.db.executemany("UPDATE ap_obs SET uploaded=1 WHERE id=?", [(i,) for i in ids])
        # keep uploaded observations a month, then let them go
        self.db.execute("DELETE FROM ap_obs WHERE uploaded=1 AND ts < ?", (time.time() - 30 * 86400,))

    # ---------------------------------------------------------------- collection finds
    def find_seen(self, coll, key, label, kind, now):
        """A find for a collection (a kind of aircraft, an airline, a kind of sensor...).
        Returns True the first time."""
        r = self.db.execute("SELECT 1 FROM finds WHERE coll=? AND key=?", (coll, key)).fetchone()
        if r:
            self.db.execute("UPDATE finds SET last_seen=?, count=count+1 WHERE coll=? AND key=?", (now, coll, key))
            return False
        self.db.execute("INSERT INTO finds (coll, key, label, kind, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                        (coll, key, label, kind, now, now))
        return True

    def finds(self, coll):
        return [dict(r) for r in self.db.execute(
            "SELECT key, label, kind, first_seen, last_seen, count FROM finds WHERE coll=? ORDER BY first_seen", (coll,))]

    def prune_obs(self, now=None, days=90):
        """Wardriving sightings are kept 90 days at most, uploaded or not: each one says where
        you were and when. (Uploaded ones go after a month.) Returns how many went."""
        cur = self.db.execute("DELETE FROM ap_obs WHERE ts < ?", ((now or time.time()) - days * 86400,))
        return cur.rowcount

    def forget_obs_where(self, inside):
        """Delete the sightings not yet uploaded for which inside(lat, lon) is true (the home zone)."""
        ids = [r[0] for r in self.db.execute("SELECT id, lat, lon FROM ap_obs WHERE uploaded = 0")
               if inside(r[1], r[2])]
        self.db.executemany("DELETE FROM ap_obs WHERE id=?", [(i,) for i in ids])
        return len(ids)

    def log_upload(self, rows, ok, message):
        self.db.execute("INSERT INTO uploads (ts, rows, ok, message) VALUES (?, ?, ?, ?)",
                        (time.time(), rows, 1 if ok else 0, message))

    def last_upload(self):
        r = self.db.execute("SELECT ts, rows, ok, message FROM uploads ORDER BY id DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    # ---------------------------------------------------------------- species
    def species_seen(self, key, label, kind, now):
        """Count one meal of this species. Returns True if it is a brand-new species."""
        r = self.db.execute("SELECT 1 FROM species WHERE key=?", (key,)).fetchone()
        if r is None:
            self.db.execute("INSERT INTO species VALUES (?, ?, ?, ?, ?, 1)", (key, label, kind, now, now))
            return True
        self.db.execute("UPDATE species SET last_seen=?, meals=meals+1 WHERE key=?", (now, key))
        return False

    def rename_maker_species(self, label_for):
        """Life-list entries saved as 'Maker 0x1234 gadget' before Harald knew the company:
        give them the company's name (label_for(code) -> new label or None; it can also be
        a dict of company names). If that species already exists, merge the two."""
        import re
        renamed = 0
        for r in list(self.db.execute("SELECT key, label, kind, first_seen, last_seen, meals FROM species "
                                      "WHERE label LIKE 'Maker 0x% gadget'")):
            m = re.match(r"Maker 0x([0-9A-Fa-f]{4}) gadget", r["label"])
            label = _maker_label(label_for, int(m.group(1), 16)) if m else None
            if not label:
                continue
            key = re.sub(r"[^a-z0-9#]+", "-", label.lower()).strip("-")
            other = self.db.execute("SELECT first_seen, last_seen, meals FROM species WHERE key=?", (key,)).fetchone()
            if other:
                self.db.execute("UPDATE species SET first_seen=MIN(first_seen, ?), last_seen=MAX(last_seen, ?), "
                                "meals=meals+? WHERE key=?", (r["first_seen"], r["last_seen"], r["meals"], key))
                self.db.execute("DELETE FROM species WHERE key=?", (r["key"],))
            else:
                self.db.execute("UPDATE species SET key=?, label=? WHERE key=?", (key, label, r["key"]))
            renamed += 1
        return renamed

    def merge_species(self, old_key, label, key):
        """Fold one life-list species into another (adding up meals), or rename it."""
        r = self.db.execute("SELECT first_seen, last_seen, meals FROM species WHERE key=?", (old_key,)).fetchone()
        if not r or old_key == key:
            return
        other = self.db.execute("SELECT 1 FROM species WHERE key=?", (key,)).fetchone()
        if other:
            self.db.execute("UPDATE species SET first_seen=MIN(first_seen, ?), last_seen=MAX(last_seen, ?), "
                            "meals=meals+? WHERE key=?", (r["first_seen"], r["last_seen"], r["meals"], key))
            self.db.execute("DELETE FROM species WHERE key=?", (old_key,))
        else:
            self.db.execute("UPDATE species SET key=?, label=?, kind='maker' WHERE key=?", (key, label, old_key))

    def tidy_code_names(self, meaningful, label, key):
        """Species named from a broadcast name that turned out to be just a code
        ("TS#A-a"): fold them into one species (`label`), diary entries too."""
        n = 0
        for r in list(self.db.execute("SELECT key, label FROM species WHERE kind='named'")):
            if meaningful(r["label"]):
                continue
            self.merge_species(r["key"], label, key)
            self.db.execute("UPDATE events SET text=REPLACE(text, ?, ?) WHERE kind='species' AND text LIKE ?",
                            (f": {r['label']}", f": {label}", f"%: {r['label']}%"))
            n += 1
        return n

    def rename_maker_events(self, label_for):
        """Old diary entries that mention 'Maker 0x1234 gadget': use the company's name."""
        import re
        pat = re.compile(r"Maker 0x([0-9A-Fa-f]{4}) gadget")

        def sub(m):
            return _maker_label(label_for, int(m.group(1), 16)) or m.group(0)
        n = 0
        for r in list(self.db.execute("SELECT id, text FROM events WHERE text LIKE '%Maker 0x% gadget%'")):
            new = pat.sub(sub, r["text"])
            if new != r["text"]:
                self.db.execute("UPDATE events SET text=? WHERE id=?", (new, r["id"]))
                n += 1
        return n

    def species_count(self):
        return self.db.execute("SELECT COUNT(*) FROM species").fetchone()[0]

    def species_list(self):
        return [dict(r) for r in self.db.execute(
            "SELECT key, label, kind, first_seen, last_seen, meals FROM species ORDER BY first_seen")]

    # ---------------------------------------------------------------- lands (squares of the map)
    def land_seen(self, cell, realm, now):
        """Returns (new_land, new_realm)."""
        if self.db.execute("SELECT 1 FROM lands WHERE cell=?", (cell,)).fetchone():
            return False, False
        new_realm = self.db.execute("SELECT 1 FROM lands WHERE realm=? LIMIT 1", (realm,)).fetchone() is None
        self.db.execute("INSERT INTO lands VALUES (?, ?, ?)", (cell, realm, now))
        return True, new_realm

    def land_counts(self):
        r = self.db.execute("SELECT COUNT(*), COUNT(DISTINCT realm) FROM lands").fetchone()
        return r[0], r[1]

    def lands_all(self):
        return [(r[0], r[1]) for r in self.db.execute("SELECT cell, realm FROM lands")]

    def forget_lands(self):
        self.db.execute("DELETE FROM lands")

    # ---------------------------------------------------------------- landmarks
    def realm_fetched(self, realm):
        r = self.db.execute("SELECT ts FROM realms_asked WHERE realm=?", (realm,)).fetchone()
        return r[0] if r else None

    def save_landmarks(self, realm, places, now):
        for p in places:
            self.db.execute(
                "INSERT INTO landmarks (qid, title, lat, lon, langs, realm) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(qid) DO UPDATE SET title=excluded.title, lat=excluded.lat, lon=excluded.lon, "
                "langs=excluded.langs",
                (p["qid"], p["title"], p["lat"], p["lon"], p["langs"], realm))
        self.db.execute("INSERT OR REPLACE INTO realms_asked VALUES (?, ?)", (realm, now))

    def landmarks_near(self, lat, lon, reach_m, min_langs):
        import math
        dlat = reach_m / 111320.0
        dlon = reach_m / (111320.0 * max(0.01, math.cos(math.radians(lat))))
        return [dict(r, seen=r["first_seen"] is not None) for r in self.db.execute(
            "SELECT qid, title, lat, lon, langs, first_seen FROM landmarks "
            "WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND langs >= ?",
            (lat - dlat, lat + dlat, lon - dlon, lon + dlon, min_langs))]

    def landmark_seen(self, qid, now):
        self.db.execute("UPDATE landmarks SET first_seen=COALESCE(first_seen, ?), last_seen=?, "
                        "visits=visits+1 WHERE qid=?", (now, now, qid))

    def landmarks_list(self, min_langs):
        return [dict(r) for r in self.db.execute(
            "SELECT qid, title, lat, lon, langs, first_seen, last_seen, visits FROM landmarks WHERE langs >= ? "
            "ORDER BY first_seen IS NULL, first_seen", (min_langs,))]

    def forget_landmarks_seen(self):
        self.db.execute("UPDATE landmarks SET first_seen=NULL, last_seen=NULL, visits=0")

    # ---------------------------------------------------------------- green spaces
    def greens_fetched(self, realm):
        r = self.db.execute("SELECT ts FROM greens_asked WHERE realm=?", (realm,)).fetchone()
        return r[0] if r else None

    def save_greens(self, realm, greens, now):
        import json
        for g in greens:
            a, b, c, d = g["bbox"]
            self.db.execute(
                "INSERT INTO greens (id, name, kind, lat, lon, minlat, minlon, maxlat, maxlon, area, rings, realm) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
                "kind=excluded.kind, lat=excluded.lat, lon=excluded.lon, minlat=excluded.minlat, "
                "minlon=excluded.minlon, maxlat=excluded.maxlat, maxlon=excluded.maxlon, area=excluded.area, "
                "rings=excluded.rings",
                (g["id"], g["name"], g["kind"], g["lat"], g["lon"], a, b, c, d, g["area"],
                 json.dumps(g["rings"], separators=(",", ":")), realm))
        self.db.execute("INSERT OR REPLACE INTO greens_asked VALUES (?, ?)", (realm, now))

    @staticmethod
    def _green(r):
        import json
        g = dict(r)
        g["rings"] = [[tuple(p) for p in ring] for ring in json.loads(g["rings"])]
        g["seen"] = g["first_seen"] is not None
        return g

    def greens_near(self, lat, lon, reach_m):
        import math
        dlat = reach_m / 111320.0
        dlon = reach_m / (111320.0 * max(0.01, math.cos(math.radians(lat))))
        return [self._green(r) for r in self.db.execute(
            "SELECT * FROM greens WHERE minlat <= ? AND maxlat >= ? AND minlon <= ? AND maxlon >= ?",
            (lat + dlat, lat - dlat, lon + dlon, lon - dlon))]

    def greens_list(self):
        return [self._green(r) for r in self.db.execute("SELECT * FROM greens ORDER BY name")]

    def green_seen(self, gid, now):
        self.db.execute("UPDATE greens SET first_seen=COALESCE(first_seen, ?), last_seen=?, "
                        "visits=visits+1 WHERE id=?", (now, now, gid))

    def green_exercise(self, gid, how, now):
        """A walk, run or ride in a green space."""
        col = {"walk": "walks", "run": "runs", "bike": "rides"}[how]
        self.db.execute(f"UPDATE greens SET last_seen=?, {col}={col}+1 WHERE id=?", (now, gid))

    def forget_greens_seen(self):
        self.db.execute("UPDATE greens SET first_seen=NULL, last_seen=NULL, visits=0, walks=0, runs=0, rides=0")

    # ---------------------------------------------------------------- stars (satellites)
    def star_seen(self, key, const, prn, now):
        """First sighting of the day (or ever) of one satellite."""
        if self.db.execute("SELECT 1 FROM stars WHERE key=?", (key,)).fetchone():
            self.db.execute("UPDATE stars SET last_seen=?, nights=nights+1 WHERE key=?", (now, key))
        else:
            self.db.execute("INSERT INTO stars VALUES (?, ?, ?, ?, ?, 1)", (key, const, prn, now, now))

    def stars(self):
        return [dict(r) for r in self.db.execute(
            "SELECT key, const, prn, first_seen, last_seen, nights FROM stars ORDER BY const, prn")]

    # ---------------------------------------------------------------- pals (own devices)
    def pals(self):
        return {r["mac"]: dict(r) for r in self.db.execute("SELECT * FROM pals ORDER BY name")}

    def add_pal(self, mac, name):
        self.db.execute("INSERT OR REPLACE INTO pals (mac, name, added, last_seen, best_rssi) "
                        "VALUES (?, ?, ?, COALESCE((SELECT last_seen FROM pals WHERE mac=?), 0), "
                        "COALESCE((SELECT best_rssi FROM pals WHERE mac=?), -127))",
                        (mac, name, time.time(), mac, mac))

    def del_pal(self, mac):
        self.db.execute("DELETE FROM pals WHERE mac=?", (mac,))

    def pal_seen(self, mac, rssi, now):
        self.db.execute("UPDATE pals SET last_seen=?, best_rssi=MAX(best_rssi, ?) WHERE mac=?", (now, rssi, mac))
