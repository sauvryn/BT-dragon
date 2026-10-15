"""
The Butterfly Garden: raising insects from Harald's surplus food (from the Bookworm project).

Locked until Harald reaches level 5 (or "Unlock now" in the den, for testing). It holds one
larva at first, and one more for each level he gains after it opened, up to three.

Feeding: treats and berries go into his BELLY, then his PACK; anything that fits in neither
used to be wasted. Now it feeds the garden, split evenly between whatever is growing there,
so raising three at once means each grows a third as fast.

A larva's life, as in Bookworm:
  - an egg waits in each free spot; the first food hatches it, and only then is its species
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
  - queens and workers: a female of a social species becomes a queen if Harald's belly never
    ran low while she was a larva, and a worker if it did.

The collection is kept per country (Bookworm's countries: United Kingdom, Ireland, United
States, Canada), following the Lair's country, or a choice in the den for anywhere else.
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

    def save(self):
        self.store.put("garden", self.s)

    # ---- where, and is it open
    def country(self, lair_code=None):
        return COUNTRY_OF.get((lair_code or "").upper()) or self.s.get("country") or "gb"

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

    def sync_slots(self, level, now=None):
        """An egg in every free spot."""
        n = self.slot_count(level)
        changed = False
        while len(self.s["slots"]) < n:
            self.s["slots"].append({"egg": True, "laid": now or time.time(), "fed": 0.0})
            changed = True
        if changed:
            self.save()

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

    @staticmethod
    def need(tier):
        return max(1.0, float(tuning.get("garden_food_" + tier.lower())))

    # ---- feeding
    def feed(self, food, level, lair_code=None, belly_low=False, now=None):
        """Surplus food from treats and berries: split between everything in the garden."""
        now = now or time.time()
        if food <= 0 or not self.unlocked(level):
            return
        self.sync_slots(level, now)
        slots = self.s["slots"][: self.slot_count(level)]
        if not slots:
            return
        share = food / len(slots)
        c = self.country(lair_code)
        for i, b in enumerate(slots):
            if b.get("egg"):
                self._hatch(b, c, now)
            if belly_low and b.get("caste") and b.get("stage", 0) < 9:
                b["hungry"] = True
            b["fed"] = min(b["need"], b["fed"] + share)
            pct = 100 * b["fed"] / b["need"]
            stage = stage_for(pct, b["pupAt"])
            if stage >= 9 and b.get("stage", 0) < 9:
                b["pupated"] = now
                self._tell("pupate", b)
            b["stage"] = stage
            if pct >= 100:
                self._emerge(i, b, now)
        self.s["slots"] = [b for b in self.s["slots"] if not b.get("done")]
        self.sync_slots(level, now)
        self.save()

    def note_belly(self, low, level):
        """Harald's belly ran low: any queen-to-be still growing becomes a worker."""
        if not low or not self.unlocked(level):
            return
        changed = False
        for b in self.s["slots"]:
            if b.get("caste") and not b.get("egg") and b.get("stage", 0) < 9 and not b.get("hungry"):
                b["hungry"] = changed = True
        if changed:
            self.save()

    def _hatch(self, b, c, now):
        tier = self.roll_rarity()
        p = self.pick(c, tier)
        sp = data()["countries"][c]["by_id"][p["species"]]
        b.clear()
        b.update({"species": sp["id"], "country": c, "sex": p["sex"], "rarity": sp["rarity"], "need": self.need(sp["rarity"]),
                  "fed": 0.0, "pupAt": sp["pupAt"], "hatched": now, "stage": 0,
                  "caste": sp["caste"] and p["sex"] == "f", "hungry": False})
        self._tell("hatch", b)

    def _emerge(self, i, b, now):
        c = b["country"]
        sp = data()["countries"][c]["by_id"][b["species"]]
        form = ("w" if b.get("hungry") else "q") if b.get("caste") else (b.get("sex") or None)
        coll = self.cdata(c)["collection"]
        is_new = not any(e["species"] == sp["id"] for e in coll)
        entry = {"species": sp["id"], "country": c, "points": data()["points"][sp["rarity"]],
                 "title": "Raised in the Butterfly Garden", "author": "", "isbn": "", "pages": 0,
                 "started": iso(b.get("hatched")), "date": iso(now)}
        if form:
            entry["sex"] = form
        coll.append(entry)
        habitat = next((h for h in sp["habitats"] if h not in self.cdata(c)["habitats"]), None)
        if habitat:
            self.cdata(c)["habitats"][habitat] = iso(now)
        b["done"] = True
        self._tell("emerge", dict(b, form=form, new=is_new, habitat=habitat, name=sp["name"]))
        for n, tid, name in TITLES:
            if n > 0 and self.score() >= n and tid not in self.s["titles"]:
                self.s["titles"][tid] = iso(now)
                self._tell("title", {"name": name})

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
               "country": c, "country_name": COUNTRY_NAME[c], "from_lair": bool(COUNTRY_OF.get((lair_code or "").upper())),
               "score": self.score(), "title": self.title(),
               "raised": len(self.cdata(c)["collection"]), "larvae": []}
        if out["unlocked"]:
            self.sync_slots(level)
        for b in self.s["slots"][: out["slots"]]:
            if b.get("egg"):
                out["larvae"].append({"egg": True})
                continue
            sp = data()["countries"][b["country"]]["by_id"][b["species"]]
            pct = 100 * b["fed"] / b["need"]
            out["larvae"].append({
                "egg": False, "species": sp["id"], "name": sp["name"], "sci": sp["sci"], "kind": sp["kind"],
                "noun": sp["noun"], "young": sp["young"], "pupa": sp["pupa"], "rarity": b["rarity"],
                "pct": round(pct, 1), "pupAt": b["pupAt"], "stage": b.get("stage", 0),
                "sex": b.get("sex"), "caste": b.get("caste"), "hungry": b.get("hungry"),
                "fed": round(b["fed"], 1), "need": b["need"], "country": b["country"]})
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
