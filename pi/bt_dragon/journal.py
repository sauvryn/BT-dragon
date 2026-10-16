"""
The Gadget Journal (Den → Life list → Open the Gadget Journal): every type of gadget Harald has
eaten, as a collection, like the Butterfly Garden's. Each type has a card: what it is, how its
signal works, and something surprising about it, with sources.

The types known in advance (the catalogue below) all have places in the collection, found or
not, so there's always something to look out for. Everything else he eats goes under "Field
finds": gadgets named by their maker's code or by the name they broadcast.

Rarity is how often a type turns up on an ordinary walk through a town: Common ones on most
walks, Uncommon ones now and then, and Rare ones seldom. It's a judgement, not a measurement.
"""
import time

from . import scores
from .ble import APPLE_PODS

FIELD_POINTS = 10          # each new field find (a maker's gadget, or a named one)

# source links used more than once
BLE = ("Wikipedia: Bluetooth Low Energy", "https://en.wikipedia.org/wiki/Bluetooth_Low_Energy")
CONTINUITY = ("furiousMAC: Apple Continuity protocol research", "https://github.com/furiousMAC/continuity")
BEACONS = ("Wikipedia: Bluetooth Low Energy beacon", "https://en.wikipedia.org/wiki/Bluetooth_Low_Energy_beacon")
ASSIGNED = ("Bluetooth SIG: Assigned Numbers", "https://www.bluetooth.com/specifications/assigned-numbers/")
FINDMY = ("Apple Platform Security: Find My", "https://support.apple.com/guide/security/sec6cbc80fd0/web")
UNWANTED = ("Apple Newsroom: unwanted tracking alerts in iOS and Android (2024)",
            "https://www.apple.com/newsroom/2024/05/apple-and-google-deliver-support-for-unwanted-tracking-alerts-in-ios-and-android/")

GROUPS = ("Phones and computers", "Listening", "Wearables and fitness", "Trackers", "Beacons", "Around the home",
          "Mysteries")

