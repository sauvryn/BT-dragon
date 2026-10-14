"""
The Moon's phases, worked out from the date alone: no internet needed.

The Moon goes from new to new in about 29.53 days, but not evenly: its orbit and Earth's
are both ellipses, and the Sun tugs on the Moon. Jean Meeus's "Astronomical Algorithms"
(chapter 49) corrects for all that with a handful of sine terms, giving the moment of
each new moon, first quarter, full moon and last quarter to within a minute or so for
centuries either side of today. That's what this file does.

In Norse myth the Moon is the god Mani, chased across the sky by the wolf Hati. At full
moon Mani shines brightest; at new moon Hati has (for now) hidden him.
"""
import math
import time

SYNODIC = 29.530588861           # days from new moon to new moon, on average
PHASES = ("new", "first quarter", "full", "last quarter")
DELTA_T_S = 70                   # Earth's rotation lags atomic time by about this much
UNIX_EPOCH_JD = 2440587.5


def _sin(deg):
    return math.sin(math.radians(deg))


def _cos(deg):
    return math.cos(math.radians(deg))


def phase_time(k):
    """Unix time of the phase numbered k: whole k = new moon, +0.25 first quarter,
    +0.5 full, +0.75 last quarter. k = 0 is the new moon of January 6, 2000."""
    T = k / 1236.85
    jde = (2451550.09766 + SYNODIC * k + 0.00015437 * T ** 2 - 0.000000150 * T ** 3
           + 0.00000000073 * T ** 4)
    E = 1 - 0.002516 * T - 0.0000074 * T ** 2
    M = 2.5534 + 29.10535670 * k - 0.0000014 * T ** 2 - 0.00000011 * T ** 3
    Mp = 201.5643 + 385.81693528 * k + 0.0107582 * T ** 2 + 0.00001238 * T ** 3 - 0.000000058 * T ** 4
    F = 160.7108 + 390.67050284 * k - 0.0016118 * T ** 2 - 0.00000227 * T ** 3 + 0.000000011 * T ** 4
    Om = 124.7746 - 1.56375588 * k + 0.0020672 * T ** 2 + 0.00000215 * T ** 3
    which = round((k % 1) * 4) % 4
    if which in (0, 2):
        new = which == 0
        c = [(-0.40720 if new else -0.40614, _sin(Mp)),
             ((0.17241 if new else 0.17302) * E, _sin(M)),
             (0.01608 if new else 0.01614, _sin(2 * Mp)),
             (0.01039 if new else 0.01043, _sin(2 * F)),
             ((0.00739 if new else 0.00734) * E, _sin(Mp - M)),
             ((-0.00514 if new else -0.00515) * E, _sin(Mp + M)),
             ((0.00208 if new else 0.00209) * E * E, _sin(2 * M)),
             (-0.00111, _sin(Mp - 2 * F)), (-0.00057, _sin(Mp + 2 * F)),
             (0.00056 * E, _sin(2 * Mp + M)), (-0.00042, _sin(3 * Mp)),
             (0.00042 * E, _sin(M + 2 * F)), (0.00038 * E, _sin(M - 2 * F)),
             (-0.00024 * E, _sin(2 * Mp - M)), (-0.00017, _sin(Om)),
             (-0.00007, _sin(Mp + 2 * M)), (0.00004, _sin(2 * Mp - 2 * F)),
             (0.00004, _sin(3 * M)), (0.00003, _sin(Mp + M - 2 * F)),
             (0.00003, _sin(2 * Mp + 2 * F)), (-0.00003, _sin(Mp + M + 2 * F)),
             (0.00003, _sin(Mp - M + 2 * F)), (-0.00002, _sin(Mp - M - 2 * F)),
             (-0.00002, _sin(3 * Mp + M)), (0.00002, _sin(4 * Mp))]
        jde += sum(a * b for a, b in c)
    else:
        c = [(-0.62801, _sin(Mp)), (0.17172 * E, _sin(M)), (-0.01183 * E, _sin(Mp + M)),
             (0.00862, _sin(2 * Mp)), (0.00804, _sin(2 * F)), (0.00454 * E, _sin(Mp - M)),
             (0.00204 * E * E, _sin(2 * M)), (-0.00180, _sin(Mp - 2 * F)),
             (-0.00070, _sin(Mp + 2 * F)), (-0.00040, _sin(3 * Mp)),
             (-0.00034 * E, _sin(2 * Mp - M)), (0.00032 * E, _sin(M + 2 * F)),
             (0.00032 * E, _sin(M - 2 * F)), (-0.00028 * E * E, _sin(Mp + 2 * M)),
             (0.00027 * E, _sin(2 * Mp + M)), (-0.00017, _sin(Om)),
             (-0.00005, _sin(Mp - M - 2 * F)), (0.00004, _sin(2 * Mp + 2 * F)),
             (-0.00004, _sin(Mp + M + 2 * F)), (0.00004, _sin(Mp - 2 * M)),
             (0.00003, _sin(Mp + M - 2 * F)), (0.00003, _sin(3 * M)),
             (0.00002, _sin(2 * Mp - 2 * F)), (0.00002, _sin(Mp - M + 2 * F)),
             (-0.00002, _sin(3 * Mp + M))]
        W = (0.00306 - 0.00038 * E * _cos(M) + 0.00026 * _cos(Mp) - 0.00002 * _cos(Mp - M)
             + 0.00002 * _cos(Mp + M) + 0.00002 * _cos(2 * F))
        jde += sum(a * b for a, b in c) + (W if which == 1 else -W)
    # small nudges from the planets
    A = [299.77 + 0.107408 * k - 0.009173 * T ** 2, 251.88 + 0.016321 * k, 251.83 + 26.651886 * k,
         349.42 + 36.412478 * k, 84.66 + 18.206239 * k, 141.74 + 53.303771 * k,
         207.14 + 2.453732 * k, 154.84 + 7.306860 * k, 34.52 + 27.261239 * k,
         207.19 + 0.121824 * k, 291.34 + 1.844379 * k, 161.72 + 24.198154 * k,
         239.56 + 25.513099 * k, 331.55 + 3.592518 * k]
    coef = [325, 165, 164, 126, 110, 62, 60, 56, 47, 42, 40, 37, 35, 23]
    jde += sum(c * 1e-6 * _sin(a) for c, a in zip(coef, A))
    return (jde - UNIX_EPOCH_JD) * 86400 - DELTA_T_S


