"""
The Wi-Fi Journal (Den → Wi-Fi → Open the Wi-Fi Journal): every kind of Wi-Fi network Harald has
found, as a collection like the Gadget Journal's. Each kind has a card: what it is and how it's
recognized, how many Harald has found and when the first one was.

It goes by each network's name (its SSID), and never shows the names: only how many of each
kind, so nobody's home network, workplace or car is written on a card. The names were chosen by
the networks' owners or their makers, and a name is only a good guess at what a network is: a
renamed router is missed, and a home network called "Office" is counted as an office.

Cars, dashcams, buses and phone hotspots come from mobilewifi.py (they travel); the rest are
recognized here, in this order, first match wins: printers, setup networks, mesh and extenders,
public and guest Wi-Fi, staff and business networks, home broadband by provider, and routers
known by their maker's own name.
"""
import re

from . import mobilewifi

# source links used more than once
PSTI = ("Wired-Gov: PSTI Regulations come into force (April 2024)",
        "https://wired-gov.net/wg/news.nsf/print/PSTI+Regulations+come+into+force+30042024162500")
CARPLAY = ("BGR: Does Apple CarPlay use Bluetooth or Wi-Fi to connect?",
           "https://bgr.com/2035526/does-apple-carplay-use-blutooth-wifi-connect/")

GROUPS = ("Cars", "On the move", "Home broadband", "Out and about")

_CAR_DYK = ("Wireless CarPlay starts over Bluetooth, to check the phone may connect, and then Wi-Fi takes over: "
            "the car makes a little closed network of its own, which is what Harald hears.", [CARPLAY])
_ISP_HOW = ("Its hubs come with a name of the provider's choosing, with a few letters or numbers that are different "
            "for every hub, and most people never change it.")
_ISP_DYK = ("Since April 29, 2024, connectable gadgets sold in the UK, routers included, may not come with a "
            "default password that's the same on every one: each needs its own, or one you choose.", [PSTI])

