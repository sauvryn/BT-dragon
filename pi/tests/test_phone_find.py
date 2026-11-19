"""The phone's voice finds Harald again after his address changes: he answers "BTDRAGON? 1", and
the helper asks every address on the hotspot (and keeps a notification with his current Den)."""
import asyncio
import importlib.util
import os
import socket
import tempfile
import threading
import time

from bt_dragon import phonevoice, server

PORT = 25150 + os.getpid() % 1000


class _Pet:
    name = "Ember"


class _App:
    def __init__(self):
        self.cfg = {"link": {"discovery_port": PORT, "port": 5151, "web_port": 8080}}
        self.pet = _Pet()
        self.stop = None

    async def _sleep(self, s):
        await asyncio.sleep(min(s, 0.1))


app = _App()
loop = asyncio.new_event_loop()


def run():
    asyncio.set_event_loop(loop)
    app.stop = asyncio.Event()
    loop.run_until_complete(server.discovery_replies(app))


t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(0.5)

# Harald answers a question, and only a question
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)
s.sendto(b"BTDRAGON 1 port=1 web=2 name=someone else\n", ("127.0.0.1", PORT))
s.sendto(b"BTDRAGON? 1\n", ("127.0.0.1", PORT))
data, _ = s.recvfrom(512)
assert data == b"BTDRAGON 1 port=5151 web=8080 name=Ember\n", data
s.close()

# the helper, as downloaded: with his address, ticket and network name filled in
code = phonevoice.script("10.201.126.241:8080", "tok", "bt-dragon")
assert "__ADDRESS__" not in code and "__HOSTNAME__" not in code and 'HOSTNAME = "bt-dragon"' in code
d = tempfile.mkdtemp()
path = os.path.join(d, "bt_dragon_voice.py")
with open(path, "w") as f:
    f.write(code)
spec = importlib.util.spec_from_file_location("helper", path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
helper.DISCOVERY_PORT = PORT

# it reads the phone's own addresses from `ip -4 -o addr show`
real_run = helper.subprocess.run


class _Done:
    def __init__(self, out):
        self.stdout = out


helper.subprocess.run = lambda *a, **k: _Done(
    "1: lo    inet 127.0.0.1/8 scope host lo\n"
    "23: rmnet_data0    inet 100.64.12.9/30 scope global rmnet_data0\n"
    "31: swlan0    inet 10.154.85.166/24 brd 10.154.85.255 scope global swlan0\n")
assert helper.local_nets() == [("10.154.85.166", 24, "10.154.85.255")]     # (not mobile data, not loopback)
helper.subprocess.run = real_run

# asking every address on the hotspot finds him (here the "hotspot" is 127.0.0.x)
helper.local_nets = lambda: [("127.0.0.2", 24, None)]
found = helper.ask()
assert found == ("127.0.0.1:8080", "Ember"), found
# a name lookup that gives the old address doesn't count as finding him
helper.by_name = lambda address: address
assert helper.find_dragon("127.0.0.9:8080") == ("127.0.0.1:8080", "Ember")
helper.by_name = lambda address: "10.1.2.3:8080"
assert helper.find_dragon("127.0.0.9:8080") == ("10.1.2.3:8080", None)

# the notification: an "Open the Den" button that goes to his current address
calls = []
helper.subprocess.run = lambda args, **k: calls.append(args)
helper.notify("10.154.85.30:8080", "Ember")
a = calls[-1]
assert a[0] == "termux-notification" and "--ongoing" in a and "Open the Den" in a
assert "termux-open-url http://10.154.85.30:8080" in a
helper.unnotify()
assert calls[-1][0] == "termux-notification-remove"

loop.call_soon_threadsafe(app.stop.set)
t.join(8)
print("phone find ok")
