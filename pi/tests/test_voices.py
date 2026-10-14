"""Voice profiles: names from speech, learning and matching voice prints, names in replies."""
import os
import tempfile

from bt_dragon import ask, tuning, voices
from bt_dragon.store import Store

store = Store(os.path.join(tempfile.mkdtemp(), "v.db"))
tuning.load(store)
C = voices.clean_name
assert C("my name is sam") == "Sam" and C("it's robin") == "Robin" and C("um this is sam") == "Sam"
assert C("hello i'm mary jane smith") == "Mary Jane" and C("") == "" and C("um") == ""

a = [1.0 if i % 2 == 0 else 0.1 for i in range(128)]
b = [0.1 if i % 2 == 0 else 1.0 for i in range(128)]
a2 = [x + 0.05 * (i % 3) for i, x in enumerate(a)]
assert voices.similarity(a, a) > 0.999 and voices.similarity(a, b) < 0.4

vp = voices.VoiceProfiles(store)
assert vp.identify(a, 300) == (None, 0, None)                  # nobody known yet
p, new = vp.add("Sam", [(a, 200), (a2, 150), (None, 0)])
assert new and p["samples"] == 2
vp.add("Robin", [(b, 300)])
assert vp.identify(a2, 300)[0] == "Sam" and vp.identify(b, 300)[0] == "Robin"
assert vp.identify(a2, 50)[0] is None                           # too short to tell
mixed = [(x + y) / 2 for x, y in zip(a, b)]
name, pct, guess = vp.identify(mixed, 300)
assert name is None and guess in ("Sam", "Robin")              # halfway: not sure
p, new = vp.add("sam", [(a, 100)])
assert not new and p["samples"] == 3                            # more samples for the same person
assert voices.VoiceProfiles(store).items == vp.items            # kept
vp.rename(p["id"], "Sam B")
assert vp.find("Sam B") and vp.delete(p["id"]) and not vp.find("Sam B")

W = voices.with_name
assert W("It's 7:30 at night.", "Sam", 100) == "It's 7:30 at night, Sam."
assert W("It's 7:30 at night.", "Sam", 0) == "It's 7:30 at night."
assert W("Right now it's 16 degrees, that's 61 Fahrenheit, and overcast. Later: rain.", "Sam", 100) == \
    "Right now it's 16 degrees, that's 61 Fahrenheit, and overcast, Sam. Later: rain."
assert W("Minus 3.4 hectopascals!", "Robin", 100) == "Minus 3.4 hectopascals, Robin!"
assert W("Hello, Sam.", "Sam", 100) == "Hello, Sam." and W("", "Sam", 100) == ""
picks = [W("Yes.", "Sam", 50, rnd=lambda: r) for r in (0.1, 0.9)]
assert picks == ["Yes, Sam.", "Yes."]

P = ask.parse
assert P("set a voice profile")["intent"] == "voice_enrol" and P("set up a voice profile")["intent"] == "voice_enrol"
assert P("learn my voice")["intent"] == "voice_enrol" and P("who am i")["intent"] == "voice_who"
assert P("set a timer for ten minutes")["intent"] == "timer_set"
print("voices ok")
