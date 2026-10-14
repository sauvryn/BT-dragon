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
