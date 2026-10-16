"""
Sky Dragons (untested): planes overhead, heard by a radio stick (RTL-SDR) on 1090 MHz (see
adsb.py for how their broadcasts are read, and rtlsdr.py for the stick).

The collection: every kind of aircraft (the "emitter category" each one's transponder
announces: light aircraft, airliner, heavy, helicopter, glider, balloon...), every airline
(from the first three letters of a flight number: EZY is easyJet), and every country whose
aircraft registrations he's heard (a private plane's callsign is often its registration:
G-ABCD is British). Points for each new one, and one for each plane, once a day.

Privacy: an aircraft's 24-bit address is fixed to the airframe, and a private plane's belongs
to its owner. So, as with gadgets, planes are counted without being kept: each address is
scrambled with a key that's thrown away at midnight (and on a restart), just to count each
plane once a day. Planes in the sky right now (their flight numbers, heights and distances)
are held in memory for the Den, and forgotten two minutes after they're last heard.
"""
import hashlib
import hmac
import os
import re
import time

from . import adsb, scores

AIRLINE_POINTS = 25
COUNTRY_POINTS = 25
PLANE_POINTS = 1
LIVE_S = 120

# kind: (title, rarity, icon, what it is, did you know)
KINDS = {
    "large": ("Airliner", "Common", "jet",
              "34 to 136 tonnes (75,000 to 300,000 lb) at take-off: the everyday airliners, the Airbus A320 family "
              "and Boeing 737s, and the bigger regional jets.",
              "The A320 and 737 families are the best-selling airliners ever: each has had more than 10,000 built."),
    "unknown": ("Unannounced aircraft", "Common", "jet",
                "An aircraft whose transponder doesn't say what kind it is (its category is \"no information\"). "
                "Plenty of airliners leave it unset.",
                "Every transponder has a 24-bit address of its own, fixed to the airframe: about 16.8 million "
                "possible, shared out between the world's countries."),
    "heavy": ("Heavy", "Uncommon", "heavy",
              "Over 136 tonnes (300,000 lb): the wide-bodied jets with two aisles, the Boeing 747, 777 and 787, and "
              "the Airbus A330, A350 and A380, on long-distance flights.",
              "Pilots add \"Heavy\" to their callsign on the radio (\"Speedbird 15 Heavy\") so controllers keep the "
              "next plane further back from its wake. The A380 is even \"Super\"."),
    "small": ("Small aircraft", "Uncommon", "prop",
              "7 to 34 tonnes (15,500 to 75,000 lb): business jets, and turboprop airliners like the ATR 72 and "
              "Dash 8 on shorter routes, to islands and smaller airports.",
              "A turboprop is a jet engine turning a propeller: on short hops it uses less fuel than a pure jet."),
    "light": ("Light aircraft", "Uncommon", "prop",
              "Under 7 tonnes (15,500 lb): small propeller planes for training, flying clubs and touring, like the "
              "Cessna 172 or Piper PA-28.",
              "Many light aircraft carry small, cheap \"electronic conspicuity\" devices that broadcast ADS-B so "
              "that other pilots' gadgets can see them, even where the law doesn't require it."),
    "rotorcraft": ("Helicopter", "Uncommon", "heli",
                   "Air ambulances, police, coastguard, oil-rig and island shuttles, and sightseeing flights.",
                   "A helicopter's blades are wings too: spinning, they make lift, and tilting the whole spinning "
                   "disc moves it in any direction."),
    "vortex": ("Boeing 757", "Rare", "jet",
               "A category for one aircraft: the Boeing 757. Every wing leaves spinning, tornado-like vortices behind "
               "it, and in the early 1990s the 757's turned out to be unusually strong for its size, so it was given "
               "a category of its own, to keep the next plane further back.",
               "The last 757 was built in 2004, after 1,050 of them, so every one heard now is a veteran."),
    "performance": ("Fast jet", "Rare", "jet",
                    "More than 5 g and faster than 400 knots: fast jets, mostly military, and some display aircraft.",
                    "Military aircraft often fly with their broadcasts turned down or off, so hearing one is a "
                    "treat."),
    "glider": ("Glider", "Rare", "glider",
               "A sailplane, with no engine: towed or winched up, then riding rising air (thermals and hillsides) "
               "for hours.",
               "Gliders have flown over 3,000 km in a single flight, and in 2018 the Perlan 2 glider climbed above "
               "23,000 m (76,000 ft) on mountain waves over the Andes."),
    "balloon": ("Balloon or airship", "Rare", "balloon",
                "Lighter than air: hot-air balloons, gas balloons and airships.",
                "A balloon can't steer: its pilot climbs or sinks to find winds blowing in a different direction."),
    "parachutist": ("Skydiver", "Rare", "glider",
                    "A parachutist or skydiver.",
                    "In freefall, belly to the earth, a skydiver falls at about 200 km/h (120 mph)."),
    "ultralight": ("Microlight or paraglider", "Rare", "glider",
                   "Microlights, hang-gliders and paragliders.",
                   "A paraglider's wing has no stiff parts at all: air rushing into cells along its front edge "
                   "inflates it into shape."),
    "uav": ("Drone", "Rare", "uav",
            "An unmanned aircraft, flown from the ground.",
            "Small hobby drones don't use ADS-B: in the US, for example, drones aren't allowed to broadcast it "
            "without permission, so as not to crowd the frequency."),
    "space": ("Spaceplane", "Rare", "jet",
              "A space or \"trans-atmospheric\" vehicle: one that flies to the edge of space.",
              "The rarest category of all: almost nothing uses it."),
    "emergency": ("Airport fire engine", "Rare", "truck",
                  "An airport's fire engines and emergency vehicles.",
                  "At big airports, vehicles carry transponders so the control tower can see them on its ground "
                  "radar and keep them off runways in use."),
    "service": ("Airport vehicle", "Rare", "truck",
                "Airport service vehicles: tugs, \"follow me\" cars and the like.",
                "A \"follow me\" car leads a plane along the taxiways to its stand at an unfamiliar airport."),
    "obstacle": ("Obstacle", "Rare", "mast",
                 "A fixed or tethered obstacle: a tall mast, crane or tethered balloon, announcing itself to pilots.",
                 "Some obstacles mark where they are this way so that pilots' own displays show them in bad "
                 "visibility."),
}
ORDER = ("large", "unknown", "heavy", "small", "light", "rotorcraft", "vortex", "performance", "glider", "balloon",
         "parachutist", "ultralight", "uav", "space", "emergency", "service", "obstacle")

