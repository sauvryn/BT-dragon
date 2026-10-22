"""Run: python3 -m tests.test_activity  (from the pi folder)"""
import asyncio, base64, hashlib, json, math, struct, time
from bt_dragon.store import Store
from bt_dragon.pet import Pet, berry_value
from bt_dragon.activity import Activity, Motion, StepLink, classify

# --- berries: +1 per day since last seen, capped at the treat value
assert [berry_value("wpa2", d) for d in range(7)] == [0, 1, 2, 3, 4, 4, 4]
assert berry_value("open", 9) == 6
st = Store(":memory:")
ap = {"bssid": "AA", "ssid": "x", "auth": "[ESS]", "channel": 1, "freq": 2412, "rssi": -50}
print("first", st.ap_seen(ap, 1_000_000))
print("2 days later", st.ap_seen(ap, 1_000_000 + 2 * 86400))
print("untouched (clock not ok)", st.ap_seen(ap, 1_000_000 + 9 * 86400, touch=False),
      st.ap_seen(ap, 1_000_000 + 9 * 86400))

# --- hunger and joy are independent
p = Pet(st, "Harald"); p.hunger, p.joy = 20, 90
print(p.feeling(), p.mood(), p.belly())
p.hunger, p.joy = 97, 20
print(p.feeling(), p.mood(), p.belly())

# --- motion: 60 s walking at 1.3 m/s north, then 30 s still, then driving at 13 m/s
m = Motion(); t = 1000.0; lat = 39.82
for i in range(60):
    lat += 1.3 / 111320; m.feed({"lat": lat, "lon": -98.57, "ts": t + i, "speed": 1.3 + (0.4 if i % 2 else -0.4), "acc": 5})
print("mode", m.mode, "walked m", {k: round(v) for k, v in m.take().items()})
for i in range(30):
    m.feed({"lat": lat + (0.000003 if i % 2 else 0), "lon": -98.57, "ts": t + 60 + i, "speed": 0.2, "acc": 5})
print("mode", m.mode, "jitter counted", m.take())
for i in range(30):
    lat += 13 / 111320; m.feed({"lat": lat, "lon": -98.57, "ts": t + 90 + i, "speed": 13, "acc": 5})
print("mode", m.mode, {k: round(v) for k, v in m.take().items()})
assert classify(1.3) == "walking" and classify(13) == "vehicle"


# --- a tram (or bus) in town: pulling away, a fast stretch, slowing, a stop, crawling.
# Speed alone files the slow parts as walking, running and cycling.
def tram(m, t, lat, laps=4):
    profile = ([1.0, 2.0, 3.5, 5.0, 7.0] + [11.0] * 25 + [7.0, 5.0, 3.5, 2.0, 1.0] + [0.0] * 20
               + [1.5] * 20)                                    # crawling behind traffic
    for _ in range(laps):
        for sp in profile:
            lat += sp / 111320
            m.feed({"lat": lat, "lon": -0.13, "ts": t, "speed": sp, "acc": 5})
            t += 1
    return t, lat


def own(d):
    return round(sum(v for k, v in d.items() if k != "vehicle"))


old = Motion()                                                  # (speed alone, the old way:)
old._update_riding = lambda now, sp: None
t, lat = tram(old, 0.0, 51.51)
assert own(old.take(t + 60)) > 100                              # lots of "walking" on a tram
m = Motion()
t, lat = tram(m, 0.0, 51.51)
got = m.take(t + 60)
assert own(got) == 0 and got["vehicle"] > 1300, got             # now: all of it the ride
assert m.riding
# getting off, no step counter: 90 s at walking pace, then it's a walk again
for i in range(120):
    lat += 1.3 / 111320; m.feed({"lat": lat, "lon": -0.13, "ts": t + i, "speed": 1.3, "acc": 5})
