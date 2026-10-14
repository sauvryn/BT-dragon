"""
Wi-Fi: Harald's treats, and the link home.

Every access point broadcasts a "beacon" about ten times a second: its BSSID (the radio's
MAC address), its network name (SSID), the channel, and which security it supports. A
normal Wi-Fi client collects these when it scans for networks, which is all Harald does.
The Pi stays a regular client the whole time (no monitor mode, nothing transmitted at
other people's networks), and it can stay connected to your hotspot while scanning: the
radio hops to each channel for a few tens of milliseconds and comes back.

The Pi Zero 2 W radio only does 2.4 GHz, so 5 GHz networks are invisible to Harald.
"""
import asyncio
import logging
import re
import shutil
import socket
import subprocess

log = logging.getLogger("wifi")
IFACE = "wlan0"


def freq_to_channel(freq):
    f = int(freq)
    if f == 2484:
        return 14
    if 2412 <= f <= 2472:
        return (f - 2407) // 5
    if 5000 <= f <= 5900:
        return (f - 5000) // 5
    if 5955 <= f <= 7115:
        return (f - 5950) // 5
    return 0


def _unescape_ssid(s):
    """iw prints non-printable SSID bytes as \\xNN."""
    raw = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)
    try:
        raw = raw.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return raw.replace("\x00", "").strip()  # hidden networks often send a name of zero bytes


def parse_iw_scan(text):
    """Parse `iw dev wlan0 scan` output into a list of dicts."""
    aps, cur, section = [], None, None
    for line in text.splitlines():
        m = re.match(r"^BSS ([0-9a-fA-F:]{17})", line)
        if m:
            cur = {"bssid": m.group(1).upper(), "ssid": "", "freq": 0, "rssi": -100,
                   "privacy": False, "rsn": None, "wpa": None, "wps": False, "channel": 0,
                   "associated": "associated" in line}
            aps.append(cur)
            section = None
            continue
        if cur is None:
            continue
        s = line.strip()
        if line.startswith("\t") and not line.startswith("\t\t") and not line.startswith("\t *"):
            section = None
        if s.startswith("freq:"):
            cur["freq"] = int(float(s.split()[1]))
        elif s.startswith("last seen:"):
            # how old this sighting is: a cached scan can still list a network that went
            # quiet a minute ago, so anything deciding "it's on the air" checks this
            try:
                cur["age_ms"] = int(s.split()[2])
            except (IndexError, ValueError):
                pass
        elif s.startswith("signal:"):
            cur["rssi"] = int(float(s.split()[1]))
        elif s.startswith("SSID:"):
            cur["ssid"] = _unescape_ssid(line.split("SSID:", 1)[1].strip())
        elif s.startswith("capability:"):
            cur["privacy"] = "Privacy" in s
        elif s.startswith("DS Parameter set: channel"):
            cur["channel"] = int(s.split()[-1])
        elif s.startswith("RSN:"):
            section = "rsn"
            cur["rsn"] = {"akm": [], "pair": []}
        elif s.startswith("WPA:"):
            section = "wpa"
            cur["wpa"] = {"akm": [], "pair": []}
        elif s.startswith("WPS:"):
            cur["wps"] = True
            section = None
        elif section and s.startswith("* Pairwise ciphers:"):
            cur[section]["pair"] = s.split(":", 1)[1].split()
        elif section and s.startswith("* Authentication suites:"):
            cur[section]["akm"] = s.split(":", 1)[1].split()
    out = []
    for a in aps:
        if not a["channel"] and a["freq"]:
            a["channel"] = freq_to_channel(a["freq"])
        a["auth"] = auth_string(a)
        a["security"] = security_tier(a)
        out.append(a)
    return out


def auth_string(a):
    """WiGLE/Android-style capabilities, e.g. [WPA2-PSK-CCMP][ESS]."""
    parts = []
    for section, prefix in (("wpa", "WPA"), ("rsn", "WPA2")):
        info = a.get(section)
        if not info:
            continue
        ciphers = "+".join(c.replace("TKIP", "TKIP").replace("CCMP", "CCMP") for c in info["pair"]) or "CCMP"
        for akm in info["akm"] or ["PSK"]:
            if akm == "SAE":
                parts.append(f"[WPA3-SAE-{ciphers}]")
            elif akm in ("PSK", "PSK/SHA-256"):
                parts.append(f"[{prefix}-PSK-{ciphers}]")
            elif "802.1X" in akm or akm.startswith("IEEE"):
                parts.append(f"[{prefix}-EAP-{ciphers}]")
            elif akm == "OWE":
                parts.append(f"[OWE-{ciphers}]")
    if not parts and a.get("privacy"):
        parts.append("[WEP]")
    if a.get("wps"):
        parts.append("[WPS]")
    parts.append("[ESS]")
    return "".join(parts)


def security_tier(a):
    auth = a.get("auth") or auth_string(a)
    if "WEP" in auth:
        return "wep"
    if "PSK" not in auth and "SAE" not in auth and "EAP" not in auth and "OWE" not in auth:
        return "open"
    if "SAE" in auth and "PSK" not in auth:
        return "wpa3"
    if "EAP" in auth:
        return "enterprise"
    return "wpa2"


