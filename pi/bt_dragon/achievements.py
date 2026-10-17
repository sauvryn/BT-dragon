"""
Achievements (Den → Achievements, and the Achievements page): milestones for how many of each
thing Harald has collected. They count things, never points (points are for titles).

Every achievement is earned in five stages, as in Bookworm: Copper, Bronze, Silver, Gold and
Platinum. Each stage is a runestone in its metal's colour, carved with the rune of its
category: ᚷ (G, the Gebo rune) for Gadgets, ᛊ (S, the Sowilo rune) for Stars, and so on. No two categories share a rune, so
where the first letter is taken, the next fitting word gives the rune: green spaces are ᚾ (N,
Nature), famous places ᛈ (P, Places), and Sky Dragons ᚨ (A, Aircraft).

The library's achievements (ᚲ, K for Knowledge) count books finished, of each length.

Two kinds of achievement:
  - a whole collection with a known size (every type in the Gadget Journal, every Common
    insect...): the stages are spread evenly over it, as in Bookworm, so Platinum always
    means all of it (thresholds = ceil(k * total / 5); with fewer than 5 to collect, the lowest
    stages are skipped: 2 things gives Gold at 1 and Platinum at 2);
  - an open-ended count (lands claimed, Wi-Fi networks found): five fixed milestones.

The Butterfly Garden's achievements are Bookworm's own: one "collect them all" for each
category of insect, with Bookworm's names for each country; every Common, Uncommon and Rare
species, in each category and in the whole country; two for sightings ("I've Seen It!"); and the
meta achievements, counting every country's collection.

Progress is always counted from what's been collected, so it's right after a restore too, and
anything collected before achievements existed counts. The stages reached are kept, with the
date each was reached, so the Den can show the latest. If the collection shrinks (Forget my
map, say), stages that no longer count are taken away quietly, as Bookworm does after unmerging.
"""
import math
import time

TIERS = ("copper", "bronze", "silver", "gold", "platinum")
TIER_NAMES = ("Copper", "Bronze", "Silver", "Gold", "Platinum")

# key, title, rune (Elder Futhark), the rune's name and the word it stands for, and a line for the page
SECTIONS = [
    ("gadgets", "Gadgets", "ᚷ", "G (the Gebo rune) for Gadgets", "Types of gadget eaten: the Gadget Journal."),
    ("wifi", "Wi-Fi Treats", "ᚹ", "W (the Wunjo rune) for Wi-Fi", "Wi-Fi networks found, every one a treat."),
    ("lands", "Lands and Realms", "ᛚ", "L (the Laguz rune) for Lands", "Squares of the map claimed."),
    ("places", "Famous Places", "ᛈ", "P (the Perthro rune) for Places", "Famous places (landmarks) seen."),
    ("nature", "Green Spaces", "ᚾ", "N (the Naudiz rune) for Nature", "Parks, woods, commons and nature reserves found."),
    ("stars", "Stars", "ᛊ", "S (the Sowilo rune) for Stars", "Navigation satellites heard: the Star Chart."),
    ("friends", "Dragon Friends", "ᚠ", "F (the Fehu rune) for Friends", "Other dragons met."),
    ("library", "The Library", "ᚲ", "K (the Kaunan rune) for Knowledge", "Books finished: the hoard of literary treasures."),
    ("garden", "Butterfly Garden", "ᛒ", "B (the Berkano rune) for Butterflies", "Insects raised in the Butterfly Garden: Bookworm's own achievements."),
    ("sky", "Sky Dragons", "ᚨ", "A (the Ansuz rune) for Aircraft", "Planes heard with the radio stick."),
    ("radio", "Radio Whispers", "ᚱ", "R (the Raido rune) for Radio", "Little radios heard with the radio stick."),
]
SECTION = {s[0]: s for s in SECTIONS}
# each rune's name (as usually reconstructed, in Proto-Germanic) and what the name means, for the page
RUNE_MEANINGS = [("ᚷ", "Gebo", "gift"), ("ᚹ", "Wunjo", "joy"), ("ᛚ", "Laguz", "water, or a lake"),
                 ("ᛈ", "Perthro", "unknown: perhaps a dice cup, or a fruit tree"), ("ᚾ", "Naudiz", "need"),
                 ("ᛊ", "Sowilo", "the sun"), ("ᚠ", "Fehu", "cattle, and so wealth"), ("ᛒ", "Berkano", "birch"),
                 ("ᚨ", "Ansuz", "a god"), ("ᚱ", "Raido", "a ride, or a journey"),
                 ("ᚲ", "Kaunan", "perhaps an ulcer; the Old English rune poem calls it cēn, a torch")]
