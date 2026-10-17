"""
Dragon friends.

Pwnagotchis found each other by injecting special Wi-Fi beacon frames, which needs the
radio in monitor mode. Harald doesn't use monitor mode, so dragons meet over Bluetooth
instead: each one sends a small, non-connectable BLE advertisement, just like a fitness
band or an earbud case does, and every other dragon's scanner hears it.

The advert carries "manufacturer data" under company ID 0xFFFF, the ID the Bluetooth SIG
reserves for testing and unregistered projects, followed by:

    'H' 'D'  version  dragon-id(4)  level  mood  name (up to 10 bytes, UTF-8)

A whole BLE advert is only 31 bytes, and BlueZ spends 3 on flags, so that's about all
that fits.

The dragon ID changes every day, at midnight. A fixed ID would let anyone with a Bluetooth
scanner recognize Harald, and so you, from one day to the next: where you go, and when. Each
day's ID is worked out from a secret that never leaves the Pi:

    ID = the first 4 bytes of HMAC-SHA256(secret, "2026-10-15")

HMAC mixes a secret key into a hash, so without the key, today's ID says nothing about
yesterday's or tomorrow's; they look like unrelated random numbers. With it, the same day
always gives the same ID, so a restart in the middle of the day doesn't make him a stranger.

Friends still recognize each other across days by name: a dragon with a new ID, the same
name as a friend, and the same level or higher is taken to be that friend (if exactly one
friend fits). The name is the price of being recognizable at all. A dragon with an unusual
name can still be told apart by anyone listening, because the name goes out in every
beacon; a common name ("Harald") hides in the crowd.

The advert is sent as "broadcast" (non-connectable), and Linux sends those from a throwaway
random Bluetooth address rather than the Pi's own fixed one. The advert is registered
again when the ID changes, which can pick a new throwaway address too.

The beacon can be switched off in bt-dragon.toml ([friends] beacon = false); Harald can
still meet dragons that do broadcast.
"""
import asyncio
import datetime
import hashlib
import hmac
import logging
import os
import time

log = logging.getLogger("friends")

COMPANY = 0xFFFF
MAGIC = b"HD"
VERSION = 1
NAME_MAX = 10
PWNAGOTCHI_BSSID = "DE:AD:BE:EF:DE:AD"  # the address every Pwnagotchi beacons from


def encode(dragon_id: bytes, level: int, mood_idx: int, name: str) -> bytes:
    nm = name.encode("utf-8")[:NAME_MAX]
    while nm:  # don't cut a multi-byte character in half
        try:
            nm.decode("utf-8")
            break
        except UnicodeDecodeError:
            nm = nm[:-1]
    return MAGIC + bytes([VERSION]) + dragon_id[:4] + bytes([min(level, 255), mood_idx & 0xFF]) + nm


def decode(mfr: dict):
    """Return dict(id, level, mood, name) if this advert is a dragon, else None."""
    data = mfr.get(COMPANY) if mfr else None
    if not data or len(data) < 9 or bytes(data[:2]) != MAGIC:
        return None
    data = bytes(data)
    return {"id": data[3:7].hex(), "level": data[7], "mood": data[8],
            "name": data[9:].decode("utf-8", "replace").strip() or "Dragon"}


class DragonId:
    """Today's dragon ID (see the top of this file)."""

    def __init__(self, store):
        key = store.get("dragon_id_key")
        if not key:
            key = os.urandom(16).hex()
            store.put("dragon_id_key", key)
            store.put("dragon_id", None)            # the old fixed ID (before daily IDs) is retired
        self.key = bytes.fromhex(key)

    def today(self, now=None):
        day = datetime.date.fromtimestamp(now or time.time()).isoformat()
        return hmac.new(self.key, day.encode(), hashlib.sha256).digest()[:4]

    def is_mine(self, hex_id, now=None):
        """One of his own IDs (today's, or yesterday's/tomorrow's around midnight)."""
        now = now or time.time()
        return any(self.today(now + d).hex() == hex_id for d in (-86400, 0, 86400))


