"""
Harald's Lair: home, as far as the weather is concerned.

You give a place (a town, "town, state", or a zip or postcode) and a country. It's looked
up once with Open-Meteo's free geocoding service (the same one that finds "the weather in
Tokyo"), and only kept to one decimal place of latitude and longitude: about 10 km, so the
Pi never holds your exact address and the weather service is never told it.

Postcodes are trimmed before they're looked up, for the same reason. A full UK postcode
covers a street or two, so only its first half (the district, "SW1A" of "SW1A 1AA") is sent; a
Canadian postal code is cut to its first three characters, a Dutch one to its four digits,
an Irish Eircode to its routing key, and a US ZIP+4 to the five-digit ZIP (which already
covers a whole area).

With **Local announcements** on, he checks the weather at the Lair while he's online (Open-
Meteo again, sent only those rounded coordinates). Each kind of news has its own minute past
the hour, so they never pile up together: how warm it is on the hour, a storm or change in
the weather at a quarter past, high pollen at half past, and high UV at a quarter to. Sunrise
and sunset are announced as they happen. High pollen and high UV show every hour they're high
("is higher" when they've gone up since the hour before); whether he also says them out loud
every hour, or only when they've gone up, is up to you in the den.

The pressure change: Open-Meteo gives the pressure hour by hour, for the past day and the
next. He compares now with three hours ago and with three hours ahead, and takes the
bigger change: a fall of 3 hPa in 3 hours is the classic sign of a storm.
"""
import datetime
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import countries, tuning
from . import weather_warnings as ww

log = logging.getLogger("lair")

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"


class LookupError_(Exception):
    """A lookup that can't be completed, with words for the den."""


def _get(url, params, timeout=12):
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=timeout) as r:
        return json.loads(r.read().decode())


# ------------------------------------------------------------------ postcodes
def trim_postcode(text, code):
    """(what to look up, whether it was trimmed). Only a postcode's area is ever sent."""
    s = " ".join(text.upper().split())
    pats = {"GB": r"([A-Z]{1,2}\d[A-Z\d]?) ?\d[A-Z]{2}", "CA": r"([A-Z]\d[A-Z]) ?-?\d[A-Z]\d",
            "US": r"(\d{5})-?\d{4}", "NL": r"(\d{4}) ?[A-Z]{2}", "IE": r"([A-Z]\d[\dW]) ?[A-Z\d]{4}"}
    p = pats.get(code)
    if p:
        m = re.fullmatch(p, s)
        if m:
            return m.group(1), True
    return text.strip(), False


def looks_like_postcode(text):
    return bool(re.search(r"\d", text))


# ------------------------------------------------------------------ finding it
def lookup(place, country, get=_get):
    """Place + country -> {label, country, code, lat, lon, tz, trimmed}. Raises
    LookupError_ with words for the den if it can't be found (or the service can't be reached)."""
    place, country = (place or "").strip(), (country or "").strip()
    if not place or not country:
        raise LookupError_("Fill in both: a place (city, city and state, or zip/postcode) and a country.")
    code = countries.code_for(country)
    if not code:
        raise LookupError_(f"I don't know a country called \"{country}\". Try its full name, like Canada or United States.")
    query, trimmed = trim_postcode(place, code)
    try:
        data = get(GEOCODE, {"name": query, "count": 10, "countryCode": code, "language": "en", "format": "json"})
    except (urllib.error.URLError, OSError, ValueError) as e:
        log.info("lair lookup failed: %s", e)
        raise LookupError_("I couldn't reach the place-finding service. Is your dragon connected to the internet?")
    res = [r for r in (data.get("results") or []) if r.get("country_code", code) == code]
    if not res:
        what = f"the postcode area {query}" if looks_like_postcode(query) else f"\"{place}\""
        raise LookupError_(f"I couldn't find {what} in {countries.name_of(code)}. Check the spelling, "
                           "or try the nearest town instead.")
    g = res[0]
    label = g["name"] + (f", {g['admin1']}" if g.get("admin1") and g["admin1"] != g["name"] else "")
    return {"label": label, "country": countries.name_of(code), "code": code,
            "lat": round(g["latitude"], 1), "lon": round(g["longitude"], 1),
            "tz": g.get("timezone", ""), "trimmed": query if trimmed else "",
            "admin1": g.get("admin1", ""), "admin2": g.get("admin2", ""),
            # the town's (or postcode area's) own middle: only for finding its warning area, never kept
            "exact_lat": g["latitude"], "exact_lon": g["longitude"]}


