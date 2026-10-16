"""
Radio Whispers (untested): the little radios around homes and streets, heard by a radio stick
(RTL-SDR) on 433 MHz and 868 MHz (915 MHz in the Americas), decoded by rtl_433.

Weather stations, tyre-pressure sensors, doorbells, remote-control sockets, energy monitors and
door sensors all send short bursts on these licence-free bands. rtl_433 recognizes a few hundred
makes and models and prints each burst as a line of JSON:
    {"time": "...", "model": "Fineoffset-WH25", "id": 112, "temperature_C": 12.3, "humidity": 81, ...}

The collection: kinds of device (worked out from what each one sends: a temperature means a
weather sensor, a tyre pressure a tyre sensor...), and every make and model heard as a field
find within its kind. Points for each new one, and one for each device, once a day.

Privacy: many of these send a fixed ID (a car's tyre sensors, for one, could be used to
follow the car), and readings from other people's homes. Neither is kept: each device is
counted once a day with a key that's thrown away at midnight, and only the model's name and
its kind are stored.
"""
import hashlib
import hmac
import json
import os
import time

from . import scores

MODEL_POINTS = 15
DEVICE_POINTS = 1

# kind: (title, rarity, icon, what it is, how it's heard, did you know)
KINDS = {
    "weather": ("Weather sensor", "Common", "thermo",
                "An outdoor thermometer or weather station, sending readings to a display indoors.",
                "Most send the temperature (and often humidity, wind or rain) every 30 seconds to a minute, unencrypted, "
                "in a burst lasting a fraction of a second.",
                "Some weather stations measure rainfall with a tiny see-saw bucket that tips each time it fills, "
                "sending a count of tips."),
    "tpms": ("Tyre pressure sensor", "Common", "tyre",
             "A sensor inside a car's tyre, telling the dashboard the pressure (and often the temperature).",
             "Each one sends a short burst with its pressure and its own fixed ID, mostly while the wheel is turning, "
             "so they're heard from passing cars.",
             "They've been required on new cars in the US since 2007 and in the EU since 2014. Because each sensor's "
             "ID never changes, researchers have shown they could be used to follow a car, which is why Harald never "
             "keeps them."),
    "doorbell": ("Wireless doorbell", "Uncommon", "bell",
                 "A wireless doorbell's button, telling its chime to ring.",
                 "Press the button and it sends its code a few times in a row; the chime rings when it hears its own.",
                 "The button usually runs for years on one small battery, because it only transmits for a moment when "
                 "it's pressed."),
    "remote": ("Remote control", "Uncommon", "remote",
               "A remote control: for plug-in sockets, lights, blinds, awnings or gates.",
               "Each press sends a short code. Cheaper ones send the same code every time, so anyone could record it "
               "and play it back.",
               "Modern car keys and garage remotes use \"rolling codes\" instead: a new code every press, so a "
               "recording is useless."),
    "security": ("Door or motion sensor", "Uncommon", "door",
                 "A burglar-alarm sensor: a door or window contact, or a motion detector.",
                 "It sends a burst when a door opens or something moves, and a check-in now and then so the alarm "
                 "knows it's still there.",
                 "A door contact is often just a magnet on the door and a reed switch on the frame: two tiny metal "
                 "strips that touch when the magnet is near."),
    "energy": ("Energy monitor", "Uncommon", "bolt",
               "A home energy monitor, showing how much electricity the house is using.",
               "A clamp around the mains cable measures the current through it (by the magnetic field it makes) and "
               "sends the reading to a display every few seconds.",
               "The clamp never touches the wires: it's a coil the cable passes through, like a transformer."),
    "meter": ("Utility meter", "Rare", "meter",
              "A gas, water or electricity meter sending its readings for the utility company to collect.",
              "Meters like these send their readings so a passing van, or a network, can read them without anyone "
              "knocking on the door.",
              "Common in North America (often around 900 MHz); in Britain, smart meters use other radios and are "
              "rarely heard this way."),
    "smoke": ("Smoke or CO alarm", "Rare", "smoke",
              "An interlinked smoke, heat or carbon monoxide alarm.",
              "When one alarm goes off, it tells the others by radio, so they all sound together.",
              "They stay silent almost all the time: one is usually only heard when someone presses its test button."),
    "garden": ("Garden or pool sensor", "Rare", "leaf",
               "A soil-moisture sensor, a pond or pool thermometer, or another garden gadget.",
               "Like a weather sensor, it sends its reading every so often to a display or a hub.",
               "A soil sensor usually measures how well the soil holds an electric charge: wet soil holds much more "
               "than dry."),
    "kitchen": ("Cooking thermometer", "Rare", "thermo",
                "A wireless meat or barbecue thermometer.",
                "A probe in the food reports its temperature to a handset, so the cook can wait elsewhere.",
                "Most use a thermocouple or a thermistor: a part whose resistance changes with temperature."),
    "lightning": ("Lightning detector", "Rare", "lightning",
                  "A lightning sensor, part of some weather stations.",
                  "It listens for the radio crackle of lightning strikes, counts them and estimates how far away the "
                  "storm is.",
                  "Lightning is a radio transmitter too: each strike sends out a burst of low-frequency radio that "
                  "can be heard hundreds of kilometres away."),
    "other": ("Something else", "Common", "wave",
              "A device rtl_433 recognized, but that doesn't send anything that says what it's for.",
              "It might be a sensor reporting only a battery level, or a remote with an unusual code.",
              "rtl_433 knows a few hundred makes and models, all worked out by enthusiasts listening to them."),
}
ORDER = ("weather", "tpms", "other", "doorbell", "remote", "security", "energy", "meter", "smoke", "garden",
         "kitchen", "lightning")