# id: (group, title, rarity, icon, pattern, what, how, did you know, sources)
CARDS = [
    # ---------------------------------------------------------------- cars (mobilewifi: a vehicle)
    ("audi", "Cars", "Audi", "Common", "car", r"audi|\bmmi\b",
     "An Audi's own Wi-Fi.", "Audis call theirs \"Audi_MMI\" (MMI is Audi's name for the dashboard system) and a number.",
     *_CAR_DYK),
    ("vw", "Cars", "Volkswagen", "Common", "car", r"(?<![a-z])vw(?![a-z])|volkswagen",
     "A Volkswagen's own Wi-Fi.", "\"My VW\" or \"VW WLAN\" (WLAN is German for Wi-Fi), and a number.", *_CAR_DYK),
    ("skoda", "Cars", "Škoda", "Uncommon", "car", r"skoda|škoda",
     "A Škoda's own Wi-Fi.", "\"My Skoda\" and a number.", *_CAR_DYK),
    ("seat", "Cars", "SEAT and Cupra", "Uncommon", "car", r"seat|cupra",
     "A SEAT's or a Cupra's own Wi-Fi.", "\"My SEAT\" or \"My Cupra\" and a number.", *_CAR_DYK),
    ("porsche", "Cars", "Porsche", "Rare", "car", r"porsche|taycan|cayenne|macan|panamera",
     "A Porsche's own Wi-Fi.", "\"Porsche_WLAN\", or the model's name (Taycan, Cayenne...), and a number.", *_CAR_DYK),
    ("bmw", "Cars", "BMW", "Uncommon", "car", r"bmw",
     "A BMW's own Wi-Fi.",
     "\"BMW\" and a number; \"DIRECT-BMW\" is its wireless CarPlay, made with Wi-Fi Direct (the way printers make "
     "networks of their own).", *_CAR_DYK),
    ("mini", "Cars", "MINI", "Uncommon", "car", r"(?<![a-z])mini(?![a-z])",
     "A MINI's own Wi-Fi.", "\"MINI\" and a number, or \"MINI CarPlay\".", *_CAR_DYK),
    ("mercedes", "Cars", "Mercedes-Benz", "Uncommon", "car", r"mercedes|mbux|\bmb\b",
     "A Mercedes-Benz's own Wi-Fi.",
     "\"MB Hotspot\", or \"MBUX\" (the Mercedes-Benz User Experience: its dashboard system), and a number.", *_CAR_DYK),
    ("ford", "Cars", "Ford", "Uncommon", "car", r"ford|sync ?\d",
     "A Ford's own Wi-Fi.", "\"My Ford\", \"FordPass\" or \"SYNC\" (Ford's dashboard system) and a number.", *_CAR_DYK),
    ("vauxhall", "Cars", "Vauxhall and Opel", "Uncommon", "car", r"vauxhall|opel",
     "A Vauxhall's or an Opel's own Wi-Fi (they're the same cars, by their British and German names).",
     "Its name has the maker's.", *_CAR_DYK),
    ("stellantis", "Cars", "Peugeot, Citroën, Fiat and friends", "Uncommon", "car",
     r"peugeot|citro[eë]n|fiat|alfa|jeep|chrysler|abarth",
     "A Peugeot's, Citroën's, DS's, Fiat's, Alfa Romeo's or Jeep's own Wi-Fi: all made by Stellantis.",
     "Its name has the maker's.", *_CAR_DYK),
    ("renault", "Cars", "Renault and Dacia", "Uncommon", "car", r"renault|r-?link|dacia",
     "A Renault's or a Dacia's own Wi-Fi.", "Its name has the maker's, or R-Link (Renault's dashboard system).",
     *_CAR_DYK),
    ("toyota", "Cars", "Toyota and Lexus", "Uncommon", "car", r"toyota|lexus",
     "A Toyota's or a Lexus's own Wi-Fi.", "Its name has the maker's.", *_CAR_DYK),
    ("japan", "Cars", "Nissan, Honda, Mazda and friends", "Uncommon", "car",
     r"nissan|honda|mazda|subaru|mitsubishi|suzuki",
     "A Nissan's, Honda's, Mazda's, Subaru's, Mitsubishi's or Suzuki's own Wi-Fi.", "Its name has the maker's.",
     *_CAR_DYK),
    ("korea", "Cars", "Hyundai and Kia", "Uncommon", "car", r"hyundai|kia",
     "A Hyundai's or a Kia's own Wi-Fi.", "Its name has the maker's.", *_CAR_DYK),
    ("volvo", "Cars", "Volvo and Polestar", "Uncommon", "car", r"volvo|polestar",
     "A Volvo's or a Polestar's own Wi-Fi.", "Its name has the maker's.", *_CAR_DYK),
    ("jlr", "Cars", "Jaguar and Land Rover", "Uncommon", "car", r"jaguar|land ?rover|range ?rover|jlr",
     "A Jaguar's, Land Rover's or Range Rover's own Wi-Fi.", "Its name has the maker's.", *_CAR_DYK),
    ("tesla", "Cars", "Tesla", "Rare", "car", r"tesla",
     "A Tesla's own Wi-Fi.", "Its name has the maker's.", *_CAR_DYK),
    ("othercar", "Cars", "Other cars", "Common", "car", r"",
     "A car's Wi-Fi without a card of its own: an in-car hotspot, wireless CarPlay or Android Auto, \"My Car\", "
     "or a maker not listed here.", "Its name says it's a car, but not which (or it's a rarer make).", *_CAR_DYK),
    # ---------------------------------------------------------------- on the move (mobilewifi)
    ("dashcam", "On the move", "Dashcams", "Common", "camera", None,
     "A dashcam's or a fleet camera's own Wi-Fi.",
     "Many dashcams make a network of their own so a phone can watch and download their videos; their names "
     "have the maker's (70mai, BlackVue, Nextbase...) or \"Dash\".",
     "Dashcams use Wi-Fi Direct: the phone joins the camera's network directly, within about 10 m, with no router "
     "in between.",
     [("BlackVue manual: Using your smartphone",
       "https://manual.blackvue.com/docs/dr900x-plus/playing-and-managing-videos/using-your-smartphone-android-ios-dr900x-plus/")]),
    ("transport", "On the move", "Buses, trams and trains", "Uncommon", "bus", None,
     "The Wi-Fi on a bus, tram or train.",
     "Its name has the operator's (Stagecoach, Arriva, Northern...) or says it's on board. It gets its internet from "
     "the mobile networks, as a phone does.", "", []),
    ("phone", "On the move", "Phone hotspots", "Common", "phone", None,
     "A phone sharing its internet, or a pocket router.",
     "A phone's hotspot is named after the phone (\"Sam's iPhone\", \"AndroidAP\", \"Galaxy A52\"), so it goes "
     "wherever its owner does.", "", []),
    # ---------------------------------------------------------------- home broadband (by provider)
    ("bt", "Home broadband", "BT and EE", "Common", "router", r"^bt[-_ ]|^bthub|^btb-|^ee[-_ ]",
     "A home or business broadband hub from BT or EE (both part of BT Group).",
     "\"BT-\" or \"EE-\" and a few letters and numbers; \"BTB-\" is BT Business.", *_ISP_DYK),
    ("sky", "Home broadband", "Sky", "Common", "router", r"^sky[a-z0-9]{4,8}$|^sky[-_ ]|^skyq",
     "A Sky Broadband hub, or a Sky Q box.", "\"SKY\" and five more letters or numbers. " + _ISP_HOW, *_ISP_DYK),
    ("virgin", "Home broadband", "Virgin Media", "Common", "router", r"^vm[0-9a-f]{5,}|^vm[-_ ]|^virgin ?media",
     "A Virgin Media hub.", "\"VM\" and seven numbers. " + _ISP_HOW, *_ISP_DYK),
    ("vodafone", "Home broadband", "Vodafone", "Uncommon", "router", r"^vodafone",
     "A Vodafone broadband hub.", "\"Vodafone\" and a few letters or numbers. " + _ISP_HOW, *_ISP_DYK),
    ("talktalk", "Home broadband", "TalkTalk", "Uncommon", "router", r"^talktalk",
     "A TalkTalk broadband hub.", "\"TALKTALK\" and six letters or numbers. " + _ISP_HOW, *_ISP_DYK),
    ("plusnet", "Home broadband", "Plusnet", "Uncommon", "router", r"^plusnet",
     "A Plusnet broadband hub (Plusnet is part of BT Group).", "\"PLUSNET-\" and a few letters or numbers.",
     *_ISP_DYK),
    ("youfibre", "Home broadband", "YouFibre", "Uncommon", "router", r"^youfibre",
     "A YouFibre broadband router.", "\"YouFibre-\" and a few letters or numbers.", *_ISP_DYK),
    ("hyperoptic", "Home broadband", "Hyperoptic", "Uncommon", "router", r"^hyperoptic",
     "A Hyperoptic broadband router, usually in a block of flats.", "\"HYPEROPTIC\" and a few letters or numbers.",
     *_ISP_DYK),
    ("communityfibre", "Home broadband", "Community Fibre", "Rare", "router", r"^community ?fibre",
     "A Community Fibre broadband router.", "\"CommunityFibre\" and a few letters or numbers.", *_ISP_DYK),
    ("mobilebb", "Home broadband", "4G and 5G home broadband", "Uncommon", "router",
     r"^three[_ -]|(?<![\d.])4g\b|\b5g ?(?:hub|router|home)|^o2 ?wireless|^huawei-|^zte",
     "A home broadband router that gets its internet from a mobile network, as a phone does.",
     "Its name has the network's (\"Three_\") or says 4G.", *_ISP_DYK),
    ("xfinity", "Home broadband", "Xfinity", "Rare", "router", r"^xfinity(?!wifi)|^comcast",
     "An Xfinity (Comcast) router, in the United States.", "Its name has the provider's.", "", []),
    ("spectrum", "Home broadband", "Spectrum", "Rare", "router", r"^myspectrumwifi|^spectrum",
     "A Spectrum router, in the United States.", "\"MySpectrumWiFi\" and a few letters or numbers.", "", []),
    ("att", "Home broadband", "AT&T", "Rare", "router", r"^att[a-z0-9]{3,7}$|^att[-_]",
     "An AT&T router, in the United States.", "\"ATT\" and a few letters or numbers.", "", []),
    ("verizon", "Home broadband", "Verizon", "Rare", "router", r"^verizon|^fios",
     "A Verizon router, in the United States.", "\"Verizon_\" or \"Fios-\" and a few letters or numbers.", "", []),
    ("canada", "Home broadband", "Bell, Rogers and Telus", "Rare", "router", r"^bell\d{3}|^rogers|^telus",
     "A Bell, Rogers or Telus router, in Canada.", "Its name has the provider's.", "", []),
    ("ownrouter", "Home broadband", "A router of their own", "Common", "router",
     r"^tp-?link|^netgear|^asus|^linksys|^d-?link|^tenda|^mercusys|^draytek|^ubnt|^unifi|^mikrotik|^fritz|"
     r"^openwrt|^cisco|^zyxel|^belkin|^arris|^technicolor",
     "A router someone bought for themselves, still named after its maker (TP-Link, NETGEAR, ASUS...).",
     "Its maker's name, and a few letters or numbers from its own address.", *_ISP_DYK),
    # ---------------------------------------------------------------- out and about
    ("printer", "Out and about", "Printers", "Common", "printer",
     r"^direct-.*(?:hp|epson|canon|brother|xerox|kyocera|ricoh|lexmark|samsung m|laserjet|deskjet|officejet|envy)|"
     r"epson|(?<![a-z])canon(?![a-z])|brother(?!hood)|^hp-|laserjet|deskjet|officejet|printer|xerox|kyocera|lexmark",
     "A printer's own network.",
     "Printers make one so a phone or laptop can print straight to them. \"DIRECT-\" at the start means Wi-Fi Direct.",
     "With Wi-Fi Direct, a printer and a phone connect to each other directly, without a router or any other "
     "network in between.",
     [("Brother: Wi-Fi Direct", "https://www.brother.com.ph/en/solutions/wifi-direct")]),
    ("setup", "Out and about", "Smart-home setup networks", "Uncommon", "gear",
     r"set-?up|^esp[_-]|tasmota|shelly|meross|smart ?life|tuya|^sonos|^amazon-|^roku|chromecast|^google ?home|"
     r"^ezviz|^wyze|^tapo|^kasa|^wiz_|^nanoleaf|^lifx|^miio|^xiaomi-|^roborock|^dreame|^ecovacs|^viomi",
     "A smart-home gadget waiting to be set up: a plug, bulb, camera, speaker or robot vacuum.",
     "Until it knows your Wi-Fi, a gadget makes a little network of its own, often with \"Setup\" or its maker's "
     "name in it, for its app to join and tell it.",
     "This is called SoftAP setup: the gadget starts its own temporary Wi-Fi, the phone joins it and sends your "
     "Wi-Fi's name and password, and then the gadget's own network goes away. Some gadgets use Bluetooth for the "
     "same job instead.",
     [("Espressif: ESP Jumpstart, network configuration",
       "https://docs.espressif.com/projects/esp-jumpstart/en/latest/networkconfig.html")]),
    ("mesh", "Out and about", "Mesh and extenders", "Common", "mesh",
     r"_ext\b|-ext\b| ext\b|^ext\d*-|extender|repeater|booster|\bmesh\b|^deco|eero|orbi(?!t)|velop|whole ?home|^plume|"
     r"amplifi|google ?wifi|nest ?wifi|\bextra\b|powerline|devolo|_rpt\b",
     "A second Wi-Fi unit spreading a home's or a building's Wi-Fi further: an extender, or one of a mesh system's "
     "units.",
     "An extender often adds \"_EXT\" to the network's name; mesh systems have their own (Deco, eero, Orbi, BT "
     "Whole Home...).",
     "Wi-Fi EasyMesh is the Wi-Fi Alliance's standard for mesh: several access points working together as one "
     "network, even from different makers.",
     [("Wi-Fi Alliance: Wi-Fi EasyMesh", "https://wi-fi.org/discover-wi-fi/wi-fi-easymesh")]),
    ("public", "Out and about", "Public and guest Wi-Fi", "Common", "guest",
     r"guest|free|public|visitor|customer|patient|the ?cloud|btwi-?fi|^ee wifi|govwifi|eduroam|xfinitywifi|"
     r"virgin media wifi|@|wi-?fi ?zone|club wifi|welcome|^_",
     "Wi-Fi for anyone, or for visitors: in shops, cafés, museums, stations, hotels and offices' guest networks.",
     "Its name says so (\"Guest\", \"Free WiFi\", \"Public\"), or it's a network you can join in many places "
     "(\"_The Cloud\", \"EE WiFi\"). A name starting with \"_\" is an old convention for public hotspots.",
     "Passpoint, from the Wi-Fi Alliance, lets a phone find and join hotspots it trusts by itself, with no "
     "sign-in page, and with WPA2-Enterprise security turned on automatically.",
     [("Wi-Fi Alliance: Passpoint", "https://www.wi-fi.org/node/6836")]),
    ("business", "Out and about", "Staff and business networks", "Common", "office",
     r"staff|corp|office|internal|secure|private|\bpos\b|\bpdq\b|\btill|cctv|voip|\biot\b|members?\b|crew|mgmt|"
     r"admin|workshop|stores?\b|partners|production|meeting|byod|warehouse|backoffice|back ?office|\blan\b|\bint\b|"
     r"business|\bltd\b|limited|\bplc\b|\binc\b|employee|\btools?\b|\btech\b|clinic|surgery|dental|practice|"
     r"school|academy|council|church|trades|backstage|volunteer",
     "A network for the people who work somewhere, or for its machines: tills and card machines (\"PDQ\"), "
     "cameras, phones, meeting rooms.",
     "Its name says so: \"Staff\", \"Corporate\", \"Office\", \"POS\", \"CCTV\", \"VoIP\"...", "", []),
]
_CAR_IDS = [c[0] for c in CARDS if c[1] == "Cars"]
_MATCH = [(c[0], re.compile(c[5], re.IGNORECASE)) for c in CARDS if c[5]]
_ORDER = ["printer", "setup", "mesh", "public", "business", "bt", "sky", "virgin", "vodafone", "talktalk", "plusnet",
          "youfibre", "hyperoptic", "communityfibre", "mobilebb", "xfinity", "spectrum", "att", "verizon", "canada",
          "ownrouter"]
