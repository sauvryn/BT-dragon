"""The calendar: events, repeats, reminders (vague on screen, named by voice), questions."""
import datetime as dt
import json
import os
import tempfile
import time

os.environ["TZ"] = "Europe/London"
time.tzset()

from bt_dragon import agenda, ask, config  # noqa: E402
from bt_dragon.app import Dragon  # noqa: E402
from bt_dragon.store import Store  # noqa: E402

tmp = tempfile.mkdtemp()
cal = agenda.Calendar(Store(os.path.join(tmp, "c.db")))
ts = lambda y, mo, d, h=0, mi=0: dt.datetime(y, mo, d, h, mi).timestamp()  # noqa: E731

# checking what comes from the den
assert agenda.clean({"title": "", "date": "2026-10-20"})[1]
assert agenda.clean({"title": "x", "date": "nope"})[1] and agenda.clean({"title": "x", "date": "2026-10-20", "time": "25:00"})[1]
dent, err = cal.put({"title": "Dental appointment", "date": "2026-10-20", "time": "14:00",
                     "reminders": [{"minutes": 60}, {"days": 1, "at": "14:00"}]})
assert not err and dent["id"] == 1
mum, _ = cal.put({"title": "Mum's birthday", "date": "1960-03-02", "repeat": "yearly",
                  "reminders": [{"days": 1, "at": "09:00"}]})
yoga, _ = cal.put({"title": "Yoga", "date": "2026-10-06", "time": "18:30", "repeat": "weekly"})
rent, _ = cal.put({"title": "Rent", "date": "2026-01-31", "repeat": "monthly"})

# repeats
on = lambda e, y, m, d: agenda.occurs_on(e, dt.date(y, m, d))  # noqa: E731
assert on(mum, 2027, 3, 2) and not on(mum, 1959, 3, 2) and on(yoga, 2026, 10, 20) and not on(yoga, 2026, 10, 21)
assert on(rent, 2026, 2, 28) and on(rent, 2026, 4, 30) and on(rent, 2026, 5, 31)
leap, _ = cal.put({"title": "Leap", "date": "2024-02-29", "repeat": "yearly"})
assert on(leap, 2025, 2, 28) and on(leap, 2028, 2, 29)
cal.delete(leap["id"])
assert [e["title"] for e in cal.on_day(dt.date(2026, 10, 20))] == ["Yoga", "Dental appointment"][::-1] or \
       [e["title"] for e in cal.on_day(dt.date(2026, 10, 20))] == ["Dental appointment", "Yoga"]

# reminders: each once, at its time
assert cal.due(ts(2026, 10, 19, 13, 59)) == []
got = cal.due(ts(2026, 10, 19, 14, 0, ))
assert [(e["title"], d.isoformat()) for e, d, r in got] == [("Dental appointment", "2026-10-20")]
assert cal.due(ts(2026, 10, 19, 14, 1)) == []                                   # only once
got = cal.due(ts(2026, 10, 20, 13, 0))
assert len(got) == 1 and got[0][2] == {"minutes": 60}
# missed while switched off: still given if the event hasn't started, not if it has
cal.put({"title": "Late", "date": "2026-10-22", "time": "10:00", "reminders": [{"minutes": 120}]})
assert [e["title"] for e, _, _ in cal.due(ts(2026, 10, 22, 9, 30))] == ["Late"]
cal.put({"title": "Missed", "date": "2026-10-23", "time": "10:00", "reminders": [{"minutes": 60}]})
assert cal.due(ts(2026, 10, 23, 10, 5)) == []
# a yearly birthday's reminder, every year
assert [e["title"] for e, _, _ in cal.due(ts(2027, 3, 1, 9, 0))] == ["Mum's birthday"]
assert agenda.Calendar(cal.store).fired == cal.fired                             # remembered

# the words: vague on screen, named by voice
now = ts(2026, 10, 20, 13, 0)
d20 = dt.date(2026, 10, 20)
assert cal.screen_text(dent, d20, now) == "REMINDER: EVENT IN 1 HOUR!"
assert "Dental" not in cal.screen_text(dent, d20, now)
assert cal.spoken_reminder(dent, d20, now) == "Reminder: Dental appointment, in 1 hour, at 2 o'clock in the afternoon."
assert cal.spoken_reminder(dent, d20, ts(2026, 10, 19, 14)) == \
    "Reminder: Dental appointment, tomorrow at 2 o'clock in the afternoon."
assert cal.screen_text(mum, dt.date(2027, 3, 2), ts(2027, 3, 1, 9)) == "REMINDER: EVENT TOMORROW!"
assert cal.spoken_reminder(mum, dt.date(2027, 3, 2), ts(2027, 3, 1, 9)) == "Reminder: Mum's birthday, tomorrow."
assert cal.spoken_day(d20, "today") == ("Today you have 2 events: Dental appointment at 2 o'clock in the afternoon; "
                                        "and Yoga at 6:30 in the evening.")
assert cal.spoken_day(dt.date(2026, 10, 21), "tomorrow") == "Nothing on your calendar tomorrow."
assert agenda.clock_words("09:05") == "9:05 in the morning" and agenda.clock_words("12:00") == "noon"

# questions
P = ask.parse
assert P("what events do i have today") == {"intent": "cal_day", "day": "today"}
assert P("what are my events for tomorrow")["day"] == "tomorrow"
assert P("what's on my calendar on friday")["day"] == "friday"
assert P("do i have anything on tomorrow")["day"] == "tomorrow"
assert P("what's on the shopping list")["intent"] == "shop_read"
assert P("add an event to october twentieth")["intent"] == "cal_edit"
assert all(w in ask.VOCABULARY for p in ask.PHRASES for w in p.split())

import asyncio  # noqa: E402


async def main():
    # the whole dragon: den commands, a reminder going off, a spoken answer
    cfg = config.load(None)
    cfg["data_dir"] = os.path.join(tmp, "app")
    app = Dragon(cfg, simulate=True, out_dir=cfg["data_dir"])
    d = app.dot
    d.connected = d.ready = True
    soon = time.time() + 30 * 60
    day = dt.date.fromtimestamp(soon)
    ev = {"title": "Pick up parcel", "date": day.isoformat(), "time": time.strftime("%H:%M", time.localtime(soon)),
          "reminders": [{"minutes": 60}]}
    r = (await (app.command("CALSAVE " + json.dumps(ev))))
    assert r[0].startswith("OK"), r
    assert (await app.command("CALSAVE {\"title\": \"\"}"))[0].startswith("ERR")
    d.remind()
    assert app.pet.message.startswith("REMINDER: EVENT IN"), app.pet.message
    assert "PARCEL" not in app.pet.message
    assert d.queue and d.queue[-1].startswith("Reminder: Pick up parcel"), d.queue
    data = app.calendar_data()
    assert data["events"] and data["upcoming"][0]["ids"]
    answer = await (d.answer("what events do i have today" if day == dt.date.today()
                                                else "what are my events for tomorrow"))
    assert "Pick up parcel" in answer, answer
    eid = int(r[0].split()[1])
    assert (await app.command(f"CALDEL {eid}")) == ["OK"]


asyncio.run(main())
print("calendar ok")