class WifiScanner:
    def __init__(self, iface=IFACE):
        self.iface = iface

    async def _run(self, *args, timeout=20):
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return 1, "", "timeout"
        return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")

    async def scan(self):
        """Ask for a fresh scan; if the radio is busy, read the results NetworkManager already has."""
        rc, out, err = await self._run("iw", "dev", self.iface, "scan")
        if rc != 0:
            rc, out, err = await self._run("iw", "dev", self.iface, "scan", "dump")
        if rc != 0:
            log.debug("scan failed: %s", err.strip())
            return []
        return parse_iw_scan(out)

    async def link(self):
        """Return the SSID we're connected to, or None."""
        rc, out, _ = await self._run("iw", "dev", self.iface, "link", timeout=5)
        if rc != 0 or "Not connected" in out:
            return None
        m = re.search(r"SSID: (.*)", out)
        return _unescape_ssid(m.group(1).strip()) if m else None


def internet_ok(host="api.wigle.net", port=443, timeout=4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def my_ip():
    """Harald's own address on the hotspot (no packets are actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((gateway_ip() or "8.8.8.8", 9))
            return s.getsockname()[0]
    except OSError:
        return None


def gateway_ip():
    """The hotspot phone's address: the default route's gateway."""
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                p = line.split()
                if p[1] == "00000000" and int(p[3], 16) & 2:
                    g = int(p[2], 16)
                    return socket.inet_ntoa(g.to_bytes(4, "little"))
    except OSError:
        pass
    return None


def profile_name(rank):
    return "bt-dragon-home" if rank == 0 else f"bt-dragon-backup-{rank}"


def ensure_profiles(networks):
    """
    Make sure NetworkManager knows every network Harald may use, in priority order:
    networks = [(ssid, secret), ...], first = the main hotspot. NetworkManager connects to
    the highest-priority one it can see whenever it has to (at startup, or after losing
    the connection). Profiles for backups that have since been removed are deleted.
    """
    if not shutil.which("nmcli"):
        return False
    base = ["nmcli", "connection"]
    ok = True
    keep = set()
    for rank, (ssid, secret) in enumerate(networks):
        if not (ssid and secret):
            continue
        name = profile_name(rank)
        keep.add(name)
        prio = "50" if rank == 0 else str(max(1, 40 - rank))
        exists = subprocess.run(base + ["show", name], capture_output=True).returncode == 0
        settings = ["802-11-wireless.ssid", ssid, "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", secret,
                    "connection.autoconnect", "yes", "connection.autoconnect-priority", prio]
        if exists:
            r = subprocess.run(base + ["modify", name] + settings, capture_output=True, text=True)
        else:
            r = subprocess.run(base + ["add", "type", "wifi", "con-name", name, "ifname", IFACE] + settings,
                               capture_output=True, text=True)
        if r.returncode != 0:
            log.warning("could not set up network profile %s: %s", name, r.stderr.strip())
            ok = False
        else:
            log.info("network profile '%s' ready for %s (priority %s)", name, ssid, prio)
    r = subprocess.run(base + ["show"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        name = line.split()[0] if line.split() else ""
        if name.startswith("bt-dragon-backup-") and name not in keep:
            subprocess.run(base + ["delete", name], capture_output=True)
            log.info("removed old backup network profile %s", name)
    return ok


async def connect_profile(name, timeout=45):
    """Switch to one of our saved networks now. Returns (ok, message)."""
    proc = await asyncio.create_subprocess_exec(
        "nmcli", "--wait", str(timeout), "connection", "up", name,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout + 10)
    except asyncio.TimeoutError:
        proc.kill()
        return False, "timed out"
    return proc.returncode == 0, (err or out).decode(errors="replace").strip()


RESCUE_PROFILE = "bt-dragon-dot-rescue"


def ensure_rescue_profile(ssid, address="10.201.126.250/28"):
    """A NetworkManager profile for the Echo Dot's own setup network (open, no password).
    The Dot hands out no addresses there, so Harald takes a fixed one in its range. It never
    becomes the default route (nothing else goes through it) and never joins by itself."""
    if not shutil.which("nmcli"):
        return False
    base = ["nmcli", "connection"]
    settings = ["802-11-wireless.ssid", ssid, "ipv4.method", "manual", "ipv4.addresses", address,
                "ipv4.never-default", "yes", "ipv6.method", "ignore",
                "connection.autoconnect", "no"]
    exists = subprocess.run(base + ["show", RESCUE_PROFILE], capture_output=True).returncode == 0
    if exists:
        r = subprocess.run(base + ["modify", RESCUE_PROFILE] + settings, capture_output=True, text=True)
    else:
        r = subprocess.run(base + ["add", "type", "wifi", "con-name", RESCUE_PROFILE, "ifname", IFACE] + settings,
                           capture_output=True, text=True)
    if r.returncode != 0:
        log.warning("could not set up the Dot rescue profile: %s", r.stderr.strip())
    return r.returncode == 0