# id: (group, title, rarity, icon, labels it covers, what it is, how it's heard, did you know, sources)
CATALOGUE = [
    ("apple-nearby", "Phones and computers", "iPhone, iPad or Mac", "Common", "phone", ["iPhone / iPad / Mac"],
     "An Apple phone, tablet or computer going about its day.",
     "Apple devices keep broadcasting short \"Nearby\" messages, part of what Apple calls Continuity, so your own "
     "devices can find each other: a Watch unlocking a Mac, a phone call moving to your laptop. Each message starts "
     "with Apple's company number (0x004C) and a byte saying what kind of message it is, and its address changes "
     "every 15 minutes or so, so that it can't be followed.",
     "In 2019, researchers showed these little messages could give away things like whether a phone's screen was "
     "on. It's one reason Harald only ever notes the kind of device, never the details or the address.",
     [CONTINUITY, BLE]),
    ("apple-other", "Phones and computers", "Apple device", "Common", "phone", ["Apple device"],
     "Something made by Apple, sending a message Harald doesn't have a name for.",
     "It carries Apple's company number (0x004C) but none of the message types Harald recognizes. Apple uses "
     "Bluetooth messages for dozens of small jobs, and adds new ones with new devices.",
     "Every Bluetooth company number is handed out by the Bluetooth Special Interest Group. Apple's is 0x004C, "
     "number 76: it joined early.",
     [CONTINUITY, ASSIGNED]),
    ("handoff", "Phones and computers", "Apple device (Handoff)", "Uncommon", "phone", ["Apple device (Handoff)"],
     "An Apple device offering to hand over what you're doing to your other Apple devices.",
     "Start an email on your phone and your Mac shows an icon to carry on there: that's Handoff. The phone "
     "broadcasts a short, encrypted note that something can be handed over; only your own devices can read it.",
     "Handoff messages carry a counter that goes up each time you switch app, which researchers have used to "
     "show how much a broadcast can reveal even when it's encrypted.",
     [CONTINUITY]),
    ("airdrop", "Phones and computers", "Apple device (AirDrop)", "Uncommon", "phone", ["Apple device (AirDrop)"],
     "Someone opening AirDrop to share a photo or a file.",
     "While the share sheet is open, the phone broadcasts that it wants to share, with tiny scrambled (hashed) "
     "scraps of its owner's phone number and email, so that nearby phones can tell whether the sender is one of "
     "their contacts.",
     "AirDrop finds the other phone over Bluetooth, but the file itself goes over a direct Wi-Fi link between the "
     "two, which is much faster.",
     [("Wikipedia: AirDrop", "https://en.wikipedia.org/wiki/AirDrop"), CONTINUITY]),
    ("hotspot", "Phones and computers", "iPhone or iPad hotspot", "Uncommon", "phone", ["iPhone / iPad hotspot"],
     "An iPhone or iPad able to share its internet connection.",
     "Apple's Instant Hotspot lets your Mac or iPad see your phone's hotspot, with its battery and signal "
     "strength, without you switching anything on. The phone broadcasts those details for your devices to pick up.",
     "The battery level and signal bars your laptop shows for your phone come from this Bluetooth message, not from "
     "Wi-Fi.",
     [CONTINUITY]),
    ("apple-setup", "Phones and computers", "Apple device setting up", "Rare", "phone", ["Apple device setting up"],
     "A brand-new or freshly reset Apple device, waiting to be set up.",
     "It broadcasts that it's ready, so an iPhone nearby can pop up \"Set up new iPhone?\" and copy its settings "
     "across.",
     "You're most likely to meet one in a shop, or at home on the day someone gets a new phone.",
     [CONTINUITY]),
    ("windows", "Phones and computers", "Windows PC", "Uncommon", "laptop", ["Windows PC"],
     "A Windows computer looking for your phone or your other computers.",
     "Windows broadcasts under Microsoft's company number (0x0006) so it can find your devices for Nearby Sharing "
     "and Phone Link, the app that shows your phone's messages on your PC.",
     "Microsoft's company number is 6: it was one of the first companies to join the Bluetooth group in the late "
     "1990s.",
     [ASSIGNED, BLE]),
    ("swift-pair", "Phones and computers", "Swift Pair accessory", "Uncommon", "laptop", ["Swift Pair accessory"],
     "A mouse, keyboard or headset asking a Windows PC to pair with it.",
     "In pairing mode, the gadget broadcasts a Microsoft \"Swift Pair\" message, and any Windows PC close by "
     "shows a pop-up offering to connect it. Windows 10 added this in 2018.",
     "Swift Pair only pops up when the gadget is very close, judged by how strong its signal is, so the "
     "neighbor's new mouse doesn't bother you.",
     [BLE]),
    ("hid", "Phones and computers", "Keyboard or mouse", "Uncommon", "laptop", ["Keyboard / mouse"],
     "A wireless keyboard, mouse, game controller or presentation clicker.",
     "It advertises the standard Human Interface Device service (0x1812), the same one USB keyboards use, so "
     "any computer, tablet or phone knows how to talk to it.",
     "\"Human Interface Device\" is also why a Bluetooth keyboard works the moment it's paired: the computer "
     "already knows the language, no driver needed.",
     [BLE, ASSIGNED]),
    # ---------------------------------------------------------------- listening
    ("airpods", "Listening", "AirPods and Beats", "Common", "earbuds", ["AirPods / Beats"] + list(APPLE_PODS.values()),
     "Apple's wireless earbuds and headphones (and Beats, which Apple owns).",
     "Open the case near an iPhone and a card pops up with the battery levels. That's because the buds and case "
     "broadcast a \"proximity pairing\" message with their model, their batteries and whether they're in the case. "
     "Harald reads only the model, and each model found is listed on this card.",
     "Each bud reports its own battery, and the case its own, so the phone can show three different levels from "
     "one short Bluetooth message.",
     [("Wikipedia: AirPods", "https://en.wikipedia.org/wiki/AirPods"), CONTINUITY]),
    ("airplay", "Listening", "AirPlay speaker or TV", "Uncommon", "speaker", ["AirPlay speaker / TV"],
     "A speaker, Apple TV or smart TV you can send music or video to from an Apple device.",
     "It broadcasts that it's an AirPlay target, so it shows up in your phone's list of places to play.",
     "The music itself goes over Wi-Fi: Bluetooth is just how your phone finds out the speaker is there.",
     [CONTINUITY]),
    ("fast-pair", "Listening", "Google Fast Pair gadget", "Uncommon", "earbuds", ["Google Fast Pair gadget"],
     "Earbuds, headphones or a speaker in pairing mode, ready for an Android phone.",
     "It advertises Google's Fast Pair service (0xFE2C) with its model number, and an Android phone nearby pops "
     "up a card with its picture and a Connect button.",
     "Fast Pair links the gadget to your Google account, so your other Android devices can use it without "
     "pairing again.",
     [BLE, ASSIGNED]),
    ("sonos", "Listening", "Sonos speaker", "Uncommon", "speaker", ["Sonos speaker"],
     "A Sonos speaker.",
     "Sonos speakers play over Wi-Fi but advertise over Bluetooth (service 0xFE07) so the Sonos app can find "
     "and set up new ones.",
     "Some Sonos portable speakers can also play straight from a phone over Bluetooth when there's no Wi-Fi.",
     [ASSIGNED]),
    ("le-audio", "Listening", "LE Audio device", "Rare", "earbuds", ["LE Audio device"],
     "The newest kind of Bluetooth audio.",
     "LE Audio, finished in 2022, carries sound over Bluetooth Low Energy with a new, more efficient way of "
     "squeezing sound down (the LC3 codec). This one advertises the audio streaming service (0x184E).",
     "LE Audio brings Auracast: one phone, TV or airport announcement system broadcasting to any number of "
     "earbuds and hearing aids at once, like a radio station.",
     [BLE, ASSIGNED]),
    # ---------------------------------------------------------------- wearables and fitness
    ("apple-watch", "Wearables and fitness", "Apple Watch", "Uncommon", "watch", ["Apple Watch"],
     "An Apple Watch.",
     "It keeps in touch with its iPhone over Bluetooth, and broadcasts a short message so the phone (and your Mac, "
     "for unlocking it) can find it.",
     "A watch unlocking a Mac checks how far away it is by timing the radio signal, so it can't be fooled by "
     "someone relaying the signal from further away.",
     [("Wikipedia: Apple Watch", "https://en.wikipedia.org/wiki/Apple_Watch"), CONTINUITY]),
    ("heart-rate", "Wearables and fitness", "Heart-rate monitor", "Uncommon", "heart", ["Heart-rate monitor"],
     "A chest strap, armband or watch sharing a heartbeat.",
     "It advertises the standard Heart Rate service (0x180D), so any gym machine, bike computer or app can read "
     "your heart rate without knowing who made the strap.",
     "A chest strap feels the tiny electrical signal of each heartbeat through your skin, just like a hospital's "
     "ECG, which is why it's more accurate than a watch's light sensor.",
     [("Wikipedia: Heart rate monitor", "https://en.wikipedia.org/wiki/Heart_rate_monitor"), ASSIGNED]),
    ("bike-speed", "Wearables and fitness", "Bike speed sensor", "Rare", "heart", ["Bike speed sensor"],
     "A sensor on a bicycle's wheel or crank.",
     "It advertises the standard Cycling Speed and Cadence service (0x1816) and counts each turn of the wheel "
     "(speed) or the pedals (cadence).",
     "It doesn't measure speed at all: it notes the time of each wheel turn, and the bike computer works out the "
     "speed from the wheel's size.",
     [ASSIGNED]),
    ("bike-power", "Wearables and fitness", "Bike power meter", "Rare", "heart", ["Bike power meter"],
     "A power meter: a cyclist's favourite gadget.",
     "It advertises the standard Cycling Power service (0x1818). Tiny strain gauges in the pedals or cranks feel "
     "them bend under each push, which gives the rider's power in watts.",
     "A strong amateur cyclist can keep up about 250 watts for an hour: enough to run a couple of old-fashioned "
     "light bulbs.",
     [("Wikipedia: Cycling power meter", "https://en.wikipedia.org/wiki/Cycling_power_meter"), ASSIGNED]),
    ("fitness-machine", "Wearables and fitness", "Fitness machine", "Rare", "heart", ["Fitness machine"],
     "A treadmill, rowing machine, exercise bike or cross-trainer.",
     "It advertises the standard Fitness Machine service (0x1826), so training apps can read its speed and "
     "distance, and some can even change its slope or resistance.",
     "Most likely heard from a gym, or a neighbour's spare room.",
     [ASSIGNED]),
    # ---------------------------------------------------------------- trackers
    ("findmy-near", "Trackers", "Find My device (near owner)", "Common", "tag", ["Find My device (near owner)"],
     "An AirTag, or anything else on Apple's Find My network, close to its owner's iPhone.",
     "Find My items keep broadcasting even at home. Near their owner they send a short message that only the "
     "owner's devices recognize.",
     "It changes what it sends regularly, so even a tag that's always with you can't be followed from one day to "
     "the next by its broadcasts.",
     [("Wikipedia: AirTag", "https://en.wikipedia.org/wiki/AirTag"), FINDMY]),
    ("findmy-away", "Trackers", "Find My item (owner away)", "Rare", "tag", ["Find My item (owner away)"],
     "An AirTag, or another Find My item, that's been away from its owner for a while.",
     "Separated from its owner, it broadcasts a longer message holding a public key. Any iPhone passing by uses "
     "that key to lock up its own location and sends it to Apple; only the owner's devices have the key that "
     "unlocks it, so not even Apple can see where the item is. The key changes regularly, so the tag can't be "
     "followed by its broadcasts.",
     "Harald's own tracker alert watches for these: one that stays with you as you move about, without being "
     "yours, could be someone tracking you. Since 2024, iPhones and Android phones warn about unknown trackers too, "
     "whichever company made them.",
     [FINDMY, UNWANTED, ("Wikipedia: Find My", "https://en.wikipedia.org/wiki/Find_My")]),
    ("tile", "Trackers", "Tile tracker", "Uncommon", "tag", ["Tile tracker"],
     "A Tile, a Bluetooth tag for keys, bags and wallets.",
     "It advertises Tile's own service (0xFEED). Every phone running the Tile app (and, since 2022, the Life360 "
     "app) listens for Tiles and reports where it heard them.",
     "Tile was selling Bluetooth trackers from 2013, eight years before the AirTag. The family-locator company "
     "Life360 bought it in 2022.",
     [("Wikipedia: Tile (company)", "https://en.wikipedia.org/wiki/Tile_(company)"), ASSIGNED]),
    ("smarttag", "Trackers", "Samsung SmartTag", "Uncommon", "tag", ["Samsung SmartTag / Find"],
     "A Samsung Galaxy SmartTag, or a Samsung phone helping to find one.",
     "It advertises Samsung's Find service (0xFD5A). Samsung Galaxy phones and tablets nearby report where they "
     "heard it, so the owner can find it on a map.",
     "Like the others, Samsung's network uses changing codes, and Galaxy phones can scan for unknown tags that "
     "seem to be travelling with you.",
     [("Samsung: About the Galaxy SmartTag+", "https://www.samsung.com/sg/support/apps-services/about-the-galaxy-smarttag-plus/"),
      ASSIGNED]),
    ("find-hub", "Trackers", "Google Find Hub tag", "Rare", "tag", ["Google Find Hub tag"],
     "A tag on Google's Find Hub network, or a lost Android phone.",
     "Google's network (called Find My Device until 2025) started taking tags in 2024. Android phones nearby "
     "report where they hear one, locked up so that only the owner can read it. It's built on Google's older "
     "Eddystone beacon format.",
     "To make stalking harder, Android phones by default only help find tags in busy places, where several phones "
     "have heard them, rather than reporting one heard by a single phone.",
     [("Wikipedia: Find Hub", "https://en.wikipedia.org/wiki/Find_Hub"),
      ("Google Security Blog: Find My Device network protections (2024)",
       "https://security.googleblog.com/2024/04/find-my-device-network-security-privacy-protections.html")]),
    # ---------------------------------------------------------------- beacons
    ("ibeacon", "Beacons", "iBeacon", "Uncommon", "beacon", ["iBeacon"],
     "A beacon in a shop, museum, station or stadium.",
     "Apple's iBeacon format (2013) is about the simplest broadcast there is: just an ID number, sent over and over. "
     "It means nothing on its own; a shop's or museum's app looks the number up to know it's \"by the dinosaurs\" "
     "or \"at gate 12\".",
     "A beacon doesn't know who's nearby and can't receive anything: it's the phone that works out it's close "
     "from how strong the signal is.",
     [("Wikipedia: iBeacon", "https://en.wikipedia.org/wiki/IBeacon"), BEACONS]),
    ("eddystone", "Beacons", "Eddystone beacon", "Rare", "beacon", ["Eddystone beacon"],
     "A beacon using Google's open format.",
     "Google's Eddystone (2015) could broadcast an ID number, a web address, or the beacon's own battery level and "
     "temperature. Its web addresses were meant to let any phone open a page about the thing in front of it, "
     "with no app needed.",
     "Google stopped showing those web-address notifications in 2018, so most Eddystone beacons still broadcasting "
     "are old ones, carrying on regardless.",
     [("Wikipedia: Eddystone (Google)", "https://en.wikipedia.org/wiki/Eddystone_(Google)"), BEACONS]),
    ("exposure", "Beacons", "Exposure-notification beacon", "Rare", "beacon", ["Exposure-notification beacon"],
     "A phone still running a COVID-19 exposure-notification app.",
     "In 2020, Apple and Google built Exposure Notifications into phones: each phone broadcast random codes "
     "(service 0xFD6F) that changed every 10 to 20 minutes, and remembered the codes it heard. If someone tested "
     "positive, their codes were shared, and phones checked privately whether they'd been near them.",
     "Most of these apps have closed (England and Wales's NHS COVID-19 app closed in April 2023), so one heard now "
     "is a little piece of recent history.",
     [("Wikipedia: Exposure Notification", "https://en.wikipedia.org/wiki/Exposure_Notification")]),
    # ---------------------------------------------------------------- around the home
    ("hue", "Around the home", "Philips Hue light", "Uncommon", "house", ["Philips Hue light"],
     "A Philips Hue smart light bulb.",
     "Hue bulbs talk to each other over Zigbee, a different low-power radio, but newer ones also have Bluetooth "
     "(service 0xFE0F), so a phone can control them without the Hue hub.",
     "Zigbee and Bluetooth share the same 2.4 GHz radio band as Wi-Fi: a single bulb can speak two of the three.",
     [("Wikipedia: Philips Hue", "https://en.wikipedia.org/wiki/Philips_Hue")]),
    ("echo", "Around the home", "Amazon Echo or Fire TV", "Uncommon", "house", ["Amazon Echo / Fire"],
     "An Amazon Echo speaker or Fire TV.",
     "It advertises Amazon's service (0xFE03) so the Alexa app can set it up and connect gadgets to it.",
     "If your dragon has an Echo Dot (Level 4), it may well be one of these.",
     [ASSIGNED]),
    ("xiaomi", "Around the home", "Xiaomi gadget", "Uncommon", "house", ["Xiaomi Mi device"],
     "A Xiaomi fitness band, thermometer, plant sensor or other smart-home gadget.",
     "Many Xiaomi gadgets broadcast their readings in \"MiBeacon\" messages (service 0xFE95), so the app (or a "
     "hub) can collect them without connecting.",
     "Some of those readings, like a room's temperature, used to be readable by anyone nearby; newer gadgets "
     "encrypt them. Harald never keeps them either way.",
     [ASSIGNED]),
    ("environment", "Around the home", "Environment sensor", "Rare", "house", ["Environment sensor"],
     "A temperature, humidity or air sensor.",
     "It advertises the standard Environmental Sensing service (0x181A), which can report temperature, humidity, "
     "air pressure, even pollen.",
     "Weather-station fans often flash cheap thermometers with their own software so they broadcast readings "
     "openly, for home-automation systems to pick up.",
     [ASSIGNED]),
    # ---------------------------------------------------------------- mysteries
    ("unbranded", "Mysteries", "Unbranded gadget", "Common", "chip", ["Unbranded gadget"],
     "A cheap bulb, LED strip, toy or tracker that doesn't say who made it.",
     "It puts made-up bytes where a company number should be: numbers the Bluetooth group has never handed out. "
     "Often they change as it goes, so they'd look like a new gadget every few minutes; Harald counts them all as "
     "one type.",
     "Joining the Bluetooth group and getting a company number costs money, which is why some makers just skip it.",
     [ASSIGNED]),
    ("mystery", "Mysteries", "Mystery morsel", "Common", "question", ["Mystery morsel"],
     "A gadget that gives nothing away: no name, no company, no services.",
     "Some gadgets advertise only that they exist, to be found by an app that already knows what to look for. "
     "Phones do this too at times, to stay private.",
     "Bluetooth's address types are a puzzle of their own: the first two bits of a random address say whether "
     "it's fixed or changes every few minutes, which is how Harald knows not to follow it.",
     [BLE]),
]
EXTRA_KINDS = {
    "maker": ("Maker's gadgets", "chip",
              "Gadgets that only say who made them, by their company number.",
              "Every Bluetooth advertisement can carry \"manufacturer data\", which starts with a 16-bit company number "
              "handed out by the Bluetooth Special Interest Group. Harald knows about 4,000 of them, so a gadget "
              "that says nothing else is named after its maker.",
              "The numbers were handed out in order: 0 went to Ericsson, the Swedish company where Bluetooth was "
              "invented in the 1990s, 1 to Nokia, 2 to Intel and 3 to IBM."),
    "named": ("Named gadgets", "tag",
              "Gadgets that broadcast their own name.",
              "An advertisement can carry a name, chosen by the maker (\"JBL Flip 6\") or by the owner (\"Sam's "
              "AirPods\"). Harald keeps it as the gadget's type, with its numbers hidden (as #) so that every JBL "
              "Flip counts as one type and no serial number is ever kept.",
              "There's only room for about 29 letters of name in an advertisement, which is why gadget names are "
              "often cut short."),
}
CAT_BY_LABEL = {lab: c for c in CATALOGUE for lab in c[5]}


