"""
Official weather warnings for Harald's Lair, straight from the national weather services.

  - **United Kingdom:** the Met Office's warnings RSS feed for the Lair's region (one of 16,
    such as "North West England" or "Strathclyde"). The region is worked out once, when the
    Lair is set, from the county or council area the place finder reports, and can be
    changed in the den if it guessed wrong.
  - **United States:** the National Weather Service's alerts, for the Lair's forecast zone
    and county. Warnings there are issued per zone and county, and the Lair is only kept to
    about 10 km, which near a county line could land in the neighbor's. So the zone and
    county are looked up once, when the Lair is set, from the town (or ZIP area) itself, and
    kept by name ("KYZ079", "KYC111"); after that only those names are sent.

Elsewhere there aren't any yet: each country publishes its own way.

He checks every 15 minutes while Local announcements are on, and announces each new
warning once.
"""
import json
import logging
import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import __version__

log = logging.getLogger("weather_warnings")

USER_AGENT = f"BTDragon/{__version__} (https://github.com/sauvryn/BT-dragon)"
MET_OFFICE = "https://weather.metoffice.gov.uk/public/data/PWSCache/WarningsRSS/Region/{}"
NWS = "https://api.weather.gov"

UK_REGIONS = {
    "os": "Orkney & Shetland", "he": "Highlands & Eilean Siar", "gr": "Grampian", "st": "Strathclyde",
    "ta": "Central, Tayside & Fife", "dg": "SW Scotland, Lothian & Borders", "ni": "Northern Ireland",
    "wl": "Wales", "nw": "North West England", "ne": "North East England", "yh": "Yorkshire & Humber",
    "wm": "West Midlands", "em": "East Midlands", "ee": "East of England", "sw": "South West England",
    "se": "London & South East England",
}
# Counties, council areas and unitary authorities, as the place finder names them, by region
_UK_AREAS = {
    "nw": "lancashire, merseyside, cheshire, cheshire east, cheshire west and chester, "
          "warrington, halton, cumbria, cumberland, westmorland and furness, blackburn with darwen, blackpool",
    "ne": "northumberland, tyne and wear, durham, county durham, darlington, hartlepool, middlesbrough, "
          "redcar and cleveland, stockton-on-tees",
    "yh": "north yorkshire, west yorkshire, south yorkshire, east riding of yorkshire, kingston upon hull, hull, "
          "york, north lincolnshire, north east lincolnshire",
    "wm": "west midlands, staffordshire, stoke-on-trent, shropshire, telford and wrekin, herefordshire, "
          "worcestershire, warwickshire",
    "em": "derbyshire, derby, nottinghamshire, nottingham, leicestershire, leicester, rutland, lincolnshire, "
          "northamptonshire, north northamptonshire, west northamptonshire",
    "ee": "norfolk, suffolk, cambridgeshire, peterborough, essex, southend-on-sea, thurrock, hertfordshire, "
          "bedfordshire, bedford, central bedfordshire, luton",
    "sw": "cornwall, isles of scilly, devon, plymouth, torbay, somerset, north somerset, "
          "bath and north east somerset, bristol, gloucestershire, south gloucestershire, wiltshire, swindon, "
          "dorset, bournemouth, christchurch and poole, bournemouth christchurch and poole",
    "se": "greater london, london, kent, medway, surrey, east sussex, west sussex, brighton and hove, hampshire, "
          "southampton, portsmouth, isle of wight, berkshire, reading, wokingham, west berkshire, "
          "bracknell forest, windsor and maidenhead, slough, buckinghamshire, milton keynes, oxfordshire",
    "os": "orkney, orkney islands, shetland, shetland islands",
    "he": "highland, eilean siar, na h-eileanan siar, na h-eileanan an iar, western isles",
    "gr": "aberdeenshire, aberdeen, aberdeen city, moray",
    "st": "glasgow, glasgow city, argyll and bute, east dunbartonshire, west dunbartonshire, east renfrewshire, "
          "renfrewshire, inverclyde, north lanarkshire, south lanarkshire, east ayrshire, north ayrshire, "
          "south ayrshire",
    "ta": "perth and kinross, angus, dundee, dundee city, fife, stirling, clackmannanshire, falkirk",
    "dg": "dumfries and galloway, scottish borders, edinburgh, city of edinburgh, east lothian, midlothian, "
          "west lothian",
}
UK_AREAS = {name.strip(): code for code, names in _UK_AREAS.items() for name in names.split(",")}
# roughly the middle of each region: a last resort when the county isn't recognised
UK_MIDDLES = {"os": (59.5, -2.0), "he": (57.5, -5.0), "gr": (57.2, -2.6), "st": (55.8, -4.6), "ta": (56.4, -3.4),
              "dg": (55.4, -3.3), "ni": (54.6, -6.7), "wl": (52.3, -3.7), "nw": (53.8, -2.7), "ne": (55.0, -1.8),
              "yh": (53.9, -1.2), "wm": (52.5, -2.2), "em": (53.0, -0.9), "ee": (52.3, 0.6),
              "sw": (50.9, -3.6), "se": (51.3, -0.5)}


