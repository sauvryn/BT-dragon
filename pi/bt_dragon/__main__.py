"""
Run Harald:   python3 -m bt_dragon            (on the Pi, as the bt-dragon service does)
Try him out:  python3 -m bt_dragon --simulate (any computer: fake Bluetooth, Wi-Fi and GPS)
"""
import argparse
import asyncio
import logging
import random
import time

from . import config
from .app import Dragon


def _nmea(kind, body, talker="GP"):
    cs = 0
    for ch in f"{talker}{kind},{body}":
        cs ^= ord(ch)
    return f"${talker}{kind},{body}*{cs:02X}"


def _dm(v, pos, neg, width):
    h = pos if v >= 0 else neg
    v = abs(v)
    d = int(v)
    return f"{d:0{width}d}{(v - d) * 60:07.4f}", h


async def simulate(app: Dragon, seconds):
    """Feed fake but realistic traffic: a walk through your local town center."""
    rnd = random.Random(7)
    lat, lon = 39.8283, -98.5795  # an imaginary town in the middle of the map
    gadgets = [  # fixed-address gadgets
        ("C0:11:22:33:44:55", "public", "JBL Flip 5", {0x0057: b"\x01"}, [], {}),
        ("F4:AA:BB:CC:DD:01", "random", "LE-Bose QC35 II", {0x009E: b"\x00"}, [], {}),
        ("D8:12:34:56:78:9A", "random", "[TV] Samsung Q60 Series (55)", {0x0075: b"\x42"}, [], {}),
        ("E1:23:45:67:89:AB", "random", "Tile", {}, ["0000feed-0000-1000-8000-00805f9b34fb"], {}),
    ]
    pods = {0x004C: bytes([0x07, 0x19, 0x01, 0x0E, 0x20]) + bytes(22)}
    phone = {0x004C: bytes([0x10, 0x05, 0x01, 0x18, 0x44, 0x00, 0x00])}
    findmy_away = {0x004C: bytes([0x12, 0x19]) + bytes(25)}
    aps = []
    for i in range(40):
        sec = rnd.choice(["wpa2"] * 8 + ["open", "wpa3"])
        auth = {"wpa2": "[WPA2-PSK-CCMP][ESS]", "open": "[ESS]", "wpa3": "[WPA3-SAE-CCMP][ESS]"}[sec]
        aps.append({"bssid": ":".join(f"{rnd.randrange(256):02X}" for _ in range(6)),
                    "ssid": rnd.choice(["NETGEAR", "xfinitywifi", "ATT", "Spectrum-", "Linksys", "coffee_shop_Guest", "Library_Free"])
                            + f"{rnd.randrange(9999):04d}",
                    "auth": auth, "security": sec, "channel": rnd.choice([1, 6, 11]), "rssi": -90,
                    "freq": 2412})
    aps[3]["ssid"] = "Bakery_WiFi_nomap"
    # pretend Wikipedia: two famous places along the walk and one off to the side
    from . import landmarks as lmmod
    lmmod.realm_landmarks = lambda realm: [
        {"qid": "Q-sim1", "title": "Old Town Hall", "lat": lat + 0.0003, "lon": lon + 0.0004, "langs": 14},
        {"qid": "Q-sim2", "title": "Grand Stone Bridge", "lat": lat + 0.0009, "lon": lon - 0.0002, "langs": 31},
        {"qid": "Q-sim3", "title": "Hilltop Castle", "lat": lat + 0.004, "lon": lon + 0.006, "langs": 22},
        {"qid": "Q-sim4", "title": "Corner Pub", "lat": lat + 0.0002, "lon": lon, "langs": 1},
    ]
    start = time.time()
    t = 0
    while not app.stop.is_set() and time.time() - start < seconds:
        t += 1
        # walk for the first 70 s, stand still for 40 s, then drive
        speed = 1.4 if t <= 70 else 0.0 if t <= 110 else 12.0
        lat += speed / 111320
        if t == 2:
            app.store.put("steps_last", 20000)   # pretend: last time, the phone had counted 20,000
            app.on_steps(23500)                  # ...and now 23,500: a story of 3,500 steps
        hhmmss = time.strftime("%H%M%S", time.gmtime())
        ddmmyy = time.strftime("%d%m%y", time.gmtime())
        la, lh = _dm(lat, "N", "S", 2)
        lo, oh = _dm(lon, "E", "W", 3)
        app.gps.feed(_nmea("GGA", f"{hhmmss},{la},{lh},{lo},{oh},1,09,0.9,92.0,M,48.0,M,,"), "sim")
        app.gps.feed(_nmea("RMC", f"{hhmmss},A,{la},{lh},{lo},{oh},{speed / 0.514444:.1f},0.0,{ddmmyy},,,A"), "sim")
        if t % 5 == 1:  # the satellites in view, as GPSd Forwarder would pass them on
            for talker, prns in (("GP", [2, 5, 12, 25, 29, 44]), ("GL", [66, 75, 81]),
                                 ("GA", [4, 9, 19, 36]), ("GB", [11, 23, 37])):
                groups = ",".join(f"{p},{rnd.randrange(10, 80)},{rnd.randrange(360)},{rnd.randrange(18, 45)}"
                                  for p in prns[:4])
                app.gps.feed(_nmea("GSV", f"1,1,{len(prns)},{groups}", talker), "sim")
        # the barometer: a flight of stairs at 50 s, otherwise steady air
        hpa = 1012.40 - (0.5 if t >= 50 else 0.0) + rnd.uniform(-0.01, 0.01)
        for _ in range(5):
            app.on_pressure([hpa])
        # rotating-address phones and earbuds wander past
        for _ in range(rnd.randrange(0, 4)):
            addr = "5" + "".join(rnd.choice("0123456789ABCDEF") for _ in range(1)) + ":" + \
                   ":".join(f"{rnd.randrange(256):02X}" for _ in range(5))
            app.on_advert(addr, "random", rnd.randrange(-95, -55), None,
                          rnd.choice([phone, phone, pods, {0x0006: b"\x01\x09"}, {0x0075: b"\x01"}]), [], {})
        for g in gadgets:
            if rnd.random() < 0.6:
                app.on_advert(g[0], g[1], rnd.randrange(-80, -45), g[2], g[3], g[4], g[5])
        app.on_advert("7A:00:11:22:33:44", "random", -70, None, findmy_away, [], {})
        if 20 <= t <= 40 or t >= 70:  # a friend's dragon wanders by, leaves, comes back
            from .friends import encode, COMPANY
            app.on_advert("C2:AA:00:00:00:01", "random", -66, None,
                          {COMPANY: encode(bytes.fromhex("0badf00d"), 3, 1, "Sigrid")}, [], {})
        if t == 30:
            app.handle_aps([{"bssid": "DE:AD:BE:EF:DE:AD", "ssid": "", "auth": "[ESS]", "security": "open",
                             "channel": 1, "rssi": -60, "freq": 2412}])
        if t % 4 == 0:
            for ap in aps[: min(len(aps), 3 + t // 2)]:
                ap["rssi"] = rnd.randrange(-92, -50)
            app.handle_aps(aps[: min(len(aps), 3 + t // 2)])
        await asyncio.sleep(1)
    app.stop.set()


def main():
    ap = argparse.ArgumentParser(prog="bt_dragon")
    ap.add_argument("--config", help="path to bt-dragon.toml")
    ap.add_argument("--simulate", action="store_true", help="fake radios, draw to PNG")
    ap.add_argument("--seconds", type=int, default=120, help="simulation length")
    ap.add_argument("--data", help="override data directory")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(name)s: %(message)s")
    cfg = config.load(args.config)
    if args.data:
        cfg["data_dir"] = args.data
    if args.simulate:
        cfg["trackers"]["alert_after_minutes"] = 1
        cfg["trackers"]["min_moved_meters"] = 50
        cfg["display"]["min_seconds_between_updates"] = 3
        from . import activity
        activity.Activity.END_AFTER_S = 12  # end the walk quickly in the simulation
        activity.Activity.MIN_ADVENTURE_M = 50
    from . import backup
    restored = backup.apply_pending(cfg)        # a backup waiting to be put back, if any
    if restored:
        cfg = config.load(args.config) if not args.data else dict(config.load(args.config), data_dir=args.data)
    app = Dragon(cfg, simulate=args.simulate)
    if restored:
        app.store.event("restore", restored)

    async def go():
        app.stop = asyncio.Event()
        app.upload_lock = asyncio.Lock()
        extra = [simulate(app, args.seconds)] if args.simulate else []
        await app.run(extra)

    asyncio.run(go())


if __name__ == "__main__":
    main()
