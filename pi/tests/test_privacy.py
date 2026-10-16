"""Privacy and the network: web pages on the internet can't reach the Den or the control link
(cross-site requests, DNS rebinding, cross-protocol), the map's code is pinned, and the system
log never gets what was said, where he's been, or other people's device addresses."""
import asyncio
import glob
import re
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request

from bt_dragon import config, server
from bt_dragon.app import Dragon

# the checks on their own
ok, bad = server.host_ok, (lambda h: not server.host_ok(h))
assert ok("192.168.1.20:8080") and ok("172.20.10.2") and ok("[fe80::1]:8080") and ok("bt-dragon:8080")
assert ok("bt-dragon.local:8080") and ok("harald.lan") and ok("pi.home.arpa") and ok(None)
assert ok("bt-dragon.tail1234.ts.net:8080") and ok("100.101.102.103:8080") and ok("[fd7a:115c:a1e0::1]:8080")
assert not server.host_ok("bt-dragon.ts.net.evil.example") and not server.host_ok("evilts.net")
assert bad("evil.example:8080") and bad("192.168.1.20.nip.io") and bad("rebind.attacker.com")
assert server.origin_ok(None, "1.2.3.4:8080") and server.origin_ok("http://1.2.3.4:8080", "1.2.3.4:8080")
assert not server.origin_ok("https://evil.example", "1.2.3.4:8080") and not server.origin_ok("null", "1.2.3.4:8080")
assert server.looks_like_http("POST / HTTP/1.1") and server.looks_like_http("GET /x?y HTTP/1.0")
assert not server.looks_like_http("STATUS") and not server.looks_like_http("NAME Post Office HTTP fan")

cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


app.cfg["link"]["web_port"], app.cfg["link"]["port"] = web, ctl = free_port(), free_port()


async def serve():
    await asyncio.gather(server.web_server(app), server.control_server(app))


threading.Thread(target=lambda: asyncio.run(serve()), daemon=True).start()
time.sleep(3)


def http(path, data=None, **headers):
    r = urllib.request.Request(f"http://127.0.0.1:{web}{path}", data=data, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# the Den's own pages work
assert http("/")[0] == 200
assert http("/api/cmd", b"STATUS", Origin=f"http://127.0.0.1:{web}")[0] == 200
assert http("/api/cmd", b"STATUS", Host=f"bt-dragon.local:{web}", Origin=f"http://bt-dragon.local:{web}")[0] == 200
assert http("/api/cmd", b"STATUS")[0] == 200                         # not a browser (a script)
# another site can't send it commands
assert http("/api/cmd", b"NAME Mallory", Origin="https://evil.example")[0] == 403 and app.pet.name == "Harald"
assert http("/api/restore", b"x" * 10, Origin="https://evil.example")[0] == 403
# a site that points its own name at the Pi gets nothing (DNS rebinding)
code, body = http("/api/backup", Host="rebind.evil.example")
assert code == 421 and not body.startswith(b"\x1f\x8b")
assert http("/", Host=f"evil.example:{web}")[0] == 421

# a web request sent to the control link's port is never run as commands
body = "\nNAME Mallory\n"
c = socket.create_connection(("127.0.0.1", ctl))
c.sendall((f"POST / HTTP/1.1\r\nHost: 172.20.10.2:{ctl}\r\nOrigin: https://evil.example\r\n"
           f"Content-Type: text/plain\r\nContent-Length: {len(body)}\r\n\r\n{body}").encode())
time.sleep(1.5)
c.close()
time.sleep(0.3)
assert app.pet.name == "Harald", app.pet.name
# (while the control link itself still works)
c = socket.create_connection(("127.0.0.1", ctl))
c.sendall(b"NAME Ember\n")
time.sleep(1)
c.close()
assert app.pet.name == "Ember"

# the map's code from the internet is pinned to Leaflet 1.9.4 exactly
with open("bt_dragon/map.html", encoding="utf-8") as f:
    m = f.read()
assert m.count('integrity="sha256-') == 2 and len(re.findall(r'(?:src|href)="https://unpkg', m)) == 2

# the system log: never what was heard, which realm, or a gadget's address
for p in glob.glob("bt_dragon/*.py"):
    with open(p, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if re.search(r"\blog\.\w+\(", line):
                assert not re.search(r"(?<!len\()\b(text|address|realm|mac|lat|lon)\s*[,)]", line.split("\",", 1)[-1].split("#")[0]), (p, n, line)
print("privacy ok")
