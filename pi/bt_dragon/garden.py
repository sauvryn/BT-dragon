"""
The Butterfly Garden: raising insects from Harald's surplus food (from the Bookworm project).

Locked until Harald reaches level 5 (or "Unlock now" in the den, for testing). It holds one
larva at first, and one more for each level he gains after it opened, up to three.

Feeding: treats and berries go into his BELLY, then his PACK; anything that fits in neither
used to be wasted. Now it feeds the garden, split evenly between whatever is growing there,
so raising three at once means each grows a third as fast.

A larva's life, as in Bookworm:
  - an egg waits in the first spot (and in any other you put one in, from the den); the
    first food hatches it, and only then is its species
    chosen (a little joy). Rarity is rolled (Common 60%, Uncommon 30%, Rare 10%), and a rarer
    one needs more food to raise, like a longer book;
  - which species: Bookworm's own rules. Every species of that rarity not yet raised, in the
    categories unlocked so far (butterflies first; moths after 2 butterflies raised, bees and
    wasps after 4 and so on), with species in season this month three times as likely. Ones
    already growing are skipped, and a species with separate forms (male and female, or
    queen and worker) stays "not yet raised" until every form has been. Only when there's
    nothing new left at that rarity can a repeat hatch;
  - growth is the share of its food it has had so far, 0 to 100%. It pupates (a chrysalis for
    butterflies) at its species' own point, worked out from its real larva and pupa days, as
    in Bookworm (a little joy), and the adult emerges at 100% (a big joy). The adult joins the
    Garden Collection, may open a habitat, and earns points towards Bookworm's titles;
  - hunger, as in Bookworm, by how long since a larva last ate: "Well fed" for 24 hours,
    "Satisfied" until 48, "Peckish" until 72, then "Hungry", and "Very hungry" from 96 hours (4 days).
    Pupae don't eat, so they're never hungry;
  - queens and workers: a female of a social species becomes a queen if she never went hungry
    as a larva, and a worker if she did.

The collection is kept per country (Bookworm's countries: United Kingdom, Ireland, United
States, Canada): the Pi's own country to start with (or the United Kingdom), then whichever
you choose in the den, or when the Lair moves to one of them and you say yes.
"""
import datetime
import json
import logging
import os
import random
import time

from . import tuning

log = logging.getLogger("garden")

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "garden")
UNLOCK_LEVEL = 5
# hours since a larva last ate: "Well fed", then "Satisfied", "Peckish", "Hungry", "Very hungry"
WELL_FED_S, SATISFIED_S, PECKISH_S, HUNGRY_S = 24 * 3600, 48 * 3600, 72 * 3600, 96 * 3600
MAX_SLOTS = 3
COUNTRY_OF = {"GB": "gb", "IE": "ie", "US": "us", "CA": "ca"}
COUNTRY_NAME = {"gb": "United Kingdom", "ie": "Ireland", "us": "United States", "ca": "Canada"}
TIERS = (("Common", 60), ("Uncommon", 30), ("Rare", 10))
IN_SEASON_WEIGHT = 3
# Bookworm's points for each title, with names about what Harald does instead of books
TITLES = [(0, "t0", "Egg Explorer"), (500, "t1", "Bluetooth Beetle"), (1500, "t2", "Wi-Fi Wasp"),
          (3000, "t3", "Berry-picking Bumblebee"), (5000, "t4", "Snack-seeking Sawfly"),
          (8000, "t5", "Treat-hunting Hoverfly"), (12000, "t6", "Beacon Butterfly"),
          (17000, "t7", "Signal-sniffing Hawk-moth"), (23000, "t8", "Land-claiming Leafcutter"),
          (30000, "t9", "Satellite Stag Beetle"), (40000, "t10", "Hotspot Hornet"),
          (55000, "t11", "Runestone Rhinoceros Beetle"), (75000, "t12", "Monarch of the Lair")]

_DATA = None


def data():
    global _DATA
    if _DATA is None:
        with open(os.path.join(HERE, "species.json"), encoding="utf-8") as f:
            _DATA = json.load(f)
        for c in _DATA["countries"].values():
            c["by_id"] = {s["id"]: s for s in c["species"]}
    return _DATA


