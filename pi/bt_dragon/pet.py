"""
Harald's body and feelings: two separate meters.

  FOOD (hunger)  0 = starving .. 100 = stuffed. Drops 1 point every 90 seconds, so a full
                 belly lasts about 2.5 hours (hunger_minutes in the config file).
  JOY            0 = sad .. 100 = happy. Drops 1 point every 10 minutes.

They're independent, so he can be hungry and happy (a long walk through a quiet park)
or stuffed and bored (a day at home next to the same old devices). Food fills FOOD and
gives a little JOY; new things, friends and adventures are what really give JOY.

FOOD
  snack     a new arrival: a fixed-address gadget he hasn't eaten  +2 food   +0.3 joy  +1 XP
            today, or one more phone/watch/earbud of a kind than were
            already around (rotating addresses are counted by heads,
            so a phone changing its address isn't a new meal)
  feast     a species he has never eaten before                  +12 food  +8 joy    +20 XP
  treat     a Wi-Fi network he has never seen before             +4 food   +2 joy    +5 XP
            (rarer kinds are worth more: open/WEP +6, WPA3/office +5)
  berries   a network he already knows: like a berry bush, it regrows one point per
            day since he last picked it, up to its full treat value. Seen yesterday: +1,
            two days ago: +2, ... a week ago: full value again. Same day: nothing.

JOY
  adventure walking or running with Harald on     +3 joy and +2 XP per 100 m
            cycling with Harald                    +1.5 joy per 100 m
            riding in a vehicle with Harald        +1 joy per km
  story     steps your phone counted while Harald wasn't with you  +1 joy per 100 m
            ("You told Harald about your adventure!")
  friends   meeting a new dragon +15, a reunion +8; spotting a pal +3

level = 1 + sqrt(XP / 50): level 2 at 50 XP, 3 at 200, 5 at 800, 10 at 4050

The face: urgent things first (alarm, uploading, short reactions like a feast), then
starving or a sleepy night, otherwise his JOY picks the eyes and his FOOD can change the
mouth: drooling when hungry, a contented wobble when stuffed.
"""
import math
import time

from . import tuning

# All food, joy and XP numbers live in tuning.py (adjustable from the den's Developer
# tools). This is just what he says about each kind of treat.
TREAT_NOTE = {"open": "AN OPEN ONE!", "wep": "RETRO WEP!", "wpa3": "WPA3, FANCY",
              "enterprise": "AN OFFICE ONE", "wpa2": ""}
TREAT_VALUE = TREAT_NOTE  # the kinds of treat


def per_meter(kind):
    """(joy, XP) per meter traveled together, by how you were moving."""
    g = tuning.get
    return {"walking": (g("walk_joy") / 100, g("walk_xp") / 100),
            "running": (g("walk_joy") / 100, g("walk_xp") / 100),
            "cycling": (g("cycle_joy") / 100, g("cycle_xp") / 100),
            "vehicle": (g("ride_joy") / 1000, g("ride_xp") / 1000)}.get(kind, (0.0, 0.0))


def level_for(xp):
    return 1 + int(math.sqrt(max(0, xp) / tuning.get("xp_curve")))


def xp_for(level):
    return math.ceil(tuning.get("xp_curve") * (level - 1) ** 2)


def treat_food(security):
    sec = security if security in TREAT_VALUE else "wpa2"
    return tuning.get("treat_food_" + sec)


def berry_value(security, days):
    """Food from a known network last seen `days` calendar days ago."""
    base = treat_food(security)
    v = max(0.0, min(base, days * tuning.get("berry_per_day")))
    return int(v) if v == int(v) else round(v, 1)


STATUS_W = 222  # pixels free on the e-ink status line with both link icons showing


def _fit(options):
    """The first wording that fits the e-ink status line. If none do, the last one is
    shortened a whole word at a time (never mid-word) and ends in '..'."""
    from .fonts import text_width
    if isinstance(options, str):
        options = [options]
    for o in options:
        if text_width(o.upper()) <= STATUS_W:
            return o
    words = options[-1].split(" ")
    small = {"AND", "OF", "THE", "&", "FOR", "AT", "IN", "ON", "TO", "A", "AN", "DE", "LA"}
    while len(words) > 1:
        words.pop()
        while len(words) > 1 and words[-1].upper() in small:
            words.pop()           # "INSTITUTE AND.." reads worse than "INSTITUTE.."
        t = " ".join(words).rstrip(",:;-(") + ".."
        if text_width(t.upper()) <= STATUS_W:
            return t
    return options[-1]   # one enormous word: the screen trims it


