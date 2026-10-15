#!/data/data/com.termux/files/usr/bin/python
"""
Harald's voice on this phone. Runs in Termux (from F-Droid) with the Termux:API app.

  pkg install -y python termux-api
  python bt_dragon_voice.py   (or harald_voice.py, if that's the name you saved it under)

It keeps asking Harald, over your hotspot, whether he has anything to say, and reads each
remark out with the phone's own text-to-speech voice, even with the screen off. Stop it
with Ctrl+C (Volume Down + C on the Termux keyboard), or close Termux's notification.

If Harald's address changes, it finds him again by himself: dragons announce themselves on
the hotspot every few seconds.
"""
import json
import socket
import subprocess
import sys
import time
import urllib.request

ADDRESS = "__ADDRESS__"          # "ip:port" of Harald's den, filled in when downloaded
DISCOVERY_PORT = 5150


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


def find_harald(wait_s=20):
    """Listen for a dragon announcing itself on the hotspot: 'BTDRAGON 1 port=... web=... name=...'."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.settimeout(wait_s)
    try:
        s.bind(("", DISCOVERY_PORT))
        data, (ip, _) = s.recvfrom(512)
        fields = dict(f.split("=", 1) for f in data.decode(errors="replace").split()[2:] if "=" in f)
        return f"{ip}:{fields.get('web', '8080')}"
    except OSError:
        return None
    finally:
        s.close()


def main():
    address = ADDRESS
    subprocess.run(["termux-wake-lock"], check=False)     # keep running with the screen off
    print(f"Listening for your dragon at {address}. Leave Termux running; the screen can go off.")
    after, fails, said_hello = -1, 0, False
    while True:
        try:
            with urllib.request.urlopen(f"http://{address}/api/phone?after={after}", timeout=75) as r:
                reply = json.load(r)
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
        except Exception as e:
            fails += 1
            if fails in (1, 10):
                print(f"Can't reach your dragon ({e}); trying again...")
            if fails % 3 == 0:
                found = find_harald()
                if found and found != address:
                    print(f"Found your dragon at {found}")
                    address, after = found, -1
            time.sleep(5)
    subprocess.run(["termux-wake-unlock"], check=False)


if __name__ == "__main__":
    main()