FORM_WORD = {"m": "Male", "f": "Female", "q": "Queen", "w": "Worker"}


def full_name(sp):
    """"Peacock" -> "Peacock butterfly", "Drinker" -> "Drinker moth"; other names stand alone
    ("Red-tailed Bumblebee", "Marmalade Fly")."""
    noun = sp.get("noun") or ""
    if sp.get("kind") in ("butterfly", "moth") and noun.lower() not in sp["name"].lower():
        return f"{sp['name']} {noun}"
    return sp["name"]


def habitat_name(c, k):
    return data()["countries"][c].get("habitats", {}).get(k, k)


def iso(ts=None):
    return datetime.datetime.fromtimestamp(ts or time.time(), datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def stage_at(k, pup):
    """Bookworm's growth stages: 1-8 spread up to the pupation point, 9 = pupa, 10 = adult."""
    return 100 if k >= 10 else pup if k == 9 else round(k * pup / 9 * 10) / 10


def stage_for(pct, pup):
    return max([k for k in range(11) if pct >= stage_at(k, pup)] or [0])


class Garden:
    def __init__(self, store, rng=None):
        self.store = store
        self.rng = rng or random.Random()
        self.s = store.get("garden") or {}
        self.s.setdefault("slots", [])
        self.s.setdefault("countries", {})
        self.s.setdefault("titles", {})
        self.on_event = None        # (kind, info) -> the app: "hatch", "pupate", "emerge", "title"
        self.default_country = "gb"  # the app sets this from the Pi's own country

    def save(self):
        self.store.put("garden", self.s)

    # ---- where, and is it open
    def country(self, lair_code=None):
        """Whose insects: the country chosen in the den (or when the Lair moved); to start with,
        the Pi's own country if it's one of Bookworm's, else the United Kingdom. (`lair_code`
        is only kept so older callers still work: the Lair no longer decides by itself.)"""
        return self.s.get("country") or self.default_country

    def set_country(self, c):
        if c not in COUNTRY_NAME:
            return "choose United Kingdom, Ireland, United States or Canada"
        self.s["country"] = c
        self.save()
        return None

    def unlocked(self, level):
        return self.s.get("unlocked_at") is not None or level >= UNLOCK_LEVEL

    def unlock_now(self, level):
        """The den's "Unlock now (prototype testing)" box."""
        if self.s.get("unlocked_at") is None and level < UNLOCK_LEVEL:
            self.s["unlocked_at"] = level
            self.s["forced"] = level < UNLOCK_LEVEL
            self.save()

    def lock_again(self):
        """Untick the box: only undoes a test unlock (and keeps anything raised)."""
        if self.s.get("forced"):
            self.s["unlocked_at"], self.s["forced"] = None, False
            self.save()

    def slot_count(self, level):
        if not self.unlocked(level):
            return 0
        start = self.s.get("unlocked_at")
        if start is None:                   # opened by reaching level 5
            start = UNLOCK_LEVEL
        return max(1, min(MAX_SLOTS, 1 + level - start))

    @staticmethod
    def _egg(now=None):
        return {"egg": True, "laid": now or time.time(), "fed": 0.0}

    def sync_slots(self, level, now=None):
        """The first spot always has an egg (or a larva) in it. Spots that open later, or that
        an adult has just left, stay empty until you put an egg in them from the den, so you
        can raise one or two at a time if you'd rather."""
        n = self.slot_count(level)
        changed = False
        while len(self.s["slots"]) < n:
            self.s["slots"].append(self._egg(now) if not self.s["slots"] else {"empty": True})
            changed = True
        if self.s["slots"] and self.s["slots"][0].get("empty"):
            self.s["slots"][0] = self._egg(now)
            changed = True
        if changed:
            self.save()

    def lay_egg(self, i, level):
        """The den's "Put an egg here" on an empty spot."""
        if not self.unlocked(level) or not 0 <= i < self.slot_count(level):
            return "there's no such spot"
        self.sync_slots(level)
        if not self.s["slots"][i].get("empty"):
            return "that spot isn't empty"
        self.s["slots"][i] = self._egg()
        self.save()
        return None

    def take_egg(self, i, level):
        """The den's "Leave this spot empty": only an egg that hasn't hatched, and never the first spot's."""
        if not 0 < i < min(len(self.s["slots"]), self.slot_count(level)):
            return "the first spot always has an egg"
        if not self.s["slots"][i].get("egg"):
            return "only an egg that hasn't hatched yet can be taken away"
        self.s["slots"][i] = {"empty": True}
        self.save()
        return None

    # ---- the collection, per country
    def cdata(self, c):
        d = self.s["countries"].setdefault(c, {})
        for k, v in (("collection", []), ("seen", {}), ("seenDates", {}), ("habitats", {})):
            d.setdefault(k, v)
        return d

    def score(self):
        return sum(e.get("points", 0) for d in self.s["countries"].values() for e in d.get("collection", []))

    def title(self):
        s = self.score()
        return [t for t in TITLES if s >= t[0]][-1][2]

    # ---- choosing a species (Bookworm's pickSpecies)
    def _butterflies(self, c):
        sp = data()["countries"][c]["by_id"]
        return sum(1 for e in self.cdata(c)["collection"] if sp.get(e["species"], {}).get("kind") == "butterfly")

    def unlocked_kinds(self, c):
        n = self._butterflies(c)
        return {"butterfly"} | {u["kind"] for u in data()["countries"][c]["unlocks"] if n >= u["n"]}

    def _missing_forms(self, c, sp):
        if any(x.get("species") == sp["id"] and x.get("country") == c for x in self.s["slots"]):
            return []
        coll = self.cdata(c)["collection"]
        if not sp["forms"]:
            return [] if any(e["species"] == sp["id"] for e in coll) else [None]
        return [f for f in sp["forms"] if not any(e["species"] == sp["id"] and e.get("sex") == f for e in coll)]

    def _weighted(self, pool, month):
        w = [IN_SEASON_WEIGHT if month in s["months"] else 1 for s in pool]
        r = self.rng.random() * sum(w)
        for s, x in zip(pool, w):
            r -= x
            if r < 0:
                return s
        return pool[-1]

    def pick(self, c, tier, month=None):
        """{species, sex}; sex is "m"/"f" for species with forms, else None."""
        month = time.localtime().tm_mon - 1 if month is None else month
        species = data()["countries"][c]["species"]
        kinds = self.unlocked_kinds(c)
        pool = [s for s in species if s["rarity"] == tier and s["kind"] in kinds]
        fresh = [s for s in pool if self._missing_forms(c, s)]
        sex_for = lambda k: "m" if k == "m" else ("f" if k else None)   # noqa: E731
        if fresh:
            s = self._weighted(fresh, month)
            return {"species": s["id"], "sex": sex_for(self.rng.choice(self._missing_forms(c, s)))}
        s = self._weighted(pool or [x for x in species if x["rarity"] == tier], month)
        return {"species": s["id"], "sex": sex_for(self.rng.choice(s["forms"])) if s["forms"] else None}

    def roll_rarity(self):
        r = self.rng.random() * 100
        for tier, p in TIERS:
            r -= p
            if r < 0:
                return tier
        return "Common"

    growth = staticmethod(lambda: 1.0)       # the dragon's appetite (set by the app)

    def need(self, tier):
        """Food to raise one of this rarity: as set, or growing with his appetite if
        "Growing up: the Butterfly Garden's needs grow too" is on (for larvae from then on)."""
        g = self.growth() if tuning.get("garden_grows") >= 1 else 1.0
        return max(1.0, float(tuning.get("garden_food_" + tier.lower())) * g)

    # ---- feeding
    def feed(self, food, level, lair_code=None, belly_low=False, now=None):
        # (belly_low is no longer used: a larva's hunger is its own, by how long since it ate)
        """Spare food: snacks and feasts that don't fit in his belly, and treats and berries that fit
        in neither his belly nor his PACK. Split between everything in the garden."""
        now = now or time.time()
        if food <= 0 or not self.unlocked(level):
            return
        self.sync_slots(level, now)
        # an adult waiting to be collected doesn't eat: only eggs and larvae share the food
        slots = [(i, b) for i, b in enumerate(self.s["slots"][: self.slot_count(level)])
                 if not b.get("empty") and not b.get("adult")]
        if not slots:
            return
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        if self.s.get("fed_day") != day:
            self.s["fed_day"], self.s["fed_today"] = day, 0.0
        self.s["fed_today"] = self.s.get("fed_today", 0.0) + food
        share = food / len(slots)
        c = self.country(lair_code)
        for i, b in slots:
            if b.get("egg"):
                self._hatch(b, c, now)
            self._check_hunger(b, now)      # (did it go hungry before this meal?)
            b["last_fed"] = now
            b["fed"] = min(b["need"], b["fed"] + share)
            pct = 100 * b["fed"] / b["need"]
            stage = stage_for(pct, b["pupAt"])
            if stage >= 9 and b.get("stage", 0) < 9:
                b["pupated"] = now
                self._tell("pupate", b)
            b["stage"] = stage
            if pct >= 100:
                self._emerge(i, b, now)
        self.sync_slots(level, now)
        self.save()

    @staticmethod
    def hunger(b, now=None):
        """"well fed", "satisfied", "peckish", "hungry" or "very hungry" for a larva; None for an
        egg, a pupa or an adult."""
        if b.get("egg") or b.get("empty") or b.get("adult") or b.get("stage", 0) >= 9:
            return None
        since = (now or time.time()) - (b.get("last_fed") or b.get("hatched") or time.time())
        return ("well fed" if since < WELL_FED_S else "satisfied" if since < SATISFIED_S
                else "peckish" if since < PECKISH_S else "hungry" if since < HUNGRY_S else "very hungry")

    def _check_hunger(self, b, now):
        """A queen-to-be that went hungry becomes a worker (Bookworm's rule)."""
        if b.get("caste") and not b.get("hungry") and self.hunger(b, now) in ("hungry", "very hungry"):
            b["hungry"] = True
            return True
        return False

    def check_hunger(self, level, now=None):
        """Every few seconds, from the app: notices larvae that have gone hungry."""
        if not self.unlocked(level):
            return
        now = now or time.time()
        if any([self._check_hunger(b, now) for b in self.s["slots"]]):
            self.save()

    def note_belly(self, low, level):
        """(Older versions: the dragon's belly decided. Now each larva's own hunger does.)"""
        self.check_hunger(level)

    def _hatch(self, b, c, now):
        tier = self.roll_rarity()
        p = self.pick(c, tier)
        sp = data()["countries"][c]["by_id"][p["species"]]
        b.clear()
        b.update({"species": sp["id"], "country": c, "sex": p["sex"], "rarity": sp["rarity"], "need": self.need(sp["rarity"]),
                  "fed": 0.0, "pupAt": sp["pupAt"], "hatched": now, "stage": 0,
                  "caste": sp["caste"] and p["sex"] == "f", "hungry": False, "last_fed": now})
        self._tell("hatch", b)

    def _emerge(self, i, b, now):
        """The adult emerges: it stays in its spot at 100% until it's collected from the den."""
        c = b["country"]
        sp = data()["countries"][c]["by_id"][b["species"]]
        b["form"] = ("w" if b.get("hungry") else "q") if b.get("caste") else (b.get("sex") or None)
        b.update(adult=True, emerged=now, stage=10, fed=b["need"])
        is_new = not any(e["species"] == sp["id"] for e in self.cdata(c)["collection"])
        self._tell("emerge", dict(b, new=is_new, name=sp["name"]))

    def collect(self, i, level, now=None):
        """The den's "tap to add to Collection": the adult joins the collection of the country it
        hatched in (wherever the garden has moved since), may open a habitat and earns its points.
        Its spot is freed: the larvae below move up one, and the last spot is left empty (or gets
        a new egg, if it's the only spot)."""
        now = now or time.time()
        slots = self.s["slots"]
        if not 0 <= i < len(slots) or not slots[i].get("adult"):
            return "there's no adult in that spot"
        b = slots[i]
        c = b["country"]
        sp = data()["countries"][c]["by_id"][b["species"]]
        form = b.get("form")
        coll = self.cdata(c)["collection"]
        is_new = not any(e["species"] == sp["id"] for e in coll)
        points = data()["points"][sp["rarity"]]
        entry = {"species": sp["id"], "country": c, "points": points,
                 "title": "Raised in the Butterfly Garden", "author": "", "isbn": "", "pages": 0,
                 "started": iso(b.get("hatched")), "date": iso(now)}
        if form:
            entry["sex"] = form
        coll.append(entry)
        habitat = next((h for h in sp["habitats"] if h not in self.cdata(c)["habitats"]), None)
        if habitat:
            self.cdata(c)["habitats"][habitat] = iso(now)
        del slots[i]
        slots.append({"empty": True})
        self.sync_slots(level, now)          # (the first spot always gets an egg, if it's now empty)
        self.save()
        self._tell("collect", dict(b, form=form, new=is_new, habitat=habitat, name=sp["name"], points=points))
        for n, tid, name in TITLES:
            if n > 0 and self.score() >= n and tid not in self.s["titles"]:
                self.s["titles"][tid] = iso(now)
                self._tell("title", {"name": name})
        self.save()
        return None

    def _tell(self, kind, info):
        if self.on_event:
            try:
                self.on_event(kind, info)
            except Exception:
                log.exception("garden event")

    # ---- for the den
    def view(self, level, lair_code=None):
        c = self.country(lair_code)
        out = {"unlocked": self.unlocked(level), "forced": bool(self.s.get("forced")), "level": level,
               "unlock_level": UNLOCK_LEVEL, "slots": self.slot_count(level), "max": MAX_SLOTS,
               "country": c, "country_name": COUNTRY_NAME[c],
               "score": self.score(), "title": self.title(),
               "raised": len(self.cdata(c)["collection"]), "larvae": [],
               "fed_today": round(self.s.get("fed_today", 0.0), 1) if self.s.get("fed_day") == time.strftime("%Y-%m-%d") else 0}
        if out["unlocked"]:
            self.sync_slots(level)
        for i, b in enumerate(self.s["slots"][: out["slots"]]):
            if b.get("empty"):
                out["larvae"].append({"empty": True, "slot": i})
                continue
            if b.get("egg"):
                out["larvae"].append({"egg": True, "slot": i})
                continue
            sp = data()["countries"][b["country"]]["by_id"][b["species"]]
            pct = 100 * b["fed"] / b["need"]
            out["larvae"].append({
                "egg": False, "species": sp["id"], "name": sp["name"], "sci": sp["sci"], "kind": sp["kind"],
                "noun": sp["noun"], "young": sp["young"], "pupa": sp["pupa"], "rarity": b["rarity"],
                "pct": round(pct, 1), "pupAt": b["pupAt"], "stage": b.get("stage", 0),
                "sex": b.get("sex"), "caste": b.get("caste"), "hungry": b.get("hungry"),
                "hunger": self.hunger(b), "last_fed": int(b.get("last_fed") or b.get("hatched") or 0),
                "fed": round(b["fed"], 1), "need": b["need"], "country": b["country"], "slot": i,
                "adult": bool(b.get("adult")), "form": b.get("form"),
                "country_name": COUNTRY_NAME.get(b["country"], "")})
        return out

    def _save_for(self, c):
        d = self.cdata(c)
        return {"books": [], "waiting": [], "collection": d["collection"], "seen": d["seen"],
                "seenDates": d["seenDates"], "habitats": d["habitats"], "habitatRule": 2,
                "achievements": {}, "offset": 0, "wtr": []}

    def page_data(self, c):
        """What shim.js writes in for Bookworm's page: every country's save (Bookworm's score
        counts them all), with `c` the one showing."""
        meta = data()["countries"]
        return {"country": c, "lang": meta[c]["lang"], "key": meta[c]["key"], "titles": self.s["titles"],
                "titleNames": [t[2] for t in TITLES],
                "saves": {meta[x]["key"]: self._save_for(x) for x in COUNTRY_NAME}}

    def set_seen(self, c, seen, dates):
        if c not in COUNTRY_NAME or not isinstance(seen, dict) or not isinstance(dates, dict):
            return "bad sightings"
        d = self.cdata(c)
        d["seen"], d["seenDates"] = seen, dates
        self.save()
        return None
