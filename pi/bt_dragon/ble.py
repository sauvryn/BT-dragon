"""
Bluetooth Low Energy: Harald's food.

How BLE advertising works: a BLE device that wants to be found shouts a short packet
(up to 31 bytes) several times a second on three "advertising" channels. The packet
carries the sender's address and a few tagged fields: maybe a name, the services it
offers (16-bit UUIDs such as 0x180D "heart rate"), and "manufacturer data" that starts
with a 16-bit company ID assigned by the Bluetooth SIG (0x004C is Apple, 0x0075 Samsung).
Nothing is decrypted or connected to here: Harald only listens to these public shouts.

Addresses come in kinds, and the kind decides what Harald may do:
  * public, or random *static*: the same every time. Fine for your own gadgets, which
    you can mark as "pals" to find them later.
  * random *private* (resolvable/non-resolvable): phones, watches and earbuds change
    these every ~15 minutes precisely so they can't be followed. Harald counts them as
    food and as a species, and never tries to link one address to the next.
The top two bits of a random address say which: 11 = static, 01 = resolvable, 00 = non-resolvable.
"""
import asyncio
import contextlib
import re
import hashlib
import hmac
import os
import time

COMPANIES = {
    0x004C: "Apple", 0x0006: "Microsoft", 0x0075: "Samsung", 0x00E0: "Google",
    0x012D: "Sony", 0x009E: "Bose", 0x0087: "Garmin", 0x0059: "Nordic", 0x0171: "Amazon",
    0x038F: "Xiaomi", 0x027D: "Huawei", 0x02E5: "Espressif", 0x0002: "Intel",
    0x000D: "Texas Instruments", 0x0046: "MediaTek", 0x0499: "Ruuvi", 0x000F: "Broadcom",
}



def _load_companies():
    """Every Bluetooth SIG company ID (companies.tsv, ~4,000 of them), with short names
    for the screen. The hand-picked names above win where both exist."""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "companies.tsv")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or "\t" not in line:
                    continue
                code, short = line.split("\t")[:2]
                COMPANIES.setdefault(int(code, 16), short.strip())
    except (OSError, ValueError):
        pass


_load_companies()

# The Bluetooth SIG hands out company IDs in order; codes far beyond the newest one, and
# 0xFFFF ("no company: testing"), aren't real companies. They come from gadgets that put
# their own bytes where the ID belongs (unbranded bulbs, LED strips, toys, cheap trackers),
# often changing them as they go, so they'd count as a new species every few minutes.
# All of them are one species: "Unbranded gadget".
UNBRANDED = "Unbranded gadget"
NEWEST_ID = max(COMPANIES)


def unbranded(code):
    return code == 0xFFFF or code > NEWEST_ID + 0x100


def maker_label(code):
    """What a manufacturer code is called: 'Apple device', 'Unbranded gadget', or None
    for a code inside the assigned range that the list doesn't have (maybe a new company)."""
    if code in COMPANIES:
        return f"{COMPANIES[code]} device"
    if unbranded(code):
        return UNBRANDED
    return None

# 16-bit service UUIDs worth a label
SERVICES = {
    0xFEED: ("Tile tracker", "tracker"),
    0xFEEC: ("Tile tracker", "tracker"),
    0xFD5A: ("Samsung SmartTag / Find", "tracker"),
    0xFE2C: ("Google Fast Pair gadget", "gadget"),
    0xFD6F: ("Exposure-notification beacon", "beacon"),
    0xFE95: ("Xiaomi Mi device", "gadget"),
    0xFE0F: ("Philips Hue light", "home"),
    0xFE07: ("Sonos speaker", "audio"),
    0xFE03: ("Amazon Echo / Fire", "home"),
    0x180D: ("Heart-rate monitor", "fitness"),
    0x1816: ("Bike speed sensor", "fitness"),
    0x1818: ("Bike power meter", "fitness"),
    0x1826: ("Fitness machine", "fitness"),
    0x1812: ("Keyboard / mouse", "gadget"),
    0x181A: ("Environment sensor", "home"),
    0x184E: ("LE Audio device", "audio"),
}

