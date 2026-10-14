"""
Places Harald knows by name, for "what time is it in ..." and "what's the weather in ...".

Each entry: spoken name -> (time zone, latitude, longitude, how to say it). Only big
cities, countries and US states: nothing more local than a major city. For a country or a
US state, the weather comes from its biggest or best-known city, and he says which.
Time zones are the IANA names Python's zoneinfo uses, so daylight saving time, and the
different dates the UK and the US change their clocks, come out right by themselves.
"""

# US states: time zone (most of the state), and a big city for the weather
_STATES = {
    "alabama": ("America/Chicago", 33.52, -86.80, "Birmingham, Alabama"),
    "alaska": ("America/Anchorage", 61.22, -149.90, "Anchorage, Alaska"),
    "arizona": ("America/Phoenix", 33.45, -112.07, "Phoenix, Arizona"),
    "arkansas": ("America/Chicago", 34.75, -92.29, "Little Rock, Arkansas"),
    "california": ("America/Los_Angeles", 34.05, -118.24, "Los Angeles, California"),
    "colorado": ("America/Denver", 39.74, -104.99, "Denver, Colorado"),
    "connecticut": ("America/New_York", 41.76, -72.67, "Hartford, Connecticut"),
    "delaware": ("America/New_York", 39.74, -75.55, "Wilmington, Delaware"),
    "florida": ("America/New_York", 25.76, -80.19, "Miami, Florida"),
    "georgia": ("America/New_York", 33.75, -84.39, "Atlanta, Georgia"),
    "hawaii": ("Pacific/Honolulu", 21.31, -157.86, "Honolulu, Hawaii"),
    "idaho": ("America/Boise", 43.62, -116.20, "Boise, Idaho"),
    "illinois": ("America/Chicago", 41.88, -87.63, "Chicago, Illinois"),
    "indiana": ("America/Indiana/Indianapolis", 39.77, -86.16, "Indianapolis, Indiana"),
    "iowa": ("America/Chicago", 41.59, -93.62, "Des Moines, Iowa"),
    "kansas": ("America/Chicago", 37.69, -97.34, "Wichita, Kansas"),
    "kentucky": ("America/New_York", 38.25, -85.76, "Louisville, Kentucky"),
    "louisiana": ("America/Chicago", 29.95, -90.07, "New Orleans, Louisiana"),
    "maine": ("America/New_York", 43.66, -70.26, "Portland, Maine"),
    "maryland": ("America/New_York", 39.29, -76.61, "Baltimore, Maryland"),
    "massachusetts": ("America/New_York", 42.36, -71.06, "Boston, Massachusetts"),
    "michigan": ("America/Detroit", 42.33, -83.05, "Detroit, Michigan"),
    "minnesota": ("America/Chicago", 44.98, -93.27, "Minneapolis, Minnesota"),
    "mississippi": ("America/Chicago", 32.30, -90.18, "Jackson, Mississippi"),
    "missouri": ("America/Chicago", 39.10, -94.58, "Kansas City, Missouri"),
    "montana": ("America/Denver", 45.78, -108.50, "Billings, Montana"),
    "nebraska": ("America/Chicago", 41.26, -95.93, "Omaha, Nebraska"),
    "nevada": ("America/Los_Angeles", 36.17, -115.14, "Las Vegas, Nevada"),
    "new hampshire": ("America/New_York", 42.99, -71.45, "Manchester, New Hampshire"),
    "new jersey": ("America/New_York", 40.74, -74.17, "Newark, New Jersey"),
    "new mexico": ("America/Denver", 35.08, -106.65, "Albuquerque, New Mexico"),
    "new york state": ("America/New_York", 40.71, -74.01, "New York City"),
    "north carolina": ("America/New_York", 35.23, -80.84, "Charlotte, North Carolina"),
    "north dakota": ("America/Chicago", 46.88, -96.79, "Fargo, North Dakota"),
    "ohio": ("America/New_York", 39.96, -83.00, "Columbus, Ohio"),
    "oklahoma": ("America/Chicago", 35.47, -97.52, "Oklahoma City"),
    "oregon": ("America/Los_Angeles", 45.52, -122.68, "Portland, Oregon"),
    "pennsylvania": ("America/New_York", 39.95, -75.17, "Philadelphia, Pennsylvania"),
    "rhode island": ("America/New_York", 41.82, -71.41, "Providence, Rhode Island"),
    "south carolina": ("America/New_York", 32.78, -79.93, "Charleston, South Carolina"),
    "south dakota": ("America/Chicago", 43.54, -96.73, "Sioux Falls, South Dakota"),
    "tennessee": ("America/Chicago", 36.16, -86.78, "Nashville, Tennessee"),
    "texas": ("America/Chicago", 29.76, -95.37, "Houston, Texas"),
    "utah": ("America/Denver", 40.76, -111.89, "Salt Lake City, Utah"),
    "vermont": ("America/New_York", 44.48, -73.21, "Burlington, Vermont"),
    "virginia": ("America/New_York", 36.85, -75.98, "Virginia Beach, Virginia"),
    "washington state": ("America/Los_Angeles", 47.61, -122.33, "Seattle, Washington"),
    "west virginia": ("America/New_York", 38.35, -81.63, "Charleston, West Virginia"),
    "wisconsin": ("America/Chicago", 43.04, -87.91, "Milwaukee, Wisconsin"),
    "wyoming": ("America/Denver", 41.14, -104.82, "Cheyenne, Wyoming"),
}