assert not m.riding and m.mode == "walking"
walk = m.take(t + 200)
assert 30 < walk.get("walking", 0) < 70, walk                   # the last half minute or so
# with a step counter: off the tram the moment the steps start
steps = {"on": False}
m = Motion(feet=lambda: steps["on"])
t, lat = tram(m, 0.0, 51.51, laps=2)
m.take()
steps["on"] = True
for i in range(30):
    lat += 1.3 / 111320; m.feed({"lat": lat, "lon": -0.13, "ts": t + i, "speed": 1.3, "acc": 5})
assert not m.riding and m.mode == "walking" and m.take(t + 100).get("walking", 0) > 30
# ...walking speed without any steps, just after vehicle speed (a bus in traffic), isn't a walk
steps["on"] = False
m = Motion(feet=lambda: steps["on"])
for i in range(12):
    lat += 10 / 111320; m.feed({"lat": lat, "lon": -0.13, "ts": 4980 + i, "speed": 10.0, "acc": 5})
m.take(4995)
for i in range(60):
    lat += 1.3 / 111320; m.feed({"lat": lat, "lon": -0.13, "ts": 5000 + i, "speed": 1.3, "acc": 5})
got = m.take(6000)
assert m.mode == "vehicle" and own(got) == 0 and got["vehicle"] > 50, got
# ...but with no vehicle speed in the last 3 minutes, steps going quiet (many phones send their
# step count only every minute or so with the screen off) don't make a walk a ride
m = Motion(feet=lambda: steps["on"])
for i in range(60):
    lat += 1.3 / 111320; m.feed({"lat": lat, "lon": -0.13, "ts": 7000 + i, "speed": 1.3, "acc": 5})
got = m.take(8000)
assert m.mode == "walking" and got.get("vehicle", 0) == 0 and got.get("walking", 0) > 50, got
# a burst of vehicle speed mid-walk (GPS between tall buildings) never starts a ride while the
# step counter says you're walking, even when the positions agree with the speed
steps["on"] = True
m = Motion(feet=lambda: steps["on"])
for i in range(40):
    lat += 1.4 / 111320; m.feed({"lat": lat, "lon": -0.13, "ts": 8100 + i, "speed": 1.4, "acc": 5})
for i in range(15):
    lat += 10 / 111320; m.feed({"lat": lat, "lon": -0.13, "ts": 8140 + i, "speed": 10.0, "acc": 5})
for i in range(40):
    lat += 1.4 / 111320; m.feed({"lat": lat, "lon": -0.13, "ts": 8155 + i, "speed": 1.4, "acc": 5})
got = m.take(8400)
assert not m.riding and got.get("vehicle", 0) == 0, got
# a bike ride (fast, but never 9 m/s for long) stays a bike ride
m = Motion()
for i in range(120):
    sp = 6.0 + (3.5 if i % 30 == 0 else 0)                      # a quick burst now and then
    lat += sp / 111320; m.feed({"lat": lat, "lon": -0.13, "ts": 9000 + i, "speed": sp, "acc": 5})
assert not m.riding and m.mode == "cycling" and m.take(9500).get("cycling", 0) > 700

# --- indoors: the phone finds itself from Wi-Fi and masts, the position jumps about, and it
# reports the jumps as bus-like speeds. Nothing real moved, so no ride, and no "cycling" either.
import random
home = (51.51, -0.13)
for seed in range(20):                                           # twenty different afternoons on the sofa
    rnd = random.Random(seed)
    m = Motion()
    for i in range(600):                                         # ten minutes each
        jump = rnd.uniform(0, 60) / 111320
        m.feed({"lat": home[0] + jump * rnd.choice((-1, 1)), "lon": home[1] + rnd.uniform(-40, 40) / 70000,
                "ts": 20000 + i, "speed": rnd.uniform(9.5, 15), "acc": rnd.choice((12, 20, 25, 45, 80))})
    got = m.take(21000)
    assert not m.riding and got.get("vehicle", 0) == 0 and got.get("cycling", 0) == 0, (seed, got)
