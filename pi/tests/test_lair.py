"""Harald's Lair: countries, postcodes cut to their area, the lookup (and its errors),
local announcements (temperature, storms, weather changes) and questions about home."""
import asyncio
import datetime
import tempfile
import time
import urllib.error

from bt_dragon import ask, config, countries, lair, tuning
from bt_dragon.app import Dragon

# countries, however they're typed
C = countries.code_for
assert C("Canada") == "CA" and C("canada ") == "CA" and C("CA") == "CA" and C("ca") == "CA"
assert C("USA") == "US" and C("U.S.A.") == "US" and C("United States of America") == "US" and C("us") == "US"
assert C("UK") == "GB" and C("England") == "GB" and C("Great Britain") == "GB" and C("United Kingdom") == "GB"
assert C("Ireland") == "IE" and C("Holland") == "NL" and C("Narnia") is None and C("") is None
assert countries.name_of("GB") == "United Kingdom" and "Canada" in countries.names()

# postcodes: only the area is ever looked up
T = lair.trim_postcode
assert T("SW1A 1AA", "GB") == ("SW1A", True) and T("e1 6an", "GB") == ("E1", True) and T("EC1A1BB", "GB") == ("EC1A", True)
assert T("SW1A", "GB") == ("SW1A", False)                       # already just the area
assert T("M5V 3L9", "CA") == ("M5V", True) and T("10001-1234", "US") == ("10001", True)
assert T("10001", "US") == ("10001", False) and T("1012 AB", "NL") == ("1012", True)
assert T("D02 X285", "IE") == ("D02", True) and T("Toronto", "CA") == ("Toronto", False)

# the lookup
asked = []


def fake_get(url, params, timeout=12):
    asked.append((url, dict(params)))
    if "geocoding" in url:
        if params["name"] == "Nowhereville":
            return {}
        if params["name"] == "offline":
            raise urllib.error.URLError("no network")
        return {"results": [{"name": "Toronto", "admin1": "Ontario", "country_code": params["countryCode"],
                             "latitude": 43.70011, "longitude": -79.4163, "timezone": "America/Toronto"}]}
    if "air-quality" in url:
        return AIR
    return FORECAST


AIR = {"current": {"grass_pollen": 3.0}}
g = lair.lookup("Toronto", "Canada", fake_get)
assert g == {"label": "Toronto, Ontario", "country": "Canada", "code": "CA", "lat": 43.7, "lon": -79.4,
             "tz": "America/Toronto", "trimmed": "", "admin1": "Ontario", "admin2": "",
             "exact_lat": 43.70011, "exact_lon": -79.4163}, g          # (exact: only to find the warning area)
assert asked[-1][1]["countryCode"] == "CA" and asked[-1][1]["name"] == "Toronto"
g = lair.lookup("SW1A 1AA", "UK", fake_get)
assert asked[-1][1]["name"] == "SW1A" and asked[-1][1]["countryCode"] == "GB" and g["trimmed"] == "SW1A"


def err(place, country):
    try:
        lair.lookup(place, country, fake_get)
    except lair.LookupError_ as e:
        return str(e)
    return None


assert "Fill in both" in err("Toronto", "") and "Fill in both" in err("", "Canada")
assert "don't know a country" in err("Toronto", "Narnia")
assert "couldn't find \"Nowhereville\" in Canada" in err("Nowhereville", "Canada")
assert "couldn't reach" in err("offline", "Canada")

