"""
The Tadpole Pond: a small pond in Harald's garden for raising amphibians (frogs, toads, newts
and salamanders) on spare food, one at a time. It opens at level 8.

The life cycle, as the pond shows it:
  spawn (eggs)  ->  tadpole or larva  ->  back legs, then front legs  ->  froglet, toadlet, eft
  or juvenile (leaving the water)  ->  adult, waiting to be added to the Pond Collection
Frog and toad tadpoles grow their back legs first; newt and salamander larvae are the other
way round, front legs first, and breathe with feathery gills on the outside of the head until
they leave the water. (The stages' places along the progress bar are the pond's own, for the
picture: real tadpoles take anything from two weeks to three years.)

Food: like the garden's larvae, it eats Harald's spare food (snacks and feasts that don't fit in
his BELLY, treats and berries that fit in neither the BELLY nor the PACK). Shared with the
garden as one more mouth, or first, with "Priority for spare food" (see app._garden_feed).

The daily limit: instead of the garden's 24 hours as a pupa, an amphibian can eat at most a
quarter of its whole progress bar (25%, Developer Tools) in a day, worked out at hatching and
again at midnight: its limit for the day is where it was at the start of the day, plus 25%. One
that had only reached 10% by midnight can eat up to 35% the next day. So it takes four days at
the very least: there are only a few species in each country, so each one is worth a wait.

The Pond Collection page (/pond, pond.html) is modelled on the Butterfly Garden's Collection:
the species of the country by kind, with sightings ("I've seen it!"), habitats that open as
species from them are raised, and a card for each species with its field notes, checked
against the sources listed on it (pond_species.json; all checked in October 2026).

Which species: the garden's country (United Kingdom, Ireland, United States or Canada), from
pond_species.json: native amphibians whose young grow up in water. Left out on purpose:
salamanders that hatch on land as tiny adults (the red-backed salamander and its lungless
cousins: no water stage to raise), and the ones that never leave the water (mudpuppies,
hellbenders, sirens). Rarity is rolled as in the garden (60/30/10), a species not raised yet is
picked first, and one whose eggs are laid in this month is three times as likely.
"""
import json
import os
import random
import time

from . import tuning

UNLOCK_LEVEL = 8
TIERS = (("Common", 60), ("Uncommon", 30), ("Rare", 10))
IN_SEASON_WEIGHT = 3
POINTS = {"Common": 100, "Uncommon": 200, "Rare": 300}
KEY = "pond"
# where each stage starts, in % of the progress bar
STAGES = {
    "frog": [(0, "tadpole"), (40, "tadpole with back legs"), (65, "tadpole with four legs"), (85, "meta")],
    "newt": [(0, "larva with feathery gills"), (35, "larva with front legs"), (60, "larva with four legs"), (85, "meta")],
}
STAGES["toad"], STAGES["salamander"] = STAGES["frog"], STAGES["newt"]

_DATA = None


def data():
    global _DATA
    if _DATA is None:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pond_species.json"), encoding="utf-8") as f:
            raw = json.load(f)
        _DATA = {c: {"species": lst, "by_id": {s["id"]: s for s in lst}} for c, lst in raw.items()}
    return _DATA


def stage(kind, pct):
    """(number 1-4, words) of a young one at `pct` (5 = adult)."""
    if pct >= 100 - 1e-6:
        return 5, "adult"
    st = STAGES[kind]
    k = max(i for i, (at, _) in enumerate(st) if pct >= at)
    return k + 1, st[k][1]