def phases_around(ts, before=1, after=5):
    """[(unix_time, phase name)] from a little before ts to a few phases after it."""
    k0 = math.floor((ts / 86400 + UNIX_EPOCH_JD - 2451550.09766) / SYNODIC * 4) / 4
    out = []
    for i in range(-before * 4 - 2, after * 4 + 2):
        k = k0 + i / 4
        out.append((phase_time(k), PHASES[round((k % 1) * 4) % 4]))
    return sorted(out)


def now_info(ts=None):
    """Tonight's Moon for the den: how far through the cycle (0 = new, 0.5 = full), how
    much is lit, and the next few phases."""
    ts = ts or time.time()
    ph = phases_around(ts)
    last_new = max(t for t, n in ph if n == "new" and t <= ts)
    next_new = min(t for t, n in ph if n == "new" and t > ts)
    frac = (ts - last_new) / (next_new - last_new)
    lit = (1 - math.cos(2 * math.pi * frac)) / 2
    if frac < 0.02 or frac > 0.98:
        name = "new moon"
    elif abs(frac - 0.5) < 0.02:
        name = "full moon"
    elif abs(frac - 0.25) < 0.02:
        name = "first quarter"
    elif abs(frac - 0.75) < 0.02:
        name = "last quarter"
    else:
        name = ("waxing " if frac < 0.5 else "waning ") + ("crescent" if lit < 0.5 else "gibbous")
    upcoming = [{"ts": int(t), "name": n} for t, n in ph if t > ts][:4]
    return {"frac": round(frac, 4), "lit": round(lit, 3), "name": name, "next": upcoming}


def todays_phase(ts=None):
    """The major phase falling on today's local date, as (phase name, unix time), or None."""
    ts = ts or time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(ts))
    for t, n in phases_around(ts, 1, 1):
        if time.strftime("%Y-%m-%d", time.localtime(t)) == today:
            return n, t
    return None