AIRLINES = {
    "AAL": "American Airlines", "ACA": "Air Canada", "AEA": "Air Europa", "AEE": "Aegean Airlines", "AFL": "Aeroflot",
    "AFR": "Air France", "AIC": "Air India", "AMX": "Aeroméxico", "ANA": "All Nippon Airways", "ANZ": "Air New Zealand",
    "ASA": "Alaska Airlines", "AUA": "Austrian Airlines", "AUR": "Aurigny", "AVA": "Avianca", "BAW": "British Airways",
    "BCS": "European Air Transport (DHL)", "BEL": "Brussels Airlines", "BTI": "airBaltic", "CCA": "Air China",
    "CES": "China Eastern", "CFE": "BA CityFlyer", "CFG": "Condor", "CKS": "Kalitta Air", "CLX": "Cargolux",
    "CPA": "Cathay Pacific", "CSN": "China Southern", "DAL": "Delta Air Lines", "DHK": "DHL Air",
    "DLH": "Lufthansa", "EDW": "Edelweiss", "EIN": "Aer Lingus", "EJA": "NetJets", "EJU": "easyJet Europe",
    "ELY": "El Al", "ENT": "Enter Air", "ENY": "Envoy Air", "ETD": "Etihad Airways", "ETH": "Ethiopian Airlines",
    "EWG": "Eurowings", "EXS": "Jet2", "EZS": "easyJet Switzerland", "EZY": "easyJet", "FDX": "FedEx",
    "FFT": "Frontier Airlines", "FIN": "Finnair", "GFA": "Gulf Air", "GIA": "Garuda Indonesia", "GLO": "Gol",
    "GTI": "Atlas Air", "HAL": "Hawaiian Airlines", "IBE": "Iberia", "ICE": "Icelandair", "ITY": "ITA Airways",
    "JAL": "Japan Airlines", "JBU": "JetBlue", "JZA": "Jazz", "KAC": "Kuwait Airways", "KAL": "Korean Air",
    "KLM": "KLM", "KQA": "Kenya Airways", "LAN": "LATAM Chile", "LOG": "Loganair", "LOT": "LOT Polish Airlines",
    "MAS": "Malaysia Airlines", "MEA": "Middle East Airlines", "MSR": "EgyptAir", "NAX": "Norwegian",
    "NJE": "NetJets Europe", "NKS": "Spirit Airlines", "OMA": "Oman Air", "PAL": "Philippine Airlines",
    "PGT": "Pegasus Airlines", "PIA": "Pakistan International Airlines", "POE": "Porter Airlines",
    "QFA": "Qantas", "QTR": "Qatar Airways", "RAM": "Royal Air Maroc", "RCH": "US Air Mobility Command (REACH)",
    "RJA": "Royal Jordanian", "ROT": "TAROM", "RPA": "Republic Airways", "RRR": "Royal Air Force (ASCOT)",
    "RUK": "Ryanair UK", "RYR": "Ryanair", "SAA": "South African Airways", "SAS": "SAS Scandinavian Airlines",
    "SHT": "British Airways Shuttle", "SIA": "Singapore Airlines", "SKW": "SkyWest", "SVA": "Saudia",
    "SWA": "Southwest Airlines", "SWR": "Swiss", "SXS": "SunExpress", "TAM": "LATAM Brasil",
    "TAP": "TAP Air Portugal", "THA": "Thai Airways", "THY": "Turkish Airlines", "TOM": "TUI Airways",
    "TRA": "Transavia", "TSC": "Air Transat", "TVF": "Transavia France", "UAE": "Emirates", "UAL": "United Airlines",
    "UPS": "UPS Airlines", "VIR": "Virgin Atlantic", "VJT": "VistaJet", "VLG": "Vueling", "VOI": "Volaris",
    "VOZ": "Virgin Australia", "WJA": "WestJet", "WUK": "Wizz Air UK", "WZZ": "Wizz Air",
}