def _day(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


class Pond:
    def __init__(self, store, rng=None):
        self.store = store
        self.rng = rng or random.Random()
        self.s = store.get(KEY) or {}
        self.s.setdefault("slot", {"egg": True})
        self.s.setdefault("collection", {})       # country -> [{species, date, points}]
        self.s.setdefault("seen", {})             # country -> {species: when you said you'd seen it}
        self.s.setdefault("habitats", {})         # country -> {habitat: when it opened}
        self.on_event = None                      # (kind, info): "hatch", "legs", "meta", "adult", "collect"

    def save(self):
        self.store.put(KEY, self.s)

    # ---- open?
    def unlocked(self, level):
        return self.s.get("unlocked_at") is not None or level >= UNLOCK_LEVEL

    def unlock_now(self, level):
        if self.s.get("unlocked_at") is None and level < UNLOCK_LEVEL:
            self.s["unlocked_at"], self.s["forced"] = level, True
            self.save()

    def lock_again(self):
        if self.s.get("forced"):
            self.s["unlocked_at"], self.s["forced"] = None, False
            self.save()

    # ---- food
    def need(self, tier):
        g = self.growth() if tuning.get("garden_grows") >= 1 else 1.0
        return max(1.0, float(tuning.get("pond_food_" + tier.lower())) * g)

    growth = staticmethod(lambda: 1.0)       # the dragon's appetite (set by the app)

    def _limit(self, b, now):
        """Today's limit, in food: where it was at the start of the day (or at hatching), plus
        the daily share of the whole bar."""
        today = _day(now)
        if b.get("cap_day") != today:
            b["cap_day"], b["cap_from"] = today, b["fed"]
        return min(b["need"], b["cap_from"] + b["need"] * tuning.get("pond_daily_pct") / 100)

    def eats(self, level):
        """Is there something in the pond that eats? (An egg does: the first food hatches it.)"""
        b = self.s["slot"]
        return self.unlocked(level) and not b.get("adult")

    def room(self, level, now=None):
        """How much it could still eat today (an egg: it hatches, so at least something)."""
        now = now or time.time()
        if not self.eats(level):
            return 0.0
        b = self.s["slot"]
        if b.get("egg"):
            return float("inf")
        return max(0.0, self._limit(b, now) - b["fed"])

    def feed(self, food, level, country, now=None):
        """Returns how much was eaten (never more than today's limit)."""
        now = now or time.time()
        if food <= 0 or not self.eats(level):
            return 0.0
        b = self.s["slot"]
        if b.get("egg"):
            self._hatch(country, now)
            b = self.s["slot"]
        before, k0 = b["fed"], stage(b["kind"], self.pct(b))[0]
        b["fed"] = min(self._limit(b, now), b["fed"] + food)
        eaten = max(0.0, b["fed"] - before)
        if eaten:
            b["last_fed"] = now
        day = _day(now)
        if self.s.get("fed_day") != day:
            self.s["fed_day"], self.s["fed_today"] = day, 0.0
        self.s["fed_today"] = self.s.get("fed_today", 0.0) + eaten
        k1 = stage(b["kind"], self.pct(b))[0]
        for k in range(k0 + 1, k1 + 1):              # (each stage reached, in order)
            if k == 5:
                b.update(adult=True, grown=now)
                is_new = not any(e["species"] == b["species"] for e in self.collection(b["country"]))
                self._tell("adult", dict(b, new=is_new))
            elif k == 4:
                self._tell("meta", b)
            else:
                self._tell("legs", dict(b, k=k))
        self.save()
        return eaten

    @staticmethod
    def pct(b):
        return 100.0 if b.get("adult") else 100 * b["fed"] / b["need"] + 1e-6 if b.get("need") else 0.0

    # ---- choosing a species
    def roll_rarity(self):
        r = self.rng.random() * 100
        for tier, p in TIERS:
            r -= p
            if r < 0:
                return tier
        return "Common"

    def pick(self, c, tier, month=None):
        month = time.localtime().tm_mon - 1 if month is None else month
        species = data()[c]["species"]
        pool = [s for s in species if s["rarity"] == tier] or species
        raised = {e["species"] for e in self.collection(c)}
        fresh = [s for s in pool if s["id"] not in raised] or pool
        w = [IN_SEASON_WEIGHT if month in s["months"] else 1 for s in fresh]
        r = self.rng.random() * sum(w)
        for s, x in zip(fresh, w):
            r -= x
            if r < 0:
                return s
        return fresh[-1]

    def _hatch(self, c, now):
        c = c if c in data() else "gb"
        sp = self.pick(c, self.roll_rarity())
        self.s["slot"] = {"species": sp["id"], "country": c, "kind": sp["kind"], "rarity": sp["rarity"],
                          "need": self.need(sp["rarity"]), "fed": 0.0, "hatched": now, "last_fed": now,
                          "cap_day": _day(now), "cap_from": 0.0}
        self._tell("hatch", self.s["slot"])

    # ---- the collection
    def collection(self, c):
        return self.s["collection"].setdefault(c, [])

    def score(self):
        return sum(e.get("points", 0) for lst in self.s["collection"].values() for e in lst)

    def collect(self, now=None):
        """The Den's "add to the Pond Collection": the adult leaves, and new spawn appears."""
        now = now or time.time()
        b = self.s["slot"]
        if not b.get("adult"):
            return "there's no grown-up amphibian to add yet"
        sp = data()[b["country"]]["by_id"][b["species"]]
        is_new = not any(e["species"] == sp["id"] for e in self.collection(b["country"]))
        pts = POINTS[sp["rarity"]]
        self.collection(b["country"]).append({"species": sp["id"], "date": int(now), "hatched": int(b.get("hatched") or now),
                                              "points": pts})
        # as in the garden: the first of its habitats not open yet opens
        opened = self.s["habitats"].setdefault(b["country"], {})
        habitat = next((h for h in sp["habitats"] if h not in opened), None)
        if habitat:
            opened[habitat] = int(now)
        self.s["slot"] = {"egg": True}
        self.save()
        self._tell("collect", dict(b, new=is_new, points=pts, habitat=habitat))
        return None

    def set_seen(self, c, sid, on, now=None):
        """The Pond Collection's "I've seen it!" (in the wild): on or off."""
        if c not in data() or sid not in data()[c]["by_id"]:
            return "no such species"
        seen = self.s["seen"].setdefault(c, {})
        if on:
            seen.setdefault(sid, int(now or time.time()))
        else:
            seen.pop(sid, None)
        self.save()
        return None

    def page_data(self, c, name="Harald", habitat_names=None):
        """Everything the Pond Collection page shows, for country `c`."""
        c = c if c in data() else "gb"
        raised = {}
        for e in self.collection(c):
            raised.setdefault(e["species"], []).append(e)
        seen = self.s["seen"].get(c, {})
        b = self.s["slot"]
        growing = None
        if not b.get("egg") and b.get("country") == c:
            growing = {"species": b["species"], "pct": round(min(100.0, self.pct(b)), 1), "adult": bool(b.get("adult")),
                       "stage": stage(b["kind"], self.pct(b))[0]}
        return {"name": name, "country": c, "score": self.score(), "points": POINTS,
                "species": data()[c]["species"], "habitat_names": habitat_names or {},
                "habitats_open": self.s["habitats"].get(c, {}),
                "raised": {k: [{"date": e["date"], "hatched": e.get("hatched"), "points": e.get("points", 0)} for e in v]
                           for k, v in raised.items()},
                "seen": seen, "growing": growing, "month": time.localtime().tm_mon - 1}

    def _tell(self, kind, info):
        if self.on_event:
            try:
                info = dict(info)
                sp = data()[info["country"]]["by_id"][info["species"]]
                info.update(name=sp["name"], young=sp["young"], meta=sp["meta"])
                self.on_event(kind, info)
            except Exception:
                pass

    # ---- for the Den
    def view(self, level, country, now=None):
        now = now or time.time()
        c = country if country in data() else "gb"
        out = {"unlocked": self.unlocked(level), "forced": bool(self.s.get("forced")), "level": level,
               "unlock_level": UNLOCK_LEVEL, "daily_pct": tuning.get("pond_daily_pct"),
               "score": self.score(), "country": c,
               "fed_today": round(self.s.get("fed_today", 0.0), 1) if self.s.get("fed_day") == _day(now) else 0,
               "slot": None, "collection": [], "total": len(data()[c]["species"])}
        b = self.s["slot"]
        if b.get("egg"):
            out["slot"] = {"egg": True}
        else:
            sp = data()[b["country"]]["by_id"][b["species"]]
            pct = self.pct(b)
            k, words = stage(b["kind"], pct)
            limit = self._limit(b, now)
            out["slot"] = {"species": sp["id"], "name": sp["name"], "sci": sp["sci"], "kind": sp["kind"],
                           "rarity": b["rarity"], "young": sp["young"], "meta": sp["meta"], "fact": sp["facts"][0],
                           "pct": round(min(100.0, pct), 1), "stage": k,
                           "stage_words": sp["meta"] if words == "meta" else words,
                           "limit_pct": round(100 * limit / b["need"], 1), "full_today": not b.get("adult") and b["fed"] >= limit - 1e-6,
                           "adult": bool(b.get("adult")), "country": b["country"], "last_fed": int(b.get("last_fed") or 0),
                           "stages": [[at, sp["meta"] if w == "meta" else w] for at, w in STAGES[sp["kind"]]]}
        by = data()[c]["by_id"]
        counts = {}
        for e in self.collection(c):
            counts.setdefault(e["species"], []).append(e["date"])
        out["raised_species"] = sum(1 for s in by if counts.get(s))
        out["raised"] = len(self.collection(c))
        return out