_BY_ID = dict(_MATCH)
_DASH = re.compile(r"(?<![a-z0-9])(?:dash ?cam\w*|dash-\d+|\w*car ?cam\w*|70mai|viofo|ddpai|nextbase|blackvue|"
                   r"thinkware|vantrue|garmin ?dash|cameramatics|connectedcam|samsara\w*|cam_iq)(?![a-z])", re.I)
_TRANSPORT = re.compile(r"(?<![a-z0-9])(?:beenetwork\w*|stagecoach\w*|arriva\w*|first ?bus|northern ?wi-?fi|"
                        r"avanti\w*|transpennine\w*|lner\w*|crosscountry\w*|national ?express|megabus|tfgm_mobile|"
                        r"on-?board ?wi-?fi)(?![a-z])", re.I)
CARD_BY_ID = {c[0]: c for c in CARDS}
assert set(_ORDER) | set(_CAR_IDS) | {"dashcam", "transport", "phone"} == set(CARD_BY_ID)


def category(ssid):
    """The Wi-Fi Journal card a network belongs to, by its name, or None."""
    if not ssid:
        return None
    kind = mobilewifi.kind(ssid)
    if kind == "phone":
        return "phone"
    if kind == "vehicle":
        if _DASH.search(ssid):
            return "dashcam"
        if _TRANSPORT.search(ssid):
            return "transport"
        for i in _CAR_IDS:
            rx = _BY_ID.get(i)
            if rx and rx.search(ssid):
                return i
        return "othercar"
    for i in _ORDER:
        if _BY_ID[i].search(ssid):
            return i
    return None


