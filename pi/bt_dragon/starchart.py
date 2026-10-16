"""
The Star Chart (Den → Conquests → Open the Star Chart): Harald's "stars", the navigation
satellites he's heard, as a collection, one card per system (constellation), with who runs
it and how it works, and how satellite navigation finds where you are.

The facts are kept short and checked against the sources listed on each card. Numbers of
satellites change as old ones retire and new ones launch, so they're given as "about".
"""
import time

# NMEA satellite numbers, for the card ("GPS satellites are numbered 1 to 32")
HOW_IT_WORKS = [
    ("Clocks in the sky",
     "Each navigation satellite carries atomic clocks and sends out, over and over, the exact time and where "
     "it is in its orbit. That's all it does: it doesn't know you're there, and nothing is ever sent back up. "
     "Harald, your phone and every satnav only ever listen."),
    ("Time is distance",
     "A receiver notes when each signal arrives. Radio travels at the speed of light, about 300,000 km a "
     "second, so the delay says how far away that satellite is: a millionth of a second is 300 meters. One "
     "satellite puts you somewhere on a giant sphere around it; three spheres meet at one point."),
    ("Why four, not three",
     "A receiver's own clock is cheap and nowhere near as good as an atomic one, so its idea of \"now\" is a "
     "little out. A fourth satellite lets it work out its own clock error along with the three directions. "
     "More satellites than that make the answer better, which is why phones listen to several systems at once."),
    ("Fainter than the noise",
     "A satellite 20,000 km away sends with about the power of a few light bulbs, and by the time it reaches "
     "you its signal is weaker than the background radio hiss around it. Receivers still find it because each "
     "satellite sends its own long, known pattern of bits (its \"code\"): listening for a pattern you know is "
     "like picking out a song you know in a noisy room. The satellite's number (its PRN, \"pseudo-random "
     "noise\" number) says which pattern is its. Harald counts a star when one is heard clearly enough "
     "(Developer Tools → Detection)."),
    ("Einstein in your pocket",
     "Up there, in weaker gravity, time runs faster: by about 45 millionths of a second a day (general "
     "relativity). Moving at nearly 4 km a second, it runs slower: by about 7 (special relativity). Together, "
     "a GPS satellite's clock gains about 38 millionths of a second a day, which, left alone, would put your "
     "position out by around 10 km after one day. So the clocks are set slightly slow before launch "
     "(10.22999999543 MHz instead of 10.23) and tick at the right rate once in orbit."),
    ("Rising and setting",
     "Most of the satellites circle the Earth every 11 to 14 hours, so the ones overhead keep changing. Harald cheers "
     "when a star already on the chart comes back up over the horizon: heard again low in the sky after being "
     "out of earshot."),
]

