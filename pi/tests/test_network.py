"""Backup hotspots: password hashing, priority order, switching and coming back home."""
import asyncio
import os
import tempfile
import tomllib

from bt_dragon import config, wifi
from bt_dragon.config import networks, wpa_psk

TOML = '''[pet]
name = "Harald"

[home_wifi]
ssid = "MyHotspot"
password = "my secret pw"
hash_password = true

[[backup_wifi]]
ssid = "HisHotspot"
password = "his secret pw"   # his phone

[[backup_wifi]]
ssid = "Library_Free"
password = "books1234"

[network]
return_to_better = true
'''
d = tempfile.mkdtemp()
path = os.path.join(d, "bt-dragon.toml")
open(path, "w").write(TOML)
cfg = config.load(path)
assert [s for s, _ in networks(cfg)] == ["MyHotspot", "HisHotspot", "Library_Free"]
config.hash_password_in_file(cfg)
text = open(path).read()
assert "secret pw" not in text and "books1234" not in text, text
again = tomllib.loads(text)
assert again["home_wifi"]["psk_hash"] == wpa_psk("MyHotspot", "my secret pw")
assert again["backup_wifi"][0]["psk_hash"] == wpa_psk("HisHotspot", "his secret pw")   # each with its own name
assert again["backup_wifi"][1]["psk_hash"] == wpa_psk("Library_Free", "books1234")
cfg2 = config.load(path)
assert [k for _, k in networks(cfg2)] == [wpa_psk("MyHotspot", "my secret pw"),
                                          wpa_psk("HisHotspot", "his secret pw"),
                                          wpa_psk("Library_Free", "books1234")]
config.hash_password_in_file(cfg2)                    # running again changes nothing
assert open(path).read() == text

# ---- switching, with a fake dragon and fake NetworkManager
from bt_dragon.app import Dragon

joined = []


async def fake_up(name, timeout=45):
    joined.append(name)
    return True, "ok"


wifi.connect_profile = fake_up


class Fake:
    pass


def make(on):
    f = Fake()
    f.cfg, f.home_ssid, f._switching, f._better_seen, f._join_errors = cfg2, on, False, 0, {}
    f.events = []
    f.event = lambda k, t: f.events.append(t)
    f.pet = Fake()
    f.pet.say = lambda *a, **k: None
    for name in ("network_rank", "switch_to_best", "_maybe_return", "_rejoin_if_lost", "network_info"):
        setattr(f, name, getattr(Dragon, name).__get__(f))
    return f


async def main():
    # out on a walk: only his hotspot is around -> join it
    f = make(None)
    print(await f.switch_to_best({"HisHotspot", "Cafe"}))
    assert joined[-1] == "bt-dragon-backup-1" and f.home_ssid == "HisHotspot"
    # back home: hers appears; one scan isn't enough (could be a blip), two in a row is
    f._maybe_return([{"ssid": "MyHotspot", "rssi": -60}, {"ssid": "HisHotspot", "rssi": -50}])
    await asyncio.sleep(0)
    assert joined == ["bt-dragon-backup-1"]
    f._maybe_return([{"ssid": "MyHotspot", "rssi": -58}, {"ssid": "HisHotspot", "rssi": -50}])
    await asyncio.sleep(0.05)
    assert joined[-1] == "bt-dragon-home" and f.home_ssid == "MyHotspot", joined
    # already on the best: the button just says so
    msg = await f.switch_to_best({"MyHotspot", "HisHotspot"})
    assert "already on MyHotspot" in msg and len(joined) == 2
    # a faint glimpse of a better network doesn't pull him away
    g = make("Library_Free")
    g._maybe_return([{"ssid": "HisHotspot", "rssi": -88}]); g._maybe_return([{"ssid": "HisHotspot", "rssi": -88}])
    await asyncio.sleep(0.05)
    assert len(joined) == 2
    # nothing of ours in range
    assert "none" in (await make(None).switch_to_best({"Cafe"}))

asyncio.run(main())


# ---- his hotspot goes off: he doesn't wait for the network manager, he joins the backup himself
async def lost():
    joined.clear()
    f = make(None)
    aps = [{"ssid": "HisHotspot", "rssi": -55, "security": "wpa2"}]
    await f._rejoin_if_lost(aps, now=1000)                 # just noticed: give it half a minute
    await f._rejoin_if_lost(aps, now=1020)
    assert joined == []
    await f._rejoin_if_lost(aps, now=1031)
    assert joined == ["bt-dragon-backup-1"] and f.home_ssid == "HisHotspot"
    # a failed join is kept for the den, and tried again a minute later (not every scan)
    async def refuse(name, timeout=45):
        joined.append(name)
        return False, "Secrets were required, but not provided"
    wifi.connect_profile = refuse
    g = make(None)
    await g._rejoin_if_lost(aps, now=0)
    await g._rejoin_if_lost(aps, now=40)
    await g._rejoin_if_lost(aps, now=60)
    assert joined[-1] == "bt-dragon-backup-1" and len(joined) == 2, joined
    await g._rejoin_if_lost(aps, now=101)
    assert len(joined) == 3
    g._last_aps = (__import__("time").time(), aps)
    info = {n["ssid"]: n for n in g.network_info()}
    assert info["HisHotspot"]["in_range"] and "Secrets were required" in info["HisHotspot"]["note"], info
    assert not info["MyHotspot"]["in_range"] and info["MyHotspot"]["note"] == ""
    # a WPA3-only hotspot can't take the scrambled key: the den says what to change
    g._last_aps = (__import__("time").time(), [{"ssid": "HisHotspot", "rssi": -55, "security": "wpa3"}])
    assert "only accepts WPA3" in {n["ssid"]: n for n in g.network_info()}["HisHotspot"]["note"]
    wifi.connect_profile = fake_up
    # nothing of ours in range: no attempt
    h = make(None)
    await h._rejoin_if_lost([{"ssid": "Cafe"}], now=0)
    await h._rejoin_if_lost([{"ssid": "Cafe"}], now=100)
    assert len(joined) == 3

asyncio.run(lost())
print("all good")
