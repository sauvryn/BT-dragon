"""Gentler on the memory card: changes wait in memory and go onto the card together; napping,
sleeping, restarting, backups and reading the diary all write everything first."""
import asyncio
import os
import sqlite3
import tempfile

from bt_dragon import config, tuning
from bt_dragon.app import Dragon
from bt_dragon.store import Store

# the store: nothing reaches the file until flush()
d = tempfile.mkdtemp()
st = Store(os.path.join(d, "x.db"))
other = lambda: sqlite3.connect(os.path.join(d, "x.db"))       # noqa: E731  (what the card holds)
for i in range(200):
    st.put("pet", {"xp": i})                                   # a busy minute: 200 changes
    st.event("snack", f"snack {i}")
assert st.pending() and st.get("pet") == {"xp": 199}           # he sees his own changes at once
assert other().execute("SELECT value FROM kv WHERE key='pet'").fetchone() is None
before = st.flushes
st.flush()
assert st.flushes == before + 1 and not st.pending()           # ...and the card gets them in one go
assert other().execute("SELECT value FROM kv WHERE key='pet'").fetchone()[0] == '{"xp": 199}'
st.flush()
assert st.flushes == before + 1                                # nothing waiting: nothing written

# the app: the knob, the Den's line, and everything written before a nap
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
assert tuning.get("card_save_min") == 10 and tuning.set_value("card_save_min", "0.5") and \
    tuning.set_value("card_save_min", "5") is None
tuning.set_value("card_save_min", "10")
db = os.path.join(cfg["data_dir"], "dragon.db")
app.event("treat", "New Wi-Fi: Somewhere [WPA2]")
assert app.store.pending()
v = app.view()
assert "card_saved" in v and "card_saves" in v


async def nap_and_wake():
    app.stop = asyncio.Event()
    app.dot.release = lambda: asyncio.sleep(0)
    assert (await app.command("NAP"))[0].startswith("OK")
    seen = [r[0] for r in sqlite3.connect(db).execute("SELECT text FROM events")]
    assert "New Wi-Fi: Somewhere [WPA2]" in seen and not app.store.pending()
    assert (await app.command("WAKE"))[0].startswith("OK") and not app.store.pending()
asyncio.run(nap_and_wake())

# the diary's rows wait too, and are written before anything reads the files
app.event("treat", "New Wi-Fi: Elsewhere [WPA2]")
folder = os.path.join(cfg["data_dir"], "diary")
on_card = lambda: "".join(open(os.path.join(folder, f), encoding="utf-8-sig").read()   # noqa: E731
                          for f in os.listdir(folder))
assert "Elsewhere" not in on_card()
assert app.diary_files.files() and "Elsewhere" in on_card()
app.event("treat", "New Wi-Fi: Over There [WPA2]")
app.store.flush()
assert "Over There" in on_card()

# a restart writes everything first
app.event("treat", "New Wi-Fi: Last One [WPA2]")
app.restart_soon("test")
assert not app.store.pending()

# speech and recordings are made in memory, and the screen isn't saved as a file on the Pi
if os.path.isdir("/dev/shm"):
    assert app.dot.tmp.startswith("/dev/shm")
with open("bt_dragon/app.py", encoding="utf-8") as f:
    assert 'if simulate else None' in f.read()

# the system log in memory: the setting the installer and updater put in place
with open("gentle-card.sh", encoding="utf-8") as f:
    sh = f.read()
assert "Storage=volatile" in sh and "journald.conf.d" in sh
for script in ("install.sh", "update.sh"):
    with open(script, encoding="utf-8") as f:
        assert "gentle-card.sh" in f.read(), script
print("card ok")