DEV = {"sky", "radio"}          # (the radio stick is still in development)

# Bookworm's achievement names for each category of insect, in each country
GARDEN_NAMES = {
    "gb": {"butterfly": "Butterfly House", "moth": "Moth Trap", "beewasp": "The Hive", "beetle": "Beetlemania",
           "ant": "Colony Complete", "fly": "Fly on the Wall", "other": "Cabinet of Curiosities"},
    "us": {"butterfly": "Star-Spangled Wings", "moth": "Porch-Light Parade", "other": "Backyard Curiosities",
           "ant": "Anthill Americana", "fly": "Fly-Over Country", "beetle": "Lightning Bug Legion",
           "beewasp": "Stars, Stripes & Stingers"},
    "ca": {"butterfly": "From Sea to Sea", "moth": "Cottage Porch Light", "beewasp": "The Maple Hive",
           "beetle": "Boreal Beetles", "ant": "Anthills of the Shield", "fly": "Black Fly Season",
           "other": "Curiosities of the True North"},
    "ie": {"butterfly": "Emerald Wings", "moth": "Bog Lanterns", "beewasp": "The Bee-loud Glade",
           "beetle": "Beetles of the Burren", "ant": "The Little People", "fly": "Flies of the Four Provinces",
           "other": "The Book of Kells"}}
KIND_TITLE = {"butterfly": "Butterflies", "moth": "Moths", "beewasp": "Bees & Wasps", "beetle": "Beetles",
              "ant": "Ants", "fly": "Flies", "other": "Other Insects"}
COUNTRY_SHORT = {"gb": "British", "ie": "Irish", "us": "American", "ca": "Canadian"}
COUNTRY_META = {"gb": "Collect All British Species", "ie": "Collect All Irish Species",
                "us": "Collect All American Species", "ca": "Collect All Canadian Species"}
RARITIES = ("Common", "Uncommon", "Rare")
RARITY_META = {"Common": "Common Ground", "Uncommon": "Uncommonly Good", "Rare": "Rarities of the World"}

# the Gadget Journal's groups
GADGET_GROUPS = {"Phones and computers": "Screen Time", "Listening": "All Ears",
                 "Wearables and fitness": "Fit for Purpose", "Trackers": "Tracking the Trackers",
                 "Beacons": "Beacon Keeper", "Around the home": "Home Comforts", "Mysteries": "Unsolved Mysteries"}

# the Star Chart: about how many of each system's satellites there are to hear (they change as old
# ones retire and new ones launch, so these are round numbers: Platinum means "about all of them")
STAR_TOTALS = {"GPS": ("Navstar Navigator", 31), "Galileo": ("Galileo's Moons", 26),
               "GLONASS": ("GLONASS Gazer", 24), "BeiDou": ("The Big Dipper", 30),
               "SBAS": ("SBAS Sentinels", 8), "QZSS": ("Michibiki Watcher", 7), "NavIC": ("NavIC Navigator", 7)}


def steps(total=None, fixed=None):
    """[(stage index, needed), ...] in order (see the top of this file)."""
    if fixed:
        return [(5 - len(fixed) + i, n) for i, n in enumerate(fixed)]
    if not total or total <= 0:
        return []
    if total < 5:
        return [(5 - total + i, i + 1) for i in range(total)]
    return [(k, math.ceil((k + 1) * total / 5)) for k in range(5)]


def stage(n, st):
    """The stage reached with n (-1 for none yet)."""
    best = -1
    for m, at in st:
        if n >= at:
            best = m
    return best


def _a(section, aid, name, desc, n, unit, total=None, fixed=None, group=None, note=None):
    st = steps(total, fixed)
    goal = st[-1][1] if st else 0
    return {"section": section, "id": aid, "name": name, "desc": desc, "unit": unit, "n": int(n),
            "goal": goal, "steps": st, "group": group, "note": note,
            "whole": fixed is None}          # (a whole collection: "14 of 33")


