"""
Mini backups: everything that's yours, in one small file, instead of an image of the
whole card.

What's in one (a .tar.gz, the same kind of archive Linux has used for decades):
  manifest.json      what it is, when it was made, whose it is
  dragon.db          his database: Harald himself, the diary, species, lands, landmarks
                     and green spaces, the shopping list, calendar, voice profiles, your
                     den and Developer Tools settings, and his ears' key for the Dot
  diary/, wigle/     the daily diary files and saved wardriving files
  bt-dragon.toml     the settings file (hotspot passwords and the WiGLE token are in it:
                     keep backups private)
  adb/               the Pi's key for the Dot's debug link, so a rebuilt Pi is let straight in
  art/               your artwork (the bt-dragon-art folder next to the settings file)

Not in it: Raspberry Pi OS, the program, the speech and voice models, and the Debian built
for the Dot. The update zip and install-voice.sh put those back.

Making one while he runs: the database keeps its newest changes in a side file
(dragon.db-wal) until they're merged in, so copying dragon.db alone could catch it half
written. SQLite's own backup feature copies it page by page into a clean, complete
snapshot instead, here straight into memory, so nothing extra is written to the card.

Restoring: the den's "Restore" button sends the file to the Pi, which keeps it as
restore-pending.tar.gz and restarts him. Or, without the den, copy a backup onto the
card's boot partition (the one Windows can open) named  bt-dragon-restore.tar.gz (or the older
name, harald-restore.tar.gz). Either
way, the next time he starts, before anything else, the file is checked (it must be one
of his backups, with nothing in it but the expected files, and a database that passes
SQLite's own check), what's there now is put aside in before-restore/ in case you change
your mind, and the backup takes its place. The file is then removed (or, on the boot
partition, renamed to bt-dragon-restore.done.tar.gz) so it only happens once.
"""
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
import time

from . import __version__

log = logging.getLogger("backup")

KIND = "bt-dragon-backup"
BOOT_NAME = "bt-dragon-restore.tar.gz"
BOOT_NAMES = (BOOT_NAME, "harald-restore.tar.gz")     # the older name still works
PENDING = "restore-pending.tar.gz"
MAX_BYTES = 300 * 1024 * 1024
ALLOWED = re.compile(r"^(manifest\.json|dragon\.db|bt-dragon\.toml|adb/adbkey(\.pub)?|"
                     r"(diary|wigle)/[A-Za-z0-9._ -]{1,120}|art/[A-Za-z_-]{1,40}\.(png|PNG))$")


ART_FOLDER, OLD_ART_FOLDER = "bt-dragon-art", "harald-art"


def art_dir(config_path, data_dir):
    """Where your artwork lives: the bt-dragon-art folder next to the settings file. An older
    harald-art folder is renamed to it the first time (or, if it can't be, still used)."""
    if not config_path:
        return os.path.join(data_dir, "art")
    here = os.path.dirname(config_path)
    new, old = os.path.join(here, ART_FOLDER), os.path.join(here, OLD_ART_FOLDER)
    if os.path.isdir(old) and not os.path.exists(new):
        try:
            os.rename(old, new)
        except OSError:
            return old
    return new


def adb_dir():
    return os.path.expanduser("~/.android")


def _add(tar, name, data, mtime=None):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = int(mtime or time.time())
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(data))


def db_snapshot(db_path):
    """A consistent copy of a live SQLite database, as bytes. Its own connection reads
    alongside his (the side-file way of working allows that), into memory."""
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    mem = sqlite3.connect(":memory:")
    try:
        src.backup(mem)
        if hasattr(mem, "serialize"):                    # Python 3.11 and newer
            return mem.serialize()
        with tempfile.TemporaryDirectory() as tmp:
            out = sqlite3.connect(os.path.join(tmp, "snap.db"))
            mem.backup(out)
            out.close()
            with open(os.path.join(tmp, "snap.db"), "rb") as f:
                return f.read()
    finally:
        mem.close()
        src.close()


def make(data_dir, config_path, name="Harald", now=None):
    """The backup, as bytes of a .tar.gz."""
    now = now or time.time()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        _add(tar, "manifest.json", json.dumps({"kind": KIND, "version": __version__, "made": int(now),
                                               "name": name}, indent=1).encode(), now)
        _add(tar, "dragon.db", db_snapshot(os.path.join(data_dir, "dragon.db")), now)
        for sub in ("diary", "wigle"):
            folder = os.path.join(data_dir, sub)
            for fn in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
                p = os.path.join(folder, fn)
                if os.path.isfile(p) and ALLOWED.match(f"{sub}/{fn}"):
                    with open(p, "rb") as f:
                        _add(tar, f"{sub}/{fn}", f.read(), os.path.getmtime(p))
        if config_path and os.path.isfile(config_path):
            with open(config_path, "rb") as f:
                _add(tar, "bt-dragon.toml", f.read(), os.path.getmtime(config_path))
        art = art_dir(config_path, data_dir)
        for fn in sorted(os.listdir(art)) if os.path.isdir(art) else []:
            p = os.path.join(art, fn)
            if os.path.isfile(p) and ALLOWED.match(f"art/{fn}"):
                with open(p, "rb") as f:
                    _add(tar, f"art/{fn}", f.read(), os.path.getmtime(p))
        for fn in ("adbkey", "adbkey.pub"):
            p = os.path.join(adb_dir(), fn)
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    _add(tar, f"adb/{fn}", f.read(), os.path.getmtime(p))
    return buf.getvalue()


