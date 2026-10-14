"""Run: python3 -m tests.test_sensorserver_gps  (from the pi folder)"""
import asyncio, base64, hashlib, json, struct

def frame(body):
    n = len(body)
    return bytes([0x81, n]) + body if n < 126 else bytes([0x81, 126]) + struct.pack(">H", n) + body

from bt_dragon.gps import Gps
from bt_dragon.activity import read_frame

async def fake(reader, writer):
    req = b""
    while not req.endswith(b"\r\n\r\n"):
        req += await reader.read(1024)
    assert b"GET /gps " in req
    key = [l.split(":", 1)[1].strip() for l in req.decode().split("\r\n") if l.lower().startswith("sec-websocket-key")][0]
    acc = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    writer.write(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n\r\n".encode())
    # stationary phone: only answers when asked
    op, data = await read_frame(reader)
    print("server got:", op, data)
    body = json.dumps({"lastKnownLocation": {"latitude": 39.8283, "longitude": -98.5795, "altitude": 90.0,
                       "accuracy": 6.0, "speed": 1.3, "time": 1791700000000}}).encode()
    writer.write(frame(body))
    # a moving phone pushes updates by itself
    body = json.dumps({"latitude": 39.8284, "longitude": -98.5794, "speed": 1.4, "accuracy": 5.0}).encode()
    writer.write(frame(body))
    await writer.drain(); await asyncio.sleep(0.3)
    writer.close()

async def main():
    srv = await asyncio.start_server(fake, "127.0.0.1", 8098)
    g, stop = Gps(), asyncio.Event()
    t = asyncio.create_task(g.connect_sensorserver(lambda: "127.0.0.1", 8098, stop))
    await asyncio.sleep(0.6); stop.set(); await t; srv.close()
    print(g.state(), g.fix)
    assert g.state() == "FIX" and abs(g.fix["lat"] - 39.8284) < 1e-6 and g.fix["speed"] == 1.4
asyncio.run(main())
print("all good")