# ---------------------------------------------------------------- counting
def gather(app):
    """Everything counted, in one go (a few database queries)."""
    from . import conquest, journal, tuning, wifi, mobilewifi
    st = app.store
    c = {}
    found, field = set(), 0
    for s in st.species_list():
        cat = journal.CAT_BY_LABEL.get(s["label"])
        if cat:
            found.add(cat[0])
        else:
            field += 1
    c["gadget_types"], c["field"] = found, field
    nets = {"all": 0, "open": 0, "wep": 0, "wpa2": 0, "wpa3": 0, "enterprise": 0, "mobile": 0}
    for ssid, auth in st.db.execute("SELECT ssid, auth FROM aps"):
        nets["all"] += 1
        if mobilewifi.kind(ssid):
            nets["mobile"] += 1
        else:
            nets[wifi.security_tier({"auth": auth or ""})] += 1
    c["nets"] = nets
    cq = conquest.counts(st, tuning.get("landmark_langs"))
    c.update(lands=cq["land"], realms=cq["realm"], places=cq["landmark"])
    greens = [g for g in st.greens_list() if g.get("first_seen")]
    c["greens"] = len(greens)
    c["green_kinds"] = {}
    for g in greens:
        c["green_kinds"][g.get("kind")] = c["green_kinds"].get(g.get("kind"), 0) + 1
    stars = st.stars()
    c["stars"] = len(stars)
    c["by_const"] = {}
    for s in stars:
        c["by_const"][s["const"]] = c["by_const"].get(s["const"], 0) + 1
    c["friends"] = app.friends.count() if getattr(app, "friends", None) else 0
    c["garden"] = app.garden if getattr(app, "garden", None) else None
    c["books"] = app.library.counts() if getattr(app, "library", None) else {"short": 0, "medium": 0, "long": 0}
    c["sky_total"] = int(st.get("sky_total", 0) or 0)
    c["finds"] = {k: len(st.finds(k)) for k in ("sky_kind", "sky_airline", "sky_country",
                                                "whisper_kind", "whisper_model")}
    return c