# Services other makers' gadgets carry too, so a gadget broadcasting its own name is filed
# under that name instead: Amazon's 0xFE03 is on Echos and Fire TVs, but also on headphones
# and speakers that work with Alexa (a JBL Tune 520BT, say).
NAME_FIRST = {0xFE03}

APPLE_PODS = {
    0x0220: "AirPods", 0x0F20: "AirPods (2nd gen)", 0x1320: "AirPods (3rd gen)",
    0x0E20: "AirPods Pro", 0x1420: "AirPods Pro 2", 0x0A20: "AirPods Max",
    0x0B20: "Powerbeats Pro", 0x1120: "Beats Studio Buds",
}

TRACKER_KINDS = ("tracker",)


def uuid16(u: str):
    """'0000feed-0000-1000-8000-00805f9b34fb' -> 0xFEED; None for vendor 128-bit UUIDs."""
    u = u.lower()
    if len(u) == 36 and u.endswith("-0000-1000-8000-00805f9b34fb") and u.startswith("0000"):
        return int(u[4:8], 16)
    if len(u) == 4:
        return int(u, 16)
    return None


def address_is_stable(address: str, address_type: str) -> bool:
    if address_type == "public":
        return True
    try:
        top = int(address[:2], 16) >> 6
    except ValueError:
        return False
    return top == 0b11  # random static


# short brand names that are real words on their own (most names need a 4-letter word)
SHORT_BRANDS = {"jbl", "lg", "tcl", "akg", "jvc", "htc", "zte", "bmw", "mi", "hp", "b&o", "ue", "jlab", "oppo"}


def meaningful(label: str) -> bool:
    """Does a name say what the gadget is ("JBL Flip #", "Govee H#"), or is it just a code
    once the numbers are hidden ("TS#A-a", "#mai_#SE_#", "G#(ID-#)")?"""
    if re.search(r"[A-Za-z]{4,}", label):
        return True
    return any(w.lower() in SHORT_BRANDS for w in re.split(r"[^A-Za-z&]+", label) if w)


def species_from_name(name: str):
    """Turn a broadcast name into a species label, or None if it's only a code.

    Names are taken as broadcast, including ones with a person's name in ("Sam's AirPods"):
    a name a gadget shouts to everyone nearby is its owner's choice to share, and dropping
    them also dropped makers' own default names. Only the numbers are hidden (as #), which
    keeps every JBL Flip together as one species and never keeps a serial number."""
    name = (name or "").strip()
    if not name:
        return None
    if re.fullmatch(r"[0-9A-Fa-f:\-_ ]{6,}", name):
        return None  # just an address or serial
    label = re.sub(r"[0-9A-Fa-f]{4,}", "#", name)  # serials / MAC fragments
    label = re.sub(r"\d+", "#", label)
    label = re.sub(r"\s+", " ", label).strip(" -_:")
    if len(label) < 2 or not meaningful(label):
        return None   # just a code: go by its maker or services instead
    return label[:28]


def _apple(data: bytes):
    """Apple 'Continuity' messages: a chain of [type, length, payload] items."""
    found = {}
    i = 0
    while i + 1 < len(data):
        t, n = data[i], data[i + 1]
        found[t] = data[i + 2:i + 2 + n]
        i += 2 + n
    if 0x12 in found:  # Find My offline-finding
        if len(found[0x12]) >= 22:
            return "Find My item (owner away)", "tracker"
        return "Find My device (near owner)", "apple"
    if 0x07 in found:
        p = found[0x07]
        model = (p[1] << 8 | p[2]) if len(p) >= 3 else 0
        return APPLE_PODS.get(model, "AirPods / Beats"), "audio"
    if 0x09 in found:
        return "AirPlay speaker / TV", "audio"
    if 0x0B in found:
        return "Apple Watch", "wearable"
    if 0x0D in found or 0x0E in found:
        return "iPhone / iPad hotspot", "apple"
    if 0x10 in found:
        return "iPhone / iPad / Mac", "apple"
    if 0x0F in found:
        return "Apple device setting up", "apple"
    if 0x0C in found:
        return "Apple device (Handoff)", "apple"
    if 0x05 in found:
        return "Apple device (AirDrop)", "apple"
    if 0x02 in found:
        return "iBeacon", "beacon"
    return "Apple device", "apple"


