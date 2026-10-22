"""The radio stick (untested on real hardware): reading planes' ADS-B broadcasts (checked
against the examples in "The 1090 Megahertz Riddle"), the little radios rtl_433 decodes,
Sky Dragons and Radio Whispers with their points and titles, Gadget Journal points, taking
turns on one stick, and nothing kept that could follow a plane, a car or a home."""
import asyncio
import json
import os
import stat
import tempfile
import time
import urllib.request

from bt_dragon import adsb, config, journal, planes, rtlsdr, scores, server, whispers
from bt_dragon.app import Dragon
from bt_dragon.store import Store

# ---- ADS-B, against the book's examples
ident = adsb.decode("*8D4840D6202CC371C32CE0576098;")
assert ident == {"icao": "4840d6", "tc": 4, "kind": "unknown", "callsign": "KLM1023"}, ident
pos = adsb.decode("*8D40621D58C382D690C8AC2863A7;", ref=(52.258, 3.918))
assert pos["alt_ft"] == 38000 and abs(pos["lat"] - 52.25720) < 1e-4 and abs(pos["lon"] - 3.91937) < 1e-4
vel = adsb.decode("*8D485020994409940838175B284F;")
assert vel["speed_kt"] == 159 and abs(vel["track"] - 182.88) < 0.1
assert adsb.decode("*8D485020994409940838175B284E;") is None          # one bit wrong: the checksum says no
assert adsb.decode("*5D4840D6A1B2C3;") is None and adsb.decode("garbage") is None
assert adsb._nl(0) == 59 and adsb._nl(52.2572) == 36 and adsb._nl(87) == 2 and adsb._nl(88) == 1
assert adsb.decode("*8D40621D58C382D690C8AC2863A7;")["alt_ft"] == 38000   # no reference: height, no position

# ---- callsigns
c = planes.classify_callsign
assert c("EZY12AB") == ("airline", "EZY", "easyJet") and c("BAW15") == ("airline", "BAW", "British Airways")
assert c("XYZ123") == ("airline", "XYZ", "Airline XYZ") and c("GABCD") == ("country", "United Kingdom", "United Kingdom")
assert c("N123AB")[1] == "United States" and c("DABCD")[1] == "Germany" and c("EIABC")[1] == "Ireland"
assert c("CFABC")[1] == "Canada" and c("") is None and c("HELLO1") is None

# ---- the sky: news once, nothing kept that follows a plane
st = Store(os.path.join(tempfile.mkdtemp(), "s.db"))
sky = planes.Sky(st)
t0 = time.time()
news = sky.heard("*8D4840D6202CC371C32CE0576098;", t0)
assert ("plane",) in news and ("kind", "unknown") in news and ("airline", "KLM", "KLM") in news
assert sky.heard("*8D4840D6202CC371C32CE0576098;", t0 + 5) == []        # the same plane: once a day
assert sky.heard("*8D40621D58C382D690C8AC2863A7;", t0 + 6, ref=(52.2, 3.9)) == [("plane",)]
now = sky.now(t0 + 7)
assert len(now) == 2 and now[0]["km"] is not None and now[0]["alt_ft"] == 38000
assert sky.now(t0 + 500) == []
sky.heard("*8D485020994409940838175B284F;", t0 + 500)
assert "4840d6" not in sky.live                                          # forgotten after two minutes
st.flush()
dump = "\n".join(str(tuple(r)) for t in ("finds", "kv", "events") for r in st.db.execute(f"SELECT * FROM {t}"))
assert "4840d6" not in dump.lower() and "40621d" not in dump.lower()   # no plane's address is ever stored
assert st.get("sky_total") == 3
assert planes.score(st) == scores.POINTS["Common"] + planes.AIRLINE_POINTS + 3 * planes.PLANE_POINTS

# ---- the little radios
k = whispers.kind_of
assert k({"model": "Fineoffset-WH25", "temperature_C": 9, "humidity": 80, "pressure_hPa": 1000}) == "weather"
assert k({"model": "Toyota", "type": "TPMS", "pressure_kPa": 230}) == "tpms"
assert k({"model": "Efergy-e2CT", "power_W": 300}) == "energy" and k({"model": "Byron-BY", "button": 1}) == "remote"
assert k({"model": "ERT-SCM", "consumption_data": 1}) == "meter" and k({"model": "X", "battery_ok": 1}) == "other"
assert k({"model": "Acurite-6045M", "strike_count": 3, "temperature_C": 3}) == "lightning"
wh = whispers.Whispers(st)
tyre = '{"model": "Schrader-EG53MA4", "type": "TPMS", "id": "f00d42", "pressure_kPa": 230, "temperature_C": 21}'
news = wh.heard(tyre, t0)
assert ("device", "tpms") in news and ("kind", "tpms") in news and ("model", "Schrader-EG53MA4", "tpms") in news
assert wh.heard(tyre, t0 + 30) == [] and wh.heard("not json", t0) == [] and wh.heard("{}", t0) == []
other_tyre = tyre.replace("f00d42", "beef01")
assert wh.heard(other_tyre, t0 + 40) == [("device", "tpms")]            # another car: counted, nothing new
st.flush()
dump = "\n".join(str(tuple(r)) for t in ("finds", "kv", "events") for r in st.db.execute(f"SELECT * FROM {t}"))
assert "f00d42" not in dump and "beef01" not in dump and "230" not in dump   # no IDs, no readings
assert whispers.score(st) == scores.POINTS["Common"] + whispers.MODEL_POINTS + 2 * whispers.DEVICE_POINTS

