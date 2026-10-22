"""The Gadget Journal's new types (personal care gadgets above all) and the Wi-Fi Journal."""
import json
import os
import re
import sqlite3
import tempfile
import time

from bt_dragon import achievements, ble, journal, mobilewifi, scores, wifijournal
from bt_dragon.diary import DiaryFiles
from bt_dragon.store import Store

# ---------------------------------------------------------------- personal care gadgets: heard, never named
CARE = ble.CARE
assert ble.classify("Dexcom7AB", {}, [], {})[1:] == (CARE, "care")
assert ble.classify(None, {0x0282: b"\x01\x02"}, [], {})[1:] == (CARE, "care")              # Sonova (Phonak)
assert ble.classify("Mum's hearing aid", {}, [], {})[1:] == (CARE, "care")
assert ble.classify(None, {}, ["00001808-0000-1000-8000-00805f9b34fb"], {})[1:] == (CARE, "care")   # Glucose
assert ble.classify(None, {}, [], {"0000fdf0-0000-1000-8000-00805f9b34fb": b"\x01"})[1:] == (CARE, "care")  # ASHA
assert ble.classify(None, {0x0BA3: b"x"}, [], {})[2] != "care"                # Sonova Consumer: Sennheiser headphones
assert ble.classify("MOMENTUM 4", {0x0BA3: b"x"}, [], {})[2] == "named"
assert ble.classify("JBL Flip 6", {}, [], {})[2] == "named"
assert ble.classify("Tile", {}, ["0000feed-0000-1000-8000-00805f9b34fb"], {})[2] == "tracker"    # trackers still first
# every company number on the list is a real one from the SIG's list, and it's a care maker
for c in ble.CARE_COMPANIES:
    assert c in ble.COMPANIES, hex(c)
assert all(not ble.COMPANIES[c].startswith(("Sonova Consumer", "Signia")) for c in ble.CARE_COMPANIES)
# the live picture keeps no name for one, even when the name comes later
w = ble.BleWatcher()
s, first, _ = w.advert("C1:22:33:44:55:66", "random", -60, "Dexcom 9Z", {}, [], {}, now=1000)
assert s.label == CARE and s.name is None and s.kind == "care"
s, _, _ = w.advert("C1:22:33:44:55:77", "random", -60, None, {0x00D0: b"\x01"}, [], {}, now=1000)
s, _, _ = w.advert("C1:22:33:44:55:77", "random", -60, "Sam's G7", {0x00D0: b"\x01"}, [], {}, now=1001)
assert s.name is None and s.label == CARE
s, _, _ = w.advert("C1:22:33:44:55:88", "random", -60, None, {0x0999: b"\x01"}, [], {}, now=1000)    # a maker...
s, _, _ = w.advert("C1:22:33:44:55:88", "random", -60, "ResMed 1234", {0x0999: b"\x01"}, [], {}, now=1001)
assert s.label == CARE and s.name is None                              # ...that turns out to be one
# old labels that were care gadgets
for lab in ("Abbott device", "Dexcom#", "ResMed #", "Sonova device", "Omron Healthcare device", "WheelAir",
            "Dynamic Controls device", "GN Hearing device", "Insulet device", "Vire Health POWER-#", "REVITIVEW#"):
    assert ble.is_care_label(lab), lab
for lab in ("Sonova Consumer MOMENTUM #", "Samsung device", "JBL Flip #", CARE, "Garmin device", "Omron device"):
    assert not ble.is_care_label(lab), lab

# ...folded into the one type, in the life list, the diary and the diary files
d = tempfile.mkdtemp()
st = Store(os.path.join(d, "t.db"))
now = time.time()
for key, lab, kind, meals in [("abbott-device", "Abbott device", "maker", 3), ("dexcom#", "Dexcom#", "named", 2),
                              ("jbl-flip-#", "JBL Flip #", "named", 5), ("resmed-#", "ResMed #", "named", 1)]:
    st.db.execute("INSERT INTO species VALUES (?, ?, ?, ?, ?, ?)", (key, lab, kind, now - 100, now, meals))
st.event("species", "New type: Abbott device")
st.event("species", "New type: Dexcom#")
st.event("species", "New type: JBL Flip #")
files = DiaryFiles(os.path.join(d, "diary"))
files.write(now, "species", "New type: ResMed #")
files.flush()
old = st.fold_care(ble.is_care_label, CARE, ble.CARE_KEY)
assert sorted(old) == ["Abbott device", "Dexcom#", "ResMed #"]
rows = {r["label"]: r for r in st.species_list()}
assert set(rows) == {CARE, "JBL Flip #"} and rows[CARE]["meals"] == 6 and rows[CARE]["kind"] == "care"
texts = [e["text"] for e in st.events(10)]
assert texts.count(f"New type: {CARE}") == 2 and "New type: JBL Flip #" in texts
assert not any(x in " ".join(texts) for x in ("Abbott", "Dexcom", "ResMed"))
assert files.replace_labels(old, CARE) == 1
for name, _ in files.files():
    with open(os.path.join(files.folder, name), encoding="utf-8-sig") as f:
        body = f.read()
    assert "ResMed" not in body and CARE in body
