"""
The diary as spreadsheet files: one CSV per day, kept on the Pi.

Every diary entry (new species, treats, pals, landmarks, weather, uploads, level-ups...)
is also written as a row of  /var/lib/bt-dragon/diary/diary-YYYY-MM-DD.csv  with the time,
what happened, his meters at that moment and, if GPS was working, where it happened.
A new file starts at local midnight, and files older than keep_days are deleted.

CSV ("comma-separated values") is plain text that any spreadsheet program opens. The file
starts with a byte-order mark so Excel knows it's UTF-8 and shows names like ᚺᚨᚱᚨᛚᛞ properly.
"""
import csv
import datetime
import logging
import os
import re
import time

log = logging.getLogger("diary")

COLUMNS = ["date", "time", "kind", "event", "food", "joy", "pack", "level", "xp", "lat", "lon"]
NAME_RE = re.compile(r"^diary-(\d{4}-\d{2}-\d{2})\.csv$")


class DiaryFiles:
    def __init__(self, folder, keep_days=90, location=True, context=None):
        self.folder = folder
        self.keep_days = max(1, int(keep_days))
        self.location = location
        self.context = context          # callback() -> dict(food, joy, pack, level, xp, lat, lon)
        self._day = None
        os.makedirs(folder, exist_ok=True)
        self.prune()

    def path_for(self, day):
        return os.path.join(self.folder, f"diary-{day}.csv")

    def write(self, ts, kind, text):
        try:
            lt = time.localtime(ts)
            day = time.strftime("%Y-%m-%d", lt)
            if day != self._day:
                self._day = day
                self.prune()            # a new day: tidy away the oldest files
            path = self.path_for(day)
            new = not os.path.exists(path)
            ctx = (self.context() if self.context else None) or {}
            if not self.location:
                ctx = dict(ctx, lat=None, lon=None)
            with open(path, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(COLUMNS)
                w.writerow([day, time.strftime("%H:%M:%S", lt), kind, text]
                           + ["" if ctx.get(k) is None else ctx[k] for k in COLUMNS[4:]])
        except OSError as e:
            log.warning("couldn't write the diary file: %s", e)

    def files(self):
        """[(name, bytes)] newest first."""
        out = []
        try:
            for name in os.listdir(self.folder):
                if NAME_RE.match(name):
                    out.append((name, os.path.getsize(os.path.join(self.folder, name))))
        except OSError:
            pass
        return sorted(out, reverse=True)

    def prune(self):
        """Delete files older than keep_days (by the date in their name)."""
        cutoff = datetime.date.today() - datetime.timedelta(days=self.keep_days)
        for name, _ in self.files():
            m = NAME_RE.match(name)
            try:
                if datetime.date.fromisoformat(m.group(1)) < cutoff:
                    os.remove(os.path.join(self.folder, name))
                    log.info("deleted old diary file %s", name)
            except (ValueError, OSError):
                pass

    def rename_makers(self, companies):
        """Rewrite 'Maker 0x1234 gadget' in the saved diary files with the company's name."""
        pat = re.compile(r"Maker 0x([0-9A-Fa-f]{4}) gadget")

        def sub(m):
            code = int(m.group(1), 16)
            if callable(companies):
                return companies(code) or m.group(0)
            name = companies.get(code)
            return f"{name} device" if name else m.group(0)
        n = 0
        for name, _ in self.files():
            path = os.path.join(self.folder, name)
            try:
                with open(path, encoding="utf-8-sig", newline="") as f:
                    text = f.read()
                new = pat.sub(sub, text)
                if new != text:
                    tmp = path + ".tmp"
                    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
                        f.write(new)
                    os.replace(tmp, path)
                    n += 1
            except OSError:
                pass
        return n

    def read(self, name):
        """The bytes of one diary file, or None (only real diary file names are allowed)."""
        if not NAME_RE.match(name or ""):
            return None
        try:
            with open(os.path.join(self.folder, name), "rb") as f:
                return f.read()
        except OSError:
            return None