# ------------------------------------------------------------------ the weather there
def fetch_conditions(lat, lon, get=_get):
    """Now and the hours around it, for a point rounded to about 10 km."""
    return get(FORECAST, {
        "latitude": round(lat, 1), "longitude": round(lon, 1),
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,pressure_msl,weather_code",
        "hourly": "pressure_msl,uv_index", "daily": "sunrise,sunset,uv_index_max",
        "timezone": "auto", "past_days": 1, "forecast_days": 2})


def fetch_air(lat, lon, get=_get):
    """Air quality and pollen (pollen: Europe only, in season)."""
    return get(AIR, {
        "latitude": round(lat, 1), "longitude": round(lon, 1), "timezone": "auto",
        "current": "european_aqi,us_aqi,alder_pollen,birch_pollen,olive_pollen,grass_pollen,"
                   "mugwort_pollen,ragweed_pollen"})


def pressure_change(data):
    """(change over the last 3 hours, change over the next 3), in hPa; None where unknown."""
    hourly = data.get("hourly") or {}
    times, p = hourly.get("time") or [], hourly.get("pressure_msl") or []
    now = (data.get("current") or {}).get("time", "")[:13]
    idx = next((i for i, t in enumerate(times) if t[:13] == now), None)
    if idx is None or idx >= len(p) or p[idx] is None:
        return None, None
    past = p[idx] - p[idx - 3] if idx >= 3 and p[idx - 3] is not None else None
    ahead = p[idx + 3] - p[idx] if idx + 3 < len(p) and p[idx + 3] is not None else None
    return past, ahead


def c_and_f(c):
    return f"{round(c)}°C ({round(c * 9 / 5 + 32)}°F)"


def deg_words(c, celsius=False):
    """Both from the exact reading, so the screen and the voice agree."""
    r = round(c)
    return f"{r} degree{'s' if abs(r) != 1 else ''}{' Celsius' if celsius else ''}, that's {round(c * 9 / 5 + 32)} Fahrenheit"


# ------------------------------------------------------------------ answers
# Pollen in grains per cubic meter, by the scale the US National Allergy Bureau uses:
# (low below, moderate below, high below; very high above)
POLLEN_SCALE = {"trees": (15, 90, 1500), "grass": (5, 20, 200), "weeds": (10, 50, 500)}
POLLEN_GROUPS = {"trees": ("alder_pollen", "birch_pollen", "olive_pollen"), "grass": ("grass_pollen",),
                 "weeds": ("mugwort_pollen", "ragweed_pollen")}


def pollen_level(group, grains):
    lo, mid, hi = POLLEN_SCALE[group]
    return "low" if grains < lo else "moderate" if grains < mid else "high" if grains < hi else "very high"


def eu_aqi_word(v):
    return ("good" if v <= 20 else "fair" if v <= 40 else "moderate" if v <= 60 else "poor" if v <= 80
            else "very poor" if v <= 100 else "extremely poor")


def us_aqi_word(v):
    return ("good" if v <= 50 else "moderate" if v <= 100 else "unhealthy for sensitive groups" if v <= 150
            else "unhealthy" if v <= 200 else "very unhealthy" if v <= 300 else "hazardous")


def uv_word(v):
    return ("low" if v < 3 else "moderate" if v < 6 else "high" if v < 8 else "very high" if v < 11 else "extreme")


def _clock(iso):
    from .ask import _clock as clock
    return clock(datetime.datetime.fromisoformat(iso))


