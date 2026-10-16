"""Run: python3 -m tests.test_parsers  (from the pi folder)"""
from bt_dragon.wifi import parse_iw_scan
from bt_dragon.gps import Gps
from bt_dragon.ble import classify, address_is_stable, species_from_name
from bt_dragon.wigle import build_csv

IW = """BSS aa:bb:cc:dd:ee:01(on wlan0) -- associated
\tlast seen: 120 ms ago
\tTSF: 0 usec (0d, 00:00:00)
\tfreq: 2437.0
\tbeacon interval: 100 TUs
\tcapability: ESS Privacy ShortSlotTime (0x0411)
\tsignal: -41.00 dBm
\tSSID: MyHotspot
\tDS Parameter set: channel 6
\tRSN:\t * Version: 1
\t\t * Group cipher: CCMP
\t\t * Pairwise ciphers: CCMP
\t\t * Authentication suites: PSK SAE
\t\t * Capabilities: 16-PTKSA-RC 1-GTKSA-RC (0x000c)
\tWPS:\t * Version: 1.0
BSS 11:22:33:44:55:66(on wlan0)
\tfreq: 2412
\tcapability: ESS ShortSlotTime (0x0401)
\tsignal: -77.00 dBm
\tSSID: Coffee\\x20Shop
BSS 11:22:33:44:55:77(on wlan0)
\tfreq: 2462
\tcapability: ESS Privacy (0x0411)
\tsignal: -88.00 dBm
\tSSID: \\x00\\x00\\x00
\tRSN:\t * Version: 1
\t\t * Pairwise ciphers: CCMP
\t\t * Authentication suites: SAE
"""
aps = parse_iw_scan(IW)
assert aps[0]["age_ms"] == 120 and "age_ms" not in aps[1]   # how old each sighting is
for a in aps: print(a["bssid"], repr(a["ssid"]), a["channel"], a["rssi"], a["auth"], a["security"])
assert aps[0]["auth"] == "[WPA2-PSK-CCMP][WPA3-SAE-CCMP][WPS][ESS]" and aps[0]["channel"] == 6
assert aps[1]["ssid"] == "Coffee Shop" and aps[1]["security"] == "open" and aps[1]["channel"] == 1
assert aps[2]["security"] == "wpa3" and aps[2]["channel"] == 11

g = Gps()
g.feed("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47")
g.feed("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A")
print(g.fix, g.state())
assert abs(g.fix["lat"] - 48.1173) < 1e-4 and abs(g.fix["lon"] - 11.516667) < 1e-4 and g.state() == "FIX"
g.feed("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*48")  # bad checksum ignored

print(classify(None, {0x004C: bytes([0x12, 0x19]) + bytes(25)}, [], {}))
print(classify(None, {0x004C: bytes([0x12, 0x02, 0, 0])}, [], {}))
print(classify(None, {0x004C: bytes([0x10, 0x05, 1, 2, 3, 4, 5])}, [], {}))
print(classify("Bob's AirPods", {0x004C: bytes([0x07, 0x19, 0x01, 0x14, 0x20]) + bytes(22)}, [], {}))
print(classify(None, {}, [], {"0000feaa-0000-1000-8000-00805f9b34fb": bytes([0x41, 1])}))
print(classify("Sam's Fitbit", {}, [], {}), species_from_name("MI_SCALE"), species_from_name("Charge 5 A1B2"))
# Amazon's service: an Echo (no name) is an Echo; Alexa-ready headphones with a name go by the name
AMZ = ["0000fe03-0000-1000-8000-00805f9b34fb"]
assert classify(None, {}, AMZ, {})[1] == "Amazon Echo / Fire"
assert "JBL Tune" in classify("JBL Tune 520BT-LE", {0x0057: b"\x01"}, AMZ, {})[1]
assert classify("JBL Tune 520BT-LE", {}, ["0000feed-0000-1000-8000-00805f9b34fb"] + AMZ, {})[1] == "Tile tracker"
assert address_is_stable("C0:00:00:00:00:00", "random") and not address_is_stable("5A:00:00:00:00:00", "random")
print(build_csv([{"bssid": "AA", "ssid": "x,y", "auth": "[ESS]", "ts": 0, "channel": 1, "freq": 2412, "rssi": -50,
                  "lat": 39.8, "lon": -98.5, "alt": 90, "acc": 5}]))
print("all good")