CONSTELLATIONS = {
    "GPS": {
        "title": "GPS", "full": "Global Positioning System (Navstar)", "country": "United States",
        "rarity": "Common", "since": "1978 (first launch); complete in 1995",
        "run": "the US Space Force", "sats": "about 31 in service", "orbit": "about 20,200 km up, twice round the Earth a day",
        "numbers": "1 to 32",
        "text": ["The oldest of today's systems, built for the US military in the 1970s and opened to everyone. It's the "
                 "one most people mean by \"GPS\", though phones now listen to every system they can hear.",
                 "The satellites fly in six rings (orbital planes) around the Earth. Each goes round twice a day, "
                 "so the same satellites return to the same part of your sky about four minutes earlier each day."],
        "dyk": "Until May 2000, the public GPS signal was deliberately blurred (\"Selective Availability\"), "
               "putting your position out by up to about 100 meters. Switching that off is why satnavs suddenly "
               "got good.",
        "sources": [("GPS.gov: Space segment", "https://www.gps.gov/systems/gps/space/"),
                    ("Wikipedia: Global Positioning System", "https://en.wikipedia.org/wiki/Global_Positioning_System"),
                    ("Penn State: The satellite clock", "https://courses.ems.psu.edu/geog862/node/1714")],
        "shape": [(10, 70), (30, 52), (52, 60), (70, 38), (88, 30), (60, 22)],
    },
    "GLONASS": {
        "title": "GLONASS", "full": "GLObalnaya NAvigatsionnaya Sputnikovaya Sistema", "country": "Russia",
        "rarity": "Common", "since": "1982 (first launch); complete in 1995, again in 2011",
        "run": "Russia's space agency, Roscosmos, and its armed forces", "sats": "about 24 in service",
        "orbit": "about 19,100 km up, round the Earth in about 11 hours 15 minutes", "numbers": "65 to 96",
        "text": ["Russia's answer to GPS, begun by the Soviet Union. After the Soviet Union broke up, too few "
                 "replacements were launched and the system fell to a handful of satellites; it was rebuilt to a "
                 "full set in 2011.",
                 "Its rings are tilted more steeply than GPS's, which helps far in the north, like Scandinavia "
                 "and northern Russia."],
        "dyk": "Older GLONASS satellites each broadcast on their own slightly different radio frequency, where "
               "every other system shares one frequency and tells satellites apart by their codes.",
        "sources": [("Wikipedia: GLONASS", "https://en.wikipedia.org/wiki/GLONASS")],
        "shape": [(14, 30), (34, 46), (50, 30), (66, 50), (86, 36), (50, 72)],
    },
    "Galileo": {
        "title": "Galileo", "full": "Galileo", "country": "European Union",
        "rarity": "Common", "since": "2011 (first working satellites); in service since December 2016",
        "run": "the EU Agency for the Space Programme (EUSPA), with the European Space Agency (ESA)",
        "sats": "about two dozen in service", "orbit": "about 23,200 km up, round the Earth in about 14 hours",
        "numbers": "1 to 36 (301 to 336 on some receivers)",
        "text": ["Europe's own system, and the only one of the big four run by civilians rather than an army. "
                 "Named after the astronomer Galileo Galilei.",
                 "It also has a search-and-rescue service: it relays distress beacons' calls for help, and can "
                 "send a message back to the beacon to say that help is on its way."],
        "dyk": "Two Galileo satellites were left in the wrong, stretched-out orbits by a faulty rocket in 2014. "
               "Scientists turned the mistake into an experiment: as the satellites swung up and down by about "
               "8,500 km twice a day, their clocks sped up and slowed down, and measuring that tested "
               "Einstein's prediction about gravity and time more precisely than ever before (2018).",
        "sources": [("ESA: Galileo satellites prove Einstein's Relativity Theory to highest accuracy yet",
                     "https://www.esa.int/Applications/Navigation/Galileo_satellites_prove_Einstein_s_Relativity_Theory_to_highest_accuracy_yet"),
                    ("Wikipedia: Galileo (satellite navigation)",
                     "https://en.wikipedia.org/wiki/Galileo_(satellite_navigation)")],
        "shape": [(12, 60), (30, 40), (50, 50), (68, 28), (88, 44), (70, 70)],
    },
    "BeiDou": {
        "title": "BeiDou", "full": "BeiDou Navigation Satellite System", "country": "China",
        "rarity": "Common", "since": "2000 (a first test system over China); worldwide since 2020",
        "run": "the China Satellite Navigation Office", "sats": "more than 40 in service",
        "orbit": "three kinds: most about 21,500 km up, the rest about 36,000 km up over Asia",
        "numbers": "201 to 263 (or 1 to 63, depending on the receiver)",
        "text": ["China's system, built in three stages: a test over China, then Asia and the Pacific, and "
                 "then the whole world in 2020.",
                 "Unlike GPS, it mixes orbits: most satellites circle the Earth like GPS's, but some sit far "
                 "higher, either fixed over one spot or tracing a figure of eight over Asia, so that part of "
                 "the world always has extra satellites high in the sky."],
        "dyk": "BeiDou (北斗) is the Chinese name for the Big Dipper, the Plough: the seven stars travellers have "
               "used to find north for thousands of years. Its picture here is the Plough.",
        "sources": [("Wikipedia: BeiDou", "https://en.wikipedia.org/wiki/BeiDou")],
        # the Plough (Big Dipper): the bowl and the handle
        "shape": [(8, 30), (26, 26), (40, 36), (54, 42), (58, 64), (80, 70), (86, 46)],
    },
    "QZSS": {
        "title": "QZSS", "full": "Quasi-Zenith Satellite System (Michibiki, \"guiding the way\")", "country": "Japan",
        "rarity": "Rare", "since": "2010 (first launch); in service since 2018",
        "run": "the Cabinet Office of Japan", "sats": "a seven-satellite system (Michibiki No. 7 launched in August 2026)",
        "orbit": "mostly tracing a tall figure of eight over Japan and Australia, about 36,000 km up",
        "numbers": "193 to 202",
        "text": ["Japan's system. In Tokyo's tall streets and steep mountain valleys, satellites low in the sky "
                 "are hidden, so QZSS's orbits are designed to keep at least one satellite almost straight "
                 "overhead (\"quasi-zenith\") over Japan at all times.",
                 "It works alongside GPS rather than alone, sending GPS-like signals plus corrections that "
                 "make positions accurate to a few centimeters for those who can use them."],
        "dyk": "Rare unless you're in East Asia or Australia: from Europe and most of the Americas, the QZSS "
               "satellites never rise above the horizon at all.",
        "sources": [("Wikipedia: Quasi-Zenith Satellite System", "https://en.wikipedia.org/wiki/Quasi-Zenith_Satellite_System"),
                    ("JAXA: launch of Michibiki No. 7 (11 August 2026)", "https://global.jaxa.jp/press/2026/08/20260811-1_e.html")],
        "shape": [(20, 20), (50, 50), (80, 20), (80, 80), (20, 80)],
    },
    "NavIC": {
        "title": "NavIC", "full": "Navigation with Indian Constellation (IRNSS)", "country": "India",
        "rarity": "Rare", "since": "2013 (first launch)",
        "run": "the Indian Space Research Organisation (ISRO)", "sats": "a handful, high over the Indian Ocean",
        "orbit": "about 36,000 km up, fixed over one spot or swinging north and south over India",
        "numbers": "depends on the receiver",
        "text": ["India's regional system, covering India and about 1,500 km around it. Navik means \"sailor\" "
                 "or \"navigator\" in Hindi.",
                 "Because its satellites stay high over the Indian Ocean, a few are enough to cover the region, "
                 "where a worldwide system needs two dozen or more."],
        "dyk": "Rare anywhere else: its satellites are only above the horizon from around India and the Indian "
               "Ocean.",
        "sources": [("Wikipedia: Indian Regional Navigation Satellite System",
                     "https://en.wikipedia.org/wiki/Indian_Regional_Navigation_Satellite_System")],
        "shape": [(50, 14), (78, 40), (66, 78), (34, 78), (22, 40)],
    },
    "SBAS": {
        "title": "SBAS", "full": "Satellite-Based Augmentation Systems: WAAS, EGNOS and others",
        "country": "the US (WAAS), Europe (EGNOS), Japan, India, Russia, South Korea, Australia and New Zealand",
        "rarity": "Uncommon", "since": "2003 (WAAS, in the US); 2009 (EGNOS, in Europe)",
        "run": "aviation and space agencies (for EGNOS, the EU's EUSPA)", "sats": "a few per region",
        "orbit": "about 36,000 km up, fixed over the equator", "numbers": "120 to 158 (33 to 64 on some receivers)",
        "text": ["Not a navigation system of their own, but helpers for GPS (and soon Galileo): ground stations "
                 "watch the GPS signals, work out their errors (clock drift, the atmosphere bending the "
                 "signals), and these satellites broadcast the corrections.",
                 "They also send warnings within seconds if a GPS satellite goes wrong. That's what lets "
                 "aircraft use satellite navigation to come in to land."],
        "dyk": "They're geostationary: they go round once a day, exactly as fast as the Earth turns, so they "
               "hang still in the sky over the equator. From Britain, EGNOS's satellites sit low in the "
               "southern sky.",
        "sources": [("Wikipedia: GNSS augmentation", "https://en.wikipedia.org/wiki/GNSS_augmentation"),
                    ("Wikipedia: EGNOS", "https://en.wikipedia.org/wiki/European_Geostationary_Navigation_Overlay_Service")],
        "shape": [(10, 50), (30, 50), (50, 50), (70, 50), (90, 50)],
    },
}
ORDER = ("GPS", "Galileo", "GLONASS", "BeiDou", "SBAS", "QZSS", "NavIC")


