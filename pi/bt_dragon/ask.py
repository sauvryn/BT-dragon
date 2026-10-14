"""
Harald answers simple questions: the time (here or elsewhere), the date, the weather and
kitchen timers.

The words come from the speech recognizer (Vosk), already as lower-case text with numbers
spelled out ("set a pasta timer for twelve minutes"). Understanding them is plain pattern
matching: the recognizer is limited to the words listed in VOCABULARY, so the sentences it
can produce are predictable. The same functions answer questions typed in the den.
"""
import datetime
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from .places import PLACES, TIME_NAME, find_place, place_words
from . import shopping as _shopping

log = logging.getLogger("ask")

# ------------------------------------------------------------------ numbers in words
_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                      "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
TIMER_NAMES = ["pasta", "rice", "egg", "eggs", "tea", "pizza", "oven", "bread", "potato", "potatoes",
               "cake", "laundry", "washing", "chicken", "kettle", "dinner", "lunch", "breakfast",
               "biscuits", "cookies", "soup", "veg", "vegetables", "roast", "chips", "fish", "beans"]


def words_to_numbers(text):
    """'twenty five minutes' -> '25 minutes'. Digits pass through."""
    out, num = [], None
    for w in text.split():
        v = _UNITS.get(w, _TENS.get(w))
        if v is not None:
            if num is None:
                num = v
            elif w in _UNITS and num >= 20 and num % 10 == 0 and v < 10:
                num += v                       # "twenty" + "five"
            else:
                out.append(str(num))
                num = v
            continue
        if w == "hundred" and num is not None:
            num *= 100
            continue
        if num is not None:
            out.append(str(num))
            num = None
        out.append(w)
    if num is not None:
        out.append(str(num))
    return " ".join(out)


def parse_duration(text):
    """Seconds in 'for 12 minutes', 'an hour and a half', '1 hour 20 minutes', 'half an hour'."""
    t = words_to_numbers(text)
    t = re.sub(r"\b(a|an|one)\s+and\s+a\s+half\s+(hour|minute)s?\b", lambda m: f"1.5 {m.group(2)}s", t)
    t = re.sub(r"\bhalf\s+an?\s+(hour|minute)\b", lambda m: f"0.5 {m.group(1)}s", t)
    t = re.sub(r"\b(an?|one)\s+(hour|minute|second)\b", lambda m: f"1 {m.group(2)}s", t)
    t = re.sub(r"\b(\d+)\s+and\s+a\s+half\s+(hour|minute|second)s?\b", lambda m: f"{m.group(1)}.5 {m.group(2)}s", t)
    t = re.sub(r"\b(\d+)\s+(hour|minute|second)s?\s+and\s+a\s+half\b", lambda m: f"{m.group(1)}.5 {m.group(2)}s", t)
    total = 0.0
    for n, unit in re.findall(r"(\d+(?:\.\d+)?)\s+(hour|minute|min|second|sec)s?\b", t):
        total += float(n) * {"hour": 3600, "minute": 60, "min": 60, "second": 1, "sec": 1}[unit]
    return int(round(total))


