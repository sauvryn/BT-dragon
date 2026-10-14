"""Official weather warnings at the Lair (Met Office regions, NWS zones found from the town
itself), announced once each; and typed answers on his screen."""
import asyncio
import json
import tempfile
import time

from bt_dragon import config, lair, weather_warnings as ww
from bt_dragon.app import Dragon
from bt_dragon.fonts import text_width
from bt_dragon.pet import STATUS_W

# which Met Office region
R = ww.uk_region
assert R("England", "Kent", 51.2, 0.7) == "se" and R("Wales", "Cardiff", 51.5, -3.2) == "wl"
assert R("Scotland", "Glasgow City", 55.9, -4.3) == "st" and R("Scotland", "City of Edinburgh", 55.95, -3.2) == "dg"
assert R("Northern Ireland", "", 54.6, -5.9) == "ni" and R("England", "West Yorkshire", 53.8, -1.5) == "yh"
assert R("England", "Unknownshire", 51.5, -0.1) == "se"                    # not recognised: the nearest region
assert R("Scotland", "", 57.1, -2.1) == "gr"

# the feeds
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Met Office warnings</title>
<item><title>Amber warning of wind affecting London &amp; South East England</title>
<description>Amber warning of wind affecting London &amp; South East England: Kent valid from 0600 Thu 15 Oct to 2100 Thu 15 Oct</description>
<link>https://example.org/w/1</link><guid>w1</guid></item>
<item><title>Yellow warning of rain affecting London &amp; South East England</title><description>x</description><guid>w2</guid></item>
<item><title>Something else entirely</title><guid>w3</guid></item>
</channel></rss>"""
got = ww.uk_warnings("se", lambda url, accept="", timeout=15: RSS)
assert [w["title"] for w in got] == ["Amber warning: wind", "Yellow warning: rain"], got
assert got[0]["spoken"] == "Amber warning of wind, valid from 0600 Thu 15 Oct to 2100 Thu 15 Oct" and got[0]["severe"]
asked = []
NWS_POINT = {"properties": {"forecastZone": "https://api.weather.gov/zones/forecast/TXZ192",
                            "county": "https://api.weather.gov/zones/county/TXC453"}}
NWS_ALERTS = {"features": [
    {"properties": {"id": "urn:a1", "event": "Heat Advisory", "severity": "Moderate", "status": "Actual",
                    "messageType": "Alert", "headline": "Heat Advisory issued until 8 PM"}},
    {"properties": {"id": "urn:t1", "event": "Test", "status": "Test", "messageType": "Alert"}}]}


def fetch(url, accept="", timeout=15):
    asked.append(url)
    if "metoffice" in url:
        return RSS
    if "/points/" in url:
        return json.dumps(NWS_POINT)
    return json.dumps(NWS_ALERTS)


assert ww.us_zones(30.2672, -97.7431, fetch) == ["TXZ192", "TXC453"] and asked[-1].endswith("/points/30.2672,-97.7431")
w = ww.us_warnings(["TXZ192", "TXC453"], fetch)
assert [x["title"] for x in w] == ["Heat Advisory"] and "zone=TXZ192%2CTXC453" in asked[-1]


# a Lair in each country
def geo(name, country_code, lat, lon, admin1, admin2):
    def get(url, params, timeout=12):
        return {"results": [{"name": name, "admin1": admin1, "admin2": admin2, "country_code": country_code,
                             "latitude": lat, "longitude": lon}]}
    return get


tmp = tempfile.mkdtemp()
cfg = config.load(None)
cfg["data_dir"] = tmp
app = Dragon(cfg, simulate=True, out_dir=tmp)
pushed = []
app.dot.phone.push = pushed.append
app.dot.s.update(enabled=False, phone=True, chatty="all", quiet_from="00:00", quiet_to="00:00")
L = app.lair
L.fetch = fetch


async def run():
    # the US: zone and county from the town itself, then only their names are used
    L.get = geo("Austin", "US", 30.26715, -97.74306, "Texas", "Travis")
    r = await app.command("LAIRSET Austin, Texas|USA")
    assert r[0].startswith("OK Found Austin, Texas"), r
    assert asked[-1].endswith("/points/30.2672,-97.7431")                     # the town's middle, once
    assert L.s["warn"] == {"source": "us", "area": ["TXZ192", "TXC453"]} and L.s["lat"] == 30.3
    assert "exact_lat" not in L.s and "30.26715" not in json.dumps(L.s)      # never kept
    assert "warnings" not in L.due(time.time())                               # Local announcements off
    await app.command("LAIRANNOUNCE on")
    lt = time.localtime()
    T = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 10, 5, 0, 0, 0, -1))
    assert "warnings" in L.due(T) and "warnings" not in L.due(T - 120)        # 5, 20, 35, 50 past
    pushed.clear()
    await app._lair_check(T, ["warnings"])
    assert pushed == ["Weather warning at the Lair: Heat Advisory issued until 8 PM."], pushed
    assert app.pet.message == "HEAT ADVISORY AT THE LAIR" and app.pet.reaction[0] == "alarmed"
    pushed.clear()
    await app._lair_check(T + 900, ["warnings"])                               # the same one: not again
    assert pushed == []
    d = dict(x.split("=", 1) for x in await app.command("LAIR") if "=" in x)
    assert d["warn_source"] == "us" and d["warn_area"] == "TXZ192, TXC453" and d["warn_active"] == "Heat Advisory"
    r = await app.command("ASK are there any weather warnings at home")
    assert r == ["OK There's one weather warning at the Lair: Heat Advisory issued until 8 PM."], r
    assert app.pet.message == "ANSWER: A LONG RESPONSE. CHECK THE DEN.", app.pet.message
    # and if the service can't be reached, nothing breaks and it's tried again next time
    L.fetch = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
    assert await L.check(T + 1800, ["warnings"]) == [] and "warnings" in L.due(T + 1800)
    L.fetch = fetch
    # warnings speech can be switched off: the screen still shows it
    NWS_ALERTS["features"][0]["properties"]["id"] = "urn:a2"
    await app.command("DOTSET say_lair_warnings false")
    pushed.clear()
    await app._lair_check(T + 2700, ["warnings"])
    assert pushed == [] and app.pet.message == "HEAT ADVISORY AT THE LAIR"
    await app.command("DOTSET say_lair_warnings true")

    # the UK: the region from the county, changeable in the den
    L.get = geo("Canterbury", "GB", 51.27904, 1.07992, "England", "Kent")
    r = await app.command("LAIRSET Canterbury|UK")
    assert r[0].startswith("OK") and L.s["warn"] == {"source": "uk", "area": "se"}, (r, L.s.get("warn"))
    await app.command("LAIRANNOUNCE on")
    pushed.clear()
    await app._lair_check(T, ["warnings"])
    assert pushed[0] == ("Weather warning at the Lair: Amber warning of wind, "
                         "valid from 0600 Thu 15 Oct to 2100 Thu 15 Oct."), pushed
    assert app.pet.message in ("AMBER WARNING: WIND AT THE LAIR", "AMBER WARNING: WIND")
    assert (await app.command("LAIRREGION nw")) == ["OK"] and L.s["warn"]["area"] == "nw"
    assert (await app.command("LAIRREGION zz"))[0].startswith("ERR")
    # elsewhere: none yet
    L.get = geo("Paris", "FR", 48.85, 2.35, "Île-de-France", "Paris")
    await app.command("LAIRSET Paris|France")
    r = await app.command("ASK any weather warnings at home")
    assert "only get official weather warnings" in r[0], r

    # typed answers on his screen: short when there's a short version, else the answer if it fits
    FORECAST = {"current": {"time": "2026-10-14T15:15", "temperature_2m": 14.2, "weather_code": 3,
                            "relative_humidity_2m": 71.6, "pressure_msl": 1013.0},
                "hourly": {}, "daily": {"sunrise": ["2026-10-13T07:24", "2026-10-14T07:26", "2026-10-15T07:28"],
                                        "sunset": ["2026-10-13T18:15", "2026-10-14T18:13", "2026-10-15T18:11"],
                                        "uv_index_max": [1, 3.4, 1]}}
    from bt_dragon import ask
    ask.fetch_weather = lambda lat, lon, timeout=10: FORECAST
    lair.fetch_conditions = lambda lat, lon, get=None: FORECAST
    pushed.clear()
    r = await app.command("ASK what's the temperature at home")
    assert app.pet.message == "ANSWER: IT'S 14°C (58°F) AT THE LAIR", app.pet.message
    assert pushed == [r[0][3:]] and "ANSWER" not in pushed[0]                     # spoken as normal, in full
    await app.command("ASK what's the humidity at home")
    assert app.pet.message == "ANSWER: 72% HUMIDITY AT THE LAIR"
    await app.command("ASK when is sunset tomorrow at home")
    assert app.pet.message == "ANSWER: SUNSET TOMORROW 6:11 PM", app.pet.message        # "at the Lair" didn't fit
    await app.command("ASK what's the uv index at home")
    assert app.pet.message == "ANSWER: UV UP TO 3 (MODERATE) AT THE LAIR", app.pet.message
    await app.command("ASK what day is it")
    assert app.pet.message.startswith("ANSWER: IT") and text_width(app.pet.message) <= STATUS_W, app.pet.message

asyncio.run(run())
assert Dragon.screen_answer("x" * 200) == "ANSWER: A LONG RESPONSE. CHECK THE DEN."
assert Dragon.screen_answer("It's noon.") == "ANSWER: IT'S NOON"
assert text_width("ANSWER: A LONG RESPONSE. CHECK THE DEN.") <= STATUS_W
print("warnings ok")