def answer_conditions(what, where, cond=None, air=None, tomorrow=False, code=None):
    """Words for one reading. `where` is 'at the Lair', 'here' or 'in Tokyo'."""
    cap = lambda s: s[:1].upper() + s[1:]   # noqa: E731
    cur = (cond or {}).get("current") or {}
    daily = (cond or {}).get("daily") or {}
    if what == "humidity":
        return f"The humidity {where} is {round(cur['relative_humidity_2m'])} percent."
    if what == "pressure":
        p = cur["pressure_msl"]
        past, ahead = pressure_change(cond)
        trend = "" if past is None else (" and rising" if past >= 1 else " and falling" if past <= -1 else " and steady")
        return (f"The air pressure {where} is {round(p)} hectopascals, about {p * 0.02953:.1f} "
                f"inches of mercury{trend}.")
    if what in ("sunrise", "sunset"):
        times = daily.get(what) or []
        # daily runs from yesterday (past_days=1): [yesterday, today, tomorrow]
        today, tom = (times[1] if len(times) > 1 else None), (times[2] if len(times) > 2 else None)
        if tomorrow and tom:
            return f"Tomorrow, {what} {where} is at {_clock(tom)}."
        if not today:
            return f"I couldn't find the {what} time just now."
        here_now = cur.get("time")
        if here_now and here_now > today and tom:
            return f"{cap(what)} {where} was at {_clock(today)} today. Tomorrow it's at {_clock(tom)}."
        return f"{cap(what)} {where} is at {_clock(today)} today."
    if what == "uv":
        uv = (daily.get("uv_index_max") or [None, None])[1]
        if uv is None:
            return "I couldn't get the UV index just now."
        return f"Today's UV index {where} goes up to {round(uv)}, which is {uv_word(uv)}."
    if what == "air":
        a = (air or {}).get("current") or {}
        if code == "US" and a.get("us_aqi") is not None:
            v = a["us_aqi"]
            return f"The air quality {where} is {us_aqi_word(v)}, with a US air quality index of {round(v)}."
        if a.get("european_aqi") is not None:
            v = a["european_aqi"]
            return f"The air quality {where} is {eu_aqi_word(v)}, with a European air quality index of {round(v)}."
        return "I couldn't get the air quality just now."
    if what == "pollen":
        a = (air or {}).get("current") or {}
        got = {}
        for group, keys in POLLEN_GROUPS.items():
            vals = [a[k] for k in keys if a.get(k) is not None]
            if vals:
                got[group] = max(vals)
        if not got:
            return "I can only get pollen counts for places in Europe, during the pollen season."
        if all(v < 1 for v in got.values()):
            return f"There's hardly any pollen in the air {where} right now."
        parts = [f"{'tree' if g == 'trees' else 'weed' if g == 'weeds' else g} pollen is {pollen_level(g, v)}"
                 for g, v in got.items()]
        return f"{cap(where)}: " + ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] + "."
    if what == "temperature":
        s = f"It's {deg_words(cur['temperature_2m'])}, {where}."
        feels = cur.get("apparent_temperature")
        if feels is not None and abs(feels - cur["temperature_2m"]) >= 3:
            s += f" It feels like {round(feels)}."
        return s
    return "Sorry, I didn't catch that."


def _short_clock(iso):
    t = datetime.datetime.fromisoformat(iso)
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def screen_conditions(what, where, cond=None, air=None, tomorrow=False):
    """Short versions for his screen, longest first ("72% HUMIDITY AT THE LAIR", then without
    the place, in case it doesn't fit), or None if there isn't one."""
    one = _screen_condition(what, where, cond, tomorrow)
    if not one:
        return None
    w = "" if where == "here" else " " + where.upper()
    return [one, one[: -len(w)]] if w and one.endswith(w) else [one]


def _screen_condition(what, where, cond=None, tomorrow=False):
    w = "" if where == "here" else " " + where.upper()
    cur = (cond or {}).get("current") or {}
    daily = (cond or {}).get("daily") or {}
    try:
        if what == "humidity":
            return f"{round(cur['relative_humidity_2m'])}% HUMIDITY{w}"
        if what == "pressure":
            past, _ = pressure_change(cond)
            trend = "" if past is None else (", RISING" if past >= 1 else ", FALLING" if past <= -1 else ", STEADY")
            return f"{round(cur['pressure_msl'])} HPA{trend}{w}"
        if what in ("sunrise", "sunset"):
            times = daily.get(what) or []
            today, tom = (times[1] if len(times) > 1 else None), (times[2] if len(times) > 2 else None)
            if tomorrow and tom:
                return f"{what.upper()} TOMORROW {_short_clock(tom)}{w}"
            if today and cur.get("time") and cur["time"] > today and tom:
                return f"NEXT {what.upper()} {_short_clock(tom)}{w}"
            return f"{what.upper()} {_short_clock(today)}{w}" if today else None
        if what == "uv":
            uv = (daily.get("uv_index_max") or [None, None])[1]
            return f"UV UP TO {round(uv)} ({uv_word(uv).upper()}){w}" if uv is not None else None
        if what == "temperature":
            return f"IT'S {c_and_f(cur['temperature_2m'])}{w}"
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return None