def build(c):
    """Every achievement, with its progress."""
    from . import journal, planes, whispers, starchart
    out = []
    # ---- Gadgets (ᚷ)
    got = c["gadget_types"]
    cat = journal.CATALOGUE
    out.append(_a("gadgets", "g-journal", "The Gadget Journal", "Find every type of gadget in the Gadget Journal",
                  sum(1 for x in cat if x[0] in got), "types", total=len(cat)))
    for g, name in GADGET_GROUPS.items():
        ids = [x[0] for x in cat if x[1] == g]
        out.append(_a("gadgets", "g-" + g.split()[0].lower(), name, f"Find every type of gadget in {g.lower()}",
                      sum(1 for i in ids if i in got), "types", total=len(ids), group="By group"))
    for r in RARITIES:
        ids = [x[0] for x in cat if x[3] == r]
        out.append(_a("gadgets", "g-" + r.lower(), f"{r} Gadgets", f"Find every {r} type of gadget",
                      sum(1 for i in ids if i in got), "types", total=len(ids), group="By rarity"))
    out.append(_a("gadgets", "g-field", "Field Notes", "Field finds: gadgets named by their maker or by the name they broadcast",
                  c["field"], "field finds", fixed=(5, 20, 50, 150, 400)))
    # ---- Wi-Fi (ᚹ)
    n = c["nets"]
    out.append(_a("wifi", "w-all", "Network Gourmet", "Find Wi-Fi networks of every kind", n["all"], "networks",
                  fixed=(25, 100, 500, 2000, 10000)))
    out += [
        _a("wifi", "w-wpa2", "Everyday Fare", "Find WPA2 networks, the everyday kind", n["wpa2"], "networks",
           fixed=(20, 80, 400, 1500, 8000), group="By kind"),
        _a("wifi", "w-wpa3", "Fresh Locks", "Find WPA3 networks, the newest kind", n["wpa3"], "networks",
           fixed=(3, 10, 40, 150, 500), group="By kind"),
        _a("wifi", "w-open", "Open Doors", "Find open networks (no password)", n["open"], "networks",
           fixed=(5, 20, 80, 250, 1000), group="By kind"),
        _a("wifi", "w-ent", "Office Hours", "Find office networks (WPA2/3-Enterprise)", n["enterprise"], "networks",
           fixed=(3, 10, 40, 150, 500), group="By kind"),
        _a("wifi", "w-wep", "Antique Locks", "Find WEP networks, from the early 2000s", n["wep"], "networks",
           fixed=(1, 3, 10, 25, 50), group="By kind"),
        _a("wifi", "w-mobile", "On the Move", "Find mobile Wi-Fi: cars, buses, trains and phone hotspots", n["mobile"],
           "networks", fixed=(5, 25, 100, 300, 1000), group="By kind"),
    ]
    # ---- Lands (ᛚ), Places (ᛈ), Nature (ᚾ)
    out.append(_a("lands", "l-lands", "Land Claimer", "Claim lands (squares of the map about 250 m across)",
                  c["lands"], "lands", fixed=(10, 50, 250, 1000, 5000)))
    out.append(_a("lands", "l-realms", "Realm Builder", "Claim realms (squares of the map about 1 km across)",
                  c["realms"], "realms", fixed=(2, 10, 50, 200, 1000)))
    out.append(_a("places", "p-seen", "Sightseer", "See famous places for the first time", c["places"], "places",
                  fixed=(1, 5, 25, 75, 200)))
    out.append(_a("nature", "n-all", "Touch Grass", "Find green spaces of any kind", c["greens"], "green spaces",
                  fixed=(1, 5, 25, 75, 200)))
    gk = c["green_kinds"]
    out += [
        _a("nature", "n-park", "Park Life", "Find parks", gk.get("park", 0), "parks",
           fixed=(1, 5, 20, 50, 120), group="By kind"),
        _a("nature", "n-wood", "Into the Woods", "Find woods and forests", gk.get("wood", 0), "woods",
           fixed=(1, 3, 10, 30, 80), group="By kind"),
        _a("nature", "n-reserve", "Wild at Heart", "Find nature reserves", gk.get("nature reserve", 0), "reserves",
           fixed=(1, 3, 10, 25, 60), group="By kind"),
        _a("nature", "n-common", "Village Greens", "Find commons and village greens",
           gk.get("common", 0) + gk.get("green", 0), "greens", fixed=(1, 3, 10, 25, 60), group="By kind"),
        _a("nature", "n-garden", "Garden Visitor", "Find public gardens", gk.get("garden", 0), "gardens",
           fixed=(1, 3, 10, 25, 60), group="By kind"),
    ]
    # ---- Stars (ᛊ)
    out.append(_a("stars", "s-stars", "Stargazer", "Hear navigation satellites", c["stars"], "stars",
                  fixed=(10, 25, 50, 100, 150)))
    found = sum(1 for k in starchart.ORDER if c["by_const"].get(k))
    out.append(_a("stars", "s-consts", "Every Constellation", "Hear a satellite from every navigation system",
                  found, "constellations", total=len(starchart.ORDER)))
    for k in starchart.ORDER:
        name, total = STAR_TOTALS[k]
        out.append(_a("stars", "s-" + k.lower(), name, f"Hear {k} satellites (about {total} of them up there)",
                      min(c["by_const"].get(k, 0), total), "satellites", total=total, group="By constellation"))
    # ---- Friends (ᚠ)
    out.append(_a("friends", "f-met", "Dragon Friends", "Meet other dragons", c["friends"], "dragons",
                  fixed=(1, 3, 5, 10, 25)))
    # ---- the Library (ᚲ): books finished, of each length (Bookworm's: under 450 pages, 450-799, 800+)
    bk = c["books"]
    out += [
        _a("library", "k-all", "The Dragon's Hoard", "Finish books of any length", sum(bk.values()), "books",
           fixed=(5, 25, 50, 100, 250)),
        _a("library", "k-short", "Short and Sweet", "Finish Short books (under 450 pages)", bk["short"], "books",
           fixed=(5, 15, 30, 60, 100), group="By length"),
        _a("library", "k-medium", "The Middle Shelf", "Finish Medium books (450 to 799 pages)", bk["medium"], "books",
           fixed=(3, 8, 15, 30, 50), group="By length"),
        _a("library", "k-long", "Doorstoppers", "Finish Long books (800 pages or more)", bk["long"], "books",
           fixed=(1, 3, 6, 12, 25), group="By length"),
    ]
    # ---- the Butterfly Garden (ᛒ): Bookworm's achievements
    if c["garden"] is not None:
        out += garden_achievements(c["garden"])
    # ---- Sky Dragons (ᚨ) and Radio Whispers (ᚱ): the radio stick (in development)
    f = c["finds"]
    out += [
        _a("sky", "a-kinds", "Sky Dragon Spotter", "Hear every kind of aircraft", f["sky_kind"], "kinds",
           total=len(planes.KINDS)),
        _a("sky", "a-planes", "Plane Spotter", "Hear planes", c["sky_total"], "planes", fixed=(10, 100, 500, 2000, 10000)),
        _a("sky", "a-airlines", "Frequent Flyer", "Hear planes from different airlines", f["sky_airline"], "airlines",
           fixed=(3, 10, 25, 60, 150)),
        _a("sky", "a-countries", "Around the World", "Hear planes from different countries", f["sky_country"],
           "countries", fixed=(2, 5, 12, 25, 50)),
        _a("radio", "r-kinds", "Whisper Catcher", "Hear every kind of little radio", f["whisper_kind"], "kinds",
           total=len(whispers.KINDS)),
        _a("radio", "r-models", "Model Collector", "Hear different models of little radio", f["whisper_model"],
           "models", fixed=(3, 10, 25, 60, 150)),
    ]
    return out


