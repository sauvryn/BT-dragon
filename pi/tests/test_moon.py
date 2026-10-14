"""Moon phases against published times (timeanddate.com / USNO), to within 2 minutes."""
import calendar
import time

from bt_dragon import moon

KNOWN = [("2000-01-06 18:14", "new"), ("2024-01-11 11:57", "new"), ("2024-01-18 03:52", "first quarter"),
         ("2024-01-25 17:54", "full"), ("2024-02-02 23:18", "last quarter"),
         ("2025-09-21 19:54", "new"), ("2025-10-07 03:47", "full")]
for when, name in KNOWN:
    t = calendar.timegm(time.strptime(when, "%Y-%m-%d %H:%M"))
    err = min(abs(x - t) for x, n in moon.phases_around(t, 1, 1) if n == name)
    assert err < 120, (when, name, err)

full = calendar.timegm(time.strptime("2025-10-07 03:47", "%Y-%m-%d %H:%M"))
info = moon.now_info(full)
assert info["name"] == "full moon" and info["lit"] > 0.99, info
info = moon.now_info(full + 4 * 86400)
assert info["name"] == "waning gibbous" and 0.5 < info["lit"] < 0.95, info
assert moon.todays_phase(full + 3600)[0] == "full"
assert moon.todays_phase(full + 3 * 86400) is None
print("all good")