def classify(name, manufacturer_data: dict, service_uuids, service_data: dict):
    """Return (species_key, label, kind) for one advertisement."""
    svcs = {uuid16(u) for u in (service_uuids or [])} | {uuid16(u) for u in (service_data or {})}
    svcs.discard(None)

    # Google Find Hub tags advertise Eddystone frames 0x40/0x41
    for u, payload in (service_data or {}).items():
        if uuid16(u) == 0xFEAA and payload:
            if payload[0] in (0x40, 0x41):
                return _key("Google Find Hub tag"), "Google Find Hub tag", "tracker"
            return _key("Eddystone beacon"), "Eddystone beacon", "beacon"

    for s in (0xFEED, 0xFEEC, 0xFD5A):  # trackers first
        if s in svcs:
            label, kind = SERVICES[s]
            return _key(label), label, kind

    md = manufacturer_data or {}
    if 0x004C in md:
        label, kind = _apple(bytes(md[0x004C]))
        return _key(label), label, kind
    if 0x0006 in md:
        p = bytes(md[0x0006])
        label = "Swift Pair accessory" if p[:1] == b"\x03" else "Windows PC"
        return _key(label), label, "computer"

    named = species_from_name(name)
    for s in svcs:
        if s in NAME_FIRST and named:
            continue        # a service other makers' gadgets carry too: a real name says more
        if s in SERVICES:
            label, kind = SERVICES[s]
            return _key(label), label, kind
    if named:
        maker = next((COMPANIES[c] for c in md if c in COMPANIES), None)
        label = named if not maker or maker.lower() in named.lower() else f"{maker} {named}"
        return _key(label), label[:32], "named"
    if md:
        # a real company first; then a code that may belong to a new one; then the rest
        c = next((c for c in md if c in COMPANIES), None) \
            or next((c for c in md if not unbranded(c)), None)
        if c is None:
            return _key(UNBRANDED), UNBRANDED, "maker"
        label = maker_label(c) or f"Maker 0x{c:04X} gadget"
        return _key(label), label, "maker"
    return "mystery-morsel", "Mystery morsel", "mystery"


def _key(label):
    return re.sub(r"[^a-z0-9#]+", "-", label.lower()).strip("-")


class Sighting:
    __slots__ = ("address", "stable", "rssi", "first", "last", "key", "label", "kind", "name")

    def __init__(self, address, stable, rssi, now, key, label, kind, name):
        self.address, self.stable, self.rssi = address, stable, rssi
        self.first = self.last = now
        self.key, self.label, self.kind, self.name = key, label, kind, name


