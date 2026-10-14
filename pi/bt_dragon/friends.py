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

The dragon ID is 4 random bytes made on first start. It is what lets a friend recognize
Harald next time, and also what would let anyone listening recognize him. That's why
the beacon can be switched off in bt-dragon.toml ([friends] beacon = false); Harald can
still meet dragons that do broadcast.
"""
import asyncio
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


def load_dragon_id(store):
    did = store.get("dragon_id")
    if not did:
        did = os.urandom(4).hex()
        store.put("dragon_id", did)
    return bytes.fromhex(did)


class FriendBook:
    """Meeting and remembering other dragons (stored in the 'friends' table)."""

    AGAIN_S = 1800  # gone this long, then back = a reunion

    def __init__(self, store, own_id: bytes):
        self.store = store
        self.own_id = own_id.hex()
        self.near = {}  # id -> dict(name, level, mood, rssi, last)
        store.db.execute(
            "CREATE TABLE IF NOT EXISTS friends (id TEXT PRIMARY KEY, name TEXT, level INT, "
            "first_met REAL, last_met REAL, meetings INT DEFAULT 1, best_rssi INT)")

    def heard(self, d, rssi, now=None):
        """Returns 'new', 'again' or None."""
        now = now or time.time()
        if d["id"] == self.own_id:
            return None
        prev = self.near.get(d["id"])
        self.near[d["id"]] = dict(d, rssi=rssi, last=now)
        if prev and now - prev["last"] < self.AGAIN_S:
            return None  # still hanging out
        row = self.store.db.execute("SELECT last_met FROM friends WHERE id=?", (d["id"],)).fetchone()
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
    """Broadcasts Harald's friend advert through BlueZ's LEAdvertisingManager1 (D-Bus)."""

    PATH = "/org/btdragon/beacon0"

    def __init__(self, payload_fn):
        self.payload_fn = payload_fn

    async def run(self, stop):
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

        while not stop.is_set():
            bus = None
            try:
                bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
                intro = await bus.introspect("org.bluez", "/org/bluez/hci0")
                mgr = bus.get_proxy_object("org.bluez", "/org/bluez/hci0", intro) \
                         .get_interface("org.bluez.LEAdvertisingManager1")
                adv = Advert()
                bus.export(self.PATH, adv)
                registered = None
                while not stop.is_set():
                    data = self.payload_fn()
                    if data != registered:  # level/mood/name changed: re-announce
                        if registered is not None:
                            await mgr.call_unregister_advertisement(self.PATH)
                        adv.data = data
                        await mgr.call_register_advertisement(self.PATH, {})
                        registered = data
                        log.info("friend beacon on (%d bytes)", len(data))
                    try:
                        await asyncio.wait_for(stop.wait(), 300)
                    except asyncio.TimeoutError:
                        pass
                try:
                    await mgr.call_unregister_advertisement(self.PATH)
                except Exception:
                    pass
            except Exception as e:
                log.warning("friend beacon unavailable: %s; retrying in 60 s", e)
                try:
                    await asyncio.wait_for(stop.wait(), 60)
                except asyncio.TimeoutError:
                    pass
            finally:
                if bus:
                    bus.disconnect()
