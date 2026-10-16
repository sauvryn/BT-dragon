"""
Reading planes' own broadcasts (ADS-B), from a radio stick (RTL-SDR) tuned to 1090 MHz.

How it works: an airliner works out where it is from satellite navigation, and twice a second
its transponder broadcasts it on 1090 MHz, along with its height, speed, flight number and a
fixed 24-bit address of its own: "Automatic Dependent Surveillance - Broadcast". Air traffic
control and other aircraft listen, and so can anyone with a cheap TV-tuner stick. Each message
is 112 bits (28 hex digits), and its last 24 bits are a checksum (a CRC), so a message garbled
on the way can be spotted and thrown away.

`rtl_adsb` (part of the rtl-sdr package) turns the radio signal into messages, one per line:
    *8d4840d6202cc371c32ce0576098;
and this module turns those into what's in them. Only "extended squitter" messages (downlink
formats 17 and 18) are read: those are the ADS-B broadcasts.

Positions are packed into 17 bits each for latitude and longitude ("Compact Position Reporting"):
too few to say where on Earth on their own, but enough to say where within a zone a few
hundred kilometres across. Knowing roughly where the receiver is (the Lair, or his GPS) is
enough to work out which zone, so one message gives a position. (The usual reference for all
of this is Junzi Sun's "The 1090 Megahertz Riddle", whose examples are in the tests.)
"""
import math

CHARS = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ##### ###############0123456789######"
GEN = 0x1FFF409                     # the Mode S CRC's generator polynomial (25 bits)

# the emitter category: (type code, category) -> kind (see planes.KINDS)
CATEGORY = {(4, 1): "light", (4, 2): "small", (4, 3): "large", (4, 4): "vortex", (4, 5): "heavy",
            (4, 6): "performance", (4, 7): "rotorcraft",
            (3, 1): "glider", (3, 2): "balloon", (3, 3): "parachutist", (3, 4): "ultralight", (3, 6): "uav",
            (3, 7): "space",
            (2, 1): "emergency", (2, 3): "service", (2, 4): "obstacle", (2, 5): "obstacle", (2, 6): "obstacle",
            (2, 7): "obstacle"}


def crc_ok(bits, n):
    """The remainder of the whole message divided by the generator is zero when it's intact."""
    for i in range(n - 24):
        if bits >> (n - 1 - i) & 1:
            bits ^= GEN << (n - 25 - i)
    return bits & 0xFFFFFF == 0


def _nl(lat):
    """How many longitude zones there are at this latitude (fewer towards the poles)."""
    if abs(lat) >= 87:
        return 1 if abs(lat) > 87 else 2
    a = 1 - math.cos(math.pi / 30)
    return int(math.floor(2 * math.pi / math.acos(1 - a / math.cos(math.pi * lat / 180) ** 2)))


def cpr_local(odd, lat_cpr, lon_cpr, ref_lat, ref_lon):
    """A position from one message, near a known reference (within about 300 km)."""
    dlat = 360 / (59 if odd else 60)
    j = math.floor(ref_lat / dlat) + math.floor((ref_lat % dlat) / dlat - lat_cpr + 0.5)
    lat = dlat * (j + lat_cpr)
    dlon = 360 / max(_nl(lat) - (1 if odd else 0), 1)
    m = math.floor(ref_lon / dlon) + math.floor((ref_lon % dlon) / dlon - lon_cpr + 0.5)
    return lat, dlon * (m + lon_cpr)


def _altitude(field):
    """The 12-bit altitude field: with the Q bit set, 25-foot steps from -1000 ft."""
    if not field:
        return None
    if field & 0x10:
        n = ((field & 0xFE0) >> 1) | (field & 0x0F)
        return n * 25 - 1000
    return None                     # (the old 100-foot Gillham code: rare now, not read)


def decode(line, ref=None):
    """One line from rtl_adsb -> a dict, or None if it isn't an intact ADS-B message.
    Keys: icao, tc, and as available: kind (emitter category), callsign, alt_ft, lat, lon,
    speed_kt, track."""
    h = line.strip().strip("*;").lower()
    if len(h) != 28:
        return None
    try:
        bits = int(h, 16)
    except ValueError:
        return None
    df = bits >> 107
    if df not in (17, 18) or not crc_ok(bits, 112):
        return None
    me = (bits >> 24) & ((1 << 56) - 1)
    tc = me >> 51
    out = {"icao": f"{(bits >> 80) & 0xFFFFFF:06x}", "tc": tc}
    if 1 <= tc <= 4:
        ca = (me >> 48) & 7
        out["kind"] = CATEGORY.get((tc, ca), "unknown")
        cs = "".join(CHARS[(me >> (42 - 6 * i)) & 0x3F] for i in range(8))
        out["callsign"] = cs.replace("#", "").strip()
    elif 9 <= tc <= 18:
        out["alt_ft"] = _altitude((me >> 36) & 0xFFF)
        if ref:
            odd = (me >> 34) & 1
            lat_cpr = ((me >> 17) & 0x1FFFF) / 131072
            lon_cpr = (me & 0x1FFFF) / 131072
            out["lat"], out["lon"] = cpr_local(odd, lat_cpr, lon_cpr, ref[0], ref[1])
    elif tc == 19 and ((me >> 48) & 7) in (1, 2):
        ew_dir, ew = (me >> 42) & 1, ((me >> 32) & 0x3FF) - 1
        ns_dir, ns = (me >> 31) & 1, ((me >> 21) & 0x3FF) - 1
        if ew >= 0 and ns >= 0:
            vx, vy = (-ew if ew_dir else ew), (-ns if ns_dir else ns)
            out["speed_kt"] = round(math.hypot(vx, vy))
            out["track"] = round(math.degrees(math.atan2(vx, vy)) % 360, 1)
    return out


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(min(1, math.sqrt(a)))
