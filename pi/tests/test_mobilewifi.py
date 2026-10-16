"""Mobile Wi-Fi: cars, dashcams, buses, trains, phone hotspots and pocket routers recognized by
name, a smaller treat, no berries, and never uploaded to WiGLE (not even sightings saved before this)."""
import tempfile
import time

from bt_dragon import config, tuning
from bt_dragon.app import Dragon
from bt_dragon.mobilewifi import is_mobile, kind

for name in ("Audi_MMI_1234", "VW_WLAN_5678", "My VW 1234", "My SEAT 1234", "InCarHotspot-123456", "CarPlay_1a2b",
             "DIRECT-BMW 12345", "BMW 12345 CarPlay", "MB Hotspot 12345 5.0 GHz", "MBUX 12345", "MYCAR1234",
             "Porsche_WLAN_1234", "Toyota-12345", "MINI12345 CarPlay", "MINI 12345", "BlackVue750X-E12345",
             "70mai_Pro Plus+_d12f", "YICarCam_DFA123", "Dash-1234", "Jamie's Car", "Car-12a", "Land Rover Dashcam 1",
             "stagecoach-wifi", "BeeNetwork_Wifi", "Northern WiFi", "TfGM_MOBILE", "SamsaraHotSpot"):
    assert kind(name) == "vehicle", name
for name in ("Oxford Uni Guest", "Cardwells", "Cardwell Est Wifi", "BT Smart Hub", "Seaton Cafe", "Mini-PC",
             "TfGM_CORPORATE_INT", "SKY12345", "Domino's Free WiFi", "", None, "Fordham", "Kiamo", "BTWholeHome-SSMG",
             "HUAWEI-B535-1A2B", "ZTE_FABD68", "Pixelated Cafe", "Honor Oak Library", "Galaxyland Arcade guests",
             "Vivobarefoot Staff", "Motorhome Park", "TP-Link_1234", "VM1234567", "EE-Hub-abc1", "Mobile Library"):
    assert not is_mobile(name), name
for name in ("Sam's iPhone", "iPhone", "AndroidAP1a2b", "AndroidAP_1234", "Galaxy A52 1a2b", "Galaxy S23 Ultra",
             "Pixel_1234", "Pixel 7 Pro", "Redmi Note 12", "OnePlus 9", "moto g 5G", "VodafoneMobileWiFi-CF12_5.0GHz",
             "EE-MiFi-12ab", "Jane's Phone", "HUAWEI P30 lite", "Xperia 10", "Nothing Phone (2)", "POCO F5"):
    assert kind(name) == "phone", name

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
fix = {"lat": 51.5, "lon": -0.12, "alt": 10.0, "acc": 5.0, "ts": time.time(), "utc": time.time()}
app.gps.current = lambda: fix
app.clock_ok = lambda: True
app.home_zone.inside = lambda lat, lon: False


def ap(ssid, bssid, auth="[WPA2-PSK-CCMP][ESS]", sec="wpa2"):
    return {"bssid": bssid, "ssid": ssid, "auth": auth, "security": sec, "channel": 6, "freq": 2437, "rssi": -60}


app.pet.hunger, app.pet.xp, app.pet.joy = 10.0, 0, 10.0
app.handle_aps([ap("Audi_MMI_1234", "aa:00:00:00:00:01")])
assert abs(app.pet.hunger - 10 - tuning.get("treat_food_mobile")) < 1e-6 and app.pet.xp == tuning.get("treat_xp_mobile")
assert abs(app.pet.joy - 10 - tuning.get("treat_joy_mobile")) < 1e-6
assert "VROOM" in app.pet.message and any("Vehicle Wi-Fi: Audi_MMI_1234" in t for _, t in
                                          [(e["kind"], e["text"]) for e in app.store.events(5)])
app.handle_aps([ap("Sam's iPhone", "aa:00:00:00:00:04")])
assert "BLEEP" in app.pet.message and app.store.events(1)[0]["text"].startswith("Mobile Wi-Fi: Sam's iPhone")
xp = app.pet.xp
app.handle_aps([ap("Home Router", "aa:00:00:00:00:02")])
assert app.pet.xp - xp == tuning.get("treat_xp_wpa2")
# only the stationary one is a WiGLE sighting, and an older car sighting isn't uploaded either
app.store.ap_seen(ap("VW_WLAN_9999", "aa:00:00:00:00:03"), time.time())
app.store.ap_observe("aa:00:00:00:00:03", time.time(), -50, fix)
app.store.ap_seen(ap("AndroidAP1234", "aa:00:00:00:00:05"), time.time())
app.store.ap_observe("aa:00:00:00:00:05", time.time(), -50, fix)
pend = {r["ssid"] for r in app.store.pending_obs()}
assert pend == {"Home Router"}, pend
# the defaults, from a day in a big city
assert (tuning.get("joy_empty_min"), tuning.get("snack_joy"), tuning.get("treat_joy"), tuning.get("feast_joy"),
        tuning.get("pack_cap"), tuning.get("treat_xp_open"), tuning.get("treat_xp_enterprise")) == (600, 0.02, 0.5, 5, 50, 4, 5)
print("mobile wi-fi ok")