_CITIES = {
    # Britain and Ireland
    "london": ("Europe/London", 51.51, -0.13, "London"),
    "manchester": ("Europe/London", 53.48, -2.24, "Manchester"),
    "liverpool": ("Europe/London", 53.41, -2.98, "Liverpool"),
    "leeds": ("Europe/London", 53.80, -1.55, "Leeds"),
    "birmingham": ("Europe/London", 52.49, -1.89, "Birmingham"),
    "sheffield": ("Europe/London", 53.38, -1.47, "Sheffield"),
    "newcastle": ("Europe/London", 54.98, -1.61, "Newcastle"),
    "bristol": ("Europe/London", 51.45, -2.59, "Bristol"),
    "glasgow": ("Europe/London", 55.86, -4.25, "Glasgow"),
    "edinburgh": ("Europe/London", 55.95, -3.19, "Edinburgh"),
    "cardiff": ("Europe/London", 51.48, -3.18, "Cardiff"),
    "belfast": ("Europe/London", 54.60, -5.93, "Belfast"),
    "dublin": ("Europe/Dublin", 53.35, -6.26, "Dublin"),
    # Europe
    "paris": ("Europe/Paris", 48.86, 2.35, "Paris"),
    "berlin": ("Europe/Berlin", 52.52, 13.40, "Berlin"),
    "rome": ("Europe/Rome", 41.90, 12.50, "Rome"),
    "madrid": ("Europe/Madrid", 40.42, -3.70, "Madrid"),
    "barcelona": ("Europe/Madrid", 41.39, 2.17, "Barcelona"),
    "lisbon": ("Europe/Lisbon", 38.72, -9.14, "Lisbon"),
    "amsterdam": ("Europe/Amsterdam", 52.37, 4.90, "Amsterdam"),
    "brussels": ("Europe/Brussels", 50.85, 4.35, "Brussels"),
    "zurich": ("Europe/Zurich", 47.38, 8.54, "Zurich"),
    "vienna": ("Europe/Vienna", 48.21, 16.37, "Vienna"),
    "prague": ("Europe/Prague", 50.08, 14.44, "Prague"),
    "warsaw": ("Europe/Warsaw", 52.23, 21.01, "Warsaw"),
    "athens": ("Europe/Athens", 37.98, 23.73, "Athens"),
    "istanbul": ("Europe/Istanbul", 41.01, 28.98, "Istanbul"),
    "oslo": ("Europe/Oslo", 59.91, 10.75, "Oslo"),
    "stockholm": ("Europe/Stockholm", 59.33, 18.07, "Stockholm"),
    "copenhagen": ("Europe/Copenhagen", 55.68, 12.57, "Copenhagen"),
    "helsinki": ("Europe/Helsinki", 60.17, 24.94, "Helsinki"),
    "reykjavik": ("Atlantic/Reykjavik", 64.15, -21.94, "Reykjavik"),
    "moscow": ("Europe/Moscow", 55.76, 37.62, "Moscow"),
    # Americas
    "new york": ("America/New_York", 40.71, -74.01, "New York City"),
    "washington": ("America/New_York", 38.91, -77.04, "Washington, D C"),
    "boston": ("America/New_York", 42.36, -71.06, "Boston"),
    "miami": ("America/New_York", 25.76, -80.19, "Miami"),
    "orlando": ("America/New_York", 28.54, -81.38, "Orlando"),
    "atlanta": ("America/New_York", 33.75, -84.39, "Atlanta"),
    "chicago": ("America/Chicago", 41.88, -87.63, "Chicago"),
    "houston": ("America/Chicago", 29.76, -95.37, "Houston"),
    "dallas": ("America/Chicago", 32.78, -96.80, "Dallas"),
    "new orleans": ("America/Chicago", 29.95, -90.07, "New Orleans"),
    "baton rouge": ("America/Chicago", 30.45, -91.19, "Baton Rouge"),
    "nashville": ("America/Chicago", 36.16, -86.78, "Nashville"),
    "denver": ("America/Denver", 39.74, -104.99, "Denver"),
    "phoenix": ("America/Phoenix", 33.45, -112.07, "Phoenix"),
    "las vegas": ("America/Los_Angeles", 36.17, -115.14, "Las Vegas"),
    "los angeles": ("America/Los_Angeles", 34.05, -118.24, "Los Angeles"),
    "san francisco": ("America/Los_Angeles", 37.77, -122.42, "San Francisco"),
    "seattle": ("America/Los_Angeles", 47.61, -122.33, "Seattle"),
    "honolulu": ("Pacific/Honolulu", 21.31, -157.86, "Honolulu"),
    "toronto": ("America/Toronto", 43.65, -79.38, "Toronto"),
    "montreal": ("America/Toronto", 45.50, -73.57, "Montreal"),
    "vancouver": ("America/Vancouver", 49.28, -123.12, "Vancouver"),
    "mexico city": ("America/Mexico_City", 19.43, -99.13, "Mexico City"),
    "rio de janeiro": ("America/Sao_Paulo", -22.91, -43.17, "Rio de Janeiro"),
    "sao paulo": ("America/Sao_Paulo", -23.55, -46.63, "Sao Paulo"),
    "buenos aires": ("America/Argentina/Buenos_Aires", -34.60, -58.38, "Buenos Aires"),
    # Africa, Asia, Oceania
    "cairo": ("Africa/Cairo", 30.04, 31.24, "Cairo"),
    "lagos": ("Africa/Lagos", 6.52, 3.38, "Lagos"),
    "nairobi": ("Africa/Nairobi", -1.29, 36.82, "Nairobi"),
    "cape town": ("Africa/Johannesburg", -33.92, 18.42, "Cape Town"),
    "johannesburg": ("Africa/Johannesburg", -26.20, 28.05, "Johannesburg"),
    "dubai": ("Asia/Dubai", 25.20, 55.27, "Dubai"),
    "mumbai": ("Asia/Kolkata", 19.08, 72.88, "Mumbai"),
    "delhi": ("Asia/Kolkata", 28.61, 77.21, "Delhi"),
    "bangkok": ("Asia/Bangkok", 13.76, 100.50, "Bangkok"),
    "singapore": ("Asia/Singapore", 1.35, 103.82, "Singapore"),
    "hong kong": ("Asia/Hong_Kong", 22.32, 114.17, "Hong Kong"),
    "beijing": ("Asia/Shanghai", 39.90, 116.41, "Beijing"),
    "shanghai": ("Asia/Shanghai", 31.23, 121.47, "Shanghai"),
    "seoul": ("Asia/Seoul", 37.57, 126.98, "Seoul"),
    "tokyo": ("Asia/Tokyo", 35.68, 139.69, "Tokyo"),
    "manila": ("Asia/Manila", 14.60, 120.98, "Manila"),
    "jakarta": ("Asia/Jakarta", -6.21, 106.85, "Jakarta"),
    "sydney": ("Australia/Sydney", -33.87, 151.21, "Sydney"),
    "melbourne": ("Australia/Melbourne", -37.81, 144.96, "Melbourne"),
    "perth": ("Australia/Perth", -31.95, 115.86, "Perth"),
    "auckland": ("Pacific/Auckland", -36.85, 174.76, "Auckland"),
}

