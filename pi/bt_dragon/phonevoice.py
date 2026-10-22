"""
Harald's voice through your phone's speaker (or whatever it's playing through: Bluetooth
earphones too), with the screen off.

How it works: a web page can't keep talking with the screen off (Android pauses it), so a
tiny program runs in Termux on the phone instead (phone/bt_dragon_voice.py, which the den
offers for download). It asks Harald "anything new to say?" and he holds the question open
for up to a minute until there is something (a "long poll": one waiting request rather than
asking every second). Each remark comes back as text, and the phone's own text-to-speech
voice reads it out (termux-tts-speak, from the Termux:API app). Nothing but the words goes
to the phone, over the hotspot, and nothing is kept.
"""
import asyncio
import time

KEEP_S = 120          # remarks older than this aren't read out (the phone was away)
LISTENING_S = 90      # a phone that asked within this long counts as listening


class PhoneVoice:
    def __init__(self):
        self.items = []           # (seq, text, ts)
        self.seq = 0
        self.last_poll = 0.0
        self.acked = -1           # the last remark the phone has finished saying (it asks again after)
        self._event = None

    def listening(self, now=None):
        return (now or time.time()) - self.last_poll < LISTENING_S

    def push(self, text):
        self.seq += 1
        now = time.time()
        self.items = [i for i in self.items if now - i[2] < KEEP_S][-20:] + [(self.seq, text, now)]
        if self._event:
            self._event.set()
        return self.seq

    def _fresh(self, after):
        now = time.time()
        return [{"seq": s, "text": t} for s, t, ts in self.items if s > after and now - ts < KEEP_S]

    async def wait(self, after, timeout=55.0):
        """What to say after remark number `after`, waiting up to `timeout` for something.
        `after` < 0 (just started) or beyond what he's said (he restarted): start from now."""
        self.last_poll = time.time()
        if 0 <= after <= self.seq:
            self.acked = max(self.acked, after)   # (it says everything it's given before asking again)
        if after < 0 or after > self.seq:
            return {"seq": self.seq, "items": []}
        if self._event is None:
            self._event = asyncio.Event()
        deadline = time.monotonic() + timeout
        while True:
            fresh = self._fresh(after)
            left = deadline - time.monotonic()
            if fresh or left <= 0:
                self.last_poll = time.time()
                return {"seq": self.seq if fresh else max(after, self.seq), "items": fresh}
            self._event.clear()
            try:
                await asyncio.wait_for(self._event.wait(), left)
            except asyncio.TimeoutError:
                pass


def script(address, token=""):
    """The Termux program, with this dragon's address (and its ticket, for when the Den has a
    password: see denauth.py) filled in."""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phone", "bt_dragon_voice.py")
    with open(path, encoding="utf-8") as f:
        return f.read().replace("__ADDRESS__", address).replace("__TOKEN__", token)
