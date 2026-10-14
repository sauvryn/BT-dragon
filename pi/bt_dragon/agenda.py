"""
Harald's calendar: kept on the Pi, edited on its own den page (/calendar), asked about by
voice ("What events do I have today?"), with reminders: a vague one on his screen
("REMINDER: EVENT IN 1 HOUR!") and the real one, with the event's name, through the Dot.

An event has a title, a date, a time (or none: all day), how it repeats (never, every
week, month or year: birthdays) and any number of reminders, each either
  {"minutes": 60}               an amount of time before it starts, or
  {"days": 1, "at": "14:00"}    a number of days before (0 = the same day), at a clock time.
"""
import calendar as _cal
import datetime as dt
import re
import time

REPEATS = ("none", "weekly", "monthly", "yearly")
LATE_LIMIT_S = 12 * 3600      # a reminder missed while he was off is still given up to this late


def _date(s):
    return dt.date.fromisoformat(s)


def _hhmm(s):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return int(m.group(1)), int(m.group(2))


def clean(ev):
    """Check and tidy an event from the den. Returns (event, None) or (None, error)."""
    title = re.sub(r"\s+", " ", str(ev.get("title", ""))).strip()[:80]
    if not title:
        return None, "give the event a name"
    try:
        date = _date(str(ev.get("date", ""))).isoformat()
    except ValueError:
        return None, "choose a date"
    at = str(ev.get("time") or "").strip() or None
    if at and not _hhmm(at):
        return None, "use a time like 14:00"
    repeat = ev.get("repeat", "none")
    if repeat not in REPEATS:
        return None, "repeat: none, weekly, monthly or yearly"
    rems = []
    for r in (ev.get("reminders") or [])[:5]:
        if "minutes" in r:
            m = int(float(r["minutes"]))
            if 0 <= m <= 60 * 24 * 14:
                rems.append({"minutes": m})
        elif "days" in r:
            d = int(float(r["days"]))
            if 0 <= d <= 60 and _hhmm(str(r.get("at", ""))):
                rems.append({"days": d, "at": str(r["at"])})
    out = {"title": title, "date": date, "time": at, "repeat": repeat, "reminders": rems}
    if ev.get("id") is not None:
        out["id"] = int(ev["id"])
    return out, None


def occurs_on(ev, day):
    """Does this event happen on `day` (a date)?"""
    start = _date(ev["date"])
    if day < start:
        return False
    r = ev.get("repeat", "none")
    if r == "none":
        return day == start
    if r == "weekly":
        return (day - start).days % 7 == 0
    if r == "monthly":
        last = _cal.monthrange(day.year, day.month)[1]
        return day.day == min(start.day, last)            # the 31st: the last day of short months
    if r == "yearly":
        if start.month == 2 and start.day == 29 and not _cal.isleap(day.year):
            return (day.month, day.day) == (2, 28)        # leap-day birthdays: the 28th
        return (day.month, day.day) == (start.month, start.day)
    return False


def start_of(ev, day):
    """When this occurrence starts (local time, as a timestamp). All day: midnight."""
    h, m = _hhmm(ev["time"]) if ev.get("time") else (0, 0)
    return dt.datetime(day.year, day.month, day.day, h, m).timestamp()


def remind_at(ev, day, r):
    if "minutes" in r:
        return start_of(ev, day) - r["minutes"] * 60
    h, m = _hhmm(r["at"])
    d = day - dt.timedelta(days=r["days"])
    return dt.datetime(d.year, d.month, d.day, h, m).timestamp()


def clock_words(hhmm):
    """'14:30' -> '2:30 in the afternoon'."""
    h, m = _hhmm(hhmm)
    part = ("at night" if h < 5 else "in the morning" if h < 12 else "in the afternoon" if h < 17
            else "in the evening" if h < 22 else "at night")
    if (h, m) == (12, 0):
        return "noon"
    if (h, m) == (0, 0):
        return "midnight"
    h12 = h % 12 or 12
    return (f"{h12} o'clock" if m == 0 else f"{h12}:{m:02d}") + " " + part


def until_words(seconds):
    """How far off something is, roughly: 'in 1 hour', 'in 20 minutes', 'tomorrow'."""
    s = max(0, seconds)
    if s < 90:
        return "now"
    if s < 3600 * 1.5:
        n = round(s / 60)
        return f"in {n} minute{'s' if n != 1 else ''}" if n < 55 else "in 1 hour"
    if s < 3600 * 20:
        n = round(s / 3600)
        return f"in {n} hours"
    n = round(s / 86400)
    return "tomorrow" if n <= 1 else f"in {n} days"


