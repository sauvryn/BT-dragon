"""The daily diary spreadsheet files."""
import csv
import datetime
import os
import tempfile
import time

from bt_dragon.diary import DiaryFiles

d = tempfile.mkdtemp()
for days in (100, 10):     # one file past the 90-day limit, one well inside it
    day = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    open(os.path.join(d, f"diary-{day}.csv"), "w").write("x")
open(os.path.join(d, "notes.txt"), "w").write("not a diary file: leave it alone")
ctx = {"food": 50, "joy": 70, "pack": 3.5, "level": 2, "xp": 80, "lat": 51.50926, "lon": -0.07441}
df = DiaryFiles(d, 90, True, lambda: ctx)
now = time.time()
df.write(now, "landmark", "Harald saw Tower Bridge for the first time!")
df.write(now + 1, "treat", 'New Wi-Fi: "Cafe, upstairs" [WPA2]')
names = sorted(os.listdir(d))
old = (datetime.date.today() - datetime.timedelta(days=100)).isoformat()
assert f"diary-{old}.csv" not in names and "notes.txt" in names and len(names) == 3, names
name = df.files()[0][0]
raw = df.read(name)
assert raw.startswith(b"\xef\xbb\xbf")                       # so Excel reads it as UTF-8
rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
assert rows[0][:4] == ["date", "time", "kind", "event"] and len(rows) == 3
assert rows[2][3] == 'New Wi-Fi: "Cafe, upstairs" [WPA2]' and rows[2][-2:] == ["51.50926", "-0.07441"]
assert df.read("../../etc/passwd") is None and df.read("notes.txt") is None
nl = DiaryFiles(d, 90, False, lambda: ctx)
nl.write(now + 2, "x", "no location")
last = list(csv.reader(nl.read(name).decode("utf-8-sig").splitlines()))[-1]
assert last[-2:] == ["", ""] and last[4] == "50"
print("all good")