def _date(t):
    return time.strftime("%d %b %Y", time.localtime(t)) if t else ""


def score(species):
    """Gadget Journal points: each catalogue type found, by its rarity, and each field find."""
    found, field = set(), 0
    for s in species:
        c = CAT_BY_LABEL.get(s["label"])
        if c:
            found.add(c[0])
        else:
            field += 1
    return sum(scores.POINTS[c[3]] for c in CATALOGUE if c[0] in found) + field * FIELD_POINTS


def points_for(label):
    """What a newly eaten type is worth (0 if its catalogue type was already found)."""
    c = CAT_BY_LABEL.get(label)
    return scores.POINTS[c[3]] if c else FIELD_POINTS


def page_data(name, species):
    """`species`: store.species_list() rows (key, label, kind, first_seen, last_seen, meals)."""
    n = lambda t: t.replace("Harald", name)          # noqa: E731  (the dragon's own name)
    found = {}
    extras = {k: [] for k in EXTRA_KINDS}
    for s in species:
        c = CAT_BY_LABEL.get(s["label"])
        if c:
            found.setdefault(c[0], []).append(s)
        else:
            extras.get(s["kind"] if s["kind"] in EXTRA_KINDS else "maker").append(s)
    groups = []
    for g in GROUPS:
        items = []
        for c in CATALOGUE:
            if c[1] != g:
                continue
            mine = found.get(c[0], [])
            meals = sum(s["meals"] or 0 for s in mine)
            first = min((s["first_seen"] for s in mine if s["first_seen"]), default=None)
            forms = [s for s in mine if s["label"] != c[5][0]] if len(c[5]) > 1 else []   # (the models: AirPods Pro 2...)
            items.append({
                "id": c[0], "title": c[2], "rarity": c[3], "icon": c[4], "found": bool(mine),
                "sub": f"eaten {meals}×" if mine else "", "count": meals,
                "card": {"title": c[2], "rarity": c[3], "group": g,
                         "text": [n(c[6]), n(c[7])], "dyk": n(c[8]), "sources": c[9],
                         "mine": {"first": first, "label": "times eaten", "count": meals,
                                  "list": [{"label": s["label"], "sub": f"first eaten {_date(s['first_seen'])} · "
                                                                         f"{s['meals']}×"} for s in forms]}},
            })
        groups.append({"name": g, "items": items})
    extra_cards = []
    for kind, (title, icon, what, how, dyk) in EXTRA_KINDS.items():
        rows = sorted(extras[kind], key=lambda s: -(s["meals"] or 0))
        extra_cards.append({"id": kind, "title": title, "icon": icon, "count": len(rows),
                            "card": {"title": title, "rarity": "", "group": "Field finds", "text": [n(what), n(how)],
                                     "dyk": n(dyk), "sources": [ASSIGNED] if kind == "maker" else [BLE],
                                     "mine": {"first": None, "label": "types",
                                              "list": [{"label": s["label"],
                                                        "sub": f"first eaten {_date(s['first_seen'])} · {s['meals']}×"}
                                                       for s in rows]}}})
    n_found = sum(1 for g in groups for i in g["items"] if i["found"])
    n_all = sum(len(g["items"]) for g in groups)
    n_field = sum(len(v) for v in extras.values())
    return {"kind": "journal", "name": name, "title": f"{name}'s Gadget Journal",
            "score": dict(scores.view(scores.JOURNAL_TITLES, score(species)), what="Gadget Journal points"),
            "rules": f"Points: {scores.POINTS['Common']} for a Common type, {scores.POINTS['Uncommon']} Uncommon, "
                     f"{scores.POINTS['Rare']} Rare, and {FIELD_POINTS} for each field find.",
            "subtitle": f"{n_found} of {n_all} gadget types found · {n_field} field find{'s' if n_field != 1 else ''}",
            "intro": f"Every kind of gadget {name} has eaten. Tap one to learn what it is and how its signal works. The "
                     "ones not found yet are here too: something to look out for.",
            "explain_title": "How gadgets are heard",
            "explain": [(h, n(p)) for h, p in [
                ("Shouting into the air",
                 "A Bluetooth Low Energy gadget that wants to be found shouts a tiny packet (31 bytes, about the "
                 "length of this sentence's first half) several times a second, on three radio channels set aside "
                 "for it. Anyone listening hears it. Harald only ever listens: never connecting, never replying."),
                ("What's in a shout",
                 "Each packet has an address, and maybe a name, the services the gadget offers (\"heart rate\", "
                 "\"find me\") as standard numbers, and \"manufacturer data\" starting with its maker's company "
                 "number. From those, Harald works out what kind of gadget it is."),
                ("Staying private",
                 "Phones, watches and earbuds change their address every 15 minutes or so, so nobody can follow "
                 "one by its broadcasts. Harald counts them as food and as a type of gadget, and never tries to "
                 "link one address to the next."),
            ]],
            "groups": groups, "extras": extra_cards}