def _n(v):
    """A food amount for messages: whole numbers stay whole, otherwise one decimal."""
    return str(int(round(v))) if abs(v - round(v)) < 0.05 else f"{v:.1f}"


def away_words(s):
    if s < 5400:
        return f"{round(s / 60)} MINUTES"
    if s < 172800:
        return f"{round(s / 3600)} HOURS"
    return f"{round(s / 86400)} DAYS"


def hunger_word(h):
    return "STARVING" if h < 10 else "HUNGRY" if h < 30 else "STUFFED" if h > 92 else "FED"


def joy_word(j):
    return "SAD" if j < 15 else "BORED" if j < 35 else "HAPPY" if j > 70 else "CONTENT"


class Pet:
    def __init__(self, store, name):
        self.store = store
        st = store.get("pet", {})
        self.name = (st.get("name") or name)[:10]
        self.xp = st.get("xp", 0)
        self.hunger = st.get("hunger", 60.0)
        self.pack = st.get("pack", 0.0)   # spare berries (see berries() and eat_from_pack())
        self.joy = st.get("joy", 50.0)
        self.total_meals = st.get("total_meals", 0)
        self.total_treats = st.get("total_treats", 0)
        self.born = st.get("born", time.time())
        # "today" counts survive restarts and updates, and start over at local midnight
        day = st.get("today", {})
        same_day = day.get("date") == time.strftime("%Y-%m-%d")
        self.session_meals = day.get("meals", 0) if same_day else 0
        self.session_treats = day.get("treats", 0) if same_day else 0
        self.session_species = day.get("species", 0) if same_day else 0
        self.lands_today = day.get("lands", 0) if same_day else 0
        self.stars_today = day.get("stars", 0) if same_day else 0
        self.climbed_today = day.get("climbed", 0.0) if same_day else 0.0
        self.storms_today = day.get("storms", 0) if same_day else 0
        self._day = time.strftime("%Y-%m-%d")
        self._pending_lands = 0
        self._pending_stars_again = []
        self._climb_said = 0.0
        self.reaction = None         # (mood, until)
        self.message = f"{self.name.upper()} WAKES UP. FEED ME!"
        self.message_ts = time.time()
        self._pending_snacks = 0
        # time between ticks is measured on the monotonic clock, which never jumps when the
        # Pi sets its clock from the network, so a clock fix can't fake hours passing
        self._last_tick = time.monotonic()
        self.saved_at = st.get("saved_at")   # wall-clock time of the last save before switch-off
        self.away_s = 0.0
        self.alarm = False
        self.uploading = False
        self.sleeping = False
        self.on_say = None           # callback(text or wordings, mood), for Harald's voice

    # ---------------------------------------------------------------- persistence
    def save(self):
        self.store.put("pet", {"name": self.name, "xp": self.xp, "hunger": round(self.hunger, 1), "pack": round(self.pack, 2),
                               "joy": round(self.joy, 1), "total_meals": self.total_meals,
                               "total_treats": self.total_treats, "born": self.born,
                               "saved_at": time.time(),
                               "today": {"date": self._day, "meals": self.session_meals,
                                         "treats": self.session_treats, "species": self.session_species,
                                         "lands": self.lands_today, "stars": self.stars_today,
                                         "climbed": round(self.climbed_today, 1),
                                         "storms": self.storms_today}})

    # ---------------------------------------------------------------- gains
    def _gain(self, hunger, xp, joy=0.0):
        """Add food, XP and joy. Returns True if he leveled up (and says so)."""
        before = level_for(self.xp)
        self.hunger = max(0.0, min(100.0, self.hunger + hunger))
        self.joy = max(0.0, min(100.0, self.joy + joy))
        # XP is whole points; fractions (berries, a few meters of walking) carry over
        self._xp_frac_carry = getattr(self, "_xp_frac_carry", 0.0) + xp
        whole = int(self._xp_frac_carry)
        self._xp_frac_carry -= whole
        self.xp += whole
        if level_for(self.xp) > before:
            self.joy = min(100.0, self.joy + tuning.get("levelup_joy"))
            self.say(f"LEVEL UP! {self.name.upper()} IS NOW LEVEL {level_for(self.xp)}", "proud", 60)
            self.store.event("level", f"{self.name} reached level {level_for(self.xp)}")
            return True
        return False

    def say(self, text, mood=None, seconds=20, speak=True):
        """Show a message on the status line. `text` may be a list of wordings, longest
        first: the first one that fits the screen is used. speak=False: the screen only,
        not the Echo Dot."""
        if self.on_say and speak:
            try:
                self.on_say(text, mood)   # the Echo Dot speaks the longest wording
            except Exception:
                pass
        text = _fit(text)
        # while the den address is being shown, faces still react but the text waits
        if time.time() >= getattr(self, "message_hold", 0):
            self.message, self.message_ts = text.upper(), time.time()
        if mood:
            self.reaction = (mood, time.time() + seconds)

    # ---------------------------------------------------------------- food
    def snack(self):
        """A new Bluetooth address. Snack messages are batched (see tick)."""
        self.session_meals += 1
        self.total_meals += 1
        self._pending_snacks += 1
        self._gain(tuning.get("snack_food"), tuning.get("snack_xp"), tuning.get("snack_joy"))

    def feast(self, label):
        self.session_species += 1
        if not self._gain(tuning.get("feast_food"), tuning.get("feast_xp"), tuning.get("feast_joy")):
            self.say([f"FEAST! NEW SPECIES: {label}", f"FEAST! {label}"], self.face_for(tuning.get("feast_joy")), 45)

    def treat(self, ap):
        self.session_treats += 1
        self.total_treats += 1
        sec = ap.get("security", "wpa2")
        sec = sec if sec in TREAT_NOTE else "wpa2"
        note = TREAT_NOTE[sec]
        food = treat_food(sec)
        packed = self._overflow(food)
        if not self._gain(food - packed, tuning.get("treat_xp_" + sec), tuning.get("treat_joy")):
            name = ap["ssid"] or "A HIDDEN ONE"
            tail = f" +{_n(packed)} IN HIS PACK" if packed else ""
            self.say(_fit([f"TREAT! {name}" + (f" ({note})" if note else "") + tail,
                           f"TREAT! {name}{tail}",
                           f"TREAT!{tail.replace(' IN HIS', ' IN')}: {name}"]), "treat", 25)
        return packed

    def _overflow(self, food):
        """Of `food`, how much doesn't fit in his belly; that much goes into his PACK
        (as far as it has room). Returns the amount packed; the rest is his to eat."""
        spare = max(0.0, food - max(0.0, 100.0 - self.hunger))
        packed = min(spare, max(0.0, tuning.get("pack_cap") - self.pack))
        self.pack += packed
        return packed

    def berries(self, food, bushes):
        """Known networks whose 'berries' have regrown since he last saw them."""
        if food <= 0:
            return 0
        # what doesn't fit in his belly goes into his PACK (until that's full too)
        eat = min(food, max(0.0, 100.0 - self.hunger))
        packed = min(food - eat, max(0.0, tuning.get("pack_cap") - self.pack))
        self.pack += packed
        if not self._gain(eat, tuning.get("berry_xp") * food, tuning.get("berry_joy") * food):
            if not self.reaction or self.reaction[1] < time.time():
                if packed and eat >= 0.5:
                    gains = [f"+{_n(eat)} FOOD, +{_n(packed)} IN HIS PACK", f"+{_n(eat)} FOOD, +{_n(packed)} IN PACK"]
                elif packed:
                    gains = [f"+{_n(packed)} INTO HIS PACK", f"+{_n(packed)} INTO PACK"]
                else:
                    gains = [f"+{_n(food)} FOOD"]
                nets = f"{bushes} KNOWN NETWORK{'S' if bushes != 1 else ''}"
                self.say(_fit([f"BERRIES! {nets} {g}" for g in gains]
                              + [f"BERRIES! {bushes} KNOWN {g}" for g in gains]
                              + [f"BERRIES! {g}" for g in gains]), "eating", 15)
        return packed

    def eat_from_pack(self):
        """
        When FOOD drops to the trigger, he eats a portion of his PACK (half, by default),
        never more than it takes to fill his belly. A small remainder is eaten whole, so
        the PACK doesn't halve forever into crumbs. Returns how much he ate.
        """
        if self.pack <= 0 or self.hunger > tuning.get("pack_trigger"):
            return 0.0
        bite = self.pack * tuning.get("pack_portion") / 100
        if bite < 1:
            bite = self.pack
        bite = min(bite, 100.0 - self.hunger)
        if bite <= 0:
            return 0.0
        self.pack -= bite
        if self.pack < 0.01:
            self.pack = 0.0
        self.hunger += bite
        return bite

    # ---------------------------------------------------------------- joy
    @staticmethod
    def face_for(joy):
        """Big joy boosts get the ecstatic face (big starry eyes), small ones the excited face."""
        return "ecstatic" if joy >= tuning.get("ecstatic_joy") else "excited"

    def cheer(self, joy, xp=0, text=None, mood=None, seconds=30):
        if mood in ("excited", "happy") and joy >= tuning.get("ecstatic_joy"):
            mood = "ecstatic"
        if not self._gain(0, xp, joy) and text:
            self.say(text, mood, seconds)

    # ---------------------------------------------------------------- the world around him
    def land(self, new_realm, riding=False):
        """A square of the map he's never been to (and maybe a whole new realm)."""
        k = tuning.get("land_vehicle_pct") / 100 if riding else 1.0
        self.lands_today += 1
        if new_realm:
            joy = tuning.get("realm_joy") * k
            if not self._gain(tuning.get("realm_food") * k, tuning.get("realm_xp") * k, joy):
                self.say(f"A NEW REALM! {self.name} CLAIMS IT", self.face_for(joy), 40)
        else:
            self._gain(tuning.get("land_food") * k, tuning.get("land_xp") * k, tuning.get("land_joy") * k)
            self._pending_lands += 1

    def stars(self, new, new_consts, risen):
        """Satellites: never-seen ones are food; known ones rising again are just joy."""
        for const in new_consts:
            joy = tuning.get("constellation_joy")
            if not self._gain(tuning.get("constellation_food"), tuning.get("constellation_xp"), joy):
                self.say(f"A NEW CONSTELLATION: {const.upper()}!", self.face_for(joy), 45)
        firsts = len(new) - len(new_consts)   # the constellation's first star was the feast
        if firsts > 0:
            joy = tuning.get("star_joy") * firsts
            self._gain(tuning.get("star_food") * firsts, tuning.get("star_xp") * firsts, joy)
            if not new_consts:
                c = new[-1][0].replace("-", " ").upper()
                self.say(f"A NEW STAR! {c}" if firsts == 1 else f"{firsts} NEW STARS IN THE SKY!",
                         self.face_for(joy), 30)
        if risen:
            self._gain(0, 0, tuning.get("star_again_joy") * len(risen))
            self._pending_stars_again.extend(risen)

    def landmark(self, title, first):
        joy = tuning.get("landmark_joy") if first else tuning.get("landmark_again_joy")
        xp = tuning.get("landmark_xp") if first else 0
        if not self._gain(0, xp, joy):
            t = title.upper()
            self.say([f"LOOK! {t}!", f"{t}!"], self.face_for(joy), 30)

    def green_found(self, name):
        if not self._gain(0, tuning.get("green_xp"), tuning.get("green_joy")):
            n = name.upper()
            self.say([f"A NEW GREEN SPACE: {n}!", f"NEW GREEN SPACE: {n}!", f"{n}!"], self.face_for(tuning.get("green_joy")), 30)

    def green_visit(self, words):
        """'Took a walk in Oakfield Country Park!'"""
        if not self._gain(0, tuning.get("green_visit_xp"), tuning.get("green_visit_joy")):
            self.say(words.upper(), self.face_for(tuning.get("green_visit_joy")), 45)

    MOON_WORDS = {
        "full": ["MANI SHINES! FULL MOON TONIGHT", "FULL MOON TONIGHT!"],
        "new": ["HATI HAS HIDDEN MANI... NEW MOON", "NEW MOON TONIGHT"],
        "first quarter": ["MANI GROWS! FIRST QUARTER MOON", "FIRST QUARTER MOON"],
        "last quarter": ["HATI GAINS ON MANI: LAST QUARTER", "LAST QUARTER MOON"],
    }

    def moon(self, phase):
        joy = tuning.get("moon_full_joy") if phase == "full" else tuning.get("moon_phase_joy")
        if not self._gain(0, tuning.get("moon_xp"), joy):
            self.say(self.MOON_WORDS[phase], self.face_for(joy), 45)

    def storm(self, hpa_change):
        first = self.storms_today == 0
        self.storms_today += 1
        joy = tuning.get("storm_first_joy") if first else tuning.get("storm_joy")
        if not self._gain(0, tuning.get("storm_xp"), joy):
            self.say(f"A STORM IS COMING! ({hpa_change:+.1f} HPA)", self.face_for(joy), 45)

    def weather_change(self, hpa_change):
        joy = tuning.get("rise_joy")
        if not self._gain(0, tuning.get("storm_xp"), joy):
            self.say("LOOKS LIKE A WEATHER CHANGE SOON!", self.face_for(joy), 40)

    def sunny(self):
        joy = tuning.get("sunny_joy")
        if not self._gain(0, 0, joy):
            self.say(["WOW! IT'S SUNNY OUT TODAY!", "WOW! SUNSHINE!"], "happy", 40)

    def climb(self, meters):
        self.climbed_today += meters
        joy = tuning.get("climb_joy") * meters / 10
        self._gain(0, tuning.get("climb_xp") * meters / 10, joy)
        if time.time() - self._climb_said > 60:
            self._climb_said = time.time()
            if not self.reaction or self.reaction[1] < time.time():
                self.say(f"CLIMBING! {self.climbed_today:.0f} M UP TODAY", self.face_for(joy), 20)

    def pal(self, name):
        self.cheer(tuning.get("pal_joy"), tuning.get("pal_xp"), f"THERE'S MY PAL {name}!", "happy", 20)

    def adventure(self, meters_by_mode):
        """Distance traveled with Harald switched on and carried along."""
        joy = xp = 0.0
        for mode, m in meters_by_mode.items():
            j, x = per_meter(mode)
            joy += j * m
            xp += x * m
        self._gain(0, xp, joy)

    def story(self, meters, steps):
        """Steps the phone counted while Harald wasn't along."""
        joy = min(tuning.get("story_cap"), meters * tuning.get("story_joy") / 100)
        self._gain(0, meters * tuning.get("story_xp") / 100, joy)
        self.say([f"YOU TOLD {self.name} ABOUT YOUR ADVENTURE! ({steps:,} STEPS)",
                  f"YOU TOLD {self.name} ABOUT YOUR ADVENTURE!", f"TOLD {self.name} ABOUT YOUR ADVENTURE!"], "happy", 40)

    # ---------------------------------------------------------------- time passes
    def catch_up(self, started_at):
        """
        Time passes while he's switched off, too. `started_at` is when this run began, on
        a clock known to be right; the gap since his last save before that is time he
        spent without food or anything new, so both meters drop as if he'd been awake.
        """
        if not self.saved_at:
            return 0.0
        gap = started_at - self.saved_at
        if gap < 120:
            return 0.0
        self.away_s = gap
        # FOOD drops through the gap; each time it reaches the trigger he digs into his PACK,
        # just as he would have if he'd been awake
        per_s = 100 / (tuning.get("food_empty_min") * 60) * tuning.get("food_off_drain") / 100
        left, self.pack_eaten_away = gap, 0.0
        while left > 0 and per_s > 0:
            to_trigger = (self.hunger - tuning.get("pack_trigger")) / per_s
            if self.pack <= 0 or to_trigger >= left:
                self.hunger = max(0.0, self.hunger - left * per_s)
                break
            step = max(0.0, to_trigger)
            self.hunger -= step * per_s
            left -= step
            bite = self.eat_from_pack()
            self.pack_eaten_away += bite
            if bite <= 0:
                self.hunger = max(0.0, self.hunger - left * per_s)
                break
        self.joy = max(0.0, self.joy - gap * 100 / (tuning.get("joy_empty_min") * 60)
                       * tuning.get("joy_off_drain") / 100)
        if gap >= 1800:
            self.say(f"YOU'RE BACK! I WAS ASLEEP FOR {away_words(gap)}", "happy" if self.hunger >= 10 else None, 30)
        return gap

    def tick(self, devices_in_range):
        now = time.time()
        mono = time.monotonic()
        dt = mono - self._last_tick
        self._last_tick = mono
        today = time.strftime("%Y-%m-%d")
        if today != self._day:  # midnight: a new day of eating begins
            self._day = today
            self.session_meals = self.session_treats = self.session_species = 0
            self.lands_today = self.stars_today = self.storms_today = 0
            self.climbed_today = 0.0
        # "empties in N minutes" = 100 points over N*60 seconds
        self.hunger = max(0.0, self.hunger - dt * 100 / (tuning.get("food_empty_min") * 60))
        self.joy = max(0.0, self.joy - dt * 100 / (tuning.get("joy_empty_min") * 60))
        bite = self.eat_from_pack()
        if bite:
            self.say([f"{self.name} DIGS INTO HIS PACK! +{_n(bite)} FOOD", f"DIGGING INTO HIS PACK! +{_n(bite)} FOOD"],
                     "eating", 20)
            self.store.event("pack", f"{self.name} ate {_n(bite)} food from his pack ({_n(self.pack)} left)")
        free = not self.reaction or self.reaction[1] < now
        if self._pending_lands:
            n, self._pending_lands = self._pending_lands, 0
            if free:
                self.say("NEW LAND CLAIMED!" if n == 1 else f"{n} NEW LANDS CLAIMED!", "excited", 20)
                free = False
        if self._pending_stars_again:
            risen, self._pending_stars_again = self._pending_stars_again, []
            if free:
                if len(risen) == 1:
                    self.say(f"A STAR RISES! {risen[0].replace('-', ' ').upper()}", "excited", 15)
                else:
                    self.say(f"{len(risen)} STARS RISING!", "excited", 15)
                free = False
        if self._pending_snacks:
            n = self._pending_snacks
            self._pending_snacks = 0
            if not self.reaction or self.reaction[1] < now or self.reaction[0] == "eating":
                self.say(f"NOM! {n} NEW SNACK{'S' if n != 1 else ''}", "eating", 15)
        self.devices_in_range = devices_in_range
        if now < getattr(self, "message_hold", 0):
            return
        if now - self.message_ts > 120:  # idle chatter replaces stale messages
            self._idle_n = getattr(self, "_idle_n", 0) + 1
            if self._idle_n % 3 == 0 and getattr(self, "den_hint", None):
                self.message, self.message_ts = self.den_hint, now  # every third idle line
                return
            h, j = hunger_word(self.hunger), joy_word(self.joy)
            extra = {
                "STARVING": "TAKE ME SOMEWHERE BUSY",
                "SAD": "A WALK WOULD CHEER ME UP",
                "BORED": "LET'S GO EXPLORING?",
            }
            tip = extra.get(h) or extra.get(j) or f"{len(devices_in_range)} DEVICES NEARBY"
            self.message, self.message_ts = f"{h} AND {j}. {tip}", now

    def feeling(self):
        return f"{hunger_word(self.hunger)} AND {joy_word(self.joy)}"

    def mood(self):
        """The face expression (see dragon.py); belly() may change the mouth."""
        now = time.time()
        if self.sleeping:
            return "asleep"
        if self.alarm:
            return "alarmed"
        if self.uploading:
            return "uploading"
        if self.reaction and self.reaction[1] > now:
            return self.reaction[0]
        if self.hunger < 10:
            return "starving"
        hour = time.localtime(now).tm_hour
        if 1 <= hour < 6 and self.joy < 70:
            return "sleepy"
        j = joy_word(self.joy)
        return {"SAD": "lonely", "BORED": "bored", "CONTENT": "content", "HAPPY": "happy"}[j]

    def belly(self):
        h = hunger_word(self.hunger)
        return "hungry" if h == "HUNGRY" else "stuffed" if h == "STUFFED" else None

    # ---------------------------------------------------------------- display
    def level(self):
        return level_for(self.xp)

    def xp_frac(self):
        lv = self.level()
        lo, hi = xp_for(lv), xp_for(lv + 1)
        return (self.xp - lo) / max(1, hi - lo)