# ------------------------------------------------------------------ the Lair itself
# When each announcement is checked, in minutes past the hour, so they don't all arrive at once.
SLOTS = (("temp", 0), ("pressure", 15), ("pollen", 30), ("uv", 45))
LEVELS = ("low", "moderate", "high", "very high", "extreme")     # pollen and UV, worst last
SUN_WINDOW_S = 30 * 60      # sunrise or sunset is announced if he notices within half an hour of it


class Lair:
    def __init__(self, store, get=_get, fetch=ww._fetch):
        self.store = store
        self.get = get
        self.fetch = fetch          # plain text from the weather services' warning feeds
        self.s = store.get("lair") or {}
        self.last = None            # the latest reading: {"temp", "pressure", "past", "ahead", "ts"}
        self.cond = None            # the latest forecast (Open-Meteo's answer) and when it came
        self.cond_ts = 0.0
        self.status = ""
        self._busy = False
        self._failed = 0.0

    def save(self):
        self.store.put("lair", self.s)

    @property
    def complete(self):
        return bool(self.s.get("place") and self.s.get("code") and self.s.get("lat") is not None)

    def where(self):
        return (self.s["lat"], self.s["lon"]) if self.s.get("lat") is not None else None

    def adopt_home_town(self, name, lat, lon):
        """An older setup's home town (no country yet): kept for the weather until the Lair is set."""
        if not self.s and name and lat is not None:
            self.s = {"place": name, "label": name, "lat": round(lat, 1), "lon": round(lon, 1), "code": ""}
            self.save()

    async def set_place(self, place, country):
        """Returns (ok, words for the den)."""
        import asyncio
        try:
            g = await asyncio.to_thread(lookup, place, country, self.get)
        except LookupError_ as e:
            return False, str(e)
        announce = self.s.get("announce", False)
        warn = await asyncio.to_thread(ww.area_for, g["code"], g, self.fetch)
        for k in ("exact_lat", "exact_lon"):
            g.pop(k)
        self.s = {"place": place.strip()[:60], "country_typed": country.strip()[:60], "announce": announce, **g,
                  "warn": warn, "warn_active": [], "warn_seen": []}
        self.last, self.cond, self.cond_ts = None, None, 0.0
        self.save()
        note = f" (only the area {g['trimmed']} was looked up)" if g["trimmed"] else ""
        return True, f"Found {g['label']}, {g['country']}{note}."

    def forget(self):
        self.s, self.last, self.cond, self.status = {}, None, None, ""
        self.save()

    def set_region(self, code):
        """The UK warning region, if the guess was wrong."""
        if (self.s.get("warn") or {}).get("source") != "uk":
            return "Warning regions are only for a Lair in the United Kingdom."
        if code not in ww.UK_REGIONS:
            return "No such region."
        self.s["warn"]["area"] = code
        self.s["warn_active"], self.s["warn_seen"] = [], []
        self.save()
        return None

    def warnings_where(self):
        """('uk' | 'us' | '', words for the den about the warning area)."""
        w = self.s.get("warn") or {}
        if w.get("source") == "uk":
            return "uk", ww.UK_REGIONS.get(w.get("area"), "")
        if w.get("source") == "us":
            return "us", (", ".join(w["area"]) if w.get("area") else "")
        return "", ""

    def set_announce(self, on):
        if on and not self.complete:
            return "Set the Lair's place and country first."
        self.s["announce"] = bool(on)
        self.save()
        return None

    @property
    def announcing(self):
        return self.complete and bool(self.s.get("announce"))

    # ---- the schedule
    def due(self, now):
        """Which checks are due now: some of temp, pressure, pollen, uv (each once an hour, at
        its own minute past the hour) and sun (sunrise or sunset, at the time itself)."""
        if not self.announcing or self._busy or now - self._failed < 300:
            return []
        lt = time.localtime(now)
        hour = time.strftime("%Y%m%d%H", lt)
        done = self.s.setdefault("done", {})
        kinds = [k for k, minute in SLOTS if lt.tm_min >= minute and done.get(k) != hour]
        warn = self.s.get("warn") or {}
        if warn.get("source") and warn.get("area") and lt.tm_min % 15 >= 5 \
                and done.get("warnings") != f"{hour}{lt.tm_min // 15}":
            kinds.append("warnings")      # every 15 minutes: 5, 20, 35 and 50 past
        if self.cond and self.sun_due(now):
            kinds.append("sun")
        return kinds

    def sun_events(self):
        """[(kind, epoch seconds)] for today's and tomorrow's sunrise and sunset at the Lair."""
        daily, out = (self.cond or {}).get("daily") or {}, []
        off = datetime.timezone(datetime.timedelta(seconds=(self.cond or {}).get("utc_offset_seconds", 0)))
        for kind in ("sunrise", "sunset"):
            for iso in daily.get(kind) or []:
                try:
                    out.append((kind, datetime.datetime.fromisoformat(iso).replace(tzinfo=off).timestamp()))
                except (TypeError, ValueError):
                    pass
        return out

    def sun_due(self, now):
        said = self.s.get("sun_said", [])
        return [(k, t) for k, t in self.sun_events() if 0 <= now - t < SUN_WINDOW_S and f"{k}@{int(t)}" not in said]

    async def check(self, now=None, kinds=None):
        """Run the checks that are due. Returns what's worth saying:
        ("temp", c), ("storm", d), ("rise", d), ("pollen", level, [groups]), ("uv", index, level),
        ("sunrise",) and ("sunset",)."""
        import asyncio
        now = now or time.time()
        kinds = self.due(now) if kinds is None else kinds
        if not kinds:
            return []
        self._busy = True
        try:
            if any(k in kinds for k in ("temp", "pressure", "uv")) and (not self.cond or now - self.cond_ts > 600):
                self.cond = await asyncio.to_thread(fetch_conditions, self.s["lat"], self.s["lon"], self.get)
                self.cond_ts = now
            air = None
            if "pollen" in kinds:
                air = await asyncio.to_thread(fetch_air, self.s["lat"], self.s["lon"], self.get)
            warns = None
            if "warnings" in kinds:
                w = self.s["warn"]
                try:
                    warns = await asyncio.to_thread(ww.fetch_warnings, w["source"], w["area"], self.fetch)
                except Exception as e:
                    log.info("warnings check failed: %s", e)
                    kinds = [k for k in kinds if k != "warnings"]    # try again next time round
        except Exception as e:
            log.info("lair weather check failed: %s", e)
            self.status = "couldn't reach the weather service last time"
            self._failed = now
            return []
        finally:
            self._busy = False
        self.status = ""
        cur = (self.cond or {}).get("current") or {}
        if self.cond:
            past, ahead = pressure_change(self.cond)
            self.last = {"temp": cur.get("temperature_2m"), "pressure": cur.get("pressure_msl"),
                         "past": past, "ahead": ahead, "ts": self.cond_ts}
        out = []
        hour = time.strftime("%Y%m%d%H", time.localtime(now))
        done = self.s.setdefault("done", {})
        lt = time.localtime(now)
        for k in kinds:
            if k == "warnings":
                done[k] = f"{hour}{lt.tm_min // 15}"
                seen = set(self.s.get("warn_seen") or [])
                for w in warns or []:
                    if w["id"] not in seen:
                        out.append(("warning", w))
                self.s["warn_active"] = [{"title": w["title"], "spoken": w["spoken"]} for w in warns or []]
                self.s["warn_seen"] = [w["id"] for w in warns or []]
                continue
            if k == "sun":
                continue
            done[k] = hour
            if k == "temp":
                every = max(1, int(tuning.get("lair_temp_every_h")))
                if cur.get("temperature_2m") is not None and time.localtime(now).tm_hour % every == 0:
                    out.append(("temp", cur["temperature_2m"]))
            elif k == "pressure":
                out += self._pressure_events()
            elif k == "pollen":
                out += self._pollen_event(air, now) + self._air_event(air)
            elif k == "uv":
                out += self._uv_event(now)
        if "sun" in kinds:
            said = self.s.setdefault("sun_said", [])
            for kind, t in self.sun_due(now):
                said.append(f"{kind}@{int(t)}")
                out.append((kind,))
            self.s["sun_said"] = said[-8:]
        self.save()
        return out

    def _pressure_events(self):
        out, last = [], self.last or {}
        changes = [d for d in (last.get("past"), last.get("ahead")) if d is not None]
        armed = self.s.setdefault("armed", {"fall": True, "rise": True})
        storm, rise = tuning.get("storm_hpa"), tuning.get("rise_hpa")
        if changes:
            fall, up = min(changes), max(changes)
            if fall <= -storm and armed.get("fall", True):
                armed["fall"] = False
                out.append(("storm", fall))
            elif fall > -storm / 3:
                armed["fall"] = True
            if up >= rise and armed.get("rise", True):
                armed["rise"] = False
                out.append(("rise", up))
            elif up < rise / 3:
                armed["rise"] = True
        return out

    def _compare(self, key, value, level):
        """Against last hour's reading: (higher, increased). 'Higher' means it was already high
        and has gone up since; 'increased' means it's gone up at all (or there's nothing to
        compare with yet), which is what "increased readings only" listens for."""
        prev = self.s.get(key) or {}
        before, before_level = prev.get("value"), prev.get("level", "low")
        self.s[key] = {"value": value, "level": level}
        higher = (before is not None and value > before
                  and LEVELS.index(before_level) >= LEVELS.index("high"))
        return higher, before is None or value > before

    def _pollen_event(self, air, now):
        a = (air or {}).get("current") or {}
        levels, grains = {}, {}
        for group, keys in POLLEN_GROUPS.items():
            vals = [a[k] for k in keys if a.get(k) is not None]
            if vals:
                grains[group] = max(vals)
                levels[group] = pollen_level(group, grains[group])
        if not levels:
            return []
        worst = max(levels.values(), key=LEVELS.index)
        top = max(grains[g] for g, lv in levels.items() if lv == worst)
        higher, increased = self._compare("pollen_prev", round(top), worst)
        if worst not in ("high", "very high"):
            return []
        return [("pollen", worst, [g for g, lv in levels.items() if lv == worst], higher, increased)]

    def _air_event(self, air):
        """Poor air quality (checked with the pollen): 'poor' or worse on the European scale,
        or 'unhealthy for sensitive groups' or worse on the US one (for a Lair in the US)."""
        a = (air or {}).get("current") or {}
        us = self.s.get("code") == "US" and a.get("us_aqi") is not None
        v = a.get("us_aqi") if us else a.get("european_aqi")
        if v is None:
            return []
        bad = v > 100 if us else v > 60
        word = us_aqi_word(v) if us else eu_aqi_word(v)
        higher, increased = self._compare("air_prev", round(v), "high" if bad else "low")
        if not bad:
            return []
        return [("air", word, round(v), "US" if us else "European", higher, increased)]

    def _uv_event(self, now):
        hourly = (self.cond or {}).get("hourly") or {}
        times, uv = hourly.get("time") or [], hourly.get("uv_index") or []
        here = ((self.cond or {}).get("current") or {}).get("time", "")[:13]
        idx = next((i for i, t in enumerate(times) if t[:13] == here), None)
        if idx is None or idx >= len(uv) or uv[idx] is None:
            return []
        level = uv_word(uv[idx])
        higher, increased = self._compare("uv_prev", round(uv[idx]), level)
        if level in ("low", "moderate"):
            return []
        return [("uv", uv[idx], level, higher, increased)]

    def summary(self):
        """For the den: 'Toronto, Ontario, Canada' and the latest reading."""
        if not self.s:
            return "", ""
        where = self.s.get("label", "") + (f", {self.s['country']}" if self.s.get("country") else "")
        r = self.last
        if not r or r.get("temp") is None:
            return where, self.status
        trend = ""
        if r.get("past") is not None:
            trend = ", rising" if r["past"] >= 1 else ", falling" if r["past"] <= -1 else ", steady"
        when = time.strftime("%H:%M", time.localtime(r["ts"]))
        pressure = f", {round(r['pressure'])} hPa{trend}" if r.get("pressure") is not None else ""
        return where, f"{c_and_f(r['temp'])}{pressure} (at {when})"
