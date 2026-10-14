"""Questions: understanding them, and the answers for time, date, weather and timers."""
import datetime
import os
import time

os.environ["TZ"] = "Europe/London"
time.tzset()

from bt_dragon import ask  # noqa: E402
from bt_dragon.places import PLACES, find_place  # noqa: E402

P = ask.parse
assert P("what time is it") == {"intent": "time", "place": None}
assert P("what timers it") == {"intent": "time", "place": None}           # misheard, run together
assert P("what timer is it in tokyo") == {"intent": "time", "place": "tokyo"}
assert P("what timers are running")["intent"] == "timer_left"
assert P("what's the time in texas") == {"intent": "time", "place": "texas"}
assert P("what time is it in new york")["place"] == "new york"
assert P("what time is it in new york state")["place"] == "new york state"
assert P("what's the date")["intent"] == "date" and P("what day is it")["intent"] == "day"
assert P("what is the date tomorrow")["tomorrow"]
assert P("what's the weather like tomorrow") == {"intent": "weather", "place": None, "when": "tomorrow", "home": False}
assert P("will it rain later")["when"] == "later"
assert P("what's the weather in tokyo on saturday") == {"intent": "weather", "place": "tokyo", "when": "saturday", "home": False}
assert P("what is the temperature in new mexico")["place"] == "new mexico"
assert P("set a timer for twelve minutes") == {"intent": "timer_set", "name": None, "seconds": 720}
assert P("set a pasta timer for twenty five minutes") == {"intent": "timer_set", "name": "pasta", "seconds": 1500}
assert P("timer for an hour and a half")["seconds"] == 5400
assert P("set a timer for one hour and twenty minutes")["seconds"] == 4800
assert P("set a timer for half an hour")["seconds"] == 1800
assert P("set a timer for two and a half minutes")["seconds"] == 150
assert P("set an egg timer for ninety seconds")["seconds"] == 90
assert P("how long is left on the pasta timer") == {"intent": "timer_left", "name": "pasta"}
assert P("cancel the timer")["intent"] == "timer_cancel" and P("cancel all timers")["all"]
assert P("stop")["intent"] == "stop" and P("okay stop")["intent"] == "stop"
assert P("blah blah")["intent"] is None and P("")["intent"] is None
assert ask.words_to_numbers("twenty five and forty two") == "25 and 42"
assert ask.say_duration(4500) == "1 hour and 15 minutes" and ask.say_duration(65) == "1 minute and 5 seconds"

# every place has a real time zone and sensible coordinates; the recognizer knows its words
from zoneinfo import ZoneInfo  # noqa: E402
for name, (tz, lat, lon, say) in PLACES.items():
    ZoneInfo(tz)
    assert -90 <= lat <= 90 and -180 <= lon <= 180, name
    assert all(w in ask.VOCABULARY for w in name.split()), name
assert find_place("what time is it in baton rouge") == "baton rouge"
assert find_place("weather in north carolina tomorrow") == "north carolina"
assert all(w in ask.VOCABULARY for p in ask.PHRASES for w in p.split())       # phrases use known words
assert set(ask.VOCABULARY) <= set(ask.GRAMMAR) and "what time is it in" in ask.GRAMMAR
assert "texas" in ask.VOCABULARY and "twelve" in ask.VOCABULARY and "pasta" in ask.VOCABULARY

# time: 17:47 BST on Monday 12 October 2026
now = datetime.datetime(2026, 10, 12, 16, 47, tzinfo=datetime.timezone.utc).timestamp()
assert ask.answer_time(None, now) == "It's 5:47 in the evening."
assert ask.answer_time("texas", now) == "In Texas it's 11:47 in the morning. That's 6 hours behind you."
assert ask.answer_time("tokyo", now) == "In Tokyo it's 1:47 at night, Tuesday. That's 8 hours ahead of you."
# the week the UK has changed its clocks and the US hasn't yet: 5 hours, not 6
oct28 = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
assert ask.answer_time("texas", oct28).endswith("5 hours behind you."), ask.answer_time("texas", oct28)
assert ask.answer_time("london", now).endswith("the same as here.")
assert ask.answer_date(now=now) == "Today is Monday the 12th of October, 2026."
assert ask.answer_date(day_only=True, now=now) == "It is Monday."
assert ask.answer_date(tomorrow=True, now=now) == "Tomorrow is Tuesday the 13th of October, 2026."

# weather, from a made-up Open-Meteo reply
hours = [f"2026-10-12T{h:02d}:00" for h in range(24)]
data = {"utc_offset_seconds": 3600,
        "current": {"temperature_2m": 14.2, "apparent_temperature": 10.9, "weather_code": 61},
        "hourly": {"time": hours, "temperature_2m": [10 + h / 4 for h in range(24)],
                   "precipitation_probability": [60 if h == 19 else 10 for h in range(24)],
                   "weather_code": [61] * 24},
        "daily": {"time": [f"2026-10-{12 + i}" for i in range(7)], "weather_code": [61, 3, 0, 2, 80, 95, 1],
                  "temperature_2m_max": [16, 15.4, 13, 12, 11, 10, 9], "temperature_2m_min": [9, 8, 7, 6, 5, 4, 3],
                  "precipitation_probability_max": [70, 10, 0, 5, 80, 90, 0]}}
w = ask.answer_weather(data, "now", None, now)
assert w.startswith("Right now it's 14 degrees, that's 57 Fahrenheit, with light rain. It feels like 11."), w
assert "Later today: between 14 and 16 degrees, with a 60 percent chance of rain." in w, w
d2 = dict(data, current={"temperature_2m": 16, "apparent_temperature": 15, "weather_code": 3})
assert ask.answer_weather(d2, "now", None, now).startswith("Right now it's 16 degrees, that's 61 Fahrenheit, and overcast.")
w = ask.answer_weather(data, "tomorrow", "Tokyo", now)
assert w == "Tomorrow in Tokyo: overcast, with a high of 15 degrees, that's 59 Fahrenheit, and a low of 8.", w
w = ask.answer_weather(data, "friday", None, now)
assert w.startswith("Friday: light showers") and "80 percent chance of rain" in w, w
assert ask.answer_weather(data, "monday", None, now).startswith("Today: light rain")


# timers
class Store(dict):
    def put(self, k, v):
        self[k] = v


st = Store()
tm = ask.Timers(st)
t0 = 1000.0
assert ask.answer_timer(P("set a pasta timer for twelve minutes"), tm, t0) == "OK. Pasta timer set for 12 minutes, starting now."
assert ask.answer_timer(P("set a timer for ninety seconds"), tm, t0) == "OK. Timer set for 1 minute and 30 seconds, starting now."
assert st["timers"] and len(tm.items) == 2
left = ask.answer_timer(P("how long left"), tm, t0 + 60)
assert left == "Your timer has 30 seconds left. Your pasta timer has 11 minutes left.", left
assert ask.answer_timer(P("cancel the timer"), tm, t0).startswith("You have 2 timers")
assert ask.answer_timer(P("cancel the pasta timer"), tm, t0) == "Your pasta timer is cancelled."
assert tm.due(t0 + 89) == [] and [t["name"] for t in tm.due(t0 + 91)] == [""]
assert ask.answer_timer(P("how long left on the timer"), tm, t0) == "You don't have any timers running."
tm2 = ask.Timers(st)                      # comes back from the database after a restart
assert tm2.items == tm.items
print("ask ok")
