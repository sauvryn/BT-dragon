"""The Den password: kept only as a stretched key, wrong guesses slowed down, logins as tickets
(cookies), the testing failsafe, the boot-partition escape hatch, the web gate, the phone voice's
own ticket, and the control link's AUTH (and the Pi itself not needing it)."""
import asyncio
import json
import os
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request

from bt_dragon import config, denauth, phonevoice, server
from bt_dragon.app import Dragon
from bt_dragon.store import Store

denauth.ITERS = 2000            # (quick, for the tests)

# ---- the password and logins, on their own
st = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
a = denauth.DenAuth(st, boot_dirs=())
assert not a.has_password and not a.enabled()
assert a.set_on(True) == "set a password first" and not a.enabled()
assert a.set_password("short") and a.set_password(" padded password ")
assert a.set_password("correct horse") is None and a.has_password
assert "correct horse" not in json.dumps(st.get("den_auth"))        # never the password itself
assert a.check("correct horse") and not a.check("wrong one!")
t0 = 1_000_000.0
assert a.set_on(True, now=t0) is None and a.enabled(t0)

# wrong guesses: five in ten minutes, then a minute's wait (even for the right one), then doubling
a2 = denauth.DenAuth(st, boot_dirs=())
for i in range(5):
    assert not a2.check("nope nope", now=t0 + i)
assert a2.locked_for(t0 + 5) > 50 and not a2.check("correct horse", now=t0 + 10)
for i in range(5):
    a2.check("nope nope", now=t0 + 100 + i)
assert a2.locked_for(t0 + 105) > 110                                  # two minutes this time
assert a2.check("correct horse", now=t0 + 300)                        # (and the right one resets it)
for i in range(5):
    a2.check("nope nope", now=t0 + 400 + i)
assert 50 < a2.locked_for(t0 + 405) <= 60

# tickets: only fingerprints are kept; changing the password throws them away
tok = a.login("correct horse", now=t0)
assert tok and a.login("bad password", now=t0) is None
assert tok not in json.dumps(st.get("den_sessions"))
hdr = f"theme=dark; {denauth.COOKIE}={tok}"
assert a.session_ok(hdr, now=t0 + 60) and not a.session_ok(hdr, now=t0 + denauth.SESSION_S + 1)
assert not a.session_ok(f"{denauth.COOKIE}=forged", now=t0) and not a.session_ok(None)
a.logout(hdr)
assert not a.session_ok(hdr, now=t0 + 60)
tok = a.login("correct horse", now=t0)
pt = a.phone_token()
assert a.phone_ok(pt) and not a.phone_ok("nope") and not a.phone_ok(None)
a.set_password("battery staple")
assert not a.session_ok(f"{denauth.COOKIE}={tok}", now=t0) and not a.phone_ok(pt)
assert a.enabled(t0)

# the failsafe: off again five minutes after it was switched on, with a note for the diary
a.set_failsafe(True, now=t0)
assert a.failsafe_at() == t0 + denauth.FAILSAFE_S
assert a.enabled(t0 + 299) and not a.enabled(t0 + 300)
assert a.news and "failsafe" in a.news[0] and not st.get("den_auth")["on"]
assert a.failsafe_at() is None
a.set_failsafe(False)
a.set_on(True, now=t0)
assert a.enabled(t0 + 10_000)                                          # without it: stays on

# the escape hatch: a file on the boot partition switches it off (and is deleted)
boot = tempfile.mkdtemp()
open(os.path.join(boot, denauth.RESET_FILE), "w").close()
a3 = denauth.DenAuth(st, boot_dirs=(boot,))
assert not a3.enabled() and a3.news and not os.path.exists(os.path.join(boot, denauth.RESET_FILE))
assert a3.has_password                                                  # (the password is kept)

# the phone script carries its ticket
assert "abc123" in phonevoice.script("1.2.3.4:8080", "abc123") and "__TOKEN__" not in phonevoice.script("x", "t")

# ---- the web gate and the control link
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


opener = urllib.request.build_opener(NoRedirect)
ORIGIN = f"http://127.0.0.1:{web}"


def http(path, data=None, **headers):
    if data is not None:
        headers.setdefault("Origin", ORIGIN)
    r = urllib.request.Request(f"http://127.0.0.1:{web}{path}", data=data,
                               headers={k.replace("_", "-"): v for k, v in headers.items()})
    try:
        with opener.open(r, timeout=20) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