# ---- titles
assert scores.title(scores.SKY_TITLES, 0) == "Grounded Gazer" and scores.title(scores.WHISPER_TITLES, 3000) == \
    "Heimdall's Apprentice" and scores.next_title(scores.JOURNAL_TITLES, 0) == (100, "Byte-Biting Bairn")
assert scores.new_titles(st, "t", scores.SKY_TITLES, 350) == ["Contrail Chaser", "Wing-Watching Wanderer"]
assert scores.new_titles(st, "t", scores.SKY_TITLES, 400) == []
for titles in (scores.JOURNAL_TITLES, scores.SKY_TITLES, scores.WHISPER_TITLES):
    assert [t[0] for t in titles] == sorted(t[0] for t in titles) and titles[0][0] == 0
    assert len({t[1] for t in titles}) == len(titles)

# ---- the app: points in the diary, titles on his screen, the Gadget Journal
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
app.on_radio("planes", "*8D4840D6202CC371C32CE0576098;")
app.on_radio("sensors", tyre)
texts = [e["text"] for e in app.store.events(20)]
assert any(t.startswith("New sky dragon: Unannounced aircraft +20") for t in texts)
assert any(t.startswith("New airline in the sky: KLM (KLM) +25") for t in texts)
assert any(t.startswith("New radio whisper: Tyre pressure sensor +20") for t in texts)
app.store.put("sky_total", 400)
app.on_radio("planes", "*8D485020994409940838175B284F;")
assert "NEW SKY DRAGON TITLE" in app.pet.message or any("New Sky Dragon title" in e["text"] for e in app.store.events(10))
app.napping = True
assert app.on_radio("sensors", tyre.replace("Schrader", "Other")) is None and \
    not any("Other" in e["text"] for e in app.store.events(10))            # nothing heard in a nap
app.napping = False
# Gadget Journal points
assert journal.points_for("Tile tracker") == scores.POINTS["Uncommon"] and journal.points_for("Garmin device") == 10 \
    and journal.points_for("JBL Flip #") == scores.POINTS["Common"] + 10
app._eat_species("tile-tracker", "Tile tracker", "tracker", time.time())
assert any(e["text"] == f"New type: Tile tracker +{scores.POINTS['Uncommon']} Gadget Journal points."
           for e in app.store.events(5))
app._eat_species("jbl-flip", "JBL Flip #", "named", time.time())
assert app.journal_score(fresh=True) == scores.POINTS["Uncommon"] + scores.POINTS["Common"] + journal.FIELD_POINTS   # (a speaker)
assert app.view()["journal"]["points"] == app.journal_score()
lines = asyncio.run(app.command("RADIO"))
d = dict(l.split("=", 1) for l in lines[:-1])
assert d["mode"] == "both" and json.loads(d["sky"])["points"] > 0 and json.loads(d["planes_now"])
assert asyncio.run(app.command("RADIOSET planes")) == ["OK"] and asyncio.run(app.command("RADIOSET radar"))[0].startswith("ERR")
assert rtlsdr.sensor_command("US")[-3] == "915M" and rtlsdr.sensor_command("GB")[-3] == "868.3M"

# ---- one stick, taking turns: fake programs
bin_ = tempfile.mkdtemp()


def fake(name, body):
    p = os.path.join(bin_, name)
    with open(p, "w") as f:
        f.write("#!/bin/sh\n" + body)
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)


fake("rtl_adsb", 'echo "*8D4840D6202CC371C32CE0576098;"\nexec sleep 30\n')
fake("rtl_433", 'echo \'{"model": "Fineoffset-WH25", "temperature_C": 9}\'\nexec sleep 30\n')
os.environ["PATH"] = bin_ + os.pathsep + os.environ["PATH"]
got = []
stick = rtlsdr.RadioStick(Store(os.path.join(tempfile.mkdtemp(), "r.db")), lambda w, l: got.append((w, l)))
rtlsdr.TURN_S = 1


async def turns():
    stop = asyncio.Event()
    task = asyncio.ensure_future(stick.run(stop))
    await asyncio.sleep(4)
    stop.set()
    await asyncio.wait_for(task, 15)
asyncio.run(turns())
whats = [w for w, _ in got]
assert "planes" in whats and "sensors" in whats and stick.found, got           # one, then the other
fake("rtl_adsb", 'echo "No supported devices found." >&2\nexit 1\n')
stick2 = rtlsdr.RadioStick(Store(os.path.join(tempfile.mkdtemp(), "q.db")), lambda w, l: None)
stick2.set_mode("planes")


async def none():
    stop = asyncio.Event()
    task = asyncio.ensure_future(stick2.run(stop))
    await asyncio.sleep(1.5)
    stop.set()
    await asyncio.wait_for(task, 15)
asyncio.run(none())
assert stick2.found is False and "No radio stick" in stick2.status

# ---- the pages
import socket  # noqa: E402
import threading  # noqa: E402
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
app.cfg["link"]["web_port"] = port
threading.Thread(target=lambda: asyncio.run(server.web_server(app)), daemon=True).start()
time.sleep(3)
for path, title in (("/sky", "Sky Dragons"), ("/whispers", "Radio Whispers"), ("/journal", "Gadget Journal")):
    html = urllib.request.urlopen(f"http://127.0.0.1:{port}{path}").read().decode()
    assert title in html and '"score"' in html and "__DATA__" not in html, path
with open("bt_dragon/den.html", encoding="utf-8") as f:
    den = f.read()
assert 'href="/sky"' in den and 'href="/whispers"' in den and 'id="rdMode"' in den and 'id="jnLine"' in den
print("radio ok")