# registration prefixes (as they're broadcast, without the dash): (pattern, country)
REGISTRATIONS = [
    (r"N[1-9][0-9A-Z]{0,4}", "United States"), (r"G[A-Z]{4}", "United Kingdom"), (r"M[A-Z]{4}", "Isle of Man"),
    (r"EI[A-Z]{3}", "Ireland"), (r"D[A-Z]{4}", "Germany"), (r"F[A-Z]{4}", "France"), (r"I[A-Z]{4}", "Italy"),
    (r"EC[A-Z]{3}", "Spain"), (r"CS[A-Z]{3}", "Portugal"), (r"PH[A-Z]{3}", "Netherlands"), (r"OO[A-Z]{3}", "Belgium"),
    (r"LX[A-Z]{3}", "Luxembourg"), (r"HB[A-Z]{3}", "Switzerland"), (r"OE[A-Z]{3}", "Austria"),
    (r"OK[A-Z]{3}", "Czechia"), (r"SP[A-Z]{3}", "Poland"), (r"SE[A-Z]{3}", "Sweden"), (r"LN[A-Z]{3}", "Norway"),
    (r"OH[A-Z]{3}", "Finland"), (r"OY[A-Z]{3}", "Denmark"), (r"TF[A-Z]{3}", "Iceland"), (r"9H[A-Z]{3}", "Malta"),
    (r"SX[A-Z]{3}", "Greece"), (r"TC[A-Z]{3}", "Turkey"), (r"C[FGI][A-Z]{3}", "Canada"),
    (r"VH[A-Z]{3}", "Australia"), (r"ZK[A-Z]{3}", "New Zealand"),
]