assert st.fold_care(ble.is_care_label, CARE, ble.CARE_KEY) == []          # nothing left to fold

# ---------------------------------------------------------------- the Gadget Journal's types
expect = {
    "Personal care gadget": "care", "LE-Bose QC Earbuds": "headphones", "Galaxy Buds# Pro (#) LE": "headphones",
    "JBL Tune #NC": "headphones", "Sonova Consumer MOMENTUM #": "headphones", "JBL Flip #": "speaker",
    "Harman International JBL Charge ": "speaker", "Charge #": "smartwatch", "Samsung Galaxy Watch# (AB#C)": "smartwatch",
    "Garmin fenix #": "smartwatch", "ELK-BLEDOM": "lights", "Triones:#": "lights", "Govee_H#_#": "lights",
    "Signify Netherlands device": "hue", "[LG] webOS TV UM#PLB": "appliance", "Samsung Washer": "appliance",
    "Daikin": "appliance", "Amazon Ring a#": "smart-home", "August Home device": "smart-home",
    "Echo Dot-PD#": "echo", "Pawfit-ABCD": "pets", "Procter & Gamble Oral-B Toothbru": "grooming",
    "JLR-BLE-Peripheral": "car", "BLE_Garmin Driv": "car", "Blackvu#X-#": "dashcam", "70mai device": "dashcam",
    "Shimano device": "bike", "smart system eBike": "bike", "Interphone TOUR BLE": "intercom", "Sena device": "intercom",
    "DTCO-#": "tacho", "OBDeleven #": "obd", "WavePlus zappi_#": "ev", "Rolec_DMH#": "ev",
    "Victron Energy device": "camper", "Garmin BLE_CamperCam #": "dashcam", "GoPro device": "camera",
    "DJI-MAVIC#PRO-#": "camera", "Quest #": "console", "Nintendo device": "console", "Seiko Epson device": "printer",
    "SumUp #": "printer", "Square device": "printer", "Apple Pencil": "hid", "Mi": "xiaomi",
    "iPhone / iPad / Mac": "apple-nearby", "AirPods Pro 2": "airpods",
}
for lab, cid in expect.items():
    c = journal.category(lab)
    assert c and c[0] == cid, (lab, c and c[0], cid)
for lab in ("Samsung device", "Garmin device", "Bose device", "Sony device", "Mystery-ish #", "Maker 0x0C98 gadget"):
    assert journal.category(lab) is None, lab
ids = [c[0] for c in journal.CATALOGUE]
assert len(ids) == len(set(ids)) and all(i in ids for i, _ in journal.MATCH)
for c in journal.CATALOGUE:
    assert c[1] in journal.GROUPS and c[4] and c[9] and all(u.startswith("https://") for _, u in c[9]), c[0]
assert set(achievements.GADGET_GROUPS) == set(journal.GROUPS)
# the dragon is never "he" on a card
words = " ".join(" ".join(c[6:9]) for c in journal.CATALOGUE)
assert not re.search(r"\b(he|him|his|himself)\b", words, re.I)

# points: a model with a type now still counts as a field find, so nothing is worth less than before
species = [{"label": lab, "kind": "named", "meals": 1, "first_seen": now} for lab in
           ("JBL Flip #", "JBL Go #", "ELK-BLEDOM", "Garmin device", "iPhone / iPad / Mac")]
old_score = scores.POINTS["Common"] + 4 * journal.FIELD_POINTS                 # (iPhone, and four field finds)
new = journal.score(species)
assert new == old_score + scores.POINTS[journal.CAT_BY_ID["speaker"][3]] + scores.POINTS[journal.CAT_BY_ID["lights"][3]]
page = journal.page_data("Ember", species)
items = {i["id"]: i for g in page["groups"] for i in g["items"]}
assert [x["label"] for x in items["speaker"]["card"]["mine"]["list"]] == ["JBL Flip #", "JBL Go #"]
assert {x["id"]: x["count"] for x in page["extras"]}["named"] == 1          # Garmin device was "named" here
care_page = journal.page_data("Ember", [{"label": CARE, "kind": "care", "meals": 4, "first_seen": now}])
ci = {i["id"]: i for g in care_page["groups"] for i in g["items"]}["care"]
assert ci["found"] and ci["card"]["mine"]["list"] == [] and "nobody else's business" in ci["card"]["text"][1]