def kind_of(d):
    """What kind of device a decoded burst is from, by its model's name and what it sends."""
    model = str(d.get("model", "")).lower()
    keys = set(d)
    if d.get("type") == "TPMS" or "tpms" in model:
        return "tpms"
    if keys & {"pressure_kPa", "pressure_PSI", "pressure_bar"} and not keys & {"humidity", "wind_avg_km_h", "rain_mm"}:
        return "tpms"               # (a weather station's air pressure comes as pressure_hPa)
    if "smoke" in model or keys & {"smoke", "alarm", "co_alarm"}:
        return "smoke"
    if "doorbell" in model or "chime" in model:
        return "doorbell"
    if keys & {"strike_count", "storm_dist", "strike_distance"}:
        return "lightning"
    if keys & {"power_W", "power0_W", "current_A", "energy_kWh"} or any(x in model for x in ("efergy", "currentcost",
                                                                                               "owl", "energy")):
        return "energy"
    if keys & {"consumption_data", "consumption", "meter_type"} or any(x in model for x in ("ert-", "scm", "meter")):
        return "meter"
    if keys & {"moisture", "moisture_pct"} or any(x in model for x in ("soil", "pool", "pond", "plant")):
        return "garden"
    if any(x in model for x in ("bbq", "meat", "grill", "maverick", "thermopro-tp")) or \
            keys & {"temperature_1_C", "meat_C"}:
        return "kitchen"
    if keys & {"contact_open", "motion", "reed_open", "tamper"} or any(x in model for x in ("door", "window", "pir",
                                                                                              "motion", "security")):
        return "security"
    if keys & {"temperature_C", "temperature_F", "humidity", "wind_avg_km_h", "wind_avg_m_s", "rain_mm", "rain_in"}:
        return "weather"
    if keys & {"button", "cmd", "command", "state", "switch"} or any(x in model for x in ("remote", "switch", "keyfob",
                                                                                          "socket", "gate")):
        return "remote"
    return "other"


def score(store):
    kinds = {r["key"] for r in store.finds("whisper_kind")}
    return (sum(scores.POINTS[KINDS[k][1]] for k in kinds if k in KINDS)
            + MODEL_POINTS * len(store.finds("whisper_model")) + DEVICE_POINTS * int(store.get("whisper_total", 0) or 0))


