"""
Finding him by Wi-Fi, for a Harald with no GPS (optional, off unless switched on in the den).

How it works: every Wi-Fi router announces itself about ten times a second, with a unique
hardware address (its BSSID), and Harald already hears those announcements on every scan.
Routers almost never move, so a service that knows roughly where millions of them sit can
take "I can hear these networks, this loudly" and answer "then you're about here". The
usual method is a weighted average of the known router positions, the louder ones counting
for more, because a loud router is usually a near one. In a town that's typically within
20-50 m; with only one or two networks around it doesn't work at all.

The service is beaconDB (https://beacondb.net), a free, community-built database that
replaced Mozilla's. Harald only *asks* it: he never sends it sightings of his own, because
his positions would have come from beaconDB in the first place.

PRIVACY: the list of networks around you IS where you are. Every lookup tells beaconDB
where Harald is, to within tens of meters. Its privacy notice says it doesn't keep the
networks asked about or the answer, but its server logs (your IP address, the time) are kept
for 28 days. That's why it's off by default, only runs when there's no GPS at all, and asks
sparingly: at most once every couple of minutes, and not again while the same networks
are around (he hasn't moved).

What a Wi-Fi position is good for: claiming lands and realms, spotting landmarks and
discovering green spaces. What it isn't: WiGLE uploads (an estimate isn't a sighting),
walk distances, or walks, runs and rides in green spaces (a Wi-Fi position jumps around by
tens of meters while you sit still, so he'd count walks you never took).
"""
import json
import logging
import time
import urllib.error
import urllib.request

from . import __version__

log = logging.getLogger("wifipos")

URL = "https://api.beacondb.net/v1/geolocate"
USER_AGENT = f"BTDragon/{__version__} (https://github.com/sauvryn/BT-dragon)"
MIN_NETWORKS = 2           # one router can't place you (and the service won't try)
MAX_NETWORKS = 20          # the loudest ones say plenty
MIN_RSSI = -90
MAX_ACCURACY_M = 200       # anything vaguer is a guess, not a position
ASK_EVERY_S = 120          # at most one lookup every two minutes
SAME_PLACE = 0.6           # this much of the loudest networks unchanged: still in the same place
FRESH_S = 180              # how long a Wi-Fi position counts as "where he is now"


def moves_around(bssid):
    """Phones, car hotspots and the like use 'locally administered' addresses (the second
    lowest bit of the first byte set). They travel with their owners, so they say nothing
    about where you are."""
    try:
        return bool(int(bssid.split(":")[0], 16) & 0x02)
    except (ValueError, IndexError):
        return True


def usable(aps, skip_ssids=()):
    """The networks worth asking about, loudest first."""
    out = []
    for ap in aps:
        ssid = ap.get("ssid") or ""
        if ssid in skip_ssids or ssid.lower().endswith("_nomap"):     # _nomap: "please don't map me"
            continue
        if ap.get("rssi", -100) < MIN_RSSI or moves_around(ap.get("bssid", "")):
            continue
        out.append(ap)
    out.sort(key=lambda a: -a.get("rssi", -100))
    return out[:MAX_NETWORKS]


def request_body(aps):
    return {"considerIp": False,                       # never fall back to "your internet address is in X"
            "fallbacks": {"ipf": False, "lacf": False},
            "wifiAccessPoints": [{"macAddress": a["bssid"].lower(), "signalStrength": int(a["rssi"])} for a in aps]}


def parse_answer(data):
    """beaconDB's answer -> (lat, lon, accuracy_m) or None."""
    try:
        loc, acc = data["location"], float(data["accuracy"])
        lat, lon = float(loc["lat"]), float(loc["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if acc > MAX_ACCURACY_M or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon, acc


def ask_beacondb(aps, timeout=15):
    """Blocking: run it in a thread. (lat, lon, accuracy) or None if it doesn't know."""
    req = urllib.request.Request(URL, data=json.dumps(request_body(aps)).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return parse_answer(json.load(r))
    except urllib.error.HTTPError as e:
        if e.code == 404:            # "not found": it doesn't know these networks
            return None
        raise


class WifiPosition:
    def __init__(self, store, asker=ask_beacondb):
        self.store = store
        self.asker = asker
        self.fix = None            # {"lat", "lon", "acc", "ts", "via": "wifi"}
        self.last_try = 0.0
        self.last_set = frozenset()
        self.lookups = 0
        self.status = "off"
        self._busy = False

    @property
    def enabled(self):
        return bool(self.store.get("wifi_position", False))

    def set_enabled(self, on):
        self.store.put("wifi_position", bool(on))
        if not on:
            self.fix, self.last_set, self.status = None, frozenset(), "off"

    def current(self, now=None):
        now = now or time.time()
        return self.fix if self.fix and now - self.fix["ts"] <= FRESH_S else None

    def wanted(self, aps, have_gps, online, skip_ssids=(), now=None):
        """The networks to ask about now, or None (and why, in self.status)."""
        now = now or time.time()
        if not self.enabled:
            self.status = "off"
            return None
        if have_gps:
            self.status = "not needed: GPS is working"
            return None
        if not online:
            self.status = "waiting for the hotspot (it needs the internet)"
            return None
        if self._busy:
            return None
        nets = usable(aps, skip_ssids)
        if len(nets) < MIN_NETWORKS:
            self.status = "not enough Wi-Fi around to tell"
            return None
        loud = frozenset(a["bssid"] for a in nets[:8])
        if self.fix and self.last_set and len(loud & self.last_set) >= SAME_PLACE * min(len(loud), len(self.last_set)):
            self.fix["ts"] = now               # same networks: still here, no need to ask again
            return None
        if now - self.last_try < ASK_EVERY_S:
            return None
        return nets

    async def locate(self, nets, now=None):
        import asyncio
        self._busy, self.last_try = True, now or time.time()
        try:
            got = await asyncio.to_thread(self.asker, nets)
            self.lookups += 1
            if got:
                lat, lon, acc = got
                self.fix = {"lat": lat, "lon": lon, "acc": round(acc), "alt": 0.0, "ts": time.time(), "via": "wifi"}
                self.last_set = frozenset(a["bssid"] for a in nets[:8])
                self.status = f"found by Wi-Fi, to within about {round(acc)} m"
            else:
                self.fix, self.last_set = None, frozenset()
                self.status = "beaconDB doesn't know the networks here"
        except Exception as e:
            log.info("Wi-Fi position lookup failed: %s", e)
            self.status = "couldn't reach beaconDB"
        finally:
            self._busy = False
        return self.fix