def _clean(name):
    n = (name or "").lower().strip()
    for lead in ("city and county of ", "county of ", "city of ", "the "):
        if n.startswith(lead):
            n = n[len(lead):]
    return n.replace("&", "and").replace(",", "").strip()


def uk_region(admin1, admin2, lat, lon):
    """The Met Office warning region for a place: from its country and county if known,
    otherwise the region whose middle is nearest."""
    a1 = _clean(admin1)
    if a1 == "wales":
        return "wl"
    if a1 == "northern ireland":
        return "ni"
    code = UK_AREAS.get(_clean(admin2))
    if code:
        return code
    pool = {"scotland": ("os", "he", "gr", "st", "ta", "dg"), "england": ("nw", "ne", "yh", "wm", "em", "ee", "sw", "se")}
    codes = pool.get(a1, tuple(UK_MIDDLES))
    return min(codes, key=lambda c: (UK_MIDDLES[c][0] - lat) ** 2 + ((UK_MIDDLES[c][1] - lon) * math.cos(math.radians(lat))) ** 2)


# ------------------------------------------------------------------ fetching
def _fetch(url, accept="application/json", timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def us_zones(lat, lon, fetch=_fetch):
    """The NWS forecast zone and county for a point: ['KYZ079', 'KYC111']."""
    p = json.loads(fetch(f"{NWS}/points/{lat:.4f},{lon:.4f}", "application/geo+json")).get("properties") or {}
    return [u.rstrip("/").rsplit("/", 1)[-1] for u in (p.get("forecastZone"), p.get("county")) if u]


def us_warnings(zones, fetch=_fetch):
    data = json.loads(fetch(f"{NWS}/alerts/active?zone={urllib.parse.quote(','.join(zones))}", "application/geo+json"))
    out = []
    for f in data.get("features") or []:
        p = f.get("properties") or {}
        if p.get("status", "Actual") != "Actual" or p.get("messageType") == "Cancel":
            continue
        out.append({"id": p.get("id") or f.get("id"), "title": p.get("event", "Weather alert"),
                    "spoken": p.get("headline") or p.get("event", "Weather alert"),
                    "severe": p.get("severity") in ("Severe", "Extreme")})
    return out


TITLE = re.compile(r"(?i)\b(yellow|amber|red)\b\s+warning of\s+(.+?)(?:\s+affecting\b.*)?$")


def uk_warnings(region, fetch=_fetch):
    root = ET.fromstring(fetch(MET_OFFICE.format(region), "application/rss+xml, application/xml"))
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        m = TITLE.search(title)
        if not m:
            continue
        colour, what = m.group(1).lower(), m.group(2).strip().rstrip(".")
        desc = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
        valid = re.search(r"(?i)valid (from .+?)(?:$|\.)", " ".join(desc.split()))
        out.append({"id": (item.findtext("guid") or item.findtext("link") or "") + "|" + title,
                    "title": f"{colour.capitalize()} warning: {what}",
                    "spoken": f"{colour.capitalize()} warning of {what}" + (f", valid {valid.group(1)}" if valid else ""),
                    "severe": colour in ("amber", "red")})
    return out


def area_for(code, lookup, fetch=_fetch):
    """When the Lair is set: {"source": "uk"|"us"|"", "area": region code or zones}. `lookup` is
    the place finder's answer, with the town's own coordinates (used here, then forgotten)."""
    if code == "GB":
        return {"source": "uk", "area": uk_region(lookup.get("admin1"), lookup.get("admin2"),
                                                 lookup["exact_lat"], lookup["exact_lon"])}
    if code in ("US", "PR", "GU", "VI", "AS", "MP"):
        try:
            zones = us_zones(lookup["exact_lat"], lookup["exact_lon"], fetch)
        except Exception as e:
            log.info("NWS zone lookup failed: %s", e)
            zones = []
        return {"source": "us", "area": zones}
    return {"source": "", "area": ""}


def fetch_warnings(source, area, fetch=_fetch):
    if source == "uk" and area:
        return uk_warnings(area, fetch)
    if source == "us" and area:
        return us_warnings(area, fetch)
    return []
