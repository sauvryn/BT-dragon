"""Mini backups: made from a live database, checked, and put back (from the den or from
the boot partition), with what was there kept aside."""
import asyncio
import io
import json
import os
import sqlite3
import tarfile
import tempfile

tmp = tempfile.mkdtemp()
os.environ["HOME"] = os.path.join(tmp, "home")          # where the Pi's adb key lives
os.makedirs(os.path.join(tmp, "home", ".android"))
open(os.path.join(tmp, "home", ".android", "adbkey"), "w").write("PRIVATE KEY")
open(os.path.join(tmp, "home", ".android", "adbkey.pub"), "w").write("PUBLIC KEY")

from bt_dragon import backup, server  # noqa: E402
from bt_dragon.store import Store  # noqa: E402

data = os.path.join(tmp, "data")
boot = os.path.join(tmp, "boot")
os.makedirs(os.path.join(data, "diary"))
os.makedirs(os.path.join(data, "wigle"))
os.makedirs(boot)
toml = os.path.join(boot, "bt-dragon.toml")
open(toml, "w").write('[home_wifi]\nssid = "MyHotspot"\n')
open(os.path.join(data, "diary", "2026-10-13.csv"), "w").write("time,what\n10:00,ate a snack\n")
open(os.path.join(data, "wigle", "upload-1.csv"), "w").write("WigleWifi-1.4\n")
os.makedirs(os.path.join(boot, "harald-art"))
open(os.path.join(boot, "harald-art", "happy.png"), "wb").write(b"\x89PNG fake picture")
store = Store(os.path.join(data, "dragon.db"))
store.put("pet", {"name": "Harald", "xp": 1234})
store.event("level", "Harald reached level 7")

# made while he's running (his own connection still open, changes still in the side file)
blob = backup.make(data, toml, "Harald", now=1791900000)
assert len(blob) < 50000
with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
    names = sorted(t.getnames())
    assert names == ["adb/adbkey", "adb/adbkey.pub", "art/happy.png", "bt-dragon.toml", "diary/2026-10-13.csv",
                     "dragon.db", "manifest.json", "wigle/upload-1.csv"], names
    man = json.loads(t.extractfile("manifest.json").read())
    snap = t.extractfile("dragon.db").read()
assert man["kind"] == "bt-dragon-backup" and man["made"] == 1791900000 and man["name"] == "Harald"
p = os.path.join(tmp, "snap.db")
open(p, "wb").write(snap)
assert json.loads(sqlite3.connect(p).execute("SELECT value FROM kv WHERE key='pet'").fetchone()[0])["xp"] == 1234
assert backup.filename(1791900000).startswith("harald-backup-") and backup.filename().endswith(".tar.gz")
good = os.path.join(tmp, "good.tar.gz")
open(good, "wb").write(blob)
files, m = backup.read(good)
assert m["made"] == 1791900000 and files["bt-dragon.toml"].startswith(b"[home_wifi]")

# things change after the backup...
store.put("pet", {"name": "Harald", "xp": 9999})
store.db.close()
open(toml, "w").write('[home_wifi]\nssid = "NewHotspot"\n')
open(os.path.join(data, "diary", "2026-10-13.csv"), "w").write("changed\n")
os.remove(os.path.join(tmp, "home", ".android", "adbkey"))
cfg = {"data_dir": data, "_path": toml}
assert backup.apply_pending(cfg) is None                         # nothing waiting

os.remove(os.path.join(boot, "harald-art", "happy.png"))
# ...then the den sends the backup back
open(os.path.join(data, backup.PENDING), "wb").write(blob)
line = backup.apply_pending(cfg)
assert line.startswith("Restored from a backup made on ") and "2026" in line, line
assert not os.path.exists(os.path.join(data, backup.PENDING))
s2 = Store(os.path.join(data, "dragon.db"))
assert s2.get("pet")["xp"] == 1234
s2.db.close()
assert open(toml).read() == '[home_wifi]\nssid = "MyHotspot"\n'
assert open(os.path.join(boot, "harald-art", "happy.png"), "rb").read() == b"\x89PNG fake picture"
assert open(os.path.join(data, "diary", "2026-10-13.csv")).read().startswith("time,what")
assert open(os.path.join(tmp, "home", ".android", "adbkey")).read() == "PRIVATE KEY"
assert oct(os.stat(os.path.join(tmp, "home", ".android", "adbkey")).st_mode)[-3:] == "600"
kept = os.path.join(data, "before-restore")                      # what was there, kept aside
k = sqlite3.connect(os.path.join(kept, "dragon.db"))
assert json.loads(k.execute("SELECT value FROM kv WHERE key='pet'").fetchone()[0])["xp"] == 9999
k.close()
assert "NewHotspot" in open(os.path.join(kept, "bt-dragon.toml")).read()