class FriendBook:
    """Meeting and remembering other dragons (stored in the 'friends' table)."""

    AGAIN_S = 1800  # gone this long, then back = a reunion

    def __init__(self, store, ids: DragonId):
        self.store = store
        self.ids = ids
        self.near = {}  # id -> dict(name, level, mood, rssi, last)
        store.db.execute(
            "CREATE TABLE IF NOT EXISTS friends (id TEXT PRIMARY KEY, name TEXT, level INT, "
            "first_met REAL, last_met REAL, meetings INT DEFAULT 1, best_rssi INT)")

    def heard(self, d, rssi, now=None):
        """Returns 'new', 'again' or None."""
        now = now or time.time()
        if self.ids.is_mine(d["id"], now):
            return None
        prev = self.near.get(d["id"])
        self.near[d["id"]] = dict(d, rssi=rssi, last=now)
        if prev and now - prev["last"] < self.AGAIN_S:
            return None  # still hanging out
        row = self.store.db.execute("SELECT last_met FROM friends WHERE id=?", (d["id"],)).fetchone()
        if row is None:
            # a new ID: a friend who's moved on to a new day's ID? (same name, same level or
            # higher, and only one friend fits)
            fits = self.store.db.execute("SELECT id, last_met FROM friends WHERE name=? AND level<=?",
                                         (d["name"], d["level"])).fetchall()
            if len(fits) == 1:
                self.store.db.execute("UPDATE friends SET id=? WHERE id=?", (d["id"], fits[0][0]))
                row = (fits[0][1],)
        if row is None:
            self.store.db.execute("INSERT INTO friends VALUES (?, ?, ?, ?, ?, 1, ?)",
                                  (d["id"], d["name"], d["level"], now, now, rssi))
            return "new"
        self.store.db.execute("UPDATE friends SET name=?, level=?, last_met=?, meetings=meetings+1, "
                              "best_rssi=MAX(best_rssi, ?) WHERE id=?",
                              (d["name"], d["level"], now, rssi, d["id"]))
        return "again" if now - row[0] >= self.AGAIN_S else None

    def nearby(self, now=None, window=120):
        now = now or time.time()
        return [dict(v, id=k) for k, v in self.near.items() if now - v["last"] < window]

    def all(self):
        return [dict(r) for r in self.store.db.execute(
            "SELECT id, name, level, first_met, last_met, meetings FROM friends ORDER BY last_met DESC")]

    def count(self):
        return self.store.db.execute("SELECT COUNT(*) FROM friends").fetchone()[0]

    def forget(self, fid):
        self.store.db.execute("DELETE FROM friends WHERE id=?", (fid,))
        self.near.pop(fid, None)