def counts(rows):
    """{card id: (networks, first found)} from (ssid, first_seen) rows."""
    out = {}
    for ssid, first in rows:
        c = category(ssid)
        if c:
            n, f = out.get(c, (0, None))
            out[c] = (n + 1, min(x for x in (f, first) if x) if (f or first) else None)
    return out


def found(rows):
    return set(counts(rows))


def page_data(name, rows):
    """`rows`: (ssid, first_seen) for every network found. The names themselves never leave this function."""
    n = lambda t: t.replace("Harald", name)          # noqa: E731
    got = counts(rows)
    groups = []
    for g in GROUPS:
        items = []
        for c in CARDS:
            if c[1] != g:
                continue
            k, first = got.get(c[0], (0, None))
            items.append({
                "id": c[0], "title": c[2], "rarity": c[3], "icon": c[4], "found": bool(k),
                "sub": f"{k:,} network{'s' if k != 1 else ''}" if k else "", "count": k,
                "card": {"title": c[2], "rarity": c[3], "group": g, "text": [n(c[6]), n(c[7])], "dyk": n(c[8]),
                         "sources": c[9], "mine": {"first": first, "count": k, "what": "networks" if k != 1 else "network",
                                                   "list": []}},
            })
        groups.append({"name": g, "items": items})
    n_found = sum(1 for g in groups for i in g["items"] if i["found"])
    n_all = len(CARDS)
    n_nets = sum(v[0] for v in got.values())
    return {"kind": "wifijournal", "name": name, "title": f"{name}'s Wi-Fi Journal",
            "subtitle": f"{n_found} of {n_all} kinds of network found · {n_nets:,} networks with a kind",
            "intro": f"Every kind of Wi-Fi network {name} has found, by what the networks are called. Tap one to learn "
                     "what it is. Only how many of each kind are shown, never the networks' names.",
            "explain_title": "How networks are recognized",
            "explain": [(h, n(p)) for h, p in [
                ("A name in the air",
                 "Every Wi-Fi network announces itself about ten times a second with a short \"beacon\": its name "
                 "(the SSID), how it's locked, and which channel it's on. Phones list those names when you look "
                 "for Wi-Fi. Harald hears the same beacons and never joins the networks."),
                ("A good guess",
                 "Routers, cars and gadgets come with names their makers chose (\"SKY\" and five letters, "
                 "\"Audi_MMI\" and a number), and most people never change them, so the name says what the network "
                 "probably is. Probably: a renamed router is missed, and a home network called \"Office\" is "
                 "counted as an office."),
                ("Nobody's name on a card",
                 "The journal keeps count of each kind and the date of the first. It doesn't show which networks "
                 "they were: those names belong to the people and places that chose them."),
            ]],
            "groups": groups, "extras": []}
