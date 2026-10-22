"""Harald's voice through the phone (which remarks go where, and the long-poll the Termux
helper uses), and a USB GPS receiver (found by itself, through a pretend serial port, and
taking turns sensibly with the phone)."""
import asyncio
import os
import time

from bt_dragon import gps as gpsmod
from bt_dragon.dot import DotLink
from bt_dragon.phonevoice import PhoneVoice, script

# ------------------------------------------------------------------ the phone's voice
async def poll_tests():
    pv = PhoneVoice()
    assert not pv.listening()
    r = await pv.wait(-1)                                  # just started: from now on
    assert r == {"seq": 0, "items": []} and pv.listening()
    pv.push("an old remark")
    r = await pv.wait(-1)
    assert r["items"] == [] and r["seq"] == 1              # nothing from before it started
    t0 = time.monotonic()
    waiter = asyncio.ensure_future(pv.wait(1, timeout=5))
    await asyncio.sleep(0.2)
    pv.push("Look! A new realm!")
    r = await waiter
    assert r["items"] == [{"seq": 2, "text": "Look! A new realm!"}] and time.monotonic() - t0 < 1
    r = await pv.wait(2, timeout=0.3)                      # nothing new: an empty answer
    assert r == {"seq": 2, "items": []}
    r = await pv.wait(99, timeout=0.3)                     # he restarted (numbers started again)
    assert r == {"seq": 2, "items": []}
    pv.items[-1] = (2, "old", time.time() - 500)
    assert (await pv.wait(1, timeout=0.1))["items"] == []  # too old to read out

asyncio.run(poll_tests())
assert "__ADDRESS__" not in script("192.168.43.17:8080") and '"192.168.43.17:8080"' in script("192.168.43.17:8080")


class Obj:
    pass


def link(enabled, phone, backup, connected, listening):
    d = Obj()
    d.s = {"enabled": enabled, "phone": phone, "phone_backup": backup, "chatty": "all"}
    d.connected = d.ready = connected
    d.phone = PhoneVoice()
    if listening:
        d.phone.last_poll = time.time()
    d.queue, d.app = [], Obj()
    d.queue_event = asyncio.Event()
    d.quiet = False
    d.quiet_now = lambda: d.quiet
    for m in ("say", "phone_route", "speaks", "story_on"):
        setattr(d, m, getattr(DotLink, m).__get__(d))
    return d


def heard(d, text="Hello!", force=False):
    d.say(text, force)
    return ([t for _, t, _ in d.phone.items], list(d.queue))


assert heard(link(True, False, True, True, True)) == ([], ["Hello!"])                 # the Dot
assert heard(link(False, True, True, False, True)) == (["Hello!"], [])                # the phone
assert heard(link(True, True, True, True, True)) == (["Hello!"], ["Hello!"])          # both
assert heard(link(False, False, True, False, True)) == ([], [])                       # neither
assert not link(False, False, True, False, True).speaks() and link(False, True, 0, 0, 0).speaks()
d = link(True, False, True, False, True)                    # the Dot's lost: the phone stands in
assert d.phone_route() == "phone" and heard(d) == (["Hello!"], [])
d.connected = d.ready = True                                # back: the Dot again
assert d.phone_route() == "dot"
d = link(True, False, False, False, True)                   # backup switched off
assert d.phone_route() == "dot"
d = link(True, False, True, False, False)                   # no phone listening: nothing to stand in
assert d.phone_route() == "dot"
d = link(False, True, True, False, True)
d.quiet = True
assert heard(d) == ([], []) and heard(d, "Timer done!", force=True) == (["Timer done!"], [])
d.app.napping = True
assert heard(d, "zzz", force=True) == (["Timer done!"], [])   # never during a nap


# ------------------------------------------------------------------ a USB GPS receiver
def nmea(body):
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"${body}*{cs:02X}\r\n".encode()


GGA = nmea("GPGGA,123519,5130.000,N,00007.200,W,1,08,0.9,95.0,M,48.0,M,,")
RMC = nmea("GPRMC,123519,A,5130.000,N,00007.200,W,003.0,084.4,131026,,")


async def usb_tests():
    g = gpsmod.Gps()
    gps_m, gps_s = os.openpty()                             # a pretend receiver...
    other_m, other_s = os.openpty()                         # ...and some other serial gadget
    gps_path, other_path = os.ttyname(gps_s), os.ttyname(other_s)
    stop = asyncio.Event()
    task = asyncio.ensure_future(gpsmod.run_usb(g, "auto", stop, patterns=(other_path, gps_path),
                                                probe_s=0.6, retry_s=0.2))
    for _ in range(40):
        os.write(other_m, b">: help\r\n")                   # not GPS: let go
        os.write(gps_m, GGA + RMC)
        await asyncio.sleep(0.1)
        if g.usb_device:
            break
    assert g.usb_device == gps_path and g.fix and abs(g.fix["lat"] - 51.5) < 1e-6 and abs(g.fix["lon"] + 0.12) < 1e-6
    assert g.source.startswith("usb:") and g.fix["via"] == "usb" and abs(g.fix["speed"] - 3 * 0.514444) < 1e-3
    assert g.state() == "FIX"
    # the phone has a fix too: it wins (prefer = phone), the dongle only fills in
    g.feed_location({"latitude": 51.51, "longitude": -0.13, "time": int(time.time() * 1000)})
    os.write(gps_m, GGA)
    await asyncio.sleep(0.3)
    assert g.fix["via"] == "phone" and abs(g.fix["lat"] - 51.51) < 1e-9
    g._fixed_by["phone"] = time.time() - 30                 # the phone's gone quiet
    os.write(gps_m, GGA)
    await asyncio.sleep(0.3)
    assert g.fix["via"] == "usb"
    g.prefer = "usb"                                        # prefer the dongle: the phone fills in
    g.feed_location({"latitude": 51.52, "longitude": -0.14, "time": int(time.time() * 1000)})
    assert g.fix["via"] == "usb"
    stop.set()
    await asyncio.wait_for(task, 3)
    for fd in (gps_m, gps_s, other_m, other_s):
        os.close(fd)

asyncio.run(usb_tests())
assert gpsmod.usb_candidates(("/nonexistent/*",)) == []
print("phone and usb gps ok")
