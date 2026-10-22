"""
Settings live in bt-dragon.toml on the SD card's boot partition, so they can be edited
from any computer by putting the card in a reader.

The hotspot password is swapped for a hashed key on first start. WPA2 networks don't
actually use your password on the air: both sides first stretch it into a 256-bit key
with PBKDF2-HMAC-SHA1 (4096 rounds, salted with the network name). Storing that key
instead of the password still lets the Pi join, but someone reading the card can't
recover the original password to try on your other accounts.
"""
import copy
import hashlib
import logging
import os
import re
import tomllib

log = logging.getLogger("config")

CONFIG_PATHS = ["/boot/firmware/bt-dragon.toml", "/boot/bt-dragon.toml"]

DEFAULTS = {
    "pet": {"name": "Harald", "hunger_minutes": 150},
    "home_wifi": {"ssid": "", "password": "", "psk_hash": "", "hash_password": True},
    "backup_wifi": [],         # [{ssid, password}], in order of preference
    "network": {"return_to_better": True},
    "wigle": {"api_name": "", "api_token": "", "auto_upload": True, "upload_every_minutes": 240,
              "min_batch": 50, "donate": False},
    "gps": {"source": "auto", "udp_port": 29998, "tcp_host": "", "tcp_port": 11123, "usb": "auto",
            "prefer": "phone"},
    "own_devices": {},
    "display": {"enabled": True, "model": "V4", "rotate": 180, "full_refresh_minutes": 20,
                "min_seconds_between_updates": 12},
    "link": {"port": 5151, "discovery_port": 5150, "web_port": 8080},
    "privacy": {"skip_nomap": True, "upload_hidden": False},
    "trackers": {"alert_after_minutes": 30, "min_moved_meters": 250},
    "friends": {"beacon": True},
    "diary": {"files": True, "keep_days": 90, "location": True},
    "sky": {"lands": True, "stars": True, "barometer": True, "landmarks": True, "greens": True, "libraries": True, "moon": True},
    "activity": {"enabled": True, "steps_host": "", "steps_port": 8080, "stride_m": 0.75},
    "dot": {"enabled": True, "address": "", "networks": [], "voice": "", "audio_device": 23, "amp_on_after": 0.3,
            "recap_after_minutes": 30,
            "stop_services": ["puffin", "ahe", "oobed_on_boot", "commsd"]},
    "data_dir": "/var/lib/bt-dragon",
}


def wpa_psk(ssid: str, password: str) -> str:
    """The WPA2 pre-shared key, exactly as wpa_passphrase computes it."""
    return hashlib.pbkdf2_hmac("sha1", password.encode(), ssid.encode(), 4096, 32).hex()


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def find_config(explicit=None):
    if explicit:
        return explicit
    for p in CONFIG_PATHS:
        if os.path.exists(p):
            return p
    return None


def load(path=None):
    path = find_config(path)
    data = {}
    if path:
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as e:
            log.error("could not read %s: %s (using defaults)", path, e)
    # older config files spelled this setting the British way
    tr = data.get("trackers", {})
    if "min_moved_metres" in tr and "min_moved_meters" not in tr:
        tr["min_moved_meters"] = tr.pop("min_moved_metres")
    cfg = _merge(DEFAULTS, data)
    cfg["_path"] = path
    # own_devices: normalise MACs to upper case
    cfg["own_devices"] = {k.upper(): str(v) for k, v in cfg["own_devices"].items()}
    return cfg


def hash_password_in_file(cfg):
    """
    Replace each plain hotspot password in the settings file with its hashed WPA2 key
    (psk_hash = "..."): the main hotspot under [home_wifi] and every [[backup_wifi]].
    The key is tied to the network name, so each is hashed with its own name.
    """
    path = cfg.get("_path")
    if not path or not cfg["home_wifi"].get("hash_password", True):
        return
    entries = [cfg["home_wifi"]] + list(cfg.get("backup_wifi") or [])
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError as e:
        log.warning("could not read %s: %s", path, e)
        return
    current, backups, changed = None, -1, False
    for i, line in enumerate(lines):
        head = line.strip()
        if head.startswith("[[backup_wifi]]"):
            backups += 1
            current = 1 + backups
            continue
        if head.startswith("["):
            current = 0 if head.startswith("[home_wifi]") else None
            continue
        if current is None or current >= len(entries):
            continue
        m = re.match(r'^(\s*)password\s*=\s*"(.*)"\s*(#.*)?$', line)
        e = entries[current]
        if m and m.group(2) and e.get("ssid"):
            psk = wpa_psk(e["ssid"], m.group(2))
            lines[i] = (f'{m.group(1)}# password replaced by its WPA2 key on first start\n'
                        f'{m.group(1)}psk_hash = "{psk}"')
            e["psk_hash"], e["password"] = psk, ""
            changed = True
    if not changed:
        return
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        log.info("hotspot passwords hashed in %s", path)
    except OSError as e:
        log.warning("could not hash passwords in %s: %s", path, e)


def network_secret(entry):
    """What NetworkManager needs: the hashed key, or the plain password for WPA3."""
    return entry.get("psk_hash") or entry.get("password") or ""


def networks(cfg):
    """Every network he may connect to, best first: [(ssid, secret)]."""
    out = [(cfg["home_wifi"]["ssid"], network_secret(cfg["home_wifi"]))]
    for e in cfg.get("backup_wifi") or []:
        if isinstance(e, dict) and e.get("ssid"):
            out.append((str(e["ssid"]), network_secret(e)))
    return [(s, k) for s, k in out if s]