# the weather there: pressure hour by hour, yesterday to tomorrow
now_hour = "2026-10-14T15"
hours = [(datetime.datetime(2026, 10, 13) + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(72)]
idx = hours.index(now_hour + ":00")


def forecast(p_then, p_now, p_ahead, temp=14.2):
    p = [1015.0] * 72
    p[idx - 3], p[idx], p[idx + 3] = p_then, p_now, p_ahead
    return {"current": {"time": now_hour + ":15", "temperature_2m": temp, "apparent_temperature": temp - 4,
                        "relative_humidity_2m": 71.6, "pressure_msl": p_now, "weather_code": 3},
            "hourly": {"time": hours, "pressure_msl": p, "uv_index": [0.0] * 72},
            "daily": {"sunrise": ["2026-10-13T07:24", "2026-10-14T07:26", "2026-10-15T07:28"],
                      "sunset": ["2026-10-13T18:15", "2026-10-14T18:13", "2026-10-15T18:11"],
                      "uv_index_max": [2.1, 3.4, 1.0]}}


FORECAST = forecast(1015.0, 1013.0, 1009.5)
assert lair.pressure_change(FORECAST) == (-2.0, -3.5)
assert lair.pressure_change({"current": {"time": "2030-01-01T00:00"}, "hourly": {"time": hours}}) == (None, None)

# answers
A = lair.answer_conditions
assert A("humidity", "at the Lair", FORECAST) == "The humidity at the Lair is 72 percent."
assert A("pressure", "here", FORECAST) == "The air pressure here is 1013 hectopascals, about 29.9 inches of mercury and falling."
assert A("sunrise", "at the Lair", FORECAST) == "Sunrise at the Lair was at 7:26 in the morning today. Tomorrow it's at 7:28 in the morning."
assert A("sunset", "at the Lair", FORECAST) == "Sunset at the Lair is at 6:13 in the evening today."
assert A("sunset", "in Tokyo", FORECAST, tomorrow=True) == "Tomorrow, sunset in Tokyo is at 6:11 in the evening."
assert A("uv", "at the Lair", FORECAST) == "Today's UV index at the Lair goes up to 3, which is moderate."
assert A("temperature", "at the Lair", FORECAST) == ("It's 14 degrees, that's 58 Fahrenheit, at the Lair. "
                                                     "It feels like 10.")
air = {"current": {"european_aqi": 18, "us_aqi": 30, "alder_pollen": 0.0, "birch_pollen": 2.0, "olive_pollen": None,
                   "grass_pollen": 25.0, "mugwort_pollen": 0.4, "ragweed_pollen": None}}
assert A("air", "at the Lair", air=air) == "The air quality at the Lair is good, with a European air quality index of 18."
assert A("air", "at the Lair", air=air, code="US") == "The air quality at the Lair is good, with a US air quality index of 30."
assert A("pollen", "at the Lair", air=air) == "At the Lair: tree pollen is low, grass pollen is high and weed pollen is low."
assert A("pollen", "here", air={"current": {"grass_pollen": None}}).startswith("I can only get pollen counts for places in Europe")
assert A("pollen", "here", air={"current": {"grass_pollen": 0.2, "birch_pollen": 0.0}}) == \
    "There's hardly any pollen in the air here right now."

# questions about home
P = ask.parse
assert P("what is the temperature at home") == {"intent": "weather", "place": None, "when": "now", "home": True}
assert P("what's the weather like at the lair")["home"] is True and P("what's the weather")["home"] is False
assert P("what's the humidity at home") == {"intent": "conditions", "what": "humidity", "place": None, "home": True,
                                            "tomorrow": False}
assert P("when is sunset tomorrow")["what"] == "sunset" and P("when is sunset tomorrow")["tomorrow"]
assert P("what time is sunrise")["intent"] == "conditions" and P("what time is it")["intent"] == "time"
assert P("what's the pollen count")["what"] == "pollen" and P("how is the air quality in tokyo")["place"] == "tokyo"
assert P("what's the uv index")["what"] == "uv" and P("what is the air pressure")["what"] == "pressure"
assert all(w in ask.VOCABULARY for p in ask.PHRASES for w in p.split())
assert ask.answer_weather({"current": {"temperature_2m": 9, "weather_code": 3}, "hourly": {}, "daily": {}}, "now",
                          "at the Lair").startswith("Right now at the Lair it's 9 degrees")

# the whole dragon
tmp = tempfile.mkdtemp()
cfg = config.load(None)
cfg["data_dir"] = tmp
app = Dragon(cfg, simulate=True, out_dir=tmp)
app.lair.get = fake_get
pushed = []
app.dot.phone.push = pushed.append
app.dot.s.update(enabled=False, phone=True, chatty="all", quiet_from="00:00", quiet_to="00:00")


async def run():
    r = await app.command("LAIRANNOUNCE on")
    assert r[0].startswith("ERR") and "first" in r[0]                        # needs a Lair
    r = await app.command("LAIRSET Toronto|")
    assert r[0].startswith("ERR Fill in both")
    r = await app.command("LAIRSET Nowhereville|Canada")
    assert r[0].startswith("ERR I couldn't find")
    r = await app.command("LAIRSET Toronto|Canada")
    assert r == ["OK Found Toronto, Ontario, Canada."], r
    d = dict(x.split("=", 1) for x in await app.command("LAIR") if "=" in x)
    assert d["place"] == "Toronto" and d["country"] == "Canada" and d["complete"] == "1" and d["announce"] == "0"
    assert app.lair.where() == (43.7, -79.4)
    # questions about home use the Lair; with no GPS, so does plain "the weather"
    lair.fetch_conditions = lambda lat, lon, get=None: (asked.append(("cond", lat, lon)), FORECAST)[1]
    r = await app.command("ASK what's the humidity at home")
    assert r == ["OK The humidity at the Lair is 72 percent."], r
    assert asked[-1] == ("cond", 43.7, -79.4)
    ask.fetch_weather = lambda lat, lon, timeout=10: {"current": FORECAST["current"], "hourly": {}, "daily": {}}
    r = await app.command("ASK what's the temperature at home")
    assert r[0].startswith("OK Right now at the Lair it's 14 degrees"), r
    assert pushed and pushed[-1].startswith("Right now at the Lair")             # said through the phone too
    # local announcements, each at its own minute past the hour
    assert (await app.command("LAIRANNOUNCE on")) == ["OK"]
    tuning._over["storm_first_joy"] = 7
    lt = time.localtime()
    T0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 10, 0, 0, 0, 0, -1))   # 10:00 today
    L = app.lair
    assert L.due(T0) == ["temp"] and L.due(T0 + 15 * 60) == ["temp", "pressure"]
    assert L.due(T0 + 50 * 60) == ["temp", "pressure", "pollen", "uv"]
    pushed.clear()
    joy0 = app.pet.joy
    await app._lair_check(T0)                                                   # 10:00: the temperature
    assert "IT'S 14°C (58°F)" in app.pet.message and "LAIR" in app.pet.message, app.pet.message
    assert pushed == ["At the Lair, the current temperature is 14 degrees Celsius, that's 58 Fahrenheit."], pushed
    assert app.pet.joy == joy0 and L.due(T0 + 60) == []                        # no joy; nothing more till :15
    pushed.clear()
    events0 = len(app.store.events(500))
    await app._lair_check(T0 + 15 * 60)                                         # 10:15: the pressure
    assert app.pet.joy > joy0                                                   # a storm: the usual joy
    texts = [e["text"] for e in app.store.events(500)[: len(app.store.events(500)) - events0]]
    assert any(t.startswith("A storm is coming at the Lair") for t in texts), texts
    assert any("storm coming at the Lair" in p for p in pushed), pushed
    # 10:30: pollen. Low: nothing. High grass: Achoo! (no joy)
    pushed.clear()
    await app._lair_check(T0 + 30 * 60)
    assert pushed == []
    AIR["current"] = {"grass_pollen": 60.0, "birch_pollen": 20.0}
    L.s["done"]["pollen"] = ""
    joy1 = app.pet.joy
    await app._lair_check(T0 + 31 * 60)
    assert pushed == ["Achoo! The grass pollen is high at the Lair."], pushed
    assert app.pet.reaction[0] == "sneezing" and "HIGH POLLEN" in app.pet.message and app.pet.joy == joy1
    # every hour it's high, it's on his screen; out loud only when it's gone up ("increased readings only")
    pushed.clear()
    app.pet.message = ""
    await app._lair_check(T0 + 90 * 60)                                         # 11:30, the same: screen only
    assert not any("pollen" in p for p in pushed), pushed
    assert "POLLEN" in app.pet.message or "LAIR" in app.pet.message
    assert (await app.command("DOTSET say_lair_pollen_when all")) == ["OK"]
    assert (await app.command("DOTSET say_lair_pollen_when sometimes"))[0].startswith("ERR")
    L.s["done"]["pollen"] = ""
    await app._lair_check(T0 + 91 * 60)                                         # "all high readings": said
    assert "Achoo! The grass pollen is high at the Lair." in pushed, pushed
    await app.command("DOTSET say_lair_pollen_when increased")
    AIR["current"] = {"grass_pollen": 250.0}
    pushed.clear()
    await app._lair_check(T0 + 150 * 60)                                        # 12:30: up, and already high
    assert "Achoo! The grass pollen is higher at the Lair! It's very high now." in pushed, pushed
    assert "HIGHER" in app.pet.message, app.pet.message
    assert (await app.command("DOTSET say_lair_pollen false")) == ["OK"]
    AIR["current"] = {"grass_pollen": 400.0}
    pushed.clear()
    await app._lair_check(T0 + 210 * 60)                                        # switched off: screen only
    assert not any("pollen" in p for p in pushed) and "HIGHER" in app.pet.message
    # :45: UV. High: sunglasses on (no joy); an hour later and higher: "is higher!"
    pushed.clear()
    FORECAST["hourly"]["uv_index"][idx] = 7.2
    L.cond_ts = 0
    joy2 = app.pet.joy
    await app._lair_check(T0 + 45 * 60)
    assert "Sunglasses on! The UV index at the Lair is 7, that's high." in pushed, pushed
    assert app.pet.reaction[0] == "dazzled" and app.pet.joy == joy2
    FORECAST["hourly"]["uv_index"][idx] = 8.4
    L.cond_ts, pushed[:] = 0, []
    L.s["done"]["uv"] = ""
    await app._lair_check(T0 + 105 * 60)
    assert "Sunglasses on! The UV index at the Lair is higher! It's 8 now, that's very high." in pushed, pushed
    # sunrise, as it happens, with a little joy
    sunrise = T0 + 170 * 60
    FORECAST["utc_offset_seconds"] = 0
    FORECAST["daily"]["sunrise"] = [datetime.datetime.fromtimestamp(sunrise, datetime.timezone.utc)
                                    .strftime("%Y-%m-%dT%H:%M")]
    FORECAST["daily"]["sunset"] = []
    L.cond, L.cond_ts = FORECAST, T0
    assert "sun" not in L.due(sunrise - 120) and "sun" in L.due(sunrise + 60)
    pushed.clear()
    joy3 = app.pet.joy
    await app._lair_check(sunrise + 60, ["sun"])
    assert app.pet.joy > joy3 and "THE SUN IS RISING AT THE LAIR" in app.pet.message, app.pet.message
    assert "sun" not in L.due(sunrise + 120)                                    # once
    # the temperature every hour on the hour, but not in quiet hours
    pushed.clear()
    app.dot.s.update(quiet_from="00:00", quiet_to="23:59")
    await app._lair_check(T0 + 3 * 3600, ["temp"])
    assert pushed == []
    app.dot.s.update(quiet_from="00:00", quiet_to="00:00")
    await app._lair_check(T0 + 4 * 3600, ["temp"])
    assert any(p.startswith("At the Lair, the current temperature is") for p in pushed)
    # forgetting it
    assert (await app.command("LAIRFORGET")) == ["OK"] and not app.lair.complete
    r = await app.command("ASK what's the humidity at home")
    assert "don't know where my Lair is" in r[0], r

asyncio.run(run())

# the phone's own sensors: sunshine and storms can be kept off his voice too (the screen still shows them)
app.dot.s.update(say_phone_sun=False, chatty="all")
pushed.clear()
app.pet.sunny(speak=app.dot.s["say_phone_sun"])
assert pushed == [] and app.pet.reaction[0] == "sunglasses"
app.dot.s["say_phone_sun"] = True
app.pet.reaction = None
app.pet.sunny(speak=True)
assert pushed and "sunny" in pushed[-1].lower(), pushed

# an older setup's home town carries over (for the weather) until the Lair is set properly
app2 = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
app2.lair.forget()
app2.lair.adopt_home_town("Toronto", 43.70011, -79.4163)
assert app2.lair.where() == (43.7, -79.4) and not app2.lair.complete
print("lair ok")