def garden_achievements(garden):
    """Bookworm's achievements, from the garden's collections and sightings (see the top of this file)."""
    from .garden import data, COUNTRY_NAME
    d = data()["countries"]
    out = []
    got = {c: {e["species"] for e in garden.cdata(c)["collection"]} for c in COUNTRY_NAME}
    c = garden.country()
    sp = d[c]["species"]
    mine = got[c]
    short = COUNTRY_SHORT[c]
    kinds = [k for k in KIND_TITLE if any(s["kind"] == k for s in sp)]
    for k in kinds:
        ids = [s["id"] for s in sp if s["kind"] == k]
        out.append(_a("garden", f"b-{c}-all-{k}", GARDEN_NAMES[c].get(k, f"All {KIND_TITLE[k]}"),
                      f"Collect all {short} {KIND_TITLE[k]}", sum(1 for i in ids if i in mine), "species",
                      total=len(ids), group=f"{COUNTRY_NAME[c]} collection"))
    for r in RARITIES:
        ids = [s["id"] for s in sp if s["rarity"] == r]
        if ids:
            out.append(_a("garden", f"b-{c}-rar-{r.lower()}", f"Every {r} Species",
                          f"Collect every {r} {short} species, in every category", sum(1 for i in ids if i in mine),
                          "species", total=len(ids), group=f"{r} species"))
        for k in kinds:
            ids = [s["id"] for s in sp if s["kind"] == k and s["rarity"] == r]
            if ids:
                out.append(_a("garden", f"b-{c}-rar-{r.lower()}-{k}", f"{r} {KIND_TITLE[k]}",
                              f"Collect every {r} {short} species in {KIND_TITLE[k]}",
                              sum(1 for i in ids if i in mine), "species", total=len(ids), group=f"{r} species"))
    seen = garden.cdata(c)["seen"] or {}
    ids = [s["id"] for s in sp if seen.get(s["id"])]
    out.append(_a("garden", f"b-{c}-seen-50", "Keen Spotter",
                  f"Mark {min(50, len(sp))} {short} species as seen in the wild, at any life stage",
                  len(ids), "species", total=min(50, len(sp)), group="Sightings"))
    whole = [i for i in ids if "young" in seen[i] and "pupa" in seen[i] and any(str(x).startswith("adult") for x in seen[i])]
    out.append(_a("garden", f"b-{c}-seen-stages-5", "Life Cycle Watcher",
                  "See the larva, the pupa and an adult of 5 species in the wild", len(whole), "species", total=5,
                  group="Sightings"))
    for x in COUNTRY_NAME:
        ids = [s["id"] for s in d[x]["species"]]
        out.append(_a("garden", f"b-meta-{x}", COUNTRY_META[x], f"Raise every species in the {COUNTRY_SHORT[x]} collection",
                      sum(1 for i in ids if i in got[x]), "species", total=len(ids), group="Meta achievements"))
    for r in RARITIES:
        n = total = 0
        for x in COUNTRY_NAME:
            ids = [s["id"] for s in d[x]["species"] if s["rarity"] == r]
            total += len(ids)
            n += sum(1 for i in ids if i in got[x])
        out.append(_a("garden", f"b-meta-{r.lower()}", RARITY_META[r], f"Raise every {r} species in every country",
                      n, "species", total=total, group="Meta achievements"))
    return out