def classify_callsign(cs):
    """('airline', code, name) for a flight number, ('country', name, name) for a registration, or None."""
    cs = (cs or "").upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z]{3})[0-9][0-9A-Z]{0,4}", cs)
    if m:
        code = m.group(1)
        return "airline", code, AIRLINES.get(code, f"Airline {code}")
    for pat, country in REGISTRATIONS:
        if re.fullmatch(pat, cs):
            return "country", country, country
    return None


def score(store):
    kinds = {r["key"] for r in store.finds("sky_kind")}
    return (sum(scores.POINTS[KINDS[k][1]] for k in kinds if k in KINDS)
            + AIRLINE_POINTS * len(store.finds("sky_airline")) + COUNTRY_POINTS * len(store.finds("sky_country"))
            + PLANE_POINTS * int(store.get("sky_total", 0) or 0))


class Sky:
    def __init__(self, store):
        self.store = store
        self.live = {}                       # address -> what's known about it, in memory only
        self._day, self._key, self._today = None, b"", set()
        self.messages = 0

    def _once_today(self, icao, now):
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        if day != self._day:
            self._day, self._key, self._today = day, os.urandom(16), set()   # yesterday's key is gone
        tag = hmac.new(self._key, icao.encode(), hashlib.sha256).digest()[:8]
        if tag in self._today:
            return False
        self._today.add(tag)
        return True

    def heard(self, line, now=None, ref=None):
        """One rtl_adsb line. Returns news: [("plane",), ("kind", key), ("airline", code, name),
        ("country", name)], each new one once."""
        now = now or time.time()
        m = adsb.decode(line, ref)
        if not m:
            return []
        self.messages += 1
        news = []
        p = self.live.setdefault(m["icao"], {"first": now})
        p["last"] = now
        if self._once_today(m["icao"], now):
            self.store.put("sky_total", int(self.store.get("sky_total", 0) or 0) + 1)
            news.append(("plane",))
        for k in ("callsign", "alt_ft", "speed_kt"):
            if m.get(k) is not None:
                p[k] = m[k]
        if m.get("lat") is not None and ref:
            p["km"] = round(adsb.distance_km(ref[0], ref[1], m["lat"], m["lon"]), 1)
        kind = m.get("kind")
        if kind and kind in KINDS and p.get("kind") != kind:
            p["kind"] = kind
            if self.store.find_seen("sky_kind", kind, KINDS[kind][0], kind, now):
                news.append(("kind", kind))
        if m.get("callsign") and not p.get("classified"):
            p["classified"] = True
            c = classify_callsign(m["callsign"])
            if c and self.store.find_seen("sky_" + c[0], c[1], c[2], c[0], now):
                news.append((c[0], c[1], c[2]))
        for a in [a for a, q in self.live.items() if now - q["last"] > LIVE_S]:
            del self.live[a]                 # gone: forgotten
        return news

    def now(self, now=None):
        """Planes heard in the last two minutes, nearest (or highest) first, for the Den."""
        now = now or time.time()
        out = [dict(callsign=p.get("callsign", ""), alt_ft=p.get("alt_ft"), km=p.get("km"),
                    kind=KINDS.get(p.get("kind"), ("",))[0]) for p in self.live.values() if now - p["last"] <= LIVE_S]
        return sorted(out, key=lambda p: (p["km"] is None, p["km"] or 0, -(p["alt_ft"] or 0)))


def _date(t):
    return time.strftime("%d %b %Y", time.localtime(t)) if t else ""


SOURCES = [("Wikipedia: Automatic Dependent Surveillance-Broadcast",
            "https://en.wikipedia.org/wiki/Automatic_Dependent_Surveillance%E2%80%93Broadcast"),
           ("Junzi Sun: The 1090 Megahertz Riddle (the ADS-B book)", "https://mode-s.org/1090mhz/")]