class TrackerWatch:
    """
    Anti-stalking check, modeled on what Apple's and Google's own unknown-tracker alerts do.

    An item tracker that is *away from its owner* and keeps showing up near you over a long
    stretch (and, when the phone's GPS is shared, while you've moved a good distance) is
    worth knowing about. Trackers near their owners (e.g. your own AirTag in your bag next
    to your phone) advertise differently and are ignored.
    """

    def __init__(self, alert_after_s=1800, min_moved_m=250):
        self.alert_after_s = alert_after_s
        self.min_moved_m = min_moved_m
        self.bucket_s = max(10, alert_after_s / 6)
        self.seen = {}        # address -> dict(first, last, buckets:set, start_fix, label)
        self.alerts = {}      # id -> dict(address, label, since, ts)
        self.dismissed = set()
        self._next_id = 1

    def observe(self, s: Sighting, now, fix):
        if s.kind != "tracker" or s.address in self.dismissed:
            return None
        w = self.seen.get(s.address)
        if w is None or now - w["last"] > 900:  # gone >15 min: start over
            w = self.seen[s.address] = {"first": now, "last": now, "buckets": set(),
                                        "start_fix": fix, "label": s.label}
        w["last"] = now
        w["buckets"].add(int(now // self.bucket_s))
        if w["start_fix"] is None and fix:
            w["start_fix"] = fix
        if any(a["address"] == s.address for a in self.alerts.values()):
            return None
        span = now - w["first"]
        # present in at least 4 of the ~6 time slices: it's sticking with you, not passing by
        if span < self.alert_after_s or len(w["buckets"]) < 4:
            return None
        if fix and w["start_fix"]:
            if distance_m(w["start_fix"], fix) < self.min_moved_m:
                return None  # it's been near you, but you haven't gone anywhere
        elif span < self.alert_after_s * 1.5:
            return None      # no GPS: wait longer before raising the alarm
        aid = self._next_id
        self._next_id += 1
        self.alerts[aid] = {"id": aid, "address": s.address, "label": w["label"],
                            "since": w["first"], "ts": now}
        return self.alerts[aid]

    def dismiss(self, aid):
        a = self.alerts.pop(aid, None)
        if a:
            self.dismissed.add(a["address"])
        return a is not None

    def prune(self, now):
        for addr in [a for a, w in self.seen.items() if now - w["last"] > 3600]:
            del self.seen[addr]


def distance_m(a, b):
    import math
    r = 6371000.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class BleWatcher:
    """Keeps the live picture of what's around, in RAM only."""

    LIVE_S = 120  # forget an address this long after its last advert

    # Headcount snacking for rotating addresses (see headcount()):
    CROWD_HEARD_S = 20     # "here now" = heard in the last 20 s
    CROWD_SAMPLES = 6      # a new head must stay for 6 checks in a row (~30 s at one per 5 s)
    CROWD_FORGET_S = 900   # the remembered crowd shrinks by one every 15 min it isn't reached

    def __init__(self):
        self.live = {}            # address -> Sighting
        # Fixed addresses already eaten today, kept only as scrambled codes (see _tag), so
        # what's saved to survive a restart is never a readable list of other people's
        # gadget addresses. The scrambling key is new each day and thrown away at midnight.
        self.eaten_today = set()
        self._day = time.strftime("%Y-%m-%d")
        self._day_key = os.urandom(16)
        self._crowd = {}          # species key -> recent headcounts (numbers only, never addresses)
        self._peak = {}           # species key -> [biggest sustained headcount, when it last shrank]
        self.last_any = 0.0

    def advert(self, address, address_type, rssi, name, mfr, uuids, sdata, now=None):
        """
        Feed one advertisement in. Returns (sighting, first, snack):
          first  this address wasn't in the live picture a moment ago
          snack  a fixed-address device he hasn't eaten yet today. Rotating addresses are
                 never snacks on their own; they're counted by headcount() instead.
        """
        now = now or time.time()
        address = address.upper()
        self.last_any = now
        s = self.live.get(address)
        first = s is None
        if first:
            key, label, kind = classify(name, mfr, uuids, sdata)
            s = Sighting(address, address_is_stable(address, address_type), rssi, now, key, label, kind, name)
            self.live[address] = s
        else:
            s.rssi, s.last = rssi, now
            if name and not s.name:
                s.name = name
                if s.kind in ("maker", "mystery"):
                    s.key, s.label, s.kind = classify(name, mfr, uuids, sdata)
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        if today != self._day:
            self._day, self.eaten_today, self._day_key = today, set(), os.urandom(16)
        tag = self._tag(address) if s.stable else None
        snack = s.stable and tag not in self.eaten_today
        if snack:
            self.eaten_today.add(tag)
        return s, first, snack

    def _tag(self, address):
        return hmac.new(self._day_key, address.encode(), hashlib.sha256).hexdigest()[:16]

    def export_state(self, now=None):
        """What has to survive a restart so he doesn't eat everything around him twice."""
        return {"day": self._day, "key": self._day_key.hex(), "eaten": sorted(self.eaten_today),
                "peak": self._peak, "saved": now or time.time()}

    def import_state(self, st, now=None):
        now = now or time.time()
        if not st or st.get("day") != time.strftime("%Y-%m-%d", time.localtime(now)):
            return  # a new day: start fresh, and yesterday's key is gone for good
        try:
            self._day, self._day_key = st["day"], bytes.fromhex(st["key"])
            self.eaten_today = set(st.get("eaten", []))
            # the headcount is only worth keeping if he wasn't off long enough to forget it
            if now - st.get("saved", 0) < self.CROWD_FORGET_S:
                self._peak = {k: [int(v[0]), now] for k, v in st.get("peak", {}).items()}
        except (KeyError, ValueError, TypeError):
            pass

    def headcount(self, now=None):
        """
        Snacks from devices whose addresses rotate (phones, watches, earbuds...). One of
        those changes its address every ~15 minutes, so counting addresses would feed
        Harald a "new" snack four times an hour from the same phone on your couch. Instead
        he counts heads: for each species, how many are here right now. Only when that
        number goes *up* and stays up for ~30 s has someone new actually arrived. An
        address change just swaps one head for another, so the count doesn't move.

        Only numbers are kept, never which address was which, so this doesn't undo the
        privacy the rotation provides. Call every ~5 s. Returns {species key: new heads}.
        """
        now = now or time.time()
        counts = {}
        for s in self.live.values():
            if not s.stable and now - s.last <= self.CROWD_HEARD_S:
                counts[s.key] = counts.get(s.key, 0) + 1
        gains = {}
        for key in set(counts) | set(self._crowd):
            hist = self._crowd.setdefault(key, [])
            hist.append(counts.get(key, 0))
            del hist[:-self.CROWD_SAMPLES]
            sustained = min(hist) if len(hist) == self.CROWD_SAMPLES else 0
            peak = self._peak.setdefault(key, [0, now])
            if sustained > peak[0]:
                gains[key] = sustained - peak[0]
                peak[0], peak[1] = sustained, now
            elif sustained < peak[0] and now - peak[1] >= self.CROWD_FORGET_S:
                peak[0], peak[1] = peak[0] - 1, now   # someone left a while ago: forget them slowly
            elif sustained == peak[0]:
                peak[1] = now
            if not any(hist) and peak[0] == 0:
                del self._crowd[key], self._peak[key]
        return gains

    def prune(self, now=None):
        now = now or time.time()
        for a in [a for a, s in self.live.items() if now - s.last > self.LIVE_S]:
            del self.live[a]

    def in_range(self, now=None, window=60):
        now = now or time.time()
        return [s for s in self.live.values() if now - s.last <= window]


class BleakScanner:
    """Runs BlueZ scanning through the bleak library and feeds a callback.

    quiet() switches scanning off for a moment, for the friend beacon. A broadcast advert goes
    out from a throwaway random address, and the Bluetooth rules say a radio may refuse to take
    a new random address while it's scanning ("Command Disallowed"). Some radios let it pass;
    the Pi 5's doesn't, and BlueZ only says "Failed to register advertisement". So the beacon
    asks for a second or two of quiet whenever it goes up, which is rarely."""

    def __init__(self, on_advert, bleak_cls=None):
        self.on_advert = on_advert
        self._scanner = None
        self._bleak = bleak_cls     # (the tests pass a stand-in)
        self._holds = 0
        self._kick = asyncio.Event()     # something changed: look again
        self._idle = asyncio.Event()     # scanning is off
        self._idle.set()

    @contextlib.asynccontextmanager
    async def quiet(self, timeout=5):
        """Scanning stays off inside this block (or the block starts after timeout seconds anyway)."""
        self._holds += 1
        self._kick.set()
        try:
            try:
                await asyncio.wait_for(self._idle.wait(), timeout)
            except asyncio.TimeoutError:
                pass
            yield
        finally:
            self._holds -= 1
            self._kick.set()

    @staticmethod
    async def _either(*events):
        waits = [asyncio.ensure_future(e.wait()) for e in events]
        try:
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for w in waits:
                w.cancel()

    async def run(self, stop_event):
        import logging
        _BS = self._bleak
        if _BS is None:
            from bleak import BleakScanner as _BS
        log = logging.getLogger("ble")

        def cb(device, adv):
            # -127 is BlueZ's "no reading" placeholder (e.g. a device that was just connected
            # to, rather than heard advertising). It's not a real signal, so skip it.
            if adv.rssi is None or adv.rssi <= -127:
                return
            details = getattr(device, "details", None) or {}
            props = details.get("props", {}) if isinstance(details, dict) else {}
            self.on_advert(device.address, props.get("AddressType", "random"), adv.rssi,
                           adv.local_name, adv.manufacturer_data, adv.service_uuids, adv.service_data)

        quietly = False
        while not stop_event.is_set():
            self._kick.clear()
            if self._holds:                     # someone wants quiet: wait until they're done
                await self._either(stop_event, self._kick)
                quietly = True
                continue
            try:
                async with _BS(detection_callback=cb, scanning_mode="active"):
                    self._idle.clear()
                    if not quietly:
                        log.info("BLE scanning")
                    quietly = False
                    await self._either(stop_event, self._kick)
            except Exception as e:  # adapter reset, BlueZ restart...
                self._idle.set()
                log.warning("BLE scanner stopped: %s; retrying in 10 s", e)
                try:
                    await asyncio.wait_for(stop_event.wait(), 10)
                except asyncio.TimeoutError:
                    pass
            finally:
                self._idle.set()
        self._idle.set()


async def classic_search(seconds, on_found):
    """
    Ask for discoverable Bluetooth Classic devices (headphones and speakers in pairing mode).

    Classic devices don't broadcast adverts like BLE ones do. They wait to be asked: the
    seeker sends "inquiry" packets and discoverable devices answer with their address,
    and then their name. Your phone's "Pair new device" screen does exactly this. Here we
    ask BlueZ (the Pi's Bluetooth service) to run a Classic ("BR/EDR") discovery alongside
    the BLE scanning, and report each device it finds:
        on_found(address, name, rssi, device_class)
    Classic addresses are fixed, so anything found can be marked as a pal.
    """
    import asyncio
    import logging
    from dbus_fast import BusType, Variant
    from dbus_fast.aio import MessageBus
    log = logging.getLogger("ble")
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        intro = await bus.introspect("org.bluez", "/org/bluez/hci0")
        adapter = bus.get_proxy_object("org.bluez", "/org/bluez/hci0", intro).get_interface("org.bluez.Adapter1")
        root = await bus.introspect("org.bluez", "/")
        om = bus.get_proxy_object("org.bluez", "/", root).get_interface("org.freedesktop.DBus.ObjectManager")

        def report(path, ifaces):
            dev = ifaces.get("org.bluez.Device1")
            if not dev:
                return
            v = {k: (x.value if hasattr(x, "value") else x) for k, x in dev.items()}
            if v.get("AddressType", "public") != "public" or "Class" not in v and "Name" not in v:
                return  # only Classic-style devices here; BLE ones come through the scanner
            on_found(v.get("Address", ""), v.get("Name") or v.get("Alias") or "",
                     v.get("RSSI", -127), v.get("Class"))

        om.on_interfaces_added(report)

        def changed(iface, props, _inv, path=None):
            pass  # RSSI updates for already-known devices arrive via the BLE scanner's callbacks

        await adapter.call_set_discovery_filter({"Transport": Variant("s", "bredr")})
        await adapter.call_start_discovery()
        log.info("Classic search for %d s", seconds)
        try:
            # devices BlueZ already knows about (e.g. found moments ago) are reported too
            await asyncio.sleep(seconds)
            objs = await om.call_get_managed_objects()
            for path, ifaces in objs.items():
                dev = ifaces.get("org.bluez.Device1")
                if dev and "RSSI" in dev:
                    report(path, ifaces)
        finally:
            try:
                await adapter.call_stop_discovery()
            except Exception:
                pass
    finally:
        bus.disconnect()


# Bluetooth "Class of Device": the major class (bits 8-12) says what kind of thing it is
_COD_MAJOR = {1: "Computer", 2: "Phone", 3: "Network device", 4: "Audio device", 5: "Keyboard / mouse",
              6: "Camera / printer", 7: "Wearable", 8: "Toy", 9: "Health device"}
_COD_AUDIO = {1: "Headset", 2: "Hands-free kit", 4: "Microphone", 5: "Speaker", 6: "Headphones",
              7: "Portable audio", 8: "Car audio", 10: "Hi-Fi audio", 12: "Video camera", 15: "TV"}


def describe_class(cod):
    if not cod:
        return None
    major, minor = (cod >> 8) & 0x1F, (cod >> 2) & 0x3F
    if major == 4 and minor in _COD_AUDIO:
        return _COD_AUDIO[minor]
    return _COD_MAJOR.get(major)


# ---------------------------------------------------------------- finding Classic pals

async def inquiry_rssi(mac, seconds=8):
    """
    Run a Classic discovery for a few seconds and return the signal strength (dBm) of one
    device if it answered, else None. Only works while that device is discoverable
    (pairing mode).
    """
    import asyncio
    from dbus_fast import BusType, Variant
    from dbus_fast.aio import MessageBus
    path = "/org/bluez/hci0/dev_" + mac.upper().replace(":", "_")
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    best = None
    try:
        intro = await bus.introspect("org.bluez", "/org/bluez/hci0")
        adapter = bus.get_proxy_object("org.bluez", "/org/bluez/hci0", intro).get_interface("org.bluez.Adapter1")

        async def rssi_now():
            try:
                di = await bus.introspect("org.bluez", path)
                props = bus.get_proxy_object("org.bluez", path, di).get_interface("org.freedesktop.DBus.Properties")
                v = await props.call_get("org.bluez.Device1", "RSSI")
                return v.value
            except Exception:
                return None

        before = await rssi_now()  # an old reading from earlier; must change to count
        await adapter.call_set_discovery_filter({"Transport": Variant("s", "bredr")})
        await adapter.call_start_discovery()
        try:
            for _ in range(int(seconds)):
                await asyncio.sleep(1)
                r = await rssi_now()
                if r is not None and r != before:
                    best = r
                    before = r
        finally:
            try:
                await adapter.call_stop_discovery()
            except Exception:
                pass
    finally:
        bus.disconnect()
    return best


async def l2ping(mac, timeout=3):
    """
    Knock on a Classic device's door: open a basic link and send one echo request, like a
    network "ping". A device that's on and in range (and listening for its owner to
    reconnect) answers, even when it isn't discoverable. Returns the round trip in ms, or None.
    """
    import asyncio
    import re as _re
    try:
        proc = await asyncio.create_subprocess_exec(
            "l2ping", "-c", "1", "-t", str(timeout), mac,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout + 8)
        except BaseException:   # timed out, or the Find was closed: don't leave it knocking
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise
    except (OSError, asyncio.TimeoutError):
        return None
    m = _re.search(r"time ([\d.]+)\s*ms", out.decode(errors="replace"))
    return float(m.group(1)) if m else None