# ---------------------------------------------------------------- the Wi-Fi Journal
assert mobilewifi.kind("Taycan_4821") == "vehicle" and mobilewifi.kind("Cayenne_12") == "vehicle"
cases = {
    "Audi_MMI_1234": "audi", "My VW 5678": "vw", "VW_WLAN_1234": "vw", "My Skoda 1234": "skoda", "My SEAT 99": "seat",
    "Taycan_4821": "porsche", "Porsche_WLAN_1a2b": "porsche", "DIRECT-BMW 12345": "bmw", "MINI 4567": "mini",
    "MBUX 1234": "mercedes", "My Ford 12": "ford", "InCarHotspot-12": "othercar", "Toyota-1234": "toyota",
    "70mai_d1": "dashcam", "stagecoach-wifi": "transport", "Sam's iPhone": "phone", "AndroidAP_1234": "phone",
    "BT-ABC123": "bt", "EE-X7Y8Z9": "bt", "SKYAB12C": "sky", "VM1234567": "virgin", "VodafoneAB12": "vodafone",
    "TALKTALK12AB34": "talktalk", "PLUSNET-ABC1": "plusnet", "YouFibre-12AB": "youfibre", "Three_12AB34": "mobilebb",
    "TP-Link_12AB": "ownrouter", "NETGEAR42": "ownrouter", "DIRECT-12-HP ENVY 6000 series": "printer",
    "HP-Print-12-Deskjet 2700": "printer", "SmartLife-1A2B": "setup", "ESP-1A2B3C": "setup", "TP-Link_Extender": "mesh",
    "SKY12345_EXT": "mesh", "BTWholeHome-ABC": "mesh", "EE WiFi": "public", "_The Cloud": "public",
    "Cafe Guest": "public", "FreeWiFi@Shop": "public", "Staff WiFi": "business", "PDQ": "business",
    "Acme Corporate": "business", "xfinitywifi": "public", "MySpectrumWiFi12-5G": "spectrum",
    "Brotherhood Guest WIFI": "public", "Orbit_12": None, "Hotspot1234": None, "": None, None: None,
}
for ssid, cid in cases.items():
    assert wifijournal.category(ssid) == cid, (ssid, wifijournal.category(ssid), cid)
ids = [c[0] for c in wifijournal.CARDS]
assert len(ids) == len(set(ids))
for c in wifijournal.CARDS:
    assert c[1] in wifijournal.GROUPS and c[3] in ("Common", "Uncommon", "Rare") and c[6] and c[7], c[0]
    assert all(u.startswith("https://") for _, u in c[9]) and (not c[8] or c[9]), c[0]   # a fact has a source
words = " ".join(" ".join(str(x) for x in c[6:9]) for c in wifijournal.CARDS)
assert not re.search(r"\b(he|him|his|himself)\b", words, re.I)
rows = [("Audi_MMI_1234", now - 50), ("Audi_MMI_9999", now - 10), ("SKYQZ12X", now), ("Somebody's Secret Lair", now)]
wp = wifijournal.page_data("Ember", rows)
blob = json.dumps(wp)
for ssid, _ in rows:
    assert ssid not in blob, ssid                                     # the networks' names are never on the page
wi = {i["id"]: i for g in wp["groups"] for i in g["items"]}
assert wi["audi"]["count"] == 2 and wi["audi"]["card"]["mine"]["first"] == now - 50 and wi["sky"]["found"]
assert not wi["bt"]["found"] and wp["title"] == "Ember's Wi-Fi Journal" and wp["extras"] == []
assert "Harald" not in json.dumps(wp["groups"])

# achievements: the Wi-Fi Journal's, counted from the networks
st2 = Store(os.path.join(d, "a.db"))
for i, (ssid, _) in enumerate(rows):
    st2.db.execute("INSERT INTO aps (bssid, ssid, auth, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                   (f"00:00:00:00:00:0{i}", ssid, "[WPA2-PSK-CCMP]", now, now))


class _App:
    store = st2
    friends = garden = pond = library = None


c = achievements.gather(_App())
assert c["wifi_kinds"] == {"audi", "sky"}
built = {a["id"]: a for a in achievements.build(c)}
assert built["w-journal"]["n"] == 2 and built["w-journal"]["goal"] == len(wifijournal.CARDS)
assert built["w-cars"]["n"] == 1 and built["w-home"]["n"] == 1 and built["w-out"]["n"] == 0
assert built["g-personal"]["goal"] == 2 and built["g-on"]["goal"] == 8
print("journals ok")