# ...a little smaller wobble, and a lot bigger, as well
for spread in (20, 150):
    for seed in range(10):
        rnd = random.Random(100 + seed)
        m = Motion()
        for i in range(600):
            m.feed({"lat": home[0] + rnd.uniform(-spread, spread) / 111320, "lon": home[1] + rnd.uniform(-spread, spread) / 70000,
                    "ts": 20000 + i, "speed": rnd.uniform(9.5, 15), "acc": rnd.choice((10, 15, 25))})
        got = m.take(21000)
        assert not m.riding and sum(got.values()) == 0, (spread, seed, got)
# a tram whose fixes jitter a few meters each still rides, and jitter never adds distance
rnd = random.Random(1)
m = Motion()
lat, lon, t, true = 51.51, -0.13, 0, 0.0
for sp in ([1.0, 2.0, 3.5, 5.0, 7.0] + [11.0] * 25 + [7.0, 5.0, 3.5, 2.0, 1.0] + [0.0] * 20 + [1.5] * 20) * 4:
    lat += sp * 0.8 / 111320; lon += sp * 0.6 / 70000; true += sp
    m.feed({"lat": lat + rnd.gauss(0, 4) / 111320, "lon": lon + rnd.gauss(0, 4) / 70000, "ts": t, "speed": sp, "acc": 15})
    t += 1
got = m.take(t + 60)
assert m.riding and 0.75 * true < got.get("vehicle", 0) <= true and own(got) == 0, (got, true)
# ...while a real ride, with the same accuracy, still counts
m = Motion()
lat = 51.51
for i in range(60):
    lat += 11 / 111320
    m.feed({"lat": lat, "lon": -0.13, "ts": 30000 + i, "speed": 11, "acc": 20})
assert m.riding and m.take(31000).get("vehicle", 0) > 400
print("indoor wobble ok")

# the step counter's evidence: steps in the last 45 s
a = Activity(Store(":memory:"))
assert a.feet() is None                                          # no step counter
a.steps(100, True)
assert a.feet() is False
a.steps(130, True)
assert a.feet() is True and a.feet(time.time() + 60) is False

# --- steps: Harald off overnight, phone counted 4000 steps
a = Activity(st)
st.put("steps_last", 10000)
print("reconnect:", a.steps(14000, False))       # story of 4000 steps
print("live, no GPS:", a.steps(14100, False))    # walking 75 m with Harald
print("live, GPS on:", a.steps(14200, True))     # GPS measures it instead
a.link_lost()
print("phone rebooted:", a.steps(50, False))     # counter reset: no story

# --- story vs adventure joy per 100 m
p.joy = 0; p.story(1000, 1333); s_joy = p.joy
p.joy = 0; p.adventure({"walking": 1000}); w_joy = p.joy
p.joy = 0; p.adventure({"vehicle": 1000}); v_joy = p.joy
print(f"1 km: told +{s_joy:.0f} joy, walked with Harald +{w_joy:.0f}, driven with Harald +{v_joy:.0f}")
assert w_joy > s_joy > v_joy

# --- websocket step link against a fake Sensor Server
async def fake_server(reader, writer):
    req = b""
    while not req.endswith(b"\r\n\r\n"):
        req += await reader.read(1024)
    key = [l.split(":", 1)[1].strip() for l in req.decode().split("\r\n") if l.lower().startswith("sec-websocket-key")][0]
    acc = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    writer.write(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n\r\n".encode())
    for n in (5000, 5003, 5010):
        body = json.dumps({"values": [float(n)], "accuracy": 3, "timestamp": 1}).encode()
        writer.write(bytes([0x81, len(body)]) + body)
        await writer.drain(); await asyncio.sleep(0.05)
    writer.write(bytes([0x88, 0])); await writer.drain(); writer.close()

async def main():
    got, lost = [], []
    srv = await asyncio.start_server(fake_server, "127.0.0.1", 8099)
    stop = asyncio.Event()
    link = StepLink(got.append, lambda: lost.append(1))
    task = asyncio.create_task(link.run(lambda: "127.0.0.1", 8099, stop))
    await asyncio.sleep(0.5); stop.set(); await task; srv.close()
    print("websocket steps:", got, "lost:", lost)
    assert got == [5000, 5003, 5010] and lost == [1]
asyncio.run(main())
print("all good")