class Whispers:
    def __init__(self, store):
        self.store = store
        self._day, self._key, self._today = None, b"", set()
        self.recent = []            # (time, model, kind) of the last few, in memory only, for the Den
        self.bursts = 0

    def _once_today(self, ident, now):
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        if day != self._day:
            self._day, self._key, self._today = day, os.urandom(16), set()
        tag = hmac.new(self._key, ident.encode(), hashlib.sha256).digest()[:8]
        if tag in self._today:
            return False
        self._today.add(tag)
        return True

    def heard(self, line, now=None):
        """One line of rtl_433's JSON. Returns news: [("device", kind), ("kind", kind),
        ("model", model, kind)]."""
        now = now or time.time()
        try:
            d = json.loads(line)
        except ValueError:
            return []
        if not isinstance(d, dict) or not d.get("model"):
            return []
        self.bursts += 1
        model = str(d["model"])[:40]
        kind = kind_of(d)
        news = []
        ident = f"{model}|{d.get('id', '')}|{d.get('channel', '')}"
        if self._once_today(ident, now):
            self.store.put("whisper_total", int(self.store.get("whisper_total", 0) or 0) + 1)
            news.append(("device", kind))
            self.recent = ([(now, model, kind)] + self.recent)[:8]
        if self.store.find_seen("whisper_kind", kind, KINDS[kind][0], kind, now):
            news.append(("kind", kind))
        if self.store.find_seen("whisper_model", model, model, kind, now):
            news.append(("model", model, kind))
        return news


def _date(t):
    return time.strftime("%d %b %Y", time.localtime(t)) if t else ""


SOURCES = [("rtl_433 (the decoder, and its list of devices)", "https://github.com/merbanan/rtl_433"),
           ("Wikipedia: ISM radio band", "https://en.wikipedia.org/wiki/ISM_radio_band")]
EXPLAIN = [
    ("Licence-free radio",
     "Some radio frequencies can be used by anyone at low power, without a licence: around 433 MHz (for gadgets like "
     "these in Europe and North America alike), 868 MHz in Europe and 915 MHz in the Americas. Car keys, weather "
     "stations, doorbells and baby monitors share them."),
    ("Short bursts",
     "Most of these gadgets send a burst of a fraction of a second, every minute or so, or when something happens. "
     "Many simply switch the radio on and off to send ones and zeros (\"on-off keying\"), like a torch flashing "
     "Morse code."),
    ("Heard, not kept",
     "Most send their readings unencrypted, for anyone nearby to hear: your neighbour's thermometer is as public "
     "as their garden. Harald keeps only the kinds of device and the makes and models heard, and counts each "
     "device once a day with a key that's thrown away at midnight. Never their IDs or what they say."),
]


def page_data(name, store, wh=None):
    kinds = {r["key"]: r for r in store.finds("whisper_kind")}
    models = store.finds("whisper_model")
    items = []
    for k in ORDER:
        title, rarity, icon, what, how, dyk = KINDS[k]
        r = kinds.get(k)
        mine = [m for m in models if m["kind"] == k]
        items.append({"id": k, "title": title, "rarity": rarity, "icon": icon, "found": bool(r),
                      "sub": f"{len(mine)} model{'s' if len(mine) != 1 else ''}" if r else "",
                      "count": len(mine),
                      "card": {"title": title, "rarity": rarity, "group": "Devices", "text": [what, how], "dyk": dyk,
                               "sources": SOURCES[:1],
                               "mine": {"first": r["first_seen"] if r else None, "label": "",
                                        "list": [{"label": m["label"], "sub": f"first heard {_date(m['first_seen'])}"}
                                                 for m in mine]}}})
    total = int(store.get("whisper_total", 0) or 0)
    found = sum(1 for i in items if i["found"])
    return {"kind": "whispers", "name": name, "title": f"{name}'s Radio Whispers",
            "subtitle": f"{found} of {len(items)} kinds · {len(models)} make{'s' if len(models) != 1 else ''} and "
                        f"models · {total} device{'s' if total != 1 else ''} heard",
            "score": dict(scores.view(scores.WHISPER_TITLES, score(store)), what="Radio Whisper points"),
            "intro": f"The little radios around homes and streets that {name} has heard with a radio stick (untested). "
                     "Tap a kind to learn about it, and see the makes and models found.",
            "rules": f"Points: {scores.POINTS['Common']} for a Common kind, {scores.POINTS['Uncommon']} Uncommon, "
                     f"{scores.POINTS['Rare']} Rare, {MODEL_POINTS} for each new make and model, and "
                     f"{DEVICE_POINTS} for each device, once a day.",
            "explain_title": "How they're heard", "explain": [(h, p.replace("Harald", name)) for h, p in EXPLAIN],
            "groups": [{"name": "Devices", "items": items}], "extras": []}