class Calendar:
    def __init__(self, store):
        self.store = store
        self.events = store.get("calendar") or []
        self.fired = store.get("calendar_fired") or {}       # "id|date|n" -> when it fired
        self._next = max([e["id"] for e in self.events] + [0]) + 1
        self.changed = time.time()

    def save(self):
        self.store.put("calendar", self.events)
        self.changed = time.time()

    def get(self, ev_id):
        return next((e for e in self.events if e["id"] == ev_id), None)

    def put(self, ev):
        """Add or change an event (from the den). Returns (event, None) or (None, error)."""
        ev, err = clean(ev)
        if err:
            return None, err
        if "id" in ev and self.get(ev["id"]):
            old = self.get(ev["id"])
            old.update(ev)
            ev = old
            # changed reminders may need to go off again
            self.fired = {k: v for k, v in self.fired.items() if not k.startswith(f"{ev['id']}|")}
            self.store.put("calendar_fired", self.fired)
        else:
            ev["id"] = self._next
            self._next += 1
            self.events.append(ev)
        self.save()
        return ev, None

    def delete(self, ev_id):
        ev = self.get(ev_id)
        if ev:
            self.events.remove(ev)
            self.save()
        return ev

    def on_day(self, day):
        """The events on a date, all-day ones first, then by time."""
        evs = [e for e in self.events if occurs_on(e, day)]
        return sorted(evs, key=lambda e: (e.get("time") is not None, e.get("time") or "", e["title"].lower()))

    def upcoming(self, days=60, today=None):
        today = today or dt.date.today()
        out = []
        for i in range(days):
            d = today + dt.timedelta(days=i)
            evs = self.on_day(d)
            if evs:
                out.append((d, evs))
        return out

    def due(self, now=None):
        """Reminders that should go off now: [(event, occurrence date, reminder)]. Each one
        goes off once. One missed while he was off or napping still goes off later, as long
        as the event hasn't started and it isn't more than half a day late."""
        now = now or time.time()
        today = dt.date.fromtimestamp(now)
        out = []
        for ev in self.events:
            for n, r in enumerate(ev.get("reminders") or []):
                ahead = (r.get("minutes", 0) // 1440) + r.get("days", 0) + 2
                for i in range(-1, ahead + 1):
                    day = today + dt.timedelta(days=i)
                    if not occurs_on(ev, day):
                        continue
                    at = remind_at(ev, day, r)
                    key = f"{ev['id']}|{day.isoformat()}|{n}"
                    start = start_of(ev, day) + (86400 if not ev.get("time") else 0)
                    if at <= now and key not in self.fired and now - at <= LATE_LIMIT_S and now < start:
                        out.append((ev, day, r))
                        self.fired[key] = now
        if out:
            # forget old ones so the list doesn't grow for ever
            self.fired = {k: v for k, v in self.fired.items() if now - v < 3 * 86400}
            self.store.put("calendar_fired", self.fired)
        return out

    # ------------------------------------------------------------ words
    @staticmethod
    def screen_text(ev, day, now=None):
        """The vague one, for his screen: nothing about what the event is."""
        now = now or time.time()
        when = until_words(start_of(ev, day) - now)
        if not ev.get("time"):
            when = ("today" if day == dt.date.fromtimestamp(now) else
                    "tomorrow" if day == dt.date.fromtimestamp(now) + dt.timedelta(days=1)
                    else f"in {(day - dt.date.fromtimestamp(now)).days} days")
        return f"REMINDER: EVENT {when.upper()}!"

    @staticmethod
    def spoken_reminder(ev, day, now=None):
        """The real one, for the Dot: 'Reminder: dental appointment, in 1 hour, at 2 o'clock...'"""
        now = now or time.time()
        today = dt.date.fromtimestamp(now)
        on = ("today" if day == today else "tomorrow" if day == today + dt.timedelta(days=1)
              else day.strftime("on %A the ") + _ordinal(day.day))
        if not ev.get("time"):
            return f"Reminder: {ev['title']}, {on}."
        until = until_words(start_of(ev, day) - now)
        if day == today and until.startswith("in ") and "day" not in until:
            return f"Reminder: {ev['title']}, {until}, at {clock_words(ev['time'])}."
        return f"Reminder: {ev['title']}, {on} at {clock_words(ev['time'])}."

    def spoken_day(self, day, label):
        """'Today you have 2 events: ...' for a spoken question."""
        evs = self.on_day(day)
        if not evs:
            return f"Nothing on your calendar {label}."
        parts = [f"{e['title']}, all day" if not e.get("time") else f"{e['title']} at {clock_words(e['time'])}"
                 for e in evs]
        listed = parts[0] if len(parts) == 1 else "; ".join(parts[:-1]) + "; and " + parts[-1]
        n = len(evs)
        return f"{label[:1].upper() + label[1:]} you have {n} event{'s' if n != 1 else ''}: {listed}."


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
