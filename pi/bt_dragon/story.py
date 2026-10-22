"""
"Read me a story": Harald reads an e-book from the library's shelf out loud, through the Echo
Dot or the phone's voice (the Termux helper), with the phone's screen off.

How it works: the reader (library.html) already has the book open and knows what each page
is. When you press Start, it gathers the words to be read, from the first sentence that starts
on the page you're looking at: just that page (to the end of the last sentence that starts on
it), to the end of the chapter, or to the end of the book. It leaves out what would break the
flow when spoken: footnote and endnote markers and the notes themselves, page numbers, tables
and figure captions, and (for the whole book) the contents, index, glossary, notes and the
other parts the reader doesn't count as the book's own text. It splits the words into
sentences and sends them to the Pi, each with where it is in the book. From then on the Pi
reads on by itself; the phone can be locked or put away.

  - Through the Echo Dot: Harald's own voice (Piper), a sentence at a time, each one made
    while the one before plays, so there are no gaps.
  - Through the phone: a few sentences at a time to the Termux helper, which reads them with
    the phone's own voice and asks for more when it's done.

"Stop after" (5 minutes to 2 hours) ends it at the end of a sentence once the time is up: a
story to fall asleep to. Quiet hours don't stop a story (you asked for it), and Harald's own
news waits while he's reading. Stop it from the reader or the Library page; a nap stops it too.

Where he stopped is kept for each book, so the reader can take you there ("Go to where
Harald stopped reading"). Listening doesn't count as reading in the book tracker: only pages
you read on screen are counted.

Nothing leaves the Pi and your phone: the words go from the reader to the Pi and from the Pi
to the Dot or the phone, all over your own hotspot.
"""
import asyncio
import logging
import time

log = logging.getLogger("story")

MAX_CHARS = 4_000_000         # a long book's whole text
MAX_ITEMS = 80_000
MINUTES = (0, 5, 10, 15, 20, 30, 45, 60, 90, 120)
PARA_PAUSE_S, HEAD_PAUSE_S = 0.45, 0.8
PHONE_CHUNK = 320             # characters sent to the phone at a time (whole sentences)
PHONE_AHEAD = 2               # chunks the phone may have waiting
PHONE_LOST_S = 150            # the phone hasn't asked for more in this long: it's gone