# off: everything is open, and /login sends you home
assert http("/")[0] == 200 and http("/login")[0] == 303
assert http("/api/cmd", b"DENAUTHSET on")[1].find(b"set a password first") > 0
code, body, h = http("/api/denpass", b"short")
assert code == 400 and not json.loads(body)["ok"]
code, body, h = http("/api/denpass", b"open sesame")
assert code == 200 and json.loads(body)["ok"]
cookie = h["Set-Cookie"].split(";")[0]
assert "HttpOnly" in h["Set-Cookie"] and "SameSite=Strict" in h["Set-Cookie"]
assert http("/api/cmd", b"DENAUTHSET on")[0] == 200 and app.den_auth.enabled()

# on: without a ticket, pages go to the login page and the API says "log in"
code, body, h = http("/")
assert code == 303 and h["Location"] == "/login"
code, body, h = http("/api/status")
assert code == 401 and json.loads(body)["error"] == "login"
assert http("/api/cmd", b"NAME Mallory")[0] == 401 and app.pet.name == "Harald"
assert http("/api/backup")[0] == 401
for p in ("/login", "/theme.css", "/lang.js", "/auth.js"):
    assert http(p)[0] == 200, p
assert b'name="password"' in http("/login")[1]
# with the ticket from setting it: in
assert http("/", Cookie=cookie)[0] == 200 and http("/api/status", Cookie=cookie)[0] == 200
# logging in
code, body, h = http("/login", b"password=wrong+guess")
assert code == 401 and b"not the password" in body
code, body, h = http("/login", b"password=open+sesame")
assert code == 303 and h["Location"] == "/" and denauth.COOKIE in h["Set-Cookie"]
cookie2 = h["Set-Cookie"].split(";")[0]
assert http("/api/status", Cookie=cookie2)[0] == 200
# another site can't log in for you (or out)
assert http("/login", b"password=open+sesame", Origin="https://evil.example")[0] == 403
# logging out
code, body, h = http("/logout", b"", Cookie=cookie2)
assert code == 303 and "Max-Age=0" in h["Set-Cookie"]
assert http("/api/status", Cookie=cookie2)[0] == 401 and http("/api/status", Cookie=cookie)[0] == 200

# the phone voice: its own ticket, for its questions and its download (and nothing else)
lines = json.loads(http("/api/cmd", b"DENAUTH", Cookie=cookie)[1])["lines"]
pt = [l for l in lines if l.startswith("phone_token=")][0].split("=", 1)[1]
assert pt and "on=1" in lines
assert http("/api/phone?after=-1")[0] == 401
assert http("/api/phone?after=-1", X_Den_Token=pt)[0] == 200
assert http("/api/status", X_Den_Token=pt)[0] == 401
code, body, h = http(f"/phone/bt_dragon_voice.py?t={pt}")
assert code == 200 and pt.encode() in body
assert http("/phone/bt_dragon_voice.py")[0] == 303

# the control link: from the Pi itself, no password needed (a way back in over SSH) ...
c = socket.create_connection(("127.0.0.1", ctl))
c.sendall(b"STATUS\n")
time.sleep(1)
assert b"name=" in c.recv(65536)
c.close()
# ... from anywhere else, AUTH first
c = socket.create_connection(("127.0.0.1", ctl), source_address=("127.0.0.2", 0))
f = c.makefile("rb")
c.sendall(b"HELLO\n")
assert f.readline().startswith(b"OK BTDRAGON")
c.sendall(b"NAME Mallory\n")
assert f.readline().startswith(b"ERR") and app.pet.name == "Harald"
c.sendall(b"AUTH not it at all\n")
assert f.readline().startswith(b"ERR")
c.sendall(b"AUTH open sesame\n")
assert f.readline() == b"OK\n"
c.sendall(b"DENAUTH\n")
assert f.readline().startswith(b"on=1")
c.close()

# the failsafe, through the Den: off after five minutes, and a note in the diary
http("/api/cmd", b"DENFAILSAFE on", Cookie=cookie)
app.den_auth.s["on_since"] = time.time() - 301
app._den_auth_news()
assert not app.den_auth.enabled() and http("/api/status")[0] == 200
assert any("failsafe" in r[0] for r in app.store.db.execute("SELECT text FROM events").fetchall())
# ... and switching it on again from the Den
assert http("/api/cmd", b"DENAUTHSET on")[0] == 200 and app.den_auth.enabled()
assert http("/api/cmd", b"DENAUTHSET off", Cookie=cookie)[0] == 200 and not app.den_auth.enabled()

print("test_denauth: OK")