def filename(now=None):
    return time.strftime("bt-dragon-backup-%Y-%m-%d-%H%M.tar.gz", time.localtime(now or time.time()))


class BadBackup(Exception):
    pass


def read(path):
    """Check a backup and return {name: bytes} and its manifest. Raises BadBackup."""
    if os.path.getsize(path) > MAX_BYTES:
        raise BadBackup("it's too big to be one of your dragon's backups")
    files, total = {}, 0
    try:
        with tarfile.open(path, "r:gz") as tar:
            for m in tar.getmembers():
                if m.isdir():
                    continue
                if not m.isfile() or not ALLOWED.match(m.name) or ".." in m.name:
                    raise BadBackup(f"it holds something unexpected ({m.name[:60]})")
                total += m.size
                if total > MAX_BYTES * 4:
                    raise BadBackup("it unpacks to something far too big")
                files[m.name] = tar.extractfile(m).read()
    except (tarfile.TarError, OSError, EOFError) as e:
        raise BadBackup(f"it isn't a readable .tar.gz ({e})")
    try:
        manifest = json.loads(files.get("manifest.json", b"{}"))
    except ValueError:
        manifest = {}
    if manifest.get("kind") != KIND:
        raise BadBackup("it isn't one of your dragon's backups (no manifest)")
    if "dragon.db" not in files:
        raise BadBackup("it has no database in it")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "check.db")
        with open(p, "wb") as f:
            f.write(files["dragon.db"])
        try:
            con = sqlite3.connect(p)
            ok = con.execute("PRAGMA quick_check").fetchone()[0]
            con.execute("SELECT count(*) FROM kv").fetchone()
            con.close()
        except sqlite3.Error as e:
            raise BadBackup(f"its database can't be read ({e})")
        if ok != "ok":
            raise BadBackup(f"its database is damaged ({ok})")
    return files, manifest


def _write(path, data, mode=0o644):
    tmp = path + ".restoring"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _set_aside(data_dir, config_path):
    """What's there now, in before-restore/ (only the latest one is kept)."""
    keep = os.path.join(data_dir, "before-restore")
    shutil.rmtree(keep, ignore_errors=True)
    os.makedirs(keep)
    db = os.path.join(data_dir, "dragon.db")
    if os.path.exists(db):
        con = sqlite3.connect(db)
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")      # fold the side file in first
        except sqlite3.Error:
            pass
        con.close()
        shutil.copy2(db, os.path.join(keep, "dragon.db"))
    if config_path and os.path.isfile(config_path):
        shutil.copy2(config_path, os.path.join(keep, "bt-dragon.toml"))
    return keep


def restore(path, data_dir, config_path):
    """Put a backup in place (he must not be running). Returns a line for the diary."""
    files, manifest = read(path)
    os.makedirs(data_dir, exist_ok=True)
    _set_aside(data_dir, config_path)
    for ext in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(os.path.join(data_dir, "dragon.db" + ext))
        except FileNotFoundError:
            pass
    _write(os.path.join(data_dir, "dragon.db"), files["dragon.db"], 0o600)
    for name, data in files.items():
        if name.startswith(("diary/", "wigle/")):
            os.makedirs(os.path.join(data_dir, name.split("/")[0]), exist_ok=True)
            _write(os.path.join(data_dir, name), data)
    if "bt-dragon.toml" in files and config_path:
        _write(config_path, files["bt-dragon.toml"])
    art = art_dir(config_path, data_dir)
    for name, data in files.items():
        if name.startswith("art/"):
            os.makedirs(art, exist_ok=True)
            _write(os.path.join(art, name[4:]), data)
    if "adb/adbkey" in files:
        os.makedirs(adb_dir(), exist_ok=True)
        _write(os.path.join(adb_dir(), "adbkey"), files["adb/adbkey"], 0o600)
        if "adb/adbkey.pub" in files:
            _write(os.path.join(adb_dir(), "adbkey.pub"), files["adb/adbkey.pub"], 0o644)
    try:
        os.sync()
    except (AttributeError, OSError):
        pass
    made = time.strftime("%d %B %Y at %H:%M", time.localtime(manifest.get("made", 0)))
    return f"Restored from a backup made on {made}"


def apply_pending(cfg):
    """At start-up, before anything opens the database: restore a waiting backup, if any.
    Returns the diary line, or None."""
    data_dir, config_path = cfg["data_dir"], cfg.get("_path")
    candidates = [(os.path.join(data_dir, PENDING), None)]
    if config_path:
        for name in BOOT_NAMES:
            boot = os.path.join(os.path.dirname(config_path), name)
            candidates.append((boot, boot.replace(".tar.gz", ".done.tar.gz")))
    for path, done in candidates:
        if not os.path.isfile(path):
            continue
        try:
            line = restore(path, data_dir, config_path)
            log.info("%s (from %s)", line, path)
        except (BadBackup, OSError) as e:
            line = None
            log.error("not restoring %s: %s", path, e)
        try:
            if done:
                os.replace(path, done if line else path + ".not-restored")
            else:
                os.remove(path)
        except OSError as e:
            log.warning("couldn't move %s out of the way: %s", path, e)
        if line:
            return line
    return None