def page_data(name, stars, in_view, now=None):
    """What the page shows. `stars`: store.stars() rows; `in_view`: keys heard just now."""
    now = now or time.time()
    by = {}
    for r in stars:
        by.setdefault(r["const"], []).append(r)
    items = []
    for c in ORDER:
        info = CONSTELLATIONS[c]
        mine = sorted(by.get(c, []), key=lambda r: r["prn"])
        first = min((r["first_seen"] for r in mine), default=None)
        items.append({
            "id": c, "title": info["title"], "rarity": info["rarity"], "found": bool(mine),
            "sub": info["country"] if len(info["country"]) < 30 else "Many countries",
            "count": len(mine), "now": sum(1 for r in mine if r["key"] in in_view),
            "shape": info["shape"],
            "card": {
                "title": info["full"], "rarity": info["rarity"],
                "facts": [("From", info["country"]), ("Run by", info["run"]), ("Since", info["since"]),
                          ("Satellites", info["sats"]), ("Orbit", info["orbit"]), ("Numbered", info["numbers"])],
                "text": info["text"], "dyk": info["dyk"], "sources": info["sources"],
                "mine": {"first": first, "label": "stars",
                         "list": [{"label": str(r["prn"]), "bold": r["key"] in in_view,
                                   "sub": f"first heard {time.strftime('%d %b %Y', time.localtime(r['first_seen']))}"
                                          f" · on {r['nights']} day{'s' if r['nights'] != 1 else ''}"}
                                  for r in mine]},
            },
        })
    found = sum(1 for i in items if i["found"])
    return {"kind": "stars", "name": name, "title": f"{name}'s Star Chart",
            "subtitle": f"{len(stars)} star{'s' if len(stars) != 1 else ''} in {found} of {len(items)} constellations"
                        + (f" · {len(in_view)} in view now" if in_view else ""),
            "intro": f"Every navigation satellite {name} has heard is a star on the chart, and each system they belong to "
                     "is a constellation. Tap one to learn who runs it and how it works. (Stars need GPSd "
                     "Forwarder, GPS2IP or a USB GPS receiver: SensorServer doesn't pass the satellites on.)",
            "explain_title": "How satellite navigation works",
            "explain": [(h, p.replace("Harald", name)) for h, p in HOW_IT_WORKS],
            "groups": [{"name": "Constellations", "items": items}], "extras": []}