EXPLAIN = [
    ("Planes say where they are",
     "Airliners work out where they are from satellite navigation, and twice a second their transponders "
     "broadcast it on 1090 MHz, with their height, speed, flight number and an address of their own: ADS-B, "
     "\"Automatic Dependent Surveillance - Broadcast\". Air traffic control and other aircraft listen, and so can an "
     "inexpensive radio stick. Airliners in Europe and the US have had to carry it since 2020."),
    ("A message in 112 bits",
     "Each message is 112 ones and zeros, sent in 120 millionths of a second. The last 24 are a checksum: if a single "
     "bit arrives wrong, the sum doesn't add up and the message is thrown away. Positions are squeezed into 17 bits "
     "each for latitude and longitude: not enough on their own, but enough knowing roughly where the listener is."),
    ("How far",
     "1090 MHz travels in straight lines, so what you can hear depends on the horizon: a plane at 11,000 m (36,000 "
     "ft) can be heard from 300 km away or more with a clear view of the sky; from indoors, or a bag, much less."),
    ("What Harald keeps",
     "The kinds of aircraft, airlines and countries heard, and how many planes a day. Not planes' addresses: each "
     "one is counted once a day with a key that's thrown away at midnight, and the planes overhead now are "
     "forgotten two minutes after they're last heard."),
]


def page_data(name, store, sky=None):
    kinds = {r["key"]: r for r in store.finds("sky_kind")}
    items = []
    for k in ORDER:
        title, rarity, icon, what, dyk = KINDS[k]
        r = kinds.get(k)
        items.append({"id": k, "title": title, "rarity": rarity, "icon": icon, "found": bool(r),
                      "sub": f"heard {r['count']}×" if r else "", "count": r["count"] if r else 0,
                      "card": {"title": title, "rarity": rarity, "group": "Aircraft", "text": [what], "dyk": dyk,
                               "sources": SOURCES, "mine": {"first": r["first_seen"] if r else None,
                                                            "label": "", "list": []}}})
    extras = []
    for coll, title, icon, what, how in (
            ("sky_airline", "Airlines", "jet", "Airlines heard, from the first three letters of their flight numbers.",
             "Every airline has a three-letter code from the International Civil Aviation Organization (ICAO): BAW is "
             "British Airways, EZY easyJet, RYR Ryanair. On the radio, each also has a spoken callsign: British "
             "Airways is \"Speedbird\"."),
            ("sky_country", "Registrations", "prop", "Countries whose aircraft registrations have been heard.",
             "Private planes often use their registration as their callsign. Its first letters say which country it's "
             "registered in: G is the United Kingdom, N the United States, D Germany, F France, EI Ireland.")):
        rows = store.finds(coll)
        extras.append({"id": coll, "title": title, "icon": icon, "count": len(rows),
                       "unit": "airline" if coll == "sky_airline" else "country",
                       "units": "airlines" if coll == "sky_airline" else "countries",
                       "card": {"title": title, "rarity": "", "group": "Field finds", "text": [what, how], "dyk": "",
                                "sources": SOURCES[:1],
                                "mine": {"first": None, "label": "",
                                         "list": [{"label": r["label"] + (f" ({r['key']})" if coll == "sky_airline" else ""),
                                                   "sub": f"first heard {_date(r['first_seen'])}"} for r in rows]}}})
    total = int(store.get("sky_total", 0) or 0)
    found = sum(1 for i in items if i["found"])
    now_planes = sky.now() if sky else []
    return {"kind": "sky", "name": name, "title": f"{name}'s Sky Dragons",
            "subtitle": f"{found} of {len(items)} kinds of aircraft · {total} plane{'s' if total != 1 else ''} heard"
                        + (f" · {len(now_planes)} overhead now" if now_planes else ""),
            "score": dict(scores.view(scores.SKY_TITLES, score(store)), what="Sky Dragon points"),
            "intro": f"Planes {name} has heard broadcasting where they are, with a radio stick (untested). Tap a kind "
                     "of aircraft to learn about it.",
            "rules": f"Points: {scores.POINTS['Common']} for a Common kind, {scores.POINTS['Uncommon']} Uncommon, "
                     f"{scores.POINTS['Rare']} Rare, {AIRLINE_POINTS} for each new airline or country, and "
                     f"{PLANE_POINTS} for each plane, once a day.",
            "explain_title": "How planes are heard", "explain": [(h, p.replace("Harald", name)) for h, p in EXPLAIN],
            "groups": [{"name": "Aircraft", "items": items}], "extras": extras}
