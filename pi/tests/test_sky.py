"""Lands, stars and the barometer, without a phone."""
import time

from bt_dragon import sky, tuning


class FakeStore(dict):
    def __init__(self):
        super().__init__()
        self.lands, self.star_rows = {}, {}

    def get(self, k, d=None):
        return dict.get(self, k, d)

    def put(self, k, v):
        self[k] = v

    def land_seen(self, cell, realm, now):
        if cell in self.lands:
            return False, False
        new_realm = realm not in self.lands.values()
        self.lands[cell] = realm
        return True, new_realm

    def star_seen(self, key, const, prn, now):
        self.star_rows[key] = const

    def stars(self):
        return [{"key": k, "const": c} for k, c in self.star_rows.items()]


# ---- grid: squares are about the right size at different latitudes
for lat in (0.0, 39.8, 53.6, 70.0):
    a = sky.grid_cell(lat, 10.0, 100)
    b = sky.grid_cell(lat, 10.0 + 150 / (111320 * __import__("math").cos(__import__("math").radians(lat))), 100)
    assert a != b, (lat, a, b)                           # 150 m east is a different square
    # and a square really is ~100 m tall: 100 neighboring rows span ~10 km of latitude
    r0 = int(sky.grid_cell(lat, 10.0, 100).split(":")[0])
    r1 = int(sky.grid_cell(lat + 10000 / 111320, 10.0, 100).split(":")[0])
    assert r1 - r0 == 100, (lat, r1 - r0)

st = FakeStore()
st.lands_all = lambda: list(st.lands.items())
st.forget_lands = lambda: st.lands.clear()
lands = sky.Lands(st)
assert st["land_grid"] == sky.LAND_M
# the middle of a square: only that square (and its realm)
lat, lon = sky.cell_center(sky.grid_cell(39.82, -98.57, 250), 250)
assert lands.visit({"lat": lat, "lon": lon, "acc": 80}) is None          # too vague to count
assert lands.visit({"lat": lat, "lon": lon, "acc": 8}) == [True]          # new land, new realm
assert lands.visit({"lat": lat, "lon": lon, "acc": 8}) == []              # already his
# walking along a square's north edge, 20 m inside it: the square beyond the edge is claimed too
s_, w_, n_, e_ = sky.cell_bounds(sky.grid_cell(lat, lon, 250), 250)
got = lands.visit({"lat": n_ - 20 / 111320, "lon": lon, "acc": 8})
assert len(got) == 1, got
assert sky.grid_cell(n_ + 100 / 111320, lon, 250) in st.lands            # the square to the north
# 60 m inside the edge is too far: nothing more to claim
assert lands.visit({"lat": s_ + 60 / 111320, "lon": lon, "acc": 8}) == []
# old 100 m squares become the 250 m square their center falls in
st2 = FakeStore()
st2.lands_all = lambda: list(st2.lands.items())
st2.forget_lands = lambda: st2.lands.clear()
for la in (39.8200, 39.8201, 39.8300):
    st2.land_seen(sky.grid_cell(la, -98.57, 100), sky.grid_cell(la, -98.57, 1000), 0)
sky.Lands(st2)
assert st2["land_grid"] == 250 and len(st2.lands) == 2, st2.lands

# ---- stars: talkers, SBAS, weak signals; known stars only count when they rise again
T = 1_800_000_000.0
stars = sky.Stars(st)
stars.gsv("GP", "$GPGSV,1,1,04,05,40,100,30,44,30,200,35,12,20,90,,25,10,10,8".split(","), T)
stars.gsv("GA", "$GAGSV,1,1,01,19,50,120,33,7".split(","), T)   # NMEA 4.10: a trailing signal ID
new, consts, risen = stars.take()
assert [k for k, _ in new] == ["GPS-5", "SBAS-44", "Galileo-19"], new  # 12 had no signal, 25 too weak
assert consts == ["GPS", "SBAS", "Galileo"] and risen == []
stars.gsv("GP", "$GPGSV,1,1,01,05,40,100,30".split(","), T + 60)
assert stars.take() == ([], [], [])                                  # still in view: nothing new
# back outdoors after 3 hours inside: GPS 5 reappears high in the sky -> not a rising
stars.gsv("GP", "$GPGSV,1,1,01,05,55,100,30".split(","), T + 3 * 3600)
assert stars.take() == ([], [], [])
# lost for 10 minutes behind a building, then heard low: too short to have set and risen
stars.gsv("GP", "$GPGSV,1,1,01,05,12,100,30".split(","), T + 3 * 3600 + 600)
assert stars.take() == ([], [], [])
# out of earshot for 6 hours, then heard just above the horizon: it has risen again
stars.gsv("GA", "$GAGSV,1,1,01,19,8,120,33".split(","), T + 6 * 3600)
assert stars.take() == ([], [], ["Galileo-19"])
assert sky.constellation("GN", 70) == "GLONASS" and sky.constellation("GN", 305) == "Galileo"

# ---- barometer: a flight of stairs is a climb; slow weather isn't
b = sky.Barometer(FakeStore())
t0 = 1_800_000_000.0
for i in range(0, 600):                       # 10 minutes, readings every second
    p = 1012.0 - (0.4 if i >= 300 else 0.0)  # up ~3.3 m at the 5-minute mark
    b.feed(p, None, "walking", t0 + i)
m = b.take_climb()
assert 3.0 <= m <= 4.0, m
b2 = sky.Barometer(FakeStore())
for i in range(0, 3 * 3600, 2):              # 3 hours of a steady 1 hPa/hour fall
    b2.feed(1015.0 - i / 3600.0, None, "still", t0 + i)
assert b2.take_climb() == 0.0                 # the weather never looks like a climb


def weather_run(fall_per_hour, moved=False, hours=3.6):
    b = sky.Barometer(FakeStore())
    fix = {"lat": 39.82, "lon": -98.57, "acc": 10}
    for i in range(0, int(hours * 3600), 10):
        if moved and i > 3600:
            fix = {"lat": 39.84, "lon": -98.57, "acc": 10}   # 2 km away
        b.feed(1015.0 - fall_per_hour * i / 3600.0, fix, "still", t0 + i)
    return b.weather(t0 + hours * 3600)


kind, d = weather_run(1.2)                    # -3.6 hPa in 3 hours: a storm
assert kind == "storm" and d < -3.0, (kind, d)
assert weather_run(0.5)[0] is None            # slow fall: nothing
assert weather_run(-1.2)[0] == "rise"         # fast rise: weather change
assert weather_run(1.2, moved=True) == (None, None)   # moved across town: can't judge
b3 = sky.Barometer(FakeStore())
for i in range(0, 4 * 3600, 10):
    b3.feed(1015.0 - 1.2 * i / 3600.0, None, "still", t0 + i)
    if i == int(3.3 * 3600):
        first = b3.weather(t0 + i)[0]
assert first == "storm" and b3.weather(t0 + 4 * 3600)[0] is None   # announced once, not again

print("all good")