# from the boot partition: once only (renamed afterwards)
open(os.path.join(boot, backup.BOOT_NAME), "wb").write(blob)
assert backup.apply_pending(cfg).startswith("Restored")
assert not os.path.exists(os.path.join(boot, backup.BOOT_NAME))
assert os.path.exists(os.path.join(boot, "harald-restore.done.tar.gz"))
assert backup.apply_pending(cfg) is None


# not his backups: refused, and nothing changed
def tar_of(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, body in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            t.addfile(info, io.BytesIO(body))
    return buf.getvalue()


manifest = json.dumps({"kind": "bt-dragon-backup", "made": 1}).encode()
bad = {
    "no manifest": tar_of({"dragon.db": snap}),
    "unexpected": tar_of({"manifest.json": manifest, "dragon.db": snap, "../../etc/passwd": b"x"}),
    "unexpected ": tar_of({"manifest.json": manifest, "dragon.db": snap, "diary/../../x": b"x"}),
    "no database": tar_of({"manifest.json": manifest}),
    "can't be read": tar_of({"manifest.json": manifest, "dragon.db": b"not a database at all" * 100}),
    "readable .tar.gz": b"this is not an archive",
}
for why, body in bad.items():
    p = os.path.join(tmp, "bad.tar.gz")
    open(p, "wb").write(body)
    try:
        backup.read(p)
        raise AssertionError(f"accepted: {why}")
    except backup.BadBackup as e:
        assert why.strip() in str(e), (why, str(e))
open(os.path.join(boot, backup.BOOT_NAME), "wb").write(bad["no manifest"])
assert backup.apply_pending(cfg) is None
assert os.path.exists(os.path.join(boot, backup.BOOT_NAME + ".not-restored"))
s3 = Store(os.path.join(data, "dragon.db"))
assert s3.get("pet")["xp"] == 1234                                 # untouched
s3.db.close()


# the den's upload: checked straight away; a good one is kept for the restart
class App:
    data_dir = data

    def __init__(self):
        self.restarts = []

    def restart_soon(self, why):
        self.restarts.append(why)


async def upload(body, length=None):
    r = asyncio.StreamReader()
    r.feed_data(body)
    r.feed_eof()
    a = App()
    out = await server._receive_restore(a, r, len(body) if length is None else length)
    head, _, payload = out.partition(b"\r\n\r\n")
    return head.split(b"\r\n")[0].decode(), json.loads(payload), a


status, j, a = asyncio.run(upload(blob))
assert status == "HTTP/1.1 200 OK" and j["ok"] and j["made"] == 1791900000 and a.restarts == ["restoring a backup"]
assert os.path.exists(os.path.join(data, backup.PENDING))
os.remove(os.path.join(data, backup.PENDING))
status, j, a = asyncio.run(upload(bad["no manifest"]))
assert status.startswith("HTTP/1.1 400") and j["error"].startswith("Not restoring: it isn't one of your dragon's backups")
assert not a.restarts and not os.path.exists(os.path.join(data, backup.PENDING))
status, j, a = asyncio.run(upload(blob[:1000], length=len(blob)))      # cut off part way
assert status.startswith("HTTP/1.1 400") and "didn't arrive whole" in j["error"] and not a.restarts
status, j, a = asyncio.run(upload(b"", length=0))
assert status.startswith("HTTP/1.1 400")
assert not os.path.exists(os.path.join(data, "restore-upload.tmp"))
print("backup ok")