class Beacon:
    """Broadcasts Harald's friend advert through BlueZ's LEAdvertisingManager1 (D-Bus).

    BlueZ can't change an advert's contents while it's on the air, so a new level, mood or
    name means taking the old one down and putting a new one up. Done straight away under the
    same name, BlueZ (5.82, on a Pi 5) sometimes refused the new one ("Failed to register
    advertisement") and kept refusing: so each one gets a name of its own, and goes up a
    moment after the old one came down.

    On a Pi 5 it was refused even the very first time, every time. A broadcast advert goes out
    from a throwaway random address, and the Bluetooth rules let a radio refuse to take a new
    random address while it's scanning, which a dragon always is. So, when there's a scanner,
    scanning is paused for the second or two it takes to put the beacon up (see
    ble.BleakScanner.quiet)."""

    PATH = "/org/btdragon/beacon"
    GAP_S = 1.5
    MOOD_EVERY_S = 600      # a new mood alone is re-announced at most this often (moods change a lot)

    @staticmethod
    def _same_but_mood(a, b):
        """The same dragon, level and name, only another mood (byte 8: see encode())."""
        return a is not None and b is not None and len(a) == len(b) and a[:8] == b[:8] and a[9:] == b[9:]

    def __init__(self, payload_fn, quiet=None, bus_fn=None, enabled_fn=None):
        self.payload_fn = payload_fn
        self.enabled_fn = enabled_fn or (lambda: True)   # the Den's "Friend beacon" tick box
        self.kick = asyncio.Event()                        # (set when it's ticked or unticked: look again now)
        self.quiet = quiet          # the scanner's quiet(): see ble.BleakScanner
        self.bus_fn = bus_fn        # (the tests pass a stand-in for BlueZ)
        self.failures = 0

    async def run(self, stop):
        import contextlib
        if self.bus_fn:
            connect, Advert = self.bus_fn()
        else:
            connect, Advert = self._bluez()
        while not stop.is_set():
            bus = None
            try:
                bus, mgr = await connect()
                registered, path, since = None, None, 0.0
                while not stop.is_set():
                    if not self.enabled_fn():          # switched off in the Den: off the air, and wait
                        if path is not None:
                            async with (self.quiet() if self.quiet else contextlib.nullcontext()):
                                try:
                                    await mgr.call_unregister_advertisement(path)
                                except Exception:
                                    pass
                                bus.unexport(path)
                            path, registered = None, None
                            log.info("friend beacon off (switched off in the den)")
                        await self._pause(stop, 60)
                        continue
                    data = self.payload_fn()
                    if self._same_but_mood(data, registered) and time.monotonic() - since < self.MOOD_EVERY_S:
                        data = registered       # (only the mood changed, and only just: later)
                    if data != registered:  # level/mood/name changed: re-announce
                        # (with scanning paused: a radio may refuse a new random address mid-scan)
                        async with (self.quiet() if self.quiet else contextlib.nullcontext()):
                            if path is not None:
                                try:
                                    await mgr.call_unregister_advertisement(path)
                                except Exception:
                                    pass
                                bus.unexport(path)
                                path = None
                                await asyncio.sleep(self.GAP_S)
                            self._n = getattr(self, "_n", 0) + 1
                            p = f"{self.PATH}{self._n}"
                            adv = Advert()
                            adv.data = data
                            bus.export(p, adv)
                            try:
                                await mgr.call_register_advertisement(p, {})
                            except Exception:
                                bus.unexport(p)
                                raise
                            path = p
                        registered, since = data, time.monotonic()
                        self.failures = 0
                        log.info("friend beacon on (%d bytes)", len(data))
                    await self._pause(stop, 60)        # (a rename shows within a minute)
                if path is not None:
                    try:
                        await mgr.call_unregister_advertisement(path)
                    except Exception:
                        pass
            except Exception as e:
                self.failures += 1
                why = getattr(e, "text", None) or str(e)
                kind = getattr(e, "type", "") or type(e).__name__
                if self.failures <= 3 or self.failures % 30 == 0:     # (not every minute, all night)
                    log.warning("friend beacon unavailable: %s (%s; %d in a row%s); retrying in 60 s",
                                why, kind, self.failures, ", scanning paused" if self.quiet else "")
                try:
                    await asyncio.wait_for(stop.wait(), 60)
                except asyncio.TimeoutError:
                    pass
            finally:
                if bus:
                    bus.disconnect()

    async def _pause(self, stop, seconds):
        """Waits `seconds`, or until he's stopping or the tick box changes."""
        self.kick.clear()
        waits = [asyncio.ensure_future(stop.wait()), asyncio.ensure_future(self.kick.wait())]
        try:
            await asyncio.wait(waits, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for w in waits:
                w.cancel()

    @staticmethod
    def _bluez():
        from dbus_fast import BusType, Variant
        from dbus_fast.aio import MessageBus
        from dbus_fast.service import ServiceInterface, dbus_property, method, PropertyAccess

        class Advert(ServiceInterface):
            def __init__(self):
                super().__init__("org.bluez.LEAdvertisement1")
                self.data = b""

            @method()
            def Release(self):
                log.info("BlueZ released the friend beacon")

            @dbus_property(access=PropertyAccess.READ)
            def Type(self) -> "s":
                return "broadcast"  # non-connectable: nothing to pair with

            @dbus_property(access=PropertyAccess.READ)
            def ManufacturerData(self) -> "a{qv}":
                return {COMPANY: Variant("ay", self.data)}

        async def connect():
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            intro = await bus.introspect("org.bluez", "/org/bluez/hci0")
            mgr = bus.get_proxy_object("org.bluez", "/org/bluez/hci0", intro) \
                     .get_interface("org.bluez.LEAdvertisingManager1")
            return bus, mgr

        return connect, Advert