_COUNTRIES = {
    "england": "london", "britain": "london", "the uk": "london", "scotland": "edinburgh",
    "wales": "cardiff", "northern ireland": "belfast", "ireland": "dublin",
    "france": "paris", "germany": "berlin", "italy": "rome", "spain": "madrid",
    "portugal": "lisbon", "holland": "amsterdam", "the netherlands": "amsterdam",
    "belgium": "brussels", "switzerland": "zurich", "austria": "vienna", "poland": "warsaw",
    "greece": "athens", "turkey": "istanbul", "norway": "oslo", "sweden": "stockholm",
    "denmark": "copenhagen", "finland": "helsinki", "iceland": "reykjavik", "russia": "moscow",
    "canada": "toronto", "mexico": "mexico city", "brazil": "sao paulo", "argentina": "buenos aires",
    "egypt": "cairo", "nigeria": "lagos", "kenya": "nairobi", "south africa": "johannesburg",
    "india": "delhi", "thailand": "bangkok", "china": "beijing", "korea": "seoul",
    "south korea": "seoul", "japan": "tokyo", "the philippines": "manila", "philippines": "manila",
    "indonesia": "jakarta", "australia": "sydney", "new zealand": "auckland",
}

PLACES = dict(_CITIES)
PLACES.update(_STATES)
for _c, _city in _COUNTRIES.items():
    _tz, _lat, _lon, _say = _CITIES[_city]
    PLACES[_c] = (_tz, _lat, _lon, _say)
PLACES["washington d c"] = _CITIES["washington"]
# A plain state name also works where it isn't a city too ("new york" means the city)

# What each place is called in answers about TIME (the state or country itself)
TIME_NAME = {k: k.title() for k in PLACES}
TIME_NAME.update({"the uk": "the U K", "washington d c": "Washington, D C", "washington": "Washington, D C",
                  "new york state": "New York", "washington state": "Washington State"})
for _k in ("the netherlands", "the philippines"):
    TIME_NAME[_k] = "the " + _k[4:].title()


def find_place(text):
    """The longest place name in `text` (lower case, words separated by spaces), or None."""
    padded = f" {text} "
    best = None
    for name in PLACES:
        if f" {name} " in padded and (best is None or len(name) > len(best)):
            best = name
    return best


def place_words():
    """Every word used in a place name (for the speech recognizer's vocabulary)."""
    out = set()
    for name in PLACES:
        out.update(name.split())
    return out
