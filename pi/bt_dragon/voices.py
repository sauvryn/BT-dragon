"""
Voice profiles: who's talking to Harald.

Vosk's small speaker model turns a few seconds of speech into a "voice print": 128 numbers
that describe how a voice sounds (its pitch, the shape of the throat and mouth), not what
was said. Two prints of the same person point in roughly the same direction, so the
cosine similarity between them (1 = identical, 0 = unrelated) says how alike two voices
are. A profile is the average of a person's prints, under the name they gave. They're kept
in Harald's database on the Pi; no recording is ever kept.

Short phrases make wobbly prints, so a profile is built from a few sentences, and very
short questions (under about a second of speech) aren't used to recognize anyone.
"""
import math
import random
import re
import time

from . import tuning

MIN_FRAMES = 100        # about a second of speech: shorter prints are too unreliable
MARGIN = 0.05           # two profiles this close: not sure enough to pick one


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def similarity(a, b):
    a, b = _norm(a), _norm(b)
    return sum(x * y for x, y in zip(a, b))


def clean_name(text):
    """'my name is sam' -> 'Sam'; 'it's robin' -> 'Robin'. '' if there's no name."""
    t = re.sub(r"[^a-z' -]", " ", (text or "").lower())
    t = re.sub(r"^\s*(hello|hi|hey|okay|ok|um|er|uh)\b", " ", t)
    t = re.sub(r"\b(my name is|my name's|this is|it is|it's|i am|i'm|i'm called|call me|speaking|here)\b", " ", t)
    words = [w for w in t.split() if w not in ("the", "a", "and", "um", "uh", "er")]
    if not words:
        return ""
    return " ".join(w.capitalize() for w in words[:2])[:24]


class VoiceProfiles:
    def __init__(self, store):
        self.store = store
        self.items = store.get("voice_profiles") or []
        self._next = max([p["id"] for p in self.items] + [0]) + 1

    def save(self):
        self.store.put("voice_profiles", self.items)

    def find(self, name):
        return next((p for p in self.items if p["name"].lower() == name.lower()), None)

    def add(self, name, samples):
        """Learn a voice from [(print, frames)]. A name already known gets more samples
        mixed in (weighted by how much speech each had). Returns (profile, is_new)."""
        samples = [(s, f) for s, f in samples if s and f >= MIN_FRAMES // 2]
        if not samples:
            return None, False
        total = sum(f for _, f in samples)
        vec = [sum(_norm(s)[i] * f for s, f in samples) / total for i in range(len(samples[0][0]))]
        old = self.find(name)
        if old:
            w = old["frames"]
            old["vec"] = [(a * w + b * total) / (w + total) for a, b in zip(old["vec"], vec)]
            old["frames"] += total
            old["samples"] += len(samples)
            old["updated"] = int(time.time())
            self.save()
            return old, False
        p = {"id": self._next, "name": name, "vec": [round(x, 5) for x in vec], "frames": total,
             "samples": len(samples), "created": int(time.time()), "updated": int(time.time())}
        self._next += 1
        self.items.append(p)
        self.save()
        return p, True

    def identify(self, vec, frames):
        """(name or None, how alike in percent, best guess's name)."""
        if not vec or frames < MIN_FRAMES or not self.items:
            return None, 0, None
        scored = sorted(((similarity(vec, p["vec"]), p["name"]) for p in self.items), reverse=True)
        best, name = scored[0]
        second = scored[1][0] if len(scored) > 1 else -1.0
        pct = round(best * 100)
        if best * 100 >= tuning.get("voice_match") and best - second >= MARGIN:
            return name, pct, name
        return None, pct, name

    def rename(self, pid, name):
        p = next((x for x in self.items if x["id"] == pid), None)
        if p and name:
            p["name"] = name[:24]
            self.save()
        return p

    def delete(self, pid):
        p = next((x for x in self.items if x["id"] == pid), None)
        if p:
            self.items.remove(p)
            self.save()
        return p


def with_name(reply, name, chance=None, rnd=random.random):
    """Sometimes (tuning name_chance, in percent) put the speaker's name into the first
    sentence of a reply: "It's 7:30 at night." -> "It's 7:30 at night, Sam." """
    if not (reply and name):
        return reply
    chance = tuning.get("name_chance") if chance is None else chance
    if rnd() * 100 >= chance:
        return reply
    m = re.match(r"(.+?)([.!?])(\s|$)", reply)
    if not m or name.lower() in reply.lower():
        return reply
    first = m.group(1)
    if first.endswith(","):
        first = first[:-1]
    return f"{first}, {name}{m.group(2)}{reply[m.end(2):]}"
