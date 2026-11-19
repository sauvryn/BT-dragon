#!/data/data/com.termux/files/usr/bin/python
"""
Harald's voice on this phone. Runs in Termux (from F-Droid) with the Termux:API app.

  pkg install -y python termux-api
  python bt_dragon_voice.py   (or harald_voice.py, if that's the name you saved it under)

It keeps asking Harald, over your hotspot, whether he has anything to say, and reads each
remark out with the phone's own text-to-speech voice, even with the screen off. Stop it
with Ctrl+C (Volume Down + C on the Termux keyboard), or close Termux's notification.

If Harald's address changes, it finds him again by himself. A phone hotspot picks a new
range of addresses each time it's switched on (Android 11 and later do), so the Pi's
address changes too. It tries, in turn:
  1. his name on the network (bt-dragon.local), which newer phones can look up;
  2. asking every address on the hotspot "BTDRAGON? 1", and he answers;
  3. listening for the line he announces himself with every few seconds.
While it runs, its notification has an "Open the Den" button that always goes to his
current address: a bookmark that keeps up.
"""
import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ADDRESS = "__ADDRESS__"          # "ip:port" of Harald's den, filled in when downloaded
TOKEN = "__TOKEN__"              # its ticket, for when the Den has a password (filled in, too)
HOSTNAME = "__HOSTNAME__"        # the Pi's name on the network (bt-dragon), filled in too
DISCOVERY_PORT = 5150
NOTE_ID = "bt-dragon-den"


def say(text, rate=1.0, pitch=1.0):
    # the "music" stream: the media volume, and Bluetooth earphones if they're connected.
    # Speed and pitch follow "Voice" in the den, on top of the phone's own settings.
    try:
        subprocess.run(["termux-tts-speak", "-s", "MUSIC", "-r", f"{rate:.2f}", "-p", f"{pitch:.2f}", text],
                       timeout=120)
    except FileNotFoundError:
        print("termux-tts-speak is missing: run  pkg install termux-api  and install the Termux:API app")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        pass


def notify(address, name="Harald"):
    """A notification with an "Open the Den" button, kept up to date with his address."""
    url = f"http://{address}"
    try:
        subprocess.run(["termux-notification", "--id", NOTE_ID, "--ongoing", "--priority", "low",
                        "--title", f"{name}'s voice is on", "--content", f"The Den: {url}",
                        "--action", f"termux-open-url {url}",
                        "--button1", "Open the Den", "--button1-action", f"termux-open-url {url}"],
                       timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def unnotify():
    try:
        subprocess.run(["termux-notification-remove", NOTE_ID], timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _port(address):
    return address.rsplit(":", 1)[1] if ":" in address else "8080"


def by_name(address):
    """1. bt-dragon.local, if this phone can look it up (Android 12 and later often can)."""
    if not HOSTNAME or HOSTNAME.startswith("__"):
        return None
    try:
        ip = socket.getaddrinfo(f"{HOSTNAME}.local", None, socket.AF_INET)[0][4][0]
    except (OSError, IndexError):
        return None
    return f"{ip}:{_port(address)}"


def local_nets():
    """This phone's own IPv4 addresses on the hotspot (and Wi-Fi): [(its address, prefix length, broadcast)]."""
    out = []
    try:
        text = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        text = ""
    for m in re.finditer(r"\binet (\d+\.\d+\.\d+\.\d+)/(\d+)(?: brd (\d+\.\d+\.\d+\.\d+))?", text):
        ip, plen, brd = m.group(1), int(m.group(2)), m.group(3)
        a = [int(x) for x in ip.split(".")]
        private = a[0] == 10 or (a[0] == 172 and 16 <= a[1] <= 31) or (a[0] == 192 and a[1] == 168)
        if private and plen >= 16:
            out.append((ip, plen, brd))
    return out


def ask(wait_s=3.0):
    """2. Ask every address on the hotspot "BTDRAGON? 1": the dragon answers with its line.
    Returns ("ip:web port", name) or None."""
    nets = local_nets()
    if not nets:
        return None
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.bind(("", 0))
        q = b"BTDRAGON? 1\n"
        for ip, plen, brd in nets:
            if brd:
                try:
                    s.sendto(q, (brd, DISCOVERY_PORT))
                except OSError:
                    pass
            base = ip.rsplit(".", 1)[0]          # (the /24 it's in: phone hotspots hand out a /24 or smaller)
            for n in range(1, 255):
                peer = f"{base}.{n}"
                if peer != ip:
                    try:
                        s.sendto(q, (peer, DISCOVERY_PORT))
                    except OSError:
                        pass
        s.settimeout(wait_s)
        end = time.time() + wait_s
        while time.time() < end:
            try:
                data, (ip, _) = s.recvfrom(512)
            except OSError:
                break
            line = data.decode(errors="replace")
            if line.startswith("BTDRAGON 1 "):
                return _parse(line, ip)
    except OSError:
        return None
    finally:
        s.close()
    return None


def _parse(line, ip):
    head, _, name = line.strip().partition(" name=")
    fields = dict(f.split("=", 1) for f in head.split()[2:] if "=" in f)
    return f"{ip}:{fields.get('web', '8080')}", (name or "Harald")


def listen(wait_s=20):
    """3. Listen for a dragon announcing itself on the hotspot: 'BTDRAGON 1 port=... web=... name=...'."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.settimeout(wait_s)
    try:
        s.bind(("", DISCOVERY_PORT))
        end = time.time() + wait_s
        while time.time() < end:
            data, (ip, _) = s.recvfrom(512)
            line = data.decode(errors="replace")
            if line.startswith("BTDRAGON 1 "):
                return _parse(line, ip)
    except OSError:
        return None
    finally:
        s.close()
    return None


def find_dragon(address):
    """Where he is now, the quickest way first. ("ip:port", name or None) or None."""
    a = by_name(address)
    if a and a != address:
        return a, None
    return ask() or listen()


def main():
    address, name = ADDRESS, "Harald"
    subprocess.run(["termux-wake-lock"], check=False)     # keep running with the screen off
    print(f"Listening for your dragon at {address}. Leave Termux running; the screen can go off.")
    notify(address, name)
    after, fails, said_hello = -1, 0, False
    try:
        while True:
            try:
                req = urllib.request.Request(f"http://{address}/api/phone?after={after}",
                                             headers={"X-Den-Token": TOKEN} if TOKEN and not TOKEN.startswith("__") else {})
                with urllib.request.urlopen(req, timeout=75) as r:
                    reply = json.load(r)
                if fails:
                    notify(address, name)
                fails = 0
                if not said_hello:
                    say("Hello! I'll talk through your phone now.", reply.get("rate", 1.0), reply.get("pitch", 1.0))
                    said_hello = True
                for item in reply.get("items", []):
                    print(time.strftime("%H:%M"), item["text"])
                    say(item["text"], reply.get("rate", 1.0), reply.get("pitch", 1.0))
                after = reply.get("seq", after)
            except KeyboardInterrupt:
                break
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    print("The Den has a (new) password: download this script again from the Den.")
                    break
                fails += 1
                time.sleep(5)
            except Exception as e:
                fails += 1
                if fails in (1, 10):
                    print(f"Can't reach your dragon ({e}); looking for him...")
                found = find_dragon(address)
                if found and found[0] != address:
                    address, after = found[0], -1
                    name = found[1] or name
                    print(f"Found your dragon at {address}")
                    notify(address, name)
                    continue
                time.sleep(5)
    except KeyboardInterrupt:
        pass
    unnotify()
    subprocess.run(["termux-wake-unlock"], check=False)


if __name__ == "__main__":
    main()