# ---------------------------------------------------------------- the stages reached
def sync(store, achs, now=None):
    """Brings the saved stages in line with progress. Returns the newly reached ones
    [(achievement, stage)], highest first. The first time ever, everything already collected
    is counted without any fuss: (achievements, 'first')."""
    now = now or time.time()
    rec = store.get("achievements")
    first = rec is None
    rec = rec or {}
    fresh, changed = [], first
    for a in achs:
        r = rec.get(a["id"]) or {"m": -1, "dates": {}}
        m = stage(a["n"], a["steps"])
        if m > r["m"]:
            for i in range(r["m"] + 1, m + 1):
                if any(s == i for s, _ in a["steps"]):
                    r["dates"][TIERS[i]] = now
            r["m"] = m
            rec[a["id"]] = r
            changed = True
            fresh.append((a, m))
        elif m < r["m"]:
            r["m"] = m
            r["dates"] = {k: v for k, v in r["dates"].items() if TIERS.index(k) <= m}
            if m < 0:
                rec.pop(a["id"], None)
            else:
                rec[a["id"]] = r
            changed = True
    if changed:
        store.put("achievements", rec)
    fresh.sort(key=lambda x: -x[1])
    return fresh, ("first" if first else None)


def latest(store, achs=None):
    """The most recently reached stage: (record id, stage index, when) or None."""
    rec = store.get("achievements") or {}
    best = None
    for aid, r in rec.items():
        for k, t in r.get("dates", {}).items():
            if best is None or t > best[2] or (t == best[2] and TIERS.index(k) > best[1]):
                best = (aid, TIERS.index(k), t)
    return best


def summary(store, achs):
    """For the Den: the latest runestone, and how many there are."""
    rec = store.get("achievements") or {}
    by_id = {a["id"]: a for a in achs}
    lt = latest(store)
    out = {"earned": sum(1 for a in achs if (rec.get(a["id"]) or {}).get("m", -1) >= 0),
           "platinum": sum(1 for a in achs if (rec.get(a["id"]) or {}).get("m", -1) == 4),
           "total": len(achs), "latest": None}
    if lt and lt[0] in by_id:
        a = by_id[lt[0]]
        s = SECTION[a["section"]]
        need = dict((m, n) for m, n in a["steps"]).get(lt[1])
        out["latest"] = {"name": a["name"], "section": s[1], "rune": s[2], "tier": TIERS[lt[1]],
                         "tier_name": TIER_NAMES[lt[1]], "when": int(lt[2]), "need": need, "unit": a["unit"],
                         "desc": a["desc"], "dev": a["section"] in DEV}
    return out


def page_data(name, store, achs, locks):
    """What the Achievements page shows. `locks`: {section: why it's locked} for sections that
    aren't open yet (the map, the Star Chart and the garden open at level 5)."""
    rec = store.get("achievements") or {}
    secs = []
    for key, title, rune, word, line in SECTIONS:
        items = []
        for a in (x for x in achs if x["section"] == key):
            r = rec.get(a["id"]) or {"m": -1, "dates": {}}
            items.append(dict(a, m=r["m"], dates={k: int(v) for k, v in r["dates"].items()}))
        if not items:
            continue
        secs.append({"key": key, "title": title, "rune": rune, "word": word, "line": line, "dev": key in DEV,
                     "locked": locks.get(key), "items": items,
                     "platinum": sum(1 for i in items if i["m"] == 4)})
    return {"name": name, "tiers": TIER_NAMES, "sections": secs, "summary": summary(store, achs),
            "runes": RUNE_MEANINGS}
