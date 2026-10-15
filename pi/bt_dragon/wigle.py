"""
WiGLE export and upload.

WiGLE takes CSV files in its "WigleWifi-1.6" format: one pre-header line describing the
app and device, one column header, then one row per observation (network + where it was
heard + how strongly). Harald stores one observation per network per minute while the
phone's GPS has a fix; WiGLE uses several observations of the same network at different
strengths and places to estimate where it actually is.

Upload: an HTTP multipart POST to https://api.wigle.net/api/v2/file/upload, using your
"API Name" and "API Token" (from wigle.net > Account) as the basic-auth user and password.
"""
import base64
import csv
import io
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid

from . import __version__

log = logging.getLogger("wigle")
URL = "https://api.wigle.net/api/v2/file/upload"
HEADER = ["MAC", "SSID", "AuthMode", "FirstSeen", "Channel", "Frequency", "RSSI", "CurrentLatitude",
          "CurrentLongitude", "AltitudeMeters", "AccuracyMeters", "RCOIs", "MfgrId", "Type"]


def build_csv(rows):
    buf = io.StringIO()
    buf.write(f"WigleWifi-1.6,appRelease=BTDragon-{__version__},model=Raspberry Pi Zero 2 W,"
              f"release=1,device=bt-dragon,display=eink-2.13,board=pi02w,brand=Raspberry Pi,"
              f"star=Sol,body=3,subBody=0\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER)
    for r in rows:
        w.writerow([
            r["bssid"], r["ssid"] or "", r["auth"], time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r["ts"])),
            r["channel"], r["freq"], r["rssi"], f"{r['lat']:.7f}", f"{r['lon']:.7f}",
            f"{r['alt']:.1f}", f"{r['acc']:.1f}", "", "", "WIFI"])
    return buf.getvalue()


def save_csv(text, folder):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, time.strftime("bt-dragon-%Y%m%d-%H%M%S.csv"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    # keep the 20 newest exports
    # (by age, not by name: older ones are named harald-..., newer ones bt-dragon-...)
    files = sorted((p for p in os.listdir(folder) if p.endswith(".csv")),
                   key=lambda p: os.path.getmtime(os.path.join(folder, p)))
    for old in files[:-20]:
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass
    return path


def upload(text, filename, api_name, api_token, donate=False, timeout=60):
    """POST the CSV. Returns (ok, message)."""
    boundary = uuid.uuid4().hex
    body = io.BytesIO()

    def part(name, value, fname=None, ctype=None):
        body.write(f"--{boundary}\r\n".encode())
        disp = f'form-data; name="{name}"' + (f'; filename="{fname}"' if fname else "")
        body.write(f"Content-Disposition: {disp}\r\n".encode())
        if ctype:
            body.write(f"Content-Type: {ctype}\r\n".encode())
        body.write(b"\r\n")
        body.write(value if isinstance(value, bytes) else value.encode())
        body.write(b"\r\n")

    part("file", text.encode("utf-8"), filename, "text/csv")
    part("donate", "true" if donate else "false")
    body.write(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(URL, data=body.getvalue(), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Accept", "application/json")
    auth = base64.b64encode(f"{api_name}:{api_token}".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:200]
        return False, f"HTTP {e.code}: {msg}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, str(e)
    if data.get("success"):
        return True, "uploaded"
    return False, str(data.get("message") or data)[:200]