def say_duration(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if m:
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
    if s and not h:
        parts.append(f"{s} second{'s' if s != 1 else ''}")
    if not parts:
        return "less than a second"
    return " and ".join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ------------------------------------------------------------------ the shopping list
_LIST = r"(?:the\s+|my\s+|our\s+)?(?:shopping\s+)?list\b"


def _items(phrase):
    """'eggs and milk' -> ['eggs', 'milk'], but 'salt and vinegar crisps' stays whole if known."""
    phrase = re.sub(r"\bunk\b", " ", phrase)       # a word the list didn't know
    phrase = re.sub(r"\s+", " ", phrase).strip()
    if " and " in phrase and not _shopping.is_known(phrase):
        parts = [p.strip() for p in re.split(r"\s+and\s+|,", phrase)]
    else:
        parts = [phrase]
    return [p for p in parts if _shopping.tidy(p)]


def parse_shopping(t):
    """Shopping-list requests, from normalized text (or None)."""
    if not re.search(r"\blist\b|\bwhat do (we|i) need\b", t):
        return None
    if re.search(r"\b(what is on|whats on|read|read out|tell me) " + _LIST, t) or \
            re.search(r"\bwhat do (we|i) need\b", t):
        return {"intent": "shop_read"}
    m = re.search(r"\b(?:add|put)\s+(.*?)\s*\b(?:to|on|onto|in)\s+" + _LIST, t)
    if m:
        return {"intent": "shop_add", "items": _items(m.group(1))}
    m = re.search(r"\b(?:remove|delete|take|cross|scratch)\s+(.*?)\s*\b(?:from|off)\s+(?:of\s+)?" + _LIST, t)
    if m:
        return {"intent": "shop_remove", "items": _items(m.group(1))}
    return None


# ------------------------------------------------------------------ the calendar
def parse_calendar(t):
    """'What events do I have today?', 'What are my events for tomorrow?', 'What's on my
    calendar on Friday?', 'Do I have anything on tomorrow?' (from normalized text)."""
    if not (re.search(r"\b(events?|appointments?|calendar|plans|schedule)\b", t)
            or re.search(r"\bwhat is on (today|tomorrow|on )", t + " ")
            or re.search(r"\bdo i have anything\b", t)):
        return None
    if re.search(r"\b(add|put|set|cancel|delete|remove|change|move)\b", t):
        return {"intent": "cal_edit"}   # by voice: not yet (the den's calendar page does it)
    day = "today"
    if " tomorrow " in t:
        day = "tomorrow"
    else:
        day = next((w for w in WEEKDAYS if f" {w} " in t), day)
    return {"intent": "cal_day", "day": day}


# ------------------------------------------------------------------ going to sleep, napping
def parse_rest(t):
    """'Go to sleep' (switch off, safe to unplug) and 'take a nap' (as good as off, but
    wakeable from the den)."""
    if re.search(r"\b(take|have|go for|time for) a (nap|lie down|little nap)\b|\bnap time\b|\bgo (and )?nap\b", t):
        return {"intent": "nap"}
    if re.search(r"\bgo (to )?sleep\b|\bgo to bed\b|\btime (for bed|to sleep)\b", t):
        return {"intent": "sleep"}
    return None


YES_WORDS = {"yes", "yeah", "yep"}
NO_WORDS = {"no", "nope", "not", "don't", "dont", "wait", "cancel", "stop"}
# what he listens for after "Shall I go to sleep now?": a tiny list, so only a clear yes counts
YES_GRAMMAR = ["yes", "yeah", "yep", "yes please", "please", "no", "nope", "no thanks", "not yet",
               "don't", "wait", "cancel", "stop"]     # anything else comes back as [unk]


def is_yes(text):
    """A clear yes ('yes', 'yeah', 'yep', 'yes please'), and nothing that takes it back."""
    words = set(re.sub(r"[^a-z' ]", " ", (text or "").lower()).split())
    return bool(words & YES_WORDS) and not words & NO_WORDS


# ------------------------------------------------------------------ which way is it
_THAT = {"", "it", "that", "this", "there", "that one", "that landmark", "the landmark", "this landmark",
         "that place", "the place", "that building", "the last landmark", "that last landmark"}


def parse_trip(t):
    """'How far have we gone on this walk?', 'How far have we traveled?', 'How far have I
    walked today?'"""
    if re.search(r"\bhow (far|much|long)\b.*\b(gone|go|went|traveled|travelled|walked|run|ran|come|"
                 r"cycled|biked|ridden|been walking|been out)\b|\bhow far (are|is) (we|it) (so far|now)\b", t):
        return {"intent": "trip", "today": bool(re.search(r"\btoday\b", t))}
    return None


GREEN_WORDS = r"\b(parks?|green spaces?|woods?|woodlands?|forests?|nature reserves?|gardens?|commons?)\b"


def parse_where(t):
    """'What direction is East Harbour Railway in?', 'Where is the castle?', 'How far is
    it?', 'In what direction?' The name is None for 'that landmark' (the one he just
    pointed out)."""
    t = re.sub(r"\bunk\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    green = bool(re.search(GREEN_WORDS, t))
    if re.search(r"\b(closest|nearest)\b", t) and (green or re.search(
            r"\b(landmarks?|famous|places?|sights?)\b|\bwhere\b", t)):
        q = {"intent": "where", "name": None, "nearest": True,
             "unseen": bool(re.search(r"\b(unseen|unknown|undiscovered|unexplored|unvisited|new)\b|"
                                      r"\b(not|never|haven't|havent|have not) (been )?(seen|found|discovered|visited|explored|been to)\b", t))}
        if green:
            q["green"] = True
        return q
    for pat in (r"\b(?:what|which) (?:direction|way) is (.*?)(?: in| from here| from us)?$",
                r"\bwhere is (.*?)(?: from here)?$",
                r"\bhow far (?:away )?is (.*?)(?: from here| away)?$",
                r"\b(?:what|which) way (?:to|for) (.*)$"):
        m = re.search(pat, t)
        if m:
            name = re.sub(r"^(?:the|a) (?=\w+ \w)", "", m.group(1).strip())
            return {"intent": "where", "name": None if m.group(1).strip() in _THAT else name}
    if re.search(r"^(?:in )?(?:what|which) (?:direction|way)$|^how far(?: away)?$", t):
        return {"intent": "where", "name": None}
    return None


# ------------------------------------------------------------------ understanding
HOME = r"\b(home|lair|the lair|my lair|your lair|our lair)\b"
CONDITIONS = [
    ("humidity", r"\bhumid(ity)?\b"),
    ("pressure", r"\b(air pressure|pressure|barometer|barometric)\b"),
    ("pollen", r"\b(pollen|hay ?fever)\b"),
    ("sunrise", r"\b(sunrise|sun rise|sun come up|sun up|dawn)\b"),
    ("sunset", r"\b(sunset|sun set|sun go down|sundown|dusk|get dark)\b"),
    ("uv", r"\b(uv|u v|ultraviolet|uv index|sunburn)\b"),
    ("air", r"\b(air quality|pollution|smog)\b"),
    ("warnings", r"\b(weather )?warnings?\b|\bweather alerts?\b"),
]


def parse_conditions(t, place):
    """Humidity, pressure, pollen, sunrise, sunset, UV and air quality: here, at home (the
    Lair), or in a named place."""
    for what, pat in CONDITIONS:
        if re.search(pat, t):
            return {"intent": "conditions", "what": what, "place": place, "home": bool(re.search(HOME, t)),
                    "tomorrow": " tomorrow " in t}
    return None


def parse(text):
    """What's being asked: {'intent': ..., plus details}. intent is one of time, date, day,
    weather, timer_set, timer_left, timer_cancel, stop, or None."""
    t = " " + re.sub(r"[^a-z0-9' ]", " ", text.lower()) + " "
    t = re.sub(r"\s+", " ", t.replace("what's", "what is").replace("it's", "it is"))
    shop = parse_shopping(t) or parse_calendar(t) or parse_rest(t) or parse_trip(t) or parse_where(t)
    if shop:
        return shop
    if re.search(r"\b(set|setup|set up|make|create|new|add|learn)\b.*\bvoice\b|\blearn my voice\b", t):
        return {"intent": "voice_enrol"}
    if re.search(r"\bwho am i\b|\bwho is (speaking|talking)\b|\bdo you know (who i am|my voice)\b", t):
        return {"intent": "voice_who"}
    place = find_place(t.strip())
    cond = parse_conditions(t, place)
    if cond:
        return cond
    if re.search(r"\b(stop|enough|quiet|shush|okay|ok)\b", t) and not re.search(r"\btimer", t):
        if len(t.split()) <= 3:
            return {"intent": "stop"}
    if re.search(r"\b(how long|how much time)\b.*\b(left|remaining)\b|\btime (left|remaining)\b", t) \
            and not re.search(r"\btimers?\b", t):
        return {"intent": "timer_left", "name": next((w for w in TIMER_NAMES if f" {w} " in t), None)}
    # "what time is it" run together can come out as "what timers it": with no timer words
    # around it (set, cancel, left, for ten minutes...), "timer" is really "time is"
    if re.search(r"\btimers?\b", t) and not re.search(
            r"\b(set|start|cancel|stop|delete|remove|clear|end|left|remaining|long|check|for|my|all|"
            r"running|minutes?|hours?|seconds?|how many)\b", t) and re.search(r"\bwhat\b", t):
        return {"intent": "time", "place": place}
    if re.search(r"\btimers?\b", t):
        name = next((w for w in TIMER_NAMES if f" {w} " in t), None)
        if re.search(r"\b(cancel|stop|delete|remove|clear|end)\b", t):
            return {"intent": "timer_cancel", "name": name, "all": bool(re.search(r"\ball\b", t))}
        if re.search(r"\b(how long|how much time|left|remaining|check)\b", t):
            return {"intent": "timer_left", "name": name}
        secs = parse_duration(t)
        if secs:
            return {"intent": "timer_set", "name": name, "seconds": secs}
        return {"intent": "timer_left", "name": name}
    if re.search(r"\b(weather|rain|raining|umbrella|temperature|forecast|hot|cold|warm|sunny|snow|windy)\b", t):
        when = "now"
        for w in WEEKDAYS:
            if f" {w} " in t:
                when = w
        if " tomorrow " in t:
            when = "tomorrow"
        elif re.search(r"\b(later|this afternoon|this evening|tonight|rest of the day)\b", t):
            when = "later"
        elif re.search(r"\btoday\b", t) and when == "now":
            when = "today"
        return {"intent": "weather", "place": place, "when": when, "home": bool(re.search(HOME, t))}
    if re.search(r"\btime\b", t):
        return {"intent": "time", "place": place}
    if re.search(r"\b(date|what day|which day|day is it|day of the week)\b", t):
        return {"intent": "day" if re.search(r"\bday\b", t) and "date" not in t else "date",
                "tomorrow": " tomorrow " in t}
    return {"intent": None}


VOCABULARY = sorted(set(
    "what what's is it the time in at whats please harald hey tell me what's date day today tomorrow "
    "of week which weather like going to be rain raining will umbrella need do i temperature forecast hot "
    "cold warm sunny snow windy later this afternoon evening tonight morning rest now right "
    "set start a an timer timers for minute minutes hour hours second seconds and half cancel stop delete "
    "remove clear end all how long much left remaining check my the on stop enough okay thank you thanks "
    "hey dragon add put remove take cross off from list shopping need we our read out "
    "events event appointments appointment calendar plans schedule anything have are my got "
    "voice profile learn who am speaking talking know "
    "go sleep bed nap lie down little yes yeah yep no nope wait "
    "where direction which way far away from here that this landmark place closest nearest famous "
    "unseen unknown undiscovered unexplored unvisited new not never seen found discovered visited haven't "
    "park parks green space spaces wood woods woodland forest nature reserve garden gardens common explored been "
    "gone went traveled travelled walked come ran cycled biked ridden walk run ride trip so "
    "home lair outside humidity humid pressure air barometer pollen count hay fever sunrise sunset sun "
    "rise up go dark when does index quality pollution ultraviolet uv warm warning warnings any there".split()
    + list(_UNITS) + list(_TENS) + ["hundred"] + WEEKDAYS + TIMER_NAMES) | place_words()
    | {w for name in _shopping.known_items() for w in name.split()})


# Whole phrases as well as single words. Given only separate words, Vosk treats them as a bag
# where any word may follow any other, and short words like "is it in" are easily swapped for
# a longer word that fits the same sounds ("what timers eighteen"). Each choice from the list
# costs the same, so a whole phrase is cheaper than the same words picked one by one: the
# usual ways of asking become the easiest paths through the list.
PHRASES = [
    "what time is it", "what time is it in", "what's the time", "what's the time in",
    "what is the time", "what is the time in", "tell me the time",
    "what's the date", "what is the date", "what's the date today", "what's the date tomorrow",
    "what day is it", "what day is it today", "what day is it tomorrow", "what day of the week is it",
    "what's the weather", "what's the weather like", "what's the weather like in", "what's the weather in",
    "what is the weather", "what is the weather like", "what's the weather going to be like",
    "will it rain", "will it rain today", "will it rain tomorrow", "is it going to rain",
    "do i need an umbrella", "what's the temperature", "what is the temperature",
    "set a timer for", "set an", "timer for", "start a timer for",
    "how long is left", "how long is left on the", "how much time is left", "how long left on the",
    "cancel the timer", "cancel all timers", "cancel the", "stop the timer",
    "thank you", "hey dragon",
    "to the shopping list", "to my shopping list", "on the shopping list", "from the shopping list",
    "off the shopping list", "what's on the shopping list", "what is on the shopping list",
    "read the shopping list", "read out the shopping list", "what do we need",
    "what events do i have", "what are my events for", "what's on my calendar", "what is on my calendar",
    "do i have anything on", "what's on today", "what's on tomorrow", "what have i got on",
    "set a voice profile", "set up a voice profile", "learn my voice", "who am i", "who is speaking",
    "go to sleep", "go to bed", "take a nap", "have a nap", "time for a nap", "go for a nap",
    "where is", "where is that landmark", "what direction is", "which direction is", "which way is",
    "how far is", "how far away is", "how far is it", "where is the closest landmark",
    "where is the nearest landmark", "what is the closest landmark", "what is the nearest landmark",
    "what's the closest landmark", "what's the nearest landmark",
    "what is the closest unseen landmark", "what is the nearest unseen landmark",
    "what is the closest undiscovered landmark", "what is the nearest undiscovered landmark",
    "what is the closest unknown landmark", "what is the nearest unknown landmark",
    "where is the closest unseen landmark", "where is the nearest undiscovered landmark",
    "that i haven't seen", "i haven't seen",
    "where is the closest park", "where is the nearest park", "what is the closest park", "what is the nearest park",
    "what's the closest park", "what's the nearest park", "the closest green space", "the nearest green space",
    "the nearest wood", "the closest wood", "the nearest nature reserve", "the closest unexplored park",
    "the nearest unexplored park", "the closest unexplored green space", "that i haven't explored",
    "where is the closest", "where is the nearest",
    "how far have we gone", "how far have we traveled", "how far have we walked", "how far have i walked",
    "what's the temperature at home", "what is the temperature at home", "what's the weather like at home",
    "what's the weather at home", "at home", "at the lair", "how warm is it at home", "how cold is it at home",
    "what's the humidity", "what is the humidity", "what's the air pressure", "what is the air pressure",
    "what's the pollen count", "what is the pollen count", "when is sunrise", "when is sunset",
    "what time is sunrise", "what time is sunset", "when does the sun rise", "when does the sun set",
    "when does the sun go down", "what's the uv index", "what is the uv index", "what's the air quality",
    "what is the air quality", "how is the air quality", "are there any weather warnings",
    "any weather warnings", "are there any warnings at home",
    "on this walk", "so far", "how far have we gone today", "how far have we come", "in what direction", "which direction", "what direction",
]
# Adding to or taking off the shopping list: the item could be anything, and with only his
# word list Vosk picks the nearest word it knows ("cranberries" -> "raspberries"). So for
# these requests the same recording is listened to again with Vosk's whole vocabulary, and
# the item is taken from that.
# The same for "where is ...": a landmark's name may hold words he's never been taught.
FREE_IF = r"\b(add|put|remove|delete|take|cross|scratch)\b.*\blist\b|\bwhere is\b|\b(what|which) (direction|way)\b|\bhow far\b"
GRAMMAR = VOCABULARY + PHRASES

# ------------------------------------------------------------------ time and date
def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _clock(dt):
    """'5:47 in the evening', 'noon', 'midnight'."""
    h, m = dt.hour, dt.minute
    if m == 0 and h == 12:
        return "noon"
    if m == 0 and h == 0:
        return "midnight"
    part = ("at night" if h < 5 else "in the morning" if h < 12 else "in the afternoon" if h < 17
            else "in the evening" if h < 22 else "at night")
    h12 = h % 12 or 12
    return (f"{h12} o'clock" if m == 0 else f"{h12}:{m:02d}") + " " + part


def answer_time(place=None, now=None):
    now = now or time.time()
    local = datetime.datetime.fromtimestamp(now).astimezone()
    if not place:
        return f"It's {_clock(local)}."
    tz = ZoneInfo(PLACES[place][0])
    there = datetime.datetime.fromtimestamp(now, tz)
    diff = (there.utcoffset() - local.utcoffset()).total_seconds() / 3600
    name = TIME_NAME[place]
    day = ""
    if there.date() != local.date():
        day = f", {there.strftime('%A')}"
    if abs(diff) < 0.01:
        rel = "the same as here"
    else:
        hrs = abs(diff)
        hs = f"{hrs:g} hour{'s' if hrs != 1 else ''}"
        rel = f"{hs} {'ahead of' if diff > 0 else 'behind'} you"
    return f"In {name} it's {_clock(there)}{day}. That's {rel}."


def answer_date(tomorrow=False, day_only=False, now=None):
    d = datetime.datetime.fromtimestamp(now or time.time()).astimezone()
    if tomorrow:
        d += datetime.timedelta(days=1)
    which = "Tomorrow is" if tomorrow else "Today is"
    if day_only:
        return f"{'Tomorrow is' if tomorrow else 'It is'} {d.strftime('%A')}."
    return f"{which} {d.strftime('%A')} the {_ordinal(d.day)} of {d.strftime('%B')}, {d.year}."


# ------------------------------------------------------------------ weather (Open-Meteo)
WMO = {0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
       61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
       71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
       82: "heavy showers", 85: "snow showers", 86: "heavy snow showers", 95: "thunderstorms",
       96: "thunderstorms with hail", 99: "thunderstorms with hail"}
SKY_WORDS = {"mostly clear", "partly cloudy", "overcast"}    # "it's 16 degrees, and overcast", not "with overcast"


def _deg(c):
    """'14 degrees, that's 57 Fahrenheit'."""
    c = round(c)
    return f"{c} degree{'s' if abs(c) != 1 else ''}, that's {round(c * 9 / 5 + 32)} Fahrenheit"


def fetch_weather(lat, lon, timeout=10):
    """Forecast for a point. Coordinates are rounded to 0.1 degree (about 10 km) first."""
    q = urllib.parse.urlencode({
        "latitude": round(lat, 1), "longitude": round(lon, 1),
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 7, "wind_speed_unit": "mph"})
    with urllib.request.urlopen("https://api.open-meteo.com/v1/forecast?" + q, timeout=timeout) as r:
        return json.loads(r.read().decode())


def geocode(name, timeout=10):
    """A town name -> (label, lat, lon) via Open-Meteo's geocoding, or None."""
    q = urllib.parse.urlencode({"name": name, "count": 1, "language": "en", "format": "json"})
    with urllib.request.urlopen("https://geocoding-api.open-meteo.com/v1/search?" + q, timeout=timeout) as r:
        res = (json.loads(r.read().decode()).get("results") or [])
    if not res:
        return None
    g = res[0]
    return g["name"], round(g["latitude"], 2), round(g["longitude"], 2)


def answer_weather(data, when="now", label=None, now=None):
    """Words for a forecast from fetch_weather(). `label` is the place ("Tokyo", or "at
    the Lair"), or None for here."""
    where = (label if label.startswith("at ") else f"in {label}") if label else ""
    pre = (lambda s: f"{s} {where}".strip())   # "Tomorrow" + " in Tokyo"
    cur, hourly, daily = data.get("current", {}), data.get("hourly", {}), data.get("daily", {})
    off = datetime.timedelta(seconds=data.get("utc_offset_seconds", 0))
    there_now = datetime.datetime.fromtimestamp(now or time.time(), datetime.timezone.utc) + off
    days = daily.get("time", [])

    def day_text(i, lead):
        code = WMO.get(daily["weather_code"][i], "mixed weather")
        rain = daily.get("precipitation_probability_max", [None] * 7)[i]
        hi, lo = daily["temperature_2m_max"][i], daily["temperature_2m_min"][i]
        s = f"{lead}: {code}, with a high of {_deg(hi)}, and a low of {round(lo)}."
        if rain is not None and rain >= 20:
            s += f" There's a {rain} percent chance of rain."
        return s

    if when in ("now", "today", "later"):
        parts = []
        if when == "now" or when == "today":
            code = WMO.get(cur.get("weather_code"), "")
            parts.append(f"{pre('Right now')} it's {_deg(cur['temperature_2m'])}"
                         + ((f", and {code}" if code in SKY_WORDS else f", with {code}") if code else "") + ".")
            feels = cur.get("apparent_temperature")
            if feels is not None and abs(feels - cur["temperature_2m"]) >= 3:
                parts.append(f"It feels like {round(feels)}.")
        # the rest of today, from the hourly forecast
        hours = hourly.get("time", [])
        rest = [i for i, h in enumerate(hours)
                if h[:10] == there_now.strftime("%Y-%m-%d") and int(h[11:13]) > there_now.hour]
        if rest:
            temps = [hourly["temperature_2m"][i] for i in rest]
            rain = max((hourly["precipitation_probability"][i] or 0) for i in rest)
            lead = "Later today" if when != "later" else pre("Later today")
            s = f"{lead}: between {round(min(temps))} and {round(max(temps))} degrees"
            s += f", with a {rain} percent chance of rain." if rain >= 20 else ", and it should stay dry."
            parts.append(s)
        elif when == "later" and days:
            parts.append(day_text(0, pre("Today")))
        return " ".join(parts)
    if when == "tomorrow" and len(days) > 1:
        return day_text(1, pre("Tomorrow"))
    if when in WEEKDAYS:
        for i, d in enumerate(days):
            if datetime.date.fromisoformat(d).strftime("%A").lower() == when:
                return day_text(i, f"{'Today' if i == 0 else when.title()} {where}".strip())
    return "I can only see a week ahead."


# ------------------------------------------------------------------ timers
class Timers:
    """Kitchen timers, kept in the database so they survive a restart."""

    def __init__(self, store):
        self.store = store
        self.items = store.get("timers") or []      # [{name, end, length}]

    def save(self):
        self.store.put("timers", self.items)

    def add(self, seconds, name=None, now=None):
        now = now or time.time()
        name = name or self._free_name()
        self.items = [t for t in self.items if t["name"] != name]
        self.items.append({"name": name, "end": now + seconds, "length": seconds})
        self.save()
        return name

    def _free_name(self):
        used = {t["name"] for t in self.items}
        if "" not in used:
            return ""
        n = 2
        while f"timer {n}" in used:
            n += 1
        return f"timer {n}"

    def find(self, name=None):
        if name:
            return [t for t in self.items if t["name"] in (name, name.rstrip("s"))]
        return list(self.items)

    def cancel(self, name=None, everything=False):
        if everything or (not name and len(self.items) == 1):
            gone = list(self.items)
        elif name:
            gone = self.find(name)
        else:
            gone = []                      # several timers and no name: ask which
        self.items = [t for t in self.items if t not in gone]
        self.save()
        return gone

    def due(self, now=None):
        now = now or time.time()
        done = [t for t in self.items if t["end"] <= now]
        if done:
            self.items = [t for t in self.items if t not in done]
            self.save()
        return done

    def soonest(self):
        return min(self.items, key=lambda t: t["end"]) if self.items else None


def label(t):
    return f"your {t['name']} timer" if t["name"] and not t["name"].startswith("timer ") else (
        f"timer {t['name'][6:]}" if t["name"] else "your timer")


def answer_timer(q, timers, now=None):
    now = now or time.time()
    if q["intent"] == "timer_set":
        name = timers.add(q["seconds"], q.get("name"), now)
        what = f"{name.capitalize()} timer" if name and not name.startswith("timer ") else "Timer"
        return f"OK. {what} set for {say_duration(q['seconds'])}, starting now."
    if q["intent"] == "timer_cancel":
        if not timers.items:
            return "You don't have any timers running."
        gone = timers.cancel(q.get("name"), q.get("all"))
        if not gone:
            if len(timers.items) > 1 and not q.get("name"):
                return f"You have {len(timers.items)} timers. Which one should I cancel?"
            return "I couldn't find that timer."
        return "Timers cancelled." if len(gone) > 1 else f"{label(gone[0])[0].upper() + label(gone[0])[1:]} is cancelled."
    if q["intent"] == "timer_left":
        found = timers.find(q.get("name"))
        if not found:
            return "You don't have any timers running." if not timers.items else "I couldn't find that timer."
        parts = [f"{label(t)[0].upper() + label(t)[1:]} has {say_duration(t['end'] - now)} left."
                 for t in sorted(found, key=lambda t: t["end"])]
        return " ".join(parts)
    return ""