class Story:
    def __init__(self, app):
        self.app = app
        self.active = False
        self.voice = None
        self.task = None
        self.cur = {}
        self._stop = False

    # ---- where it can be read
    def voices(self):
        dot = self.app.dot
        return {"dot": bool(dot.s.get("enabled") and dot.connected and dot.ready),
                "phone": bool(dot.phone.listening())}

    def view(self):
        c = self.cur
        return {"active": self.active, "voice": self.voice, "book": c.get("book"), "title": c.get("title", ""),
                "label": c.get("label", ""), "minutes": c.get("minutes", 0), "ends_at": c.get("ends_at"),
                "done": c.get("i", 0), "total": len(c.get("items", [])), "voices": self.voices(),
                "last": self.app.store.get("story_last") or {}}

    # ---- starting and stopping
    def start(self, d):
        """`d`: {book, title, label, voice, minutes, items: [{t, p, h, ch, k}]}. Returns an error or None."""
        if getattr(self.app, "napping", False):
            return f"{self.app.pet.name} is napping"
        voice = d.get("voice")
        if voice not in ("dot", "phone"):
            return "choose the Echo Dot or the phone"
        if not self.voices()[voice]:
            return ("the Echo Dot isn't connected" if voice == "dot"
                    else "the phone's voice isn't listening (start the Termux helper)")
        items = d.get("items")
        if not isinstance(items, list) or not items:
            return "nothing to read here"
        if len(items) > MAX_ITEMS or sum(len(str(x.get("t", ""))) for x in items if isinstance(x, dict)) > MAX_CHARS:
            return "that's too much to send at once"
        clean = []
        for x in items:
            if not isinstance(x, dict):
                continue
            t = " ".join(str(x.get("t", "")).split())
            if t:
                clean.append({"t": t[:2000], "p": bool(x.get("p")), "h": bool(x.get("h")),
                              "ch": int(x.get("ch") or 0), "k": int(x["k"]) if isinstance(x.get("k"), int) else None})
        if not clean:
            return "nothing to read here"
        try:
            minutes = int(d.get("minutes") or 0)
        except (TypeError, ValueError):
            minutes = 0
        minutes = minutes if minutes in MINUTES else 0
        self.stop(save=True)
        now = time.time()
        self.cur = {"book": str(d.get("book") or "")[:40], "title": str(d.get("title") or "")[:200],
                    "label": str(d.get("label") or "")[:80], "minutes": minutes, "started": now,
                    "ends_at": now + minutes * 60 if minutes else None, "items": clean, "i": 0, "said": None}
        self.voice, self.active, self._stop = voice, True, False
        self.task = asyncio.ensure_future(self._run())
        return None

    def stop(self, save=True):
        if not self.active:
            return False
        self._stop = True
        if self.voice == "dot":
            self.app.dot.hush()
        if save:
            self._finish("stopped")
        if self.task and not self.task.done():
            self.task.cancel()
        return True

    # ---- reading
    def _next(self):
        """(sentence, pause after) or None: the end, Stop, or the time's up."""
        c = self.cur
        if self._stop or c["i"] >= len(c["items"]):
            return None
        if c["ends_at"] and time.time() >= c["ends_at"]:
            return None
        x = c["items"][c["i"]]
        c["i"] += 1
        return (x["t"], HEAD_PAUSE_S if x["h"] else PARA_PAUSE_S if x["p"] else 0.0, x)

    def _said(self, part):
        self.cur["said"] = part[2]

    async def _run(self):
        how = "done"
        try:
            if self.voice == "dot":
                how = await self.app.dot.speak_stream(lambda: self._next(), self._said)
            else:
                how = await self._phone()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("story")
            how = "lost"
        if self.active:
            self._finish("time" if how == "done" and self.cur.get("ends_at") and self.cur["i"] < len(self.cur["items"])
                         else how)

    async def _phone(self):
        ph = self.app.dot.phone
        pending = []           # (seq, last item in it)
        last_ask = time.time()
        while True:
            while len(pending) < PHONE_AHEAD:
                parts = []
                while sum(len(p[0]) for p in parts) < PHONE_CHUNK:
                    p = self._next()
                    if p is None:
                        break
                    parts.append(p)
                    if p[2]["p"] or p[2]["h"]:
                        break
                if not parts:
                    break
                pending.append((ph.push(" ".join(p[0] for p in parts)), parts[-1]))
                self.cur.setdefault("sent", parts[0][2])      # (if it's stopped before the phone says it's done)
            if not pending:
                return "done"
            seq, last = pending[0]
            while ph.acked < seq:
                if self._stop:
                    return "stopped"
                if ph.last_poll > last_ask:
                    last_ask = ph.last_poll
                if time.time() - max(last_ask, ph.last_poll) > PHONE_LOST_S:
                    return "lost"
                await asyncio.sleep(0.5)
            pending.pop(0)
            self._said(last)

    def _finish(self, how):
        """Keeps where he stopped (for "Go to where Harald stopped reading"), and a diary line."""
        c, self.active = self.cur, False
        said = c.get("said") or c.get("sent")
        mins = max(1, round((time.time() - c.get("started", time.time())) / 60))
        if said and c.get("book") and not getattr(self.app, "napping", False):
            last = self.app.store.get("story_last") or {}
            last[c["book"]] = {"ch": said["ch"], "k": said["k"], "ts": int(time.time()), "label": c.get("label", ""),
                               "end": c["i"] >= len(c["items"]) and how == "done"}
            for b in sorted(last, key=lambda b: last[b]["ts"])[:-50]:
                del last[b]
            self.app.store.put("story_last", last)
        why = {"done": "", "time": " (the time was up)", "stopped": "", "lost": " (the voice was lost)"}.get(how, "")
        if said:
            self.app.event("library", f"{self.app.pet.name} read {c.get('title') or 'a book'} out loud for {mins} "
                                      f"minute{'s' if mins != 1 else ''}{why}")
