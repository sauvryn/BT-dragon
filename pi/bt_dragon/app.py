"""
BT Dragon: ties the scanners, Harald, the screen and the control link together.

Everything runs in one asyncio event loop: one thread that juggles many waiting tasks
(the BLE scanner, the Wi-Fi scan every 20 s, the GPS feed, the network servers), switching
whenever one of them is waiting for I/O. Only the slow e-ink refresh and WiGLE upload are
pushed to worker threads so they don't freeze the rest.
"""
import asyncio
import datetime
import json
import logging
import os
import re
import signal
import subprocess
import time

from . import __version__
from .ble import BleWatcher, TrackerWatch
from .config import hash_password_in_file, networks as config_networks
from .display import Display
from . import activity as actmod
from . import sky as skymod
from .landmarks import Landmarks
from .greens import Greens, visit_words
from .garden import Garden
from . import mobilewifi
from . import garden as gardenmod
from . import garden_page
from . import lang as langmod
from . import conquest
from . import journal as journalmod
from . import scores
from . import planes as planesmod
from . import whispers as whispersmod
from .rtlsdr import RadioStick
from .diary import DiaryFiles
from .dot import DotLink
from . import moon as moonmod
from . import tuning
from .pet import _n, berry_value, hunger_word, joy_word, xp_for
from . import friends as friendsmod
from .homezone import HomeZone, SIZES as HOME_SIZES
from .aurora import words as aurora_words
from .dragon import MOODS
from .gps import Gps
from .wifipos import WifiPosition
from .lair import Lair, LookupError_, c_and_f, deg_words
from .pet import Pet
from . import pet as petmod
from .screen import render, render_nap, render_sleep
from .store import Store
from .sysstats import SysStats
from . import wifi as wifimod
from . import wigle

log = logging.getLogger("dragon")
MAC_RE = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")


class Dragon:
    def __init__(self, cfg, simulate=False, out_dir=None):
        self.cfg = cfg
        self.simulate = simulate
        data_dir = cfg["data_dir"]
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.store = Store(os.path.join(data_dir, "dragon.db"))
        from .denauth import DenAuth
        self.den_auth = DenAuth(self.store)
        from . import art as artmod
        from .backup import art_dir
        self.art = artmod.configure(art_dir(cfg.get("_path"), data_dir))
        tuning.load(self.store, {"food_empty_min": cfg["pet"]["hunger_minutes"]})
        self.pet = Pet(self.store, cfg["pet"]["name"])
        self._mono_start = time.monotonic()
        self._caught_up = False
        from .ble import COMPANIES
        from .ble import maker_label
        n = self.store.rename_maker_species(maker_label)
        if n:
            log.info("named %d life-list species from the company list", n)
        if not self.store.get("code_names_tidied"):     # once: names that were only codes
            from .ble import UNBRANDED, _key, meaningful
            n = self.store.tidy_code_names(meaningful, UNBRANDED, _key(UNBRANDED))
            self.store.put("code_names_tidied", True)
            if n:
                log.info("folded %d code-named species into %s", n, UNBRANDED)
        if not self.store.get("types_renamed"):         # once: the diary says "type" now, not "species"
            self.store.db.execute("UPDATE events SET text='New type: ' || substr(text, 14) "
                                  "WHERE kind='species' AND text LIKE 'New species: %'")
            self.store.db.commit()
            self.store.put("types_renamed", True)
        self._known_species = {r["key"] for r in self.store.species_list()}
        self.ble = BleWatcher()
        self.ble.import_state(self.store.get("ble_today"))
        self.dragon_id = friendsmod.DragonId(self.store)       # a new one every day
        self.friends = friendsmod.FriendBook(self.store, self.dragon_id)
        self._pwna_last = 0.0
        self.activity = actmod.Activity(self.store, cfg["activity"]["stride_m"])
        self.steplink = actmod.StepLink(self.on_steps, self.activity.link_lost)
        self.trackers = TrackerWatch(cfg["trackers"]["alert_after_minutes"] * 60,
                                     cfg["trackers"]["min_moved_meters"])
        self.gps = Gps()
        self._draw_lock = asyncio.Lock()
        self._join_errors = {}          # ssid -> why joining it last failed
        self.wifipos = WifiPosition(self.store)   # only when there's no GPS, and only if switched on
        sky_cfg = cfg["sky"]
        self.lands = skymod.Lands(self.store) if sky_cfg["lands"] else None
        from .offlinemap import OfflineMap
        self.offline_map = OfflineMap(self.store, data_dir)
        self.stars = skymod.Stars(self.store) if sky_cfg["stars"] else None
        if self.stars:
            self.gps.on_gsv = lambda *a, **k: None if self.napping or not self.explore_open() \
                else self.stars.gsv(*a, **k)
        self.baro = skymod.Barometer(self.store) if sky_cfg["barometer"] else None
        self.landmarks = Landmarks(self.store) if sky_cfg["landmarks"] else None
        self.greens = Greens(self.store) if sky_cfg.get("greens", True) else None
        self.baro_link = actmod.PressureLink(self.on_pressure)
        self.sun = skymod.Sunshine(self.store)
        self.light_link = actmod.LightLink(self.on_light)
        dcfg = cfg["diary"]
        self.diary_files = DiaryFiles(os.path.join(data_dir, "diary"), dcfg["keep_days"], dcfg["location"],
                                      self._diary_context) if dcfg["files"] else None
        self.store.diary = self.diary_files
        if self.diary_files:
            self.store.before_flush.append(self.diary_files.flush)   # its rows go when the database does
        from .ble import COMPANIES
        named = f"{len(COMPANIES)}+unbranded"
        if self.store.get("makers_named") != named:   # once per new company list
            e = self.store.rename_maker_events(maker_label)
            f = self.diary_files.rename_makers(maker_label) if self.diary_files else 0
            self.store.put("makers_named", named)
            if e or f:
                log.info("named makers in %d diary entries and %d diary files", e, f)
        self._weather_check = 0.0
        self.stats = SysStats()
        self.vitals = self.stats.sample()
        self.wifi = wifimod.WifiScanner()
        # the simulation saves each picture as a file to look at; on the Pi the Den gets it
        # from memory (/screen.png), so nothing is written to the card every few seconds
        png = os.path.join(out_dir or data_dir, "screen.png") if simulate else None
        self.display = Display(cfg["display"]["enabled"] and not simulate,
                               cfg["display"]["full_refresh_minutes"] * 60, png,
                               cfg["display"]["rotate"], cfg["display"]["model"])
        self.stop = asyncio.Event()
        self.home_ssid = None          # SSID we're connected to right now
        self._switching = False
        self._better_seen = 0
        self.my_ip = None
        self.internet = False
        self.clients = set()           # control-link writers
        self.den_seen = 0.0            # when a den or map page last checked in
        self.tracking = {}             # writer -> mac being tracked
        self.classic_find = {}         # mac -> what the Classic finder last learned
        self._find_wanted = {}
        self._find_tasks = {}
        self._pal_seen_write = {}
        # when each pal was last around, so a restart doesn't cheer "there's my pal!" again
        self._pal_present = {k: float(v) for k, v in (self.store.get("pal_present", {}) or {}).items()}
        self._obs_last = {}
        self.home_zone = HomeZone(self.store)
        # the radio stick (RTL-SDR): planes and the little radios around homes
        self.sky = planesmod.Sky(self.store)
        self.whispers = whispersmod.Whispers(self.store)
        self.radio = RadioStick(self.store, self.on_radio,
                                region=lambda: self._lair_code() or (getattr(self, "os_country", "") or ""))
        self._obs_pruned = 0.0
        self._clock_ok = (False, 0.0)
        self.upload_lock = asyncio.Lock()
        self.started = time.time()
        # napping: as good as switched off (nothing runs, nothing is written to the card),
        # except the den, so he can be woken from it. It survives a restart or power cut.
        nap = self.store.get("napping")
        self.napping = bool(nap)
        self.nap_since = nap.get("since", 0) if isinstance(nap, dict) else 0
        # the Echo Dot: Harald's voice and light ring
        self.dot = DotLink(self)
        self.lair = Lair(self.store)                # home, as far as the weather is concerned
        self.lair.adopt_home_town(self.dot.s.get("home_town"), self.dot.s.get("home_lat"), self.dot.s.get("home_lon"))
        self.pet.on_say = self.dot.on_say
        # the Butterfly Garden (from the Bookworm project): raised on food that fits nowhere else
        self._nap_redraw = False
        self.garden = Garden(self.store)
        self.garden.growth = lambda: self.pet.growth()          # (only if its knob is on)
        self.garden.on_event = self._garden_event
        # which English (British, American, Canadian) his screen and the Den are in, and the
        # garden's starting country: from the Pi's own country (set in Raspberry Pi Imager)
        self.os_country = None if simulate else langmod.os_country()
        self.language = langmod.Language(self.store, self.os_country)
        self.garden.default_country = gardenmod.COUNTRY_OF.get((self.os_country or "").upper(), "gb")
        if "country" not in self.garden.s and gardenmod.COUNTRY_OF.get(self._lair_code().upper()):
            # (once, from an older version, where the garden followed the Lair)
            self.garden.s["country"] = gardenmod.COUNTRY_OF[self._lair_code().upper()]
            self.garden.save()
        self._garden_news = []
        self._garden_fed, self._garden_fed_said, self._garden_shown = 0.0, 0.0, None
        self.pet.on_surplus = self._garden_feed
        if simulate:
            self.dot.state = "not used in the simulation"
        self.store.listeners = (self.dot.on_event,)
        # pals: config file entries are added to the database
        for mac, name in cfg["own_devices"].items():
            if MAC_RE.match(mac) and mac not in self.store.pals():
                self.store.add_pal(mac, name)

    def _tuning_changed(self):
        """A knob changed in Developer Tools: a smaller PACK spills what no longer fits (it
        would otherwise show as more than full, and nothing could go into it)."""
        cap = self.pet.pack_cap()
        if self.pet.pack > cap:
            self.pet.pack = cap
            self.pet.save()

    # ================================================================ Color Blindness Mode
    def cvd_mode(self):
        from . import access
        m = self.store.get("cvd")
        return m if m in access.MODES else "full"

    # ================================================================ sleep screens
    def sleep_screens(self):
        """Which sleep screens are on: like an e-reader's, they hide what his screen last
        showed. Both on unless you untick them in the den."""
        s = self.store.get("sleep_screen") or {}
        return {"nap": s.get("nap", True), "sleep": s.get("sleep", True)}

    def _nap_picture(self):
        return self.art.screen("nap") if self.sleep_screens()["nap"] else render_nap(self.view())

    # ================================================================ the Butterfly Garden
    def _lair_code(self):
        return (self.lair.s or {}).get("code") or ""

    # ================================================================ conquest points
    def conquest_score(self, fresh=False):
        """(score, title); counted from what's been claimed, at most every 20 s."""
        now = time.time()
        if fresh or now - getattr(self, "_cq_at", 0) > 20:
            self._cq = conquest.score(self.store, tuning.get("landmark_langs"))
            self._cq_at = now
        return self._cq, conquest.title(self._cq)

    # ================================================================ the radio stick
    def on_radio(self, what, line, now=None):
        """A line from rtl_adsb (planes) or rtl_433 (the little radios)."""
        if self.napping:
            return
        now = now or time.time()
        if what == "planes":
            fix = self.gps.current()
            ref = (fix["lat"], fix["lon"]) if fix else self.lair.where()
            news = self.sky.heard(line, now, ref)
            for n in news:
                if n[0] == "plane":
                    self.pet.radio_find(tuning.get("radio_food"), 0, 0)
                elif n[0] == "kind":
                    title = planesmod.KINDS[n[1]][0]
                    pts = scores.POINTS[planesmod.KINDS[n[1]][1]]
                    self.pet.radio_find(tuning.get("radio_kind_food"), tuning.get("radio_kind_xp"),
                                        tuning.get("radio_kind_joy"),
                                        [f"A NEW SKY DRAGON: {title.upper()}!", f"NEW SKY DRAGON: {title.upper()}",
                                         "A NEW SKY DRAGON!"], "excited")
                    self.event("sky", f"New sky dragon: {title} +{pts} Sky Dragon points.")
                elif n[0] in ("airline", "country"):
                    word = "AIRLINE" if n[0] == "airline" else "COUNTRY"
                    self.pet.radio_find(0, tuning.get("radio_find_xp"), tuning.get("radio_find_joy"),
                                        [f"A NEW {word} IN THE SKY: {n[2].upper()}", f"NEW {word}: {n[2].upper()}"])
                    pts = planesmod.AIRLINE_POINTS if n[0] == "airline" else planesmod.COUNTRY_POINTS
                    self.event("sky", (f"New airline in the sky: {n[2]} ({n[1]})" if n[0] == "airline"
                                       else f"New country in the sky: an aircraft registered in {n[2]}")
                               + f" +{pts} Sky Dragon points.")
            if news:
                self._new_titles("sky_titles", scores.SKY_TITLES, planesmod.score(self.store), "Sky Dragon", "sky")
            return
        news = self.whispers.heard(line, now)
        for n in news:
            if n[0] == "device":
                self.pet.radio_find(tuning.get("radio_food"), 0, 0)
            elif n[0] == "kind":
                title, rarity = whispersmod.KINDS[n[1]][:2]
                self.pet.radio_find(tuning.get("radio_kind_food"), tuning.get("radio_kind_xp"),
                                    tuning.get("radio_kind_joy"),
                                    [f"A NEW RADIO WHISPER: {title.upper()}!", f"NEW WHISPER: {title.upper()}",
                                     "A NEW RADIO WHISPER!"], "excited")
                self.event("radio", f"New radio whisper: {title} +{scores.POINTS[rarity]} Radio Whisper points.")
            elif n[0] == "model":
                self.pet.radio_find(0, tuning.get("radio_find_xp"), tuning.get("radio_find_joy"),
                                    [f"A NEW WHISPER: {n[1].upper()}", "A NEW MAKE AND MODEL!"])
                self.event("radio", f"New make and model heard: {n[1]} ({whispersmod.KINDS[n[2]][0].lower()}) "
                                    f"+{whispersmod.MODEL_POINTS} Radio Whisper points.")
        if news:
            self._new_titles("whisper_titles", scores.WHISPER_TITLES, whispersmod.score(self.store), "Radio Whisper",
                             "radio")

    def sky_data(self):
        return planesmod.page_data(self.pet.name, self.store, self.sky)

    def whispers_data(self):
        return whispersmod.page_data(self.pet.name, self.store, self.whispers)

    def journal_score(self, fresh=False):
        """Gadget Journal points, counted from his life list (at most every 20 s, unless fresh)."""
        now = time.time()
        if fresh or now - getattr(self, "_jn_at", 0) > 20:
            self._jn = journalmod.score(self.store.species_list())
            self._jn_at = now
        return self._jn

    def _new_titles(self, key, titles, s, what, kind):
        """Any title newly reached in a collection ("Gadget Journal"): on his screen, and in the diary."""
        for name in scores.new_titles(self.store, key, titles, s):
            self.pet.say([f"NEW {what.upper()} TITLE: {name.upper()}!", f"NEW TITLE: {name.upper()}!"], "proud", 30)
            self.event(kind, f"New {what} title: {name}")

    def _conquered(self, text, pts, kind="land"):
        """A claim for the diary, with its points; and any new title it brings."""
        self.event(kind, f"{text} +{pts} Conquest point{'s' if pts != 1 else ''}.")
        s, _ = self.conquest_score(fresh=True)
        for name in conquest.new_titles(self.store, s):
            self.pet.say([f"NEW CONQUEST TITLE: {name.upper()}!", f"NEW TITLE: {name.upper()}!"], "proud", 30)
            self.event("land", f"New conquest title: {name}")

    def _lair_clock(self, now):
        """The time at the Lair, as it's said: "7:12 in the morning" (in the Lair's own time zone)."""
        from . import ask
        tz = (self.lair.s or {}).get("tz")
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.datetime.fromtimestamp(now, ZoneInfo(tz)) if tz else datetime.datetime.fromtimestamp(now)
        except Exception:
            dt = datetime.datetime.fromtimestamp(now)
        return ask._clock(dt)

    def lang(self):
        """gb, us or ca: the English his screen and the Den are written in."""
        return self.language.current(self._lair_code())

    GARDEN_FED_EVERY_S = 300     # "FED 12 FOOD TO THE BUTTERFLY GARDEN": at most every 5 minutes (with
                                 # a full belly, snacks go to the garden all the time)

    def _garden_feed(self, food):
        if self.napping or not self.garden.unlocked(self.pet.level()):
            return
        self.garden.feed(food, self.pet.level(), self._lair_code(), belly_low=self.pet.hunger < 30)
        self._garden_fed += food           # said on his screen a moment later (see _garden_tick)

    def _garden_event(self, kind, info):
        """Hatching, pupating and emerging: queued, so a treat's own message isn't covered up."""
        self._garden_news.append((kind, info))

    def _garden_tick(self):
        """One garden message per pet tick (every 5 s)."""
        self.garden.check_hunger(self.pet.level())
        now = time.time()
        if now < getattr(self.pet, "message_hold", 0):
            return
        waiting = self._garden_news or (self._garden_fed >= 0.05 and now - self._garden_fed_said >= self.GARDEN_FED_EVERY_S)
        if not waiting:
            self._garden_shown = None
            return
        if self._garden_shown is None:
            self._garden_shown = now        # (when this started waiting)
        if now - getattr(self.pet, "message_ts", 0) < 6 and now - self._garden_shown < 30:
            return                          # let the message that's showing be read first (in a busy
                                            # place there's always one: then it waits 30 s at most)
        self._garden_shown = now
        if not self._garden_news:
            if self._garden_fed >= 0.05 and time.time() - self._garden_fed_said >= self.GARDEN_FED_EVERY_S:
                n = self._garden_fed
                self._garden_fed, self._garden_fed_said = 0.0, time.time()
                self.pet.say([f"FED {_n(n)} FOOD TO THE BUTTERFLY GARDEN", f"FED {_n(n)} FOOD TO THE GARDEN",
                              f"+{_n(n)} FOOD TO THE GARDEN"], None, 10, speak=False)
            return
        kind, info = self._garden_news.pop(0)
        if kind == "say":               # held back while "LEVEL UP!" was showing
            self.pet.say(*info)
            return
        if kind == "title":
            text = f"NEW BUTTERFLY GARDEN TITLE: {info['name'].upper()}!"
            self.pet.say([text, f"NEW TITLE: {info['name'].upper()}!"], "proud", 30)
            self.event("garden", f"New Butterfly Garden title: {info['name']}")
            return
        sp = gardenmod.data()["countries"][info["country"]]["by_id"][info["species"]]
        name = gardenmod.full_name(sp)
        young, pupa = sp["young"], sp["pupa"]
        if kind == "hatch":
            j = tuning.get("garden_hatch_joy")
            self.pet._gain(0, 0, j)
            words = [f"AN EGG HATCHED! A {name.upper()} {young.upper()}", f"EGG HATCHED: {name.upper()}!",
                     f"A {young.upper()} HATCHED!"]
            self.pet.say(words, "happy", 20, speak=False)
            self.dot.news(f"An egg hatched in the Butterfly Garden! It's a {name} {young}.")
            self.event("garden", f"An egg hatched in the Butterfly Garden: a {name} {young} ({info['rarity']})")
        elif kind == "pupate":
            j = tuning.get("garden_pupate_joy")
            self.pet._gain(0, 0, j)
            words = [f"THE {name.upper()} {young.upper()} IS NOW A {pupa.upper()}!",
                     f"{name.upper()}: NOW A {pupa.upper()}!", f"A {young.upper()} PUPATED!"]
            self.pet.say(words, "happy", 20, speak=False)
            self.dot.news(f"The {name} {young} in the Butterfly Garden is now a {pupa}!")
            self.event("garden", f"The {name} {young} became a {pupa}")
        elif kind == "emerge":
            j = tuning.get("garden_emerge_joy")
            leveled = self.pet._gain(0, tuning.get("garden_xp"), j)
            form = gardenmod.FORM_WORD.get(info.get("form") or "", "")
            new = "A NEW " if info.get("new") else "A "
            words = [f"{new}{name.upper()} EMERGED{(' (' + form.upper() + ')') if form else ''}!",
                     f"{new}{name.upper()} EMERGED!", f"{name.upper()} EMERGED!"]
            if leveled:
                self._garden_news.insert(0, ("say", (words, self.pet.face_for(j), 45)))
            else:
                self.pet.say(words, self.pet.face_for(j), 45)
            line = f"{'A new' if info.get('new') else 'A'} {name} emerged in the Butterfly Garden"
            if form:
                line += f" ({form.lower()})"
            self.event("garden", line + ". Add it to the Collection from the Den.")
        elif kind == "collect":
            form = gardenmod.FORM_WORD.get(info.get("form") or "", "")
            where = gardenmod.COUNTRY_NAME.get(info["country"], "")
            self.pet.say([f"{name.upper()} ADDED TO THE COLLECTION!", f"{name.upper()} COLLECTED!"], "happy", 20,
                         speak=False)
            line = (f"Added {'a new' if info.get('new') else 'a'} {name}{' (' + form.lower() + ')' if form else ''} "
                    f"to the {where} collection.")
            if info.get("habitat"):
                line += f" A new habitat opened: {gardenmod.habitat_name(info['country'], info['habitat'])}."
            self.event("garden", f"{line} +{info.get('points', 0)} Butterfly Garden points.")

    def garden_page(self, c=""):
        c = c if c in gardenmod.COUNTRY_NAME else self.garden.country(self._lair_code())
        return garden_page.build(dict(self.garden.page_data(c), name=self.pet.name, lang=self.lang()))

    def _den_auth_news(self):
        """The Den password switching itself off (the failsafe, or the boot file): into the diary."""
        self.den_auth.enabled()
        while self.den_auth.news:
            self.event("care", self.den_auth.news.pop(0))

    # ================================================================ events
    def event(self, kind, text):
        if self.napping:                # nothing is written to the card during a nap (the log included:
            return                      # the system log is kept on the card too)
        self.store.event(kind, text)
        line = f"EVT {kind}|{text}\n".encode()
        for w in list(self.clients):
            try:
                w.write(line)
            except Exception:
                self.clients.discard(w)

    # ================================================================ Bluetooth
    def _eat_species(self, key, label, kind, now):
        """Count a meal of this species; a species he's never had before is a feast."""
        before = self.journal_score(fresh=True) if key not in self._known_species else None
        if self.store.species_seen(key, label, kind, now):
            self.pet.feast(label)
            gained = self.journal_score(fresh=True) - (before or 0)
            self.event("species", f"New type: {label}" + (f" +{gained} Gadget Journal points." if gained else ""))
            self._new_titles("journal_titles", scores.JOURNAL_TITLES, self.journal_score(), "Gadget Journal", "species")
        self._known_species.add(key)

    def _headcount_snacks(self, now):
        labels = {s.key: s for s in self.ble.live.values()}
        for key, n in self.ble.headcount(now).items():
            s = labels.get(key)
            for _ in range(n):
                self.pet.snack()
                if s:
                    self._eat_species(key, s.label, s.kind, now)

    def on_advert(self, address, address_type, rssi, name, mfr, uuids, sdata):
        if self.napping:
            return
        now = time.time()
        d = friendsmod.decode(mfr)
        if d:  # another dragon: a friend, not food
            self.meet_dragon(d, rssi, now)
            return
        s, first, snack = self.ble.advert(address, address_type, rssi, name, mfr, uuids, sdata, now)
        if first and s.key not in self._known_species:
            self._eat_species(s.key, s.label, s.kind, now)
        if snack:
            self.pet.snack()
            self._eat_species(s.key, s.label, s.kind, now)
        pals = self._pals_cache()
        if s.address in pals:
            if now - self._pal_seen_write.get(s.address, 0) > 30:
                self.store.pal_seen(s.address, rssi, now)
                self._pal_seen_write[s.address] = now
            if now - self._pal_present.get(s.address, 0) > 600:
                name_ = pals[s.address]["name"]
                self.pet.pal(name_)
                self.event("pal", f"{name_} is nearby")
            self._pal_present[s.address] = now
            for w, mac in list(self.tracking.items()):
                if mac == s.address:
                    try:
                        w.write(f"RSSI {mac} {rssi}\n".encode())
                    except Exception:
                        self.tracking.pop(w, None)
        alert = None if s.address in pals else self.trackers.observe(s, now, self.gps.current())
        if alert:
            mins = int((now - alert["since"]) // 60)
            self.pet.alarm = True
            self.pet.say([f"UNKNOWN {alert['label']} NEAR YOU FOR {mins} MIN",
                          f"UNKNOWN TRACKER NEAR YOU FOR {mins} MIN"], "alarmed", 120)
            self.event("tracker", f"Unknown {alert['label']} has been near you for {mins} min "
                                  f"(alert {alert['id']})")

    def meet_dragon(self, d, rssi, now):
        what = self.friends.heard(d, rssi, now)
        name = d["name"]
        if what == "new":
            self.pet.cheer(tuning.get("friend_new_joy"), tuning.get("friend_new_xp"), f"A NEW DRAGON! HELLO {name}!", "excited", 60)
            self.event("friend", f"Made a new friend: {name} (level {d['level']})")
        elif what == "again":
            self.pet.cheer(tuning.get("friend_back_joy"), tuning.get("friend_back_xp"), f"{name} IS BACK! HI FRIEND!", "happy", 45)
            self.event("friend", f"{name} came back (level {d['level']})")

    def beacon_payload(self):
        mood = self.pet.mood()
        return friendsmod.encode(self.dragon_id.today(), self.pet.level(),
                                 MOODS.index(mood) if mood in MOODS else 0, self.pet.name)

    async def classic_search(self, seconds):
        from .ble import classic_search, describe_class
        self._searching = True
        self.pet.say("LOOKING FOR GADGETS IN PAIRING MODE...")

        def found(address, name, rssi, cod):
            if rssi is None or rssi <= -127:
                return  # known to BlueZ but not actually heard in this search
            kind = describe_class(cod)
            label = name or kind or "Classic device"
            # feed it in like an advert: it shows under "Gadgets nearby" with its fixed address
            self.on_advert(address, "public", rssi, name or None, {}, [], {})
            s = self.ble.live.get(address.upper())
            if s and kind and s.kind in ("maker", "mystery"):
                s.label = kind
            log.debug("classic device heard: %s", kind or "unknown kind")   # never its address or name

        try:
            await classic_search(seconds, found)
            self.pet.say("SEARCH DONE")
        except Exception as e:
            log.warning("classic search failed: %s", e)
            self.pet.say(f"SEARCH FAILED: {e}")
        finally:
            self._searching = False

    # ---------------------------------------------------------------- finding Classic pals
    FIND_GAP_S = 5  # no request for this long = the next one starts a fresh Find

    def classic_find_request(self, mac, fresh=False):
        """
        Called whenever someone is looking at Find for this pal; keeps the finder running.
        A new Find (fresh=True, or the first request after a pause) throws away what the
        last Find learned and starts over from "listen first", so an old knock answer is
        never shown as if it had just happened.
        """
        now = time.time()
        if now - self._find_wanted.get(mac, 0) > self.FIND_GAP_S:
            fresh = True
        self._find_wanted[mac] = now
        if fresh:
            old = self._find_tasks.pop(mac, None)
            if old:
                old.cancel()
            self.classic_find[mac] = {"mode": "listening", "rssi": None, "rtt": None, "ts": 0}
        if mac not in self._find_tasks:
            self._find_tasks[mac] = asyncio.ensure_future(self._classic_finder(mac))
        return self.classic_find.get(mac)

    async def _classic_finder(self, mac):
        """
        Find a pal, gentlest method first. The Pi has one Bluetooth radio, and while it is
        searching or knocking it can't listen for adverts, so listening always comes first:
          1. listen only (6 s): if it advertises (like most BLE gadgets), use that
          2. search for it in pairing mode (8 s): gives a real signal strength
          3. knock (l2ping), with a 3 s quiet listen before each knock so an advert that
             starts up is never drowned out
        """
        from .ble import inquiry_rssi, l2ping
        st = self.classic_find.setdefault(mac, {"mode": "listening", "rssi": None, "rtt": None, "ts": 0})
        started = time.time()
        st.update(mode="listening", rssi=None, rtt=None, ts=0)
        last_inquiry = 0.0
        me = asyncio.current_task()

        def advertising():
            live = self.ble.live.get(mac)
            return live if live and time.time() - live.last < self.BLE_FRESH_S else None

        try:
            while (time.time() - self._find_wanted.get(mac, 0) < 15 or mac in self.tracking.values()) \
                    and not self.stop.is_set():
                live = advertising()
                if live:
                    st.update(mode="ble", rssi=live.rssi, ts=time.time())
                    await self._sleep(1)
                    continue
                if time.time() - started < 6:
                    st["mode"] = "listening"
                    await self._sleep(1)
                    continue
                pairing_recent = st["mode"] == "pairing" and time.time() - st["ts"] < 20
                if pairing_recent or time.time() - last_inquiry > 30:
                    last_inquiry = time.time()
                    if st["mode"] == "listening":
                        st["mode"] = "searching"
                    r = await inquiry_rssi(mac, 8)
                    if r is not None:
                        st.update(mode="pairing", rssi=r, rtt=None, ts=time.time())
                        self.store.pal_seen(mac, r, time.time())
                        self._pals_dirty()
                        self._pal_present[mac] = time.time()
                        self._push_rssi(mac, r)
                        continue
                await self._sleep(3)          # quiet: give adverts a chance first
                if advertising():
                    continue
                rtt = await l2ping(mac)
                if rtt is not None:
                    st.update(mode="ping", rssi=None, rtt=rtt, ts=time.time())
                    self.store.pal_seen(mac, -127, time.time())
                    self._pals_dirty()
                    self._pal_present[mac] = time.time()
                    for w, m in list(self.tracking.items()):
                        if m == mac:
                            try:
                                w.write(f"NEAR {mac} yes {rtt:.0f}\n".encode())
                            except Exception:
                                self.tracking.pop(w, None)
                elif time.time() - st["ts"] > 15:
                    st.update(mode="silent", rssi=None, rtt=None)
        except asyncio.CancelledError:
            pass  # a newer Find took over
        finally:
            if self._find_tasks.get(mac) is me:
                self._find_tasks.pop(mac, None)

    def _push_rssi(self, mac, rssi):
        for w, m in list(self.tracking.items()):
            if m == mac:
                try:
                    w.write(f"RSSI {mac} {rssi}\n".encode())
                except Exception:
                    self.tracking.pop(w, None)

    STAR_NOW_S = 30   # a satellite heard this recently counts as "in view now"
    DEN_OPEN_S = 40   # the anchor shows while a den page has checked in this recently

    BLE_FRESH_S = 15  # an advert this recent means "it's advertising": use its signal

    _pals = None
    _pals_ts = 0.0

    def _pals_cache(self):
        if self._pals is None or time.time() - self._pals_ts > 10:
            self._pals, self._pals_ts = self.store.pals(), time.time()
        return self._pals

    def _pals_dirty(self):
        self._pals = None

    # ================================================================ Wi-Fi
    def clock_ok(self):
        ok, ts = self._clock_ok
        if time.time() - ts > 60:
            ok = self.simulate
            if not ok:
                try:
                    r = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                                       capture_output=True, text=True, timeout=5)
                    ok = r.stdout.strip() == "yes"
                except (OSError, subprocess.SubprocessError):
                    ok = False
            self._clock_ok = (ok, time.time())
        return ok

    @staticmethod
    def screen_answer(reply, short=None):
        """A typed question's answer on his screen (only there, never spoken): the short version
        if there is one, the whole answer if it fits, otherwise a pointer to the den."""
        from .fonts import text_width
        from .pet import STATUS_W
        options = ([short] if isinstance(short, str) else list(short or [])) + [reply.rstrip(".")]
        for t in options:
            if t and text_width(f"ANSWER: {t}".upper()) <= STATUS_W:
                return f"ANSWER: {t}".upper()
        return "ANSWER: A LONG RESPONSE. CHECK THE DEN."

    def own_ssids(self):
        mine = {ssid for ssid, _ in config_networks(self.cfg)}   # our own hotspots
        if self.dot.s.get("setup_network"):
            mine.add(self.dot.s["setup_network"])    # and your own Echo Dot's setup network
        return mine

    def where_now(self):
        """Where he is: the GPS if it has a fix, else a Wi-Fi position if that's switched on.
        Only for things an estimate is good enough for (never WiGLE, walks or distances)."""
        return self.gps.current() or self.wifipos.current()

    def handle_aps(self, aps):
        now = time.time()
        mine = self.own_ssids()                      # our own hotspots aren't food
        fix = self.gps.current()     # real GPS only: a Wi-Fi position is never a WiGLE sighting
        obs_ts = None
        clock = self.clock_ok()
        berry_food = bushes = 0
        if fix:
            obs_ts = now if self.clock_ok() else fix.get("utc")
        at_home = bool(fix) and self.home_zone.inside(fix["lat"], fix["lon"])   # no sightings in the home zone
        for ap in aps:
            if ap["ssid"] in mine:
                continue  # our own hotspots aren't food, and aren't uploaded
            if ap["bssid"] == friendsmod.PWNAGOTCHI_BSSID:
                if now - self._pwna_last > 1800:  # a real Pwnagotchi's friend beacon
                    self.pet.say("A WILD PWNAGOTCHI! A DISTANT COUSIN", "excited", 30)
                    self.event("friend", "Spotted a wild Pwnagotchi")
                self._pwna_last = now
                continue  # not a real network: no treat, never uploaded
            moving = mobilewifi.kind(ap["ssid"])     # a car's, a bus's, a phone's...: see mobilewifi.py
            is_new, prev = self.store.ap_seen(ap, now, touch=clock)
            if is_new:
                packed = self.pet.treat(ap, mobile=moving)
                label = {"vehicle": "Vehicle", "phone": "Mobile"}.get(moving, "New")
                self.event("treat", f"{label} Wi-Fi: {ap['ssid'] or '(hidden)'} {ap['auth']}"
                                    + (f" ({_n(packed)} into the pack)" if packed else ""))
            elif clock and prev and not moving:       # (a vehicle isn't a bush that stays put)
                # berry bush: one point of food per calendar day since he last picked it
                days = (datetime.date.fromtimestamp(now) - datetime.date.fromtimestamp(prev)).days
                food = berry_value(ap.get("security", "wpa2"), days)
                if food:
                    berry_food += food
                    bushes += 1
            if obs_ts and now - self._obs_last.get(ap["bssid"], 0) >= 60 and not at_home and not moving:
                self.store.ap_observe(ap["bssid"], obs_ts, ap["rssi"], fix)
                self._obs_last[ap["bssid"]] = now
        if berry_food:
            packed = self.pet.berries(berry_food, bushes)
            self.event("berries", f"Picked berries from {bushes} familiar network{'s' if bushes != 1 else ''} "
                                  f"(+{_n(berry_food)} food" + (f", {_n(packed)} into the pack" if packed else "") + ")")

    async def wifi_loop(self):
        last_look = 0.0
        while not self.stop.is_set():
            if self.napping:
                # only stays on (or looks for) one of his own networks, so the den can wake him
                try:
                    self.home_ssid = await self.wifi.link()
                    self.my_ip = wifimod.my_ip() if self.home_ssid else None
                    if not self.home_ssid and time.time() - last_look >= 300 and not self._switching:
                        last_look = time.time()
                        await self.switch_to_best(reason="looking for home while napping")
                except Exception as e:
                    log.warning("wifi loop (napping): %s", e)
                await self._sleep(20)
                continue
            try:
                self.home_ssid = await self.wifi.link()
                ip = wifimod.my_ip() if self.home_ssid else None
                if ip and ip != self.my_ip:  # just joined: tell the human where the den is
                    self.pet.say(f"MY DEN: {ip}:{self.cfg['link']['web_port']}")
                    self.pet.message_hold = time.time() + 90
                self.my_ip = ip
                self.pet.den_hint = f"DEN: {ip}:{self.cfg['link']['web_port']}" if ip else None
                aps = await self.wifi.scan()
                self._last_aps = (time.time(), aps)
                await self._rejoin_if_lost(aps)
                self.handle_aps(aps)
                self._maybe_return(aps)
                nets = self.wifipos.wanted(aps, self.gps.current() is not None, bool(self.home_ssid),
                                           self.own_ssids())
                if nets:
                    asyncio.ensure_future(self.wifipos.locate(nets))
                if self.dot.rescue_wanted(aps):
                    asyncio.ensure_future(self.dot.rescue())
            except Exception as e:
                log.warning("wifi loop: %s", e)
            await self._sleep(20)

    # ================================================================ WiGLE
    def wigle_ready(self):
        w = self.cfg["wigle"]
        if not (w["api_name"] and w["api_token"]):
            return False, "no WiGLE API key in bt-dragon.toml"
        if not self.home_ssid:
            return False, "not connected to the hotspot"
        return True, ""

    def _quota_wait(self):
        """Seconds left before WiGLE's daily upload limit resets (0 if not blocked)."""
        return max(0.0, (self.store.get("wigle_quota_until") or 0) - time.time())

    async def upload_now(self, manual=False):
        async with self.upload_lock:
            ok, why = self.wigle_ready()
            if not ok:
                return False, why
            wait = self._quota_wait()
            if wait:
                at = time.strftime("%H:%M", time.localtime(time.time() + wait))
                return False, f"WiGLE's daily upload limit reached. Trying again after {at}"
            p = self.cfg["privacy"]
            rows = self.store.pending_obs(p["skip_nomap"], p["upload_hidden"])
            if not rows:
                return False, "nothing new to upload"
            if not manual:
                # Few, big uploads: WiGLE limits how many files you send per day, not their size.
                last_ok = self.store.get("wigle_last_ok") or 0
                if len(rows) < self.cfg["wigle"]["min_batch"] and time.time() - last_ok < 86400:
                    return False, f"waiting for {self.cfg['wigle']['min_batch']} sightings"
            internet = await asyncio.to_thread(wifimod.internet_ok)
            if not internet:
                return False, "no internet"
            self.pet.uploading = True
            self.pet.say(f"SENDING {len(rows)} SIGHTINGS TO WIGLE...")
            text = wigle.build_csv(rows)
            path = await asyncio.to_thread(wigle.save_csv, text, os.path.join(self.data_dir, "wigle"))
            w = self.cfg["wigle"]
            self.store.put("wigle_last_try", time.time())     # an attempt that reaches WiGLE
            ok, msg = await asyncio.to_thread(wigle.upload, text, os.path.basename(path),
                                              w["api_name"], w["api_token"], w["donate"])
            self.pet.uploading = False
            if ok:
                self.store.put("wigle_last_ok", time.time())
                self.store.mark_uploaded([r["id"] for r in rows])
                self.pet._gain(0, max(1, len(rows) // 10), 3)
                self.pet.say(f"WIGLE GOT {len(rows)} SIGHTINGS!", "proud", 30)
                self.event("upload", f"Uploaded {len(rows)} sightings to WiGLE")
            elif "429" in msg or "too many" in msg.lower():
                # WiGLE counts uploads per UTC day: wait until 10 minutes past UTC midnight
                now = time.time()
                until = (int(now // 86400) + 1) * 86400 + 600
                self.store.put("wigle_quota_until", until)
                at = time.strftime("%H:%M", time.localtime(until))
                msg = f"WiGLE's daily upload limit reached. Trying again after {at} (nothing is lost)"
                self.pet.say([f"WIGLE SAYS ENOUGH FOR TODAY. RETRY AFTER {at}", f"WIGLE: DAILY LIMIT. RETRY AFTER {at}"])
                self.event("upload", msg)
            else:
                self.pet.say(f"WIGLE UPLOAD FAILED: {msg}")
                self.event("upload", f"WiGLE upload failed: {msg}")
            self.store.log_upload(len(rows), ok, msg)
            return ok, msg

    def _next_upload_in(self):
        """Seconds until the next automatic upload may try. The last try is remembered on
        the card, so restarting him (or the Pi) doesn't start a fresh round of uploads."""
        every = max(60, self.cfg["wigle"]["upload_every_minutes"]) * 60
        last = self.store.get("wigle_last_try") or 0
        return max(0.0, last + every - time.time(), self._quota_wait())

    async def offline_map_loop(self):
        """Once a day (when there's internet), the map tiles covering the lands claimed since
        last time, for the map page without a signal (see offlinemap.py)."""
        await self._sleep(90)
        while not self.stop.is_set():
            om = self.offline_map
            if self.lands and not self.napping and not self.simulate and om.due():
                bounds = [skymod.cell_bounds(c, skymod.LAND_M) for c, _ in self.store.lands_all()]
                if bounds:
                    result = await asyncio.to_thread(om.run, bounds)
                    if "new map tiles" in result:
                        self.event("map", f"Offline map: {result}")
            for _ in range(120):                      # 10 minutes, or "Update now" in the den
                if self.stop.is_set() or om.s.get("last_try") == 0:
                    break
                await self._sleep(5)

    async def wigle_loop(self):
        await self._sleep(120)
        while not self.stop.is_set():
            wait = self._next_upload_in()
            if wait > 0:
                await self._sleep(min(wait, 600))      # look again at least every 10 minutes
                continue
            if self.cfg["wigle"]["auto_upload"] and not self.napping:
                try:
                    await self.upload_now()
                except Exception as e:
                    log.warning("upload: %s", e)
            await self._sleep(600)

    # ================================================================ pet + screen
    def view(self):
        p = self.cfg["privacy"]
        in_range = self.ble.in_range()
        pals = self._pals_cache()
        now = time.time()
        pals_near = sum(1 for m in pals if now - self._pal_present.get(m, 0) < 120)
        message = self.pet.message
        if self.trackers.alerts:  # an alert stays on the status line until dismissed
            a = max(self.trackers.alerts.values(), key=lambda a: a["ts"])
            message = f"! UNKNOWN TRACKER WITH YOU {int((now - a['since']) // 60)} MIN"
        if self.pet.sleeping:
            message = self.pet.message
        return {
            "name": self.pet.name, "level": self.pet.level(), "xp_frac": self.pet.xp_frac(),
            "stage": petmod.stage(self.pet.level())[0], "stage_next": petmod.stage(self.pet.level())[1] or 0,
            "explore_open": self.explore_open(), "explore_forced": bool(self.store.get("explore_unlocked")),
            "explore_level": petmod.EXPLORE_LEVEL,
            "lang": self.lang(),
            "mood": self.pet.mood(), "belly": self.pet.belly(), "hunger": round(self.pet.hunger), "pack": round(self.pet.pack, 1), "pack_cap": round(self.pet.pack_cap(), 1),
            "rations": int(self.pet.rations + 1e-9), "ration_part": round((self.pet.rations + 1e-9) % 1, 2),
            "ration_room": round(self.pet.ration_room(), 1),
            "belly_holds": round(100 * self.pet.growth()), "growth": round(self.pet.growth(), 3),
            "joy": round(self.pet.joy), "feeling": self.pet.feeling(),
            "moving": self.activity.motion.mode if self.gps.state() == "FIX" else "",
            "headless": self.display.headless, "headless_why": self.display.headless_why,
            "trip": self._trip_view(), "exercise_today": self._exercise_today(),
            "walked_today": round(self.activity.today["walked"]), "rode_today": round(self.activity.today["rode"]),
            "told_today": round(self.activity.today["told"]), "steps_link": self.steplink.connected,
            "session_meals": self.pet.session_meals, "total_meals": self.pet.total_meals,
            "species": self.store.species_count(), "new_species": self.pet.session_species,
            "session_treats": self.pet.session_treats, "total_treats": self.pet.total_treats,
            "pals_near": pals_near, "pals_total": len(pals),
            "friends": self.friends.count(), "friends_near": len(self.friends.nearby(now)),
            "gps": self.gps.state(), "wigle_pending": self.store.pending_count(p["skip_nomap"], p["upload_hidden"]),
            "awake": int(now - self.started), "uptime": self.vitals["uptime"], "temp": self.vitals["temp"], "cpu": self.vitals["cpu"],
            "mem": self.vitals["mem"], "message": message.upper(),
            "card_saved": int(now - self.store.flushed_at), "card_saves": self.store.flushes,
            "journal": scores.view(scores.JOURNAL_TITLES, self.journal_score()),
            "alert": bool(self.trackers.alerts), "home": bool(self.home_ssid), "linked": bool(self.clients) or now - self.den_seen < self.DEN_OPEN_S,
            "nearby": len(in_range), "xp": self.pet.xp, "next_xp": xp_for(self.pet.level() + 1),
            "network": self.home_ssid or "", "network_rank": self.network_rank(self.home_ssid),
            "napping": self.napping, "nap_since": int(self.nap_since),
            **self._sky_view(now),
        }

    def _sky_view(self, now):
        lands, realms = self.store.land_counts() if self.lands else (0, 0)
        cq, cq_title = self.conquest_score()
        nxt = conquest.next_title(cq)
        v = {"lands": lands, "realms": realms, "lands_today": self.pet.lands_today,
             "conquest": cq, "conquest_title": cq_title, "conquest_next": nxt[1] if nxt else "",
             "conquest_next_at": nxt[0] if nxt else 0,
             "stars": len(self.stars.known) if self.stars else 0, "stars_today": len(self.stars.today) if self.stars else 0,
             "climbed_today": round(self.pet.climbed_today), "baro_link": self.baro_link.connected,
             "light_link": self.light_link.connected,
             "lux": round(self.sun.lux) if self.sun.lux is not None and time.time() - self.sun.ts < 60 else None,
             "pressure": None, "tendency": None,
             "moon": moonmod.now_info(now) if self.cfg["sky"]["moon"] else None,
             "south": bool(self.gps.fix and self.gps.fix["lat"] < 0)}
        if self.baro and self.baro.hpa and now - self.baro.ts < 120:
            v["pressure"] = round(self.baro.hpa, 1)
            t = self.baro.tendency(now)
            v["tendency"] = None if t is None else round(t, 1)
        return v

    def _catch_up(self):
        """Once the clock is known to be right, account for the time he was switched off."""
        if self._caught_up or not (self.simulate or self.clock_ok()):
            return
        self._caught_up = True
        started_at = time.time() - (time.monotonic() - self._mono_start)
        nap = getattr(self, "_from_nap", False)
        self._from_nap = False
        gap = self.pet.catch_up(started_at, quiet=nap)
        if nap:
            if gap >= 120:          # a nap: the wake-up line in the diary already says how long
                self.pet.save()
            return
        if gap >= 120:
            from .pet import away_words
            ate = getattr(self.pet, "pack_eaten_away", 0)
            self.event("away", f"{self.pet.name} was switched off for {away_words(gap).lower()}: "
                               + (f"ate {ate:.0f} from the pack, " if ate >= 0.5 else "")
                               + f"food now {self.pet.hunger:.0f}%, joy {self.pet.joy:.0f}%")
            self.pet.save()

    def _save_ble(self):
        if self.stars:
            self.stars.save()
        if self.landmarks:
            self.landmarks.save()
        if self.greens:
            self.greens.save()
        if self.baro:
            self.baro.save()
        self.store.put("ble_today", self.ble.export_state())
        recent = {k: v for k, v in self._pal_present.items() if time.time() - v < 3600}
        self.store.put("pal_present", recent)

    async def pet_loop(self):
        last_save = time.time()
        while not self.stop.is_set():
            if self.napping:            # frozen, and nothing saved
                last_save = time.time()
                await self._sleep(5)
                continue
            self._catch_up()
            self._den_auth_news()
            self._headcount_snacks(time.time())
            self._sky_tick(time.time())
            self.ble.prune()
            self.trackers.prune(time.time())
            if time.time() - self._obs_pruned > 3600:   # wardriving sightings: 90 days at most
                self._obs_pruned = time.time()
                self.store.prune_obs()
            self.pet.alarm = bool(self.trackers.alerts)
            self.pet.tick(self.ble.in_range())
            self._garden_tick()
            self.vitals = self.stats.sample()
            if time.time() - last_save > 60:
                self.pet.save()
                self.activity.save()
                self._save_ble()
                last_save = time.time()
            if time.time() - self.store.flushed_at > tuning.get("card_save_min") * 60:
                self.store.flush()          # everything gathered since, onto the card in one go
            await self._sleep(5)

    # ================================================================ sky: lands, stars, weather
    def on_light(self, vals):
        """The phone's light sensor: a cheer when he's out in the sunshine."""
        if self.napping:
            return
        lux = self.sun.feed(float(vals[0]))
        if lux is not None:
            say = self.dot.s["say_phone_sun"]
            self.pet.sunny(speak=say)
            if say:
                self.dot.adventure("sunny")
            self.event("weather", f"Sunshine! The phone saw {lux:,.0f} lux")

    def on_pressure(self, vals):
        if self.napping:
            return
        if self.baro:
            self.baro.feed(float(vals[0]), self.gps.current(), self.activity.moving_mode())

    def _sky_tick(self, now):
        if self.stars:
            new, new_consts, risen = self.stars.take()
            if new or risen:
                self.pet.stars(new, new_consts, risen)
                for c in new_consts:
                    self._conquered(f"{self.pet.name} saw a first {c} satellite: a new constellation!",
                                    conquest.points("star") + conquest.points("constellation"), "star")
                    self.dot.adventure("constellation", name=c)
                if len(new) > len(new_consts):
                    self.dot.adventure("stars", n=len(new) - len(new_consts))
                if new and len(new) > len(new_consts):
                    n = len(new) - len(new_consts)
                    names = ", ".join(k.replace("-", " ") for k, _ in new[:6]) + (" ..." if len(new) > 6 else "")
                    self._conquered(f"New star{'s' if len(new) != 1 else ''} in the sky: {names}.",
                                    n * conquest.points("star"), "star")
        self._moon_tick(now)
        kinds = self.lair.due(now) if (self.home_ssid or self.simulate) else []
        if kinds:
            self.lair._busy = True               # (until the check itself runs)
            asyncio.ensure_future(self._lair_check(now, kinds))
        if self.baro:
            m = self.baro.take_climb()
            if m:
                self.pet.climb(m)
            if now - self._weather_check >= 60:
                self._weather_check = now
                kind, d = self.baro.weather(now)
                say = self.dot.s["say_phone_storm"]
                if kind == "storm":
                    self.pet.storm(d, speak=say)
                    if say:
                        self.dot.adventure("storm")
                    self.event("weather", f"A storm is coming: pressure fell {abs(d):.1f} hPa in 3 hours")
                elif kind == "rise":
                    self.pet.weather_change(d, speak=say)
                    if say:
                        self.dot.adventure("weather")
                    self.event("weather", f"Weather change ahead: pressure rose {d:.1f} hPa in 3 hours")

    def _diary_context(self):
        """His meters, and where he is if GPS is working, for each row of the diary file."""
        fix = self.gps.current()
        return {"food": round(self.pet.hunger), "joy": round(self.pet.joy), "pack": round(self.pet.pack, 1),
                "level": self.pet.level(), "xp": self.pet.xp,
                "lat": round(fix["lat"], 5) if fix else None, "lon": round(fix["lon"], 5) if fix else None}

    def map_data(self):
        """Everything the den's map page draws: claimed squares, realms and where he is now."""
        rows = self.store.lands_all() if self.lands else []
        realms = sorted({r for _, r in rows})
        fix = self.where_now()
        cq, cq_title = self.conquest_score()
        return {"name": self.pet.name, "conquest": cq, "conquest_title": cq_title,
                "locked": None if self.explore_open() else petmod.EXPLORE_LEVEL,
                "lands": [skymod.cell_bounds(c, skymod.LAND_M) for c, _ in rows],
                "realms": [skymod.cell_bounds(r, skymod.REALM_M) for r in realms],
                "here": {"lat": round(fix["lat"], 6), "lon": round(fix["lon"], 6),
                         "wifi": fix.get("via") == "wifi", "acc": fix.get("acc", 0)} if fix else None,
                "today": self.pet.lands_today,
                "landmarks": [{"title": r["title"], "lat": r["lat"], "lon": r["lon"], "seen": bool(r["first_seen"])}
                              for r in (self.store.landmarks_list(tuning.get("landmark_langs"))
                                        if self.landmarks else [])],
                "greens": [{"name": g["name"], "kind": g["kind"], "seen": g["seen"], "rings": g["rings"]}
                           for g in (self.store.greens_list() if self.greens else [])]}

    def explore_open(self):
        """The map (lands, famous places, green spaces) and the stars: from level 5, when he's a
        child (see pet.STAGES), or sooner with the den's "Unlock now (prototype testing)" box.
        A baby eats, makes friends, and grows."""
        return self.pet.level() >= petmod.EXPLORE_LEVEL or bool(self.store.get("explore_unlocked"))

    def _look_around(self, fix):
        """Famous places: ask Wikipedia about each new realm, then point out what's near."""
        if not self.landmarks or fix.get("acc", 99) > 100 or not self.explore_open():
            return
        realm = self.landmarks.wanted(fix)
        if realm and (self.home_ssid or self.simulate):
            asyncio.ensure_future(self.landmarks.fetch(realm))
        for lm, first in self.landmarks.near(fix):
            self.pet.landmark(lm["title"], first)
            self.dot.saw_landmark(lm)
            self.dot.adventure("landmark", title=lm["title"], first=first)
            if first:
                self._conquered(f"{self.pet.name} saw {lm['title']} for the first time!", conquest.points("landmark"),
                                "landmark")
            else:
                self.event("landmark", f"{self.pet.name} saw {lm['title']}")

    def _green_tick(self, fix):
        """Parks and woods: ask OpenStreetMap about each new realm, then notice when we're in one."""
        if not self.greens or fix.get("acc", 99) > 100 or not self.explore_open():
            return
        realm = self.greens.wanted(fix)
        if realm and (self.home_ssid or self.simulate):
            asyncio.ensure_future(self.greens.fetch(realm))
        for what, g in self.greens.update(fix, self.activity.motion.mode):
            if what == "found":
                self.pet.green_found(g["name"])
                self.dot.adventure("green_found", name=g["name"])
                self._conquered(f"{self.pet.name} found a new green space: {g['name']}.", conquest.points("green"), "green")
            else:
                words = visit_words(what, g["name"])
                self.pet.green_visit(words)
                self.dot.adventure("green_visit", text=words)
                self.event("green", f"{self.pet.name}: {words}")

    async def _lair_check(self, now, kinds=None):
        """Local announcements, each at its own time: how warm it is at the Lair (on the hour),
        storms or changes on the way (a quarter past), high pollen (half past), high UV (a
        quarter to), and sunrise and sunset as they happen."""
        self.lair._busy = False
        say, warned = self.dot.s, []
        for ev in await self.lair.check(now, kinds):
            if self.napping:
                return
            kind = ev[0]
            if kind == "storm":
                self.pet.storm(ev[1], at_lair=True, speak=say["say_lair_storm"])
                self.event("weather", f"A storm is coming at the Lair: pressure {ev[1]:+.1f} hPa over 3 hours")
            elif kind == "rise":
                self.pet.weather_change(ev[1], at_lair=True, speak=say["say_lair_storm"])
                self.event("weather", f"The weather is changing at the Lair: pressure {ev[1]:+.1f} hPa over 3 hours")
            elif kind == "temp" and not self.dot.quiet_now():
                t = c_and_f(ev[1])
                self.pet.say([f"IT'S {t} OUTSIDE AT THE LAIR", f"IT'S {t} AT THE LAIR", f"{t} AT THE LAIR"],
                             None, 30, speak=False)
                if say["say_lair_temp"]:     # ticked: said even in "Big moments"
                    # the place first and the number last: a few words to catch your attention
                    # before the part that matters
                    self.dot.news(f"At the Lair, the current temperature is {deg_words(ev[1], celsius=True)}.", big=True)
                self.lair.s["temp_said"] = [now, t]
                self.lair.save()
            elif kind == "pollen":
                level, groups, higher, increased = ev[1], ev[2], ev[3], ev[4]
                names = " and ".join({"trees": "tree", "weeds": "weed"}.get(g, g) for g in groups)
                screen = ([f"ACHOO! POLLEN IS HIGHER AT THE LAIR", "ACHOO! POLLEN IS HIGHER!", "ACHOO! HIGHER POLLEN"]
                          if higher else
                          [f"ACHOO! {level.upper()} POLLEN AT THE LAIR", f"ACHOO! {level.upper()} POLLEN", "ACHOO! POLLEN!"])
                self.pet.say(screen, "sneezing", 45, speak=False)
                if say["say_lair_pollen"] and (increased or say["say_lair_pollen_when"] == "all"):
                    self.dot.news(f"Achoo! The {names} pollen is higher at the Lair! It's {level} now." if higher
                                  else f"Achoo! The {names} pollen is {level} at the Lair.", big=True)
                if increased:
                    self.event("weather", f"{level.capitalize()} {names} pollen at the Lair")
            elif kind == "air":
                word, v, scale, higher, increased = ev[1], ev[2], ev[3], ev[4], ev[5]
                self.pet.say([f"AIR QUALITY {word.upper()} AT THE LAIR", f"AIR QUALITY: {word.upper()}", "POOR AIR QUALITY!"],
                             "sneezing", 45, speak=False)
                if say["say_lair_air"] and (increased or say["say_lair_air_when"] == "all"):
                    self.dot.news(f"The air quality at the Lair is getting worse! It's {word} now, with a {scale} "
                                  f"air quality index of {v}." if higher else
                                  f"The air quality at the Lair is {word}, with a {scale} air quality index of {v}.",
                                  big=True)
                if increased:
                    self.event("weather", f"Air quality at the Lair: {word} ({scale} index {v})")
            elif kind == "uv":
                uv, level, higher, increased = ev[1], ev[2], ev[3], ev[4]
                screen = (["SUNGLASSES ON! UV IS HIGHER AT THE LAIR", "UV IS HIGHER AT THE LAIR", "HIGHER UV!"]
                          if higher else
                          [f"SUNGLASSES ON! {level.upper()} UV AT THE LAIR", f"{level.upper()} UV AT THE LAIR",
                           f"{level.upper()} UV!"])
                self.pet.say(screen, "dazzled", 45, speak=False)
                if say["say_lair_uv"] and (increased or say["say_lair_uv_when"] == "all"):
                    self.dot.news(f"Sunglasses on! The UV index at the Lair is higher! It's {round(uv)} now, that's {level}."
                                  if higher else
                                  f"Sunglasses on! The UV index at the Lair is {round(uv)}, that's {level}.", big=True)
                if increased:
                    self.event("weather", f"{level.capitalize()} UV at the Lair (UV index {round(uv)})")
            elif kind == "warning":
                w = ev[1]
                warned.append(w)
                if say["say_lair_warnings"]:
                    self.dot.news(f"Weather warning at the Lair: {w['spoken']}.", big=True)
                self.event("weather", f"Weather warning at the Lair: {w['spoken']}")
            elif kind == "aurora":
                level, kp, south, how = ev[1], ev[2], ev[3], ev[4]
                lights = "SOUTHERN LIGHTS" if south else "NORTHERN LIGHTS"
                screen = {"overhead": [f"{lights} OVERHEAD AT THE LAIR? LOOK UP!", f"{lights} AT THE LAIR!", f"{lights}!"],
                          "horizon": [f"{lights} POSSIBLE AT THE LAIR!", f"{lights} POSSIBLE!", f"{lights}?"],
                          "camera": [f"{lights}: TRY A CAMERA AT THE LAIR", f"{lights}: TRY A CAMERA", f"{lights}?"]}[level]
                self.pet.cheer(tuning.get("aurora_joy"), 0, screen, "ecstatic" if level == "overhead" else "excited",
                               60, speak=False)
                if say["say_lair_aurora"]:
                    self.dot.news(("Northern lights alert! " if not south else "Southern lights alert! ")
                                  + aurora_words(level, south), big=True)
                self.event("weather", f"{lights.capitalize()} possible at the Lair tonight: Kp {kp:.1f} "
                                      f"({'measured' if how == 'observed' else how or 'forecast'}), "
                                      + {"overhead": "maybe overhead", "horizon": "low in the sky",
                                         "camera": "a phone camera might catch it"}[level])
            elif kind in ("sunrise", "sunset"):
                self.pet.cheer(tuning.get("sun_joy"), 0, "THE SUN IS RISING AT THE LAIR!" if kind == "sunrise"
                               else "THE SUN IS SETTING AT THE LAIR", "happy", 30, speak=False)
                if say["say_lair_sun"]:
                    # the place first, then the time, then the news: time to start listening
                    self.dot.news(f"At the Lair, it is {self._lair_clock(now)} and the sun is "
                                  f"{'rising' if kind == 'sunrise' else 'setting'}.", big=True)
        if warned and not self.napping:
            # several at once: all are said (and in the diary), and the most serious stays on his screen
            w = next((x for x in warned if x.get("severe")), warned[0])
            self.pet.say([f"{w['title'].upper()} AT THE LAIR", w["title"].upper(), "WEATHER WARNING AT THE LAIR!"],
                         "alarmed", 60, speak=False)

    def star_chart_data(self):
        from . import starchart
        now = time.time()
        heard = self.stars.last_heard if self.stars else {}
        in_view = {k for k, t in heard.items() if now - t <= self.STAR_NOW_S}
        return starchart.page_data(self.pet.name, self.store.stars(), in_view, now, where=self.lair.where())

    def journal_data(self):
        from . import journal
        return journal.page_data(self.pet.name, self.store.species_list())

    def _aurora_lines(self):
        """For the Den: the Kp each kind of sighting needs at the Lair, and the latest reading."""
        needs, south = self.lair.aurora_needs()
        if not needs:
            return []
        fmt = lambda v: "" if v is None else f"{v:g}"          # noqa: E731
        last = self.lair.s.get("aurora_last") or {}
        return [f"aurora_south={1 if south else 0}", f"aurora_camera={fmt(needs['camera'])}",
                f"aurora_horizon={fmt(needs['horizon'])}", f"aurora_overhead={fmt(needs['overhead'])}",
                f"aurora_kp={fmt(last.get('kp'))}", f"aurora_kind={last.get('kind', '')}",
                "aurora_at=" + (time.strftime("%H:%M", time.localtime(last["ts"])) if last.get("ts") else "")]

    def _moon_tick(self, now):
        """On the day of each major moon phase, once (needs a clock that's been set)."""
        if not self.cfg["sky"]["moon"] or now - getattr(self, "_moon_checked", 0) < 300:
            return
        if not (self.simulate or self.clock_ok()):
            return
        self._moon_checked = now
        got = moonmod.todays_phase(now)
        if not got:
            return
        phase, at = got
        key = f"{time.strftime('%Y-%m-%d', time.localtime(at))}-{phase}"
        if self.store.get("moon_done") == key:
            return
        self.store.put("moon_done", key)
        self.pet.moon(phase)
        name = {"new": "New moon", "full": "Full moon", "first quarter": "First quarter moon",
                "last quarter": "Last quarter moon"}[phase]
        self.event("moon", f"{name} today, at {time.strftime('%H:%M', time.localtime(at))}")
        self.dot.adventure("moon", text=f"{name} today!")

    def _visit_land(self, fix):
        claimed = self.lands.visit(fix) if self.lands and self.explore_open() else None
        for new_realm in claimed or []:
            self.pet.land(new_realm, riding=self.activity.motion.mode == "vehicle")
            self.dot.adventure("realm" if new_realm else "land")
            lands, realms = self.store.land_counts()
            if new_realm:          # (its first land comes with it)
                self._conquered(f"{self.pet.name} claimed a new realm (realm {realms}, land {lands}).",
                                conquest.points("realm") + conquest.points("land"))
            else:
                self._conquered(f"{self.pet.name} claimed a new land (land {lands}).", conquest.points("land"))

    # ================================================================ activity
    def on_steps(self, total):
        if self.napping:
            return
        moving_gps = self.gps.state() == "FIX"
        res = self.activity.steps(total, moving_gps)
        if not res:
            return
        kind, n = res
        if kind == "story":
            meters = n * self.activity.stride
            self.pet.story(meters, n)
            self.event("story", f"You told {self.pet.name} about your adventure! {n:,} steps "
                                f"(about {actmod.describe_km(meters).lower()})")
        else:  # walking with Harald while GPS can't see (indoors, no GPS app)
            self.activity.add("walking", n)
            self.pet.adventure({"walking": n})
            self._adventure_face("walking")

    def _adventure_face(self, mode):
        r = self.pet.reaction
        if r is None or r[1] < time.time() or r[0] in ("adventure", "riding"):
            self.pet.reaction = ("riding" if mode == "vehicle" else "adventure", time.time() + 15)

    async def activity_loop(self):
        last_fix_ts = last_wifi_ts = None
        next_milestone = 500.0
        while not self.stop.is_set():
            if self.napping:
                await self._sleep(2)
                continue
            fix = self.gps.current()
            if fix and fix["ts"] != last_fix_ts:
                last_fix_ts = fix["ts"]
                self.activity.motion.feed(fix)
                self._visit_land(fix)
                self._look_around(fix)
                self._green_tick(fix)
            elif not fix:
                # no GPS: a Wi-Fi position (if switched on) still claims land, spots landmarks
                # and discovers green spaces, but it never counts distance, walks or WiGLE
                wfix = self.wifipos.current()
                if wfix and wfix["ts"] != last_wifi_ts:
                    last_wifi_ts = wfix["ts"]
                    self._visit_land(wfix)
                    self._look_around(wfix)
                    self._green_tick(wfix)
            got = self.activity.take_motion()
            if got:
                self.pet.adventure(got)
                self._adventure_face(self.activity.motion.mode)
                on_foot = sum(m for k, m in self.activity.trip.items() if k != "vehicle")
                if on_foot >= next_milestone:
                    self.pet.say(f"ADVENTURE! {actmod.describe_km(on_foot)} TOGETHER", "adventure", 20)
                    next_milestone += 500
            trip = self.activity.finished_trip()
            if trip:
                next_milestone = 500.0
                on_foot = sum(m for k, m in trip.items() if k != "vehicle")
                ride = trip.get("vehicle", 0.0)
                if on_foot >= actmod.Activity.MIN_ADVENTURE_M and self.activity.last_trip:
                    # the outing itself, for the diary: what, how far, how long, when
                    summary = actmod.trip_summary(trip, *self.activity.last_trip)
                    self.event("exercise", actmod.exercise_line(summary))
                    if not self.napping:
                        self.store.exercise_add(summary["start"], summary["start"] + summary["seconds"],
                                                summary["kind"], summary["meters"])
                if on_foot >= actmod.Activity.MIN_ADVENTURE_M:
                    # a bonus for the walk itself, even if there was nothing new to eat
                    self.pet.cheer(tuning.get("adventure_bonus"), tuning.get("adventure_xp"), [f"YOU TOOK {self.pet.name} ON AN ADVENTURE! {actmod.describe_km(on_foot)} ON FOOT",
                                          f"YOU TOOK {self.pet.name} ON AN ADVENTURE!",
                                          f"AN ADVENTURE! {actmod.describe_km(on_foot)} ON FOOT"], "happy", 60)
                    self.event("adventure", f"You took {self.pet.name} on an adventure! "
                                            f"{actmod.describe_km(on_foot).lower()} on foot"
                               + (f", {actmod.describe_km(ride).lower()} riding" if ride >= 100 else ""))
                elif ride >= 1000:
                    self.event("adventure", f"{self.pet.name} went for a ride: {actmod.describe_km(ride).lower()}")
                self.activity.save()
                self._save_ble()
            await self._sleep(2)

    async def display_loop(self):
        min_gap = self.cfg["display"]["min_seconds_between_updates"]
        last_key, last_draw, phase = None, 0.0, 0
        napped = False
        while not self.stop.is_set():
            if self.napping:
                if not napped or self._nap_redraw:     # drawn once and left alone
                    napped, self._nap_redraw = True, False
                    await asyncio.to_thread(self.display.show, self._nap_picture(), True)
                    await asyncio.to_thread(self._flush_to_card)     # the screen picture too
                await self._sleep(2)
                continue
            if napped:
                napped, last_key = False, None
            if self.pet.sleeping:       # going to sleep: the "safe to unplug" picture stays
                await self._sleep(2)
                continue
            v = self.view()
            v["awake_min"] = v["awake"] // 60  # redraw when the UP clock's minute changes
            key = tuple((k, v[k]) for k in ("mood", "belly", "joy", "walked_today", "hunger", "pack", "pack_cap", "session_meals", "species", "session_treats", "lang",
                                             "pals_near", "friends_near", "gps", "wigle_pending", "message", "alert",
                                             "awake_min",
                                             "home", "linked", "level"))
            now = time.time()
            if (key != last_key and now - last_draw >= min_gap) or now - last_draw > 60:
                phase ^= 1
                v["phase"] = phase
                async with self._draw_lock:
                    if not self.pet.sleeping:
                        await asyncio.to_thread(self.display.show, render(v))
                last_key, last_draw = key, now
            await self._sleep(2)

    # ================================================================ commands (link + web)
    async def command(self, line, writer=None):
        """Run one text command; returns a list of response lines."""
        parts = line.strip().split(" ", 1)
        cmd = parts[0].upper()
        arg = parts[1].strip() if len(parts) > 1 else ""
        now = time.time()
        if cmd == "HELLO":
            return [f"OK BTDRAGON {__version__} name={self.pet.name}"]
        if cmd == "STATUS":
            v = self.view()
            v.update(gps_source=self.gps.source or "", home_ssid=self.home_ssid or "", ip=self.my_ip or "",
                     upload=(self.store.last_upload() or {}).get("message", ""))
            return [f"{k}={v[k]}" for k in v] + ["END"]
        if cmd == "GARDEN":
            v = self.garden.view(self.pet.level(), self._lair_code())
            h = self.pet.hunger
            v.update(belly=round(h, 1), pack=round(self.pet.pack, 1), pack_cap=round(self.pet.pack_cap(), 1))
            v["art"] = self.garden_art_version() if hasattr(self, "garden_art_version") else ""
            return [json.dumps(v), "END"]
        if cmd == "DENAUTH":        # the Den password: on=, has_password=, failsafe=, failsafe_in=, phone_token=
            a = self.den_auth
            return a.lines() + [f"phone_token={a.phone_token() if a.has_password else ''}", "END"]
        if cmd == "DENAUTHSET":     # on / off
            on = arg.lower() in ("on", "1", "yes")
            err = self.den_auth.set_on(on)
            if err:
                return [f"ERR {err}"]
            self.event("care", "The Den password was switched " + ("on" if on else "off"))
            return ["OK"]
        if cmd == "DENFAILSAFE":    # on / off: switch the password off again five minutes after it's switched on
            self.den_auth.set_failsafe(arg.lower() in ("on", "1", "yes"))
            return ["OK"]
        if cmd == "DENPASS":        # a new password (over SSH; the Den uses /api/denpass, which logs it in too)
            err = self.den_auth.set_password(arg)
            if err:
                return [f"ERR {err}"]
            self.event("care", "The Den password was set")
            return ["OK"]
        if cmd == "OFFLINEMAP":     # on=, tiles=, bytes=, last=, build=, busy=, state=, ready=, then END
            return self.offline_map.lines() + ["END"]
        if cmd == "OFFLINEMAPSET":  # on / off
            self.offline_map.set_on(arg.lower() in ("on", "1", "yes"))
            return ["OK"]
        if cmd == "OFFLINEMAPNOW":  # fetch today's (new) tiles at the next look, within 10 minutes
            om = self.offline_map
            if not om.s.get("on"):
                return ["ERR switch the offline map on first"]
            om.s.pop("last_day", None)
            om.s["last_try"] = 0
            om._save()
            return ["OK Fetching the map now (it needs the internet)"]
        if cmd == "EXPLOREUNLOCK":  # on / off: the map and the stars before level 5 (prototype testing)
            self.store.put("explore_unlocked", arg.lower() in ("on", "1", "yes"))
            return ["OK"]
        if cmd == "GARDENUNLOCK":
            if arg.lower() in ("on", "1", "yes"):
                self.garden.unlock_now(self.pet.level())
            else:
                self.garden.lock_again()
            return ["OK"]
        if cmd == "GARDENCOLLECT":      # an emerged adult into its collection, freeing its spot
            if not arg.strip().isdigit():
                return ["ERR which spot?"]
            err = self.garden.collect(int(arg), self.pet.level())
            return [f"ERR {err}"] if err else ["OK"]
        if cmd in ("GARDENEGG", "GARDENEMPTY"):     # put an egg in a spot, or take one away
            if not arg.strip().isdigit():
                return ["ERR which spot?"]
            f = self.garden.lay_egg if cmd == "GARDENEGG" else self.garden.take_egg
            err = f(int(arg), self.pet.level())
            return [f"ERR {err}"] if err else ["OK"]
        if cmd == "LANG":    # the language setting, and what moving the Lair would offer
            code = self._lair_code().upper()
            return [f"auto={1 if self.language.auto else 0}", f"lang={self.lang()}",
                    f"chosen={self.language.chosen or ''}", f"os={self.os_country or ''}",
                    f"default={self.language.default()}", f"lair_lang={langmod.OF_COUNTRY.get(code, '')}",
                    f"lair_country={gardenmod.COUNTRY_OF.get(code, '')}", f"garden={self.garden.country()}", "END"]
        if cmd == "LANGSET":  # LANGSET auto on|off, or LANGSET gb|us|ca
            a = arg.lower().split()
            if a[:1] == ["auto"] and a[1:] in (["on"], ["off"]):
                err = self.language.set(auto=a[1] == "on", lair_code=self._lair_code())
            elif len(a) == 1:
                err = self.language.set(lang=a[0])
            else:
                err = "use: LANGSET auto on|off, or LANGSET gb|us|ca"
            return [f"ERR {err}"] if err else ["OK"]
        if cmd == "GARDENCOUNTRY":
            err = self.garden.set_country(arg.lower())
            return [f"ERR {err}"] if err else ["OK"]
        if cmd == "LOG":
            n = int(arg) if arg.isdigit() else 20
            return [f"{int(e['ts'])}|{e['kind']}|{e['text']}" for e in self.store.events(n)] + ["END"]
        if cmd == "NEARBY":
            pals = self._pals_cache()
            out = []
            for s in sorted(self.ble.in_range(), key=lambda s: -s.rssi):
                if s.stable:  # rotating addresses are never listed individually
                    out.append(f"{s.address}|{s.rssi}|{1 if s.address in pals else 0}|{s.label}|{s.name or ''}")
            return out[:40] + ["END"]
        if cmd == "PALS":
            out = []
            for mac, p in self._pals_cache().items():
                live = self.ble.live.get(mac)
                rssi = live.rssi if live and now - live.last < 60 else ""
                ago = int(now - p["last_seen"]) if p["last_seen"] else -1
                out.append(f"{mac}|{rssi}|{ago}|{p['name']}")
            return out + ["END"]
        if cmd == "ADDPAL":
            mac, _, name = arg.partition(" ")
            mac = mac.upper()
            if not MAC_RE.match(mac):
                return ["ERR bad address"]
            live = self.ble.live.get(mac)
            name = (name.strip() or (live.name if live else "") or "My device")[:24]
            self.store.add_pal(mac, name)
            self._pals_dirty()
            self.event("pal", f"Added pal {name}")
            return ["OK"]
        if cmd == "DELPAL":
            self.store.del_pal(arg.upper())
            self._pals_dirty()
            return ["OK"]
        if cmd == "TRACK":
            mac = arg.upper()
            if mac not in self._pals_cache():
                return ["ERR only your own devices (pals) can be tracked"]
            if writer is not None:
                self.tracking[writer] = mac
                self.classic_find_request(mac, fresh=True)  # listens first; knocks only if needed
            return ["OK"]
        if cmd == "NETWORK":  # rank|ssid|connected|in range|security|note, for each of our networks, best first
            return [f"{n['rank']}|{n['ssid'].replace('|', '/')}|{1 if n['connected'] else 0}|"
                    f"{1 if n['in_range'] else 0}|{n['security']}|{n['note'].replace('|', '/')}"
                    for n in self.network_info()] + ["END"]
        if cmd == "RECONNECT":  # drop the current network and join the best one in range
            asyncio.ensure_future(self.switch_to_best(reason="asked from the den"))
            return ["OK looking for the best network (the den may lose its connection for a moment)"]
        if cmd == "FIND":  # a new Find just opened (the den sends this, then polls RSSI)
            mac = arg.upper()
            if mac not in self._pals_cache():
                return ["ERR only your own devices (pals) can be tracked"]
            self.classic_find_request(mac, fresh=True)
            return ["OK"]
        if cmd == "STOP":
            self.tracking.pop(writer, None)
            return ["OK"]
        if cmd == "RSSI":  # one-shot reading, for clients that poll (the web page)
            mac = arg.upper()
            if mac not in self._pals_cache():
                return ["ERR only your own devices (pals) can be tracked"]
            live = self.ble.live.get(mac)
            st = self.classic_find_request(mac) or {}   # keeps the finder going while you look
            if live and now - live.last < self.BLE_FRESH_S:
                return [f"RSSI {mac} {live.rssi}"]
            fresh = now - st.get("ts", 0) < 15
            if fresh and st.get("mode") == "pairing":
                return [f"RSSI {mac} {st['rssi']}", f"CLASSIC {mac} pairing"]
            if fresh and st.get("mode") == "ping":
                return [f"RSSI {mac} none", f"CLASSIC {mac} ping {st['rtt']:.0f}"]
            mode = st.get("mode", "listening")
            if mode in ("ping", "pairing"):
                mode = "checking"  # between answers: still working on it
            return [f"RSSI {mac} none", f"CLASSIC {mac} {mode}"]
        if cmd == "TUNE":  # developer tools: list knobs, or TUNE <key> <value|default>
            if not arg:
                return tuning.listing() + ["END"]
            key, _, val = arg.partition(" ")
            if val.strip().lower() == "default":
                err = tuning.set_value(key, tuning.default(key)) if key in dict.fromkeys(k[0] for k in tuning.KNOBS) else "no such knob"
            else:
                err = tuning.set_value(key, val.strip())
            if err:
                return [f"ERR {err}"]
            self._tuning_changed()
            log.info("tuning: %s = %s", key, tuning.get(key))
            return [f"OK {key}={tuning.get(key):g}"]
        if cmd == "TUNERESET":  # TUNERESET food|joy|all
            tuning.reset(arg.lower() or "all")
            self._tuning_changed()
            return ["OK"]
        if cmd == "METER":  # METER food|joy <0-100>: set a meter for playtesting
            which, _, val = arg.lower().partition(" ")
            try:
                v = max(0.0, min(100.0, float(val)))
            except ValueError:
                return ["ERR give a number from 0 to 100"]
            if which == "xp":  # XP isn't a percentage: any whole number
                try:
                    self.pet.xp = max(0, int(float(val)))
                except ValueError:
                    return ["ERR give a number"]
                self.pet.save()
                self.pet.say(f"XP SET TO {self.pet.xp} (LEVEL {self.pet.level()})")
                return ["OK"]
            if which == "rations":
                try:
                    self.pet.rations = max(0.0, float(val))
                except ValueError:
                    return ["ERR give a number"]
                self.pet.save()
                return ["OK"]
            if which == "pack":
                try:
                    self.pet.pack = max(0.0, min(self.pet.pack_cap(), float(val)))
                except ValueError:
                    return ["ERR give a number"]
                self.pet.save()
                self.pet.say(f"PACK SET TO {_n(self.pet.pack)}")
                return ["OK"]
            if which == "food":
                self.pet.hunger = v
            elif which == "joy":
                self.pet.joy = v
            else:
                return ["ERR food, joy, pack or xp"]
            self.pet.save()
            self.pet.say(f"{which.upper()} SET TO {v:g}%")
            return ["OK"]
        if cmd == "ALERTS":
            return [f"{a['id']}|{int(a['since'])}|{a['label']}" for a in self.trackers.alerts.values()] + ["END"]
        if cmd == "DISMISS":
            ok = arg.isdigit() and self.trackers.dismiss(int(arg))
            if ok and not self.trackers.alerts:
                self.pet.alarm, self.pet.reaction = False, None
                self.pet.say("PHEW. ALERT DISMISSED")
            return ["OK" if ok else "ERR no such alert"]
        if cmd == "STARS":  # key|constellation|number|first_seen|days_seen|in_view_now(1/0)
            if not self.stars:
                return ["END"]
            heard = self.stars.last_heard
            return [f"{r['key']}|{r['const']}|{r['prn']}|{int(r['first_seen'])}|{r['nights']}|"
                    f"{1 if now - heard.get(r['key'], 0) <= self.STAR_NOW_S else 0}"
                    for r in self.store.stars()] + ["END"]
        if cmd == "LANDMARKS":  # qid|title|languages|first_seen (0 = not seen yet)|visits
            if not self.landmarks:
                return ["END"]
            return [f"{r['qid']}|{r['title'].replace('|', '/')}|{r['langs']}|{int(r['first_seen'] or 0)}|{r['visits']}"
                    for r in self.store.landmarks_list(tuning.get("landmark_langs"))] + ["END"]
        if cmd == "GREENS":  # id|name|kind|first_seen (0 = not yet)|visits|walks|runs|rides
            if not self.greens:
                return ["END"]
            return [f"{g['id']}|{g['name'].replace('|', '/')}|{g['kind']}|{int(g['first_seen'] or 0)}|"
                    f"{g['visits'] or 0}|{g['walks'] or 0}|{g['runs'] or 0}|{g['rides'] or 0}"
                    for g in self.store.greens_list()] + ["END"]
        if cmd == "LAIR":  # place=, country=, found=, announce=, complete=, now=, then END
            lr = self.lair
            found, reading = lr.summary()
            return [f"place={lr.s.get('place', '')}", f"country={lr.s.get('country_typed', lr.s.get('country', ''))}",
                    f"found={found}", f"announce={1 if lr.s.get('announce') else 0}",
                    f"complete={1 if lr.complete else 0}", f"now={reading}",
                    f"warn_source={lr.warnings_where()[0]}", f"warn_area={lr.warnings_where()[1]}",
                    f"warn_region={(lr.s.get('warn') or {}).get('area', '') if lr.warnings_where()[0] == 'uk' else ''}",
                    "warn_active=" + " || ".join(w["title"] for w in lr.s.get("warn_active") or []),
                    "temp_said=" + (f"{lr.s['temp_said'][1]} at {time.strftime('%H:%M', time.localtime(lr.s['temp_said'][0]))}"
                                    if lr.s.get("temp_said") else "")] + self._aurora_lines() + ["END"]
        if cmd == "LAIRSET":  # place|country: looked up straight away
            place, _, country = arg.partition("|")
            ok, words = await self.lair.set_place(place, country)
            if ok:
                self.event("network", f"{self.pet.name}'s Lair set: {self.lair.s['label']}, {self.lair.s['country']}")
            return [("OK " if ok else "ERR ") + words]
        if cmd == "LAIRREGION":  # the UK warning region, if the guess was wrong (e.g. LAIRREGION nw)
            err = self.lair.set_region(arg.strip().lower())
            return [f"ERR {err}" if err else "OK"]
        if cmd == "LAIRANNOUNCE":  # on / off
            err = self.lair.set_announce(arg.strip().lower() in ("on", "1", "true"))
            return [f"ERR {err}" if err else "OK"]
        if cmd == "LAIRFORGET":
            self.lair.forget()
            self.dot.s["home_town"], self.dot.s["home_lat"], self.dot.s["home_lon"] = "", None, None
            self.dot.save()
            return ["OK"]
        if cmd == "WIFIPOS":  # finding him by Wi-Fi: on=, status=, lookups=, fix_acc=
            w = self.wifipos
            if w.enabled and self.gps.current():
                w.status = "not needed: GPS is working"
            f = w.current()
            return [f"on={1 if w.enabled else 0}", f"status={w.status}", f"lookups={w.lookups}",
                    f"fix_acc={f['acc'] if f else ''}", "END"]
        if cmd == "WIFIPOSSET":  # on / off
            on = arg.strip().lower() in ("on", "1", "true")
            self.wifipos.set_enabled(on)
            self.event("network", f"Finding {self.pet.name} by Wi-Fi switched " + ("on (beaconDB)" if on else "off"))
            return ["OK"]
        if cmd == "RADIO":  # the radio stick: mode=, status=, listening=, found=, scores, planes now
            sky = scores.view(scores.SKY_TITLES, planesmod.score(self.store))
            wh = scores.view(scores.WHISPER_TITLES, whispersmod.score(self.store))
            return self.radio.lines() + [
                "sky=" + json.dumps(sky), "whispers=" + json.dumps(wh),
                "planes_now=" + json.dumps(self.sky.now()[:8]),
                "whispers_recent=" + json.dumps([{"ago": int(time.time() - t), "model": m,
                                                  "kind": whispersmod.KINDS[k][0]} for t, m, k in self.whispers.recent]),
                "installed=" + json.dumps(self.radio.installed()), "END"]
        if cmd == "RADIOSET":  # both / planes / sensors / off
            err = self.radio.set_mode(arg.strip().lower())
            return [f"ERR {err}" if err else "OK"]
        if cmd == "HOMEZONE":  # on=, r=, set=, sizes=
            z = self.home_zone.state()
            return [f"on={1 if z['on'] else 0}", f"r={z['r']}", f"set={1 if z['set'] else 0}",
                    "sizes=" + ",".join(map(str, HOME_SIZES)), "END"]
        if cmd == "HOMEZONESET":  # off / on (around the place set before) / here [meters]
            a = arg.strip().lower().split()
            if a[:1] == ["off"]:
                self.home_zone.off()
                self.event("network", "Home zone switched off")
                return ["OK"]
            if a[:1] == ["on"] and self.home_zone.state()["set"]:
                z = self.store.get("home_zone")
                z["on"] = True
                self.store.put("home_zone", z)
                gone = self.store.forget_obs_where(self.home_zone.inside)
                return [f"OK {gone}"]
            if a[:1] not in (["on"], ["here"]):
                return ["ERR say off, on or here"]
            r = int(a[1]) if len(a) > 1 and a[1].isdigit() else None
            if r is not None and r not in HOME_SIZES:
                return ["ERR sizes are " + ", ".join(map(str, HOME_SIZES)) + " meters"]
            fix = self.gps.current()
            if not fix:
                return [f"ERR {self.pet.name} needs a GPS position to know where home is. Try again at home "
                        "with the GPS working."]
            gone = self.home_zone.set_here(fix, r)
            # (no diary entry: the diary notes where each entry happened, and this one would say
            # "home is here")
            return [f"OK {gone}"]
        if cmd == "FORGETMAP":  # forget every claimed land and realm (and which landmarks he's seen)
            self.store.forget_lands()
            self.store.forget_landmarks_seen()
            self.store.forget_greens_seen()
            self.offline_map.forget()               # (the offline map shows where he's been, too)
            self.event("land", "Forgot the map of claimed lands (and the Conquest points they earned)")
            self.conquest_score(fresh=True)
            return ["OK"]
        if cmd == "SPECIES":
            return [f"{s['meals']}|{s['kind']}|{s['label']}" for s in self.store.species_list()] + ["END"]
        if cmd == "TREATS":
            n = int(arg) if arg.isdigit() else 20
            return [f"{a['bssid']}|{a['best_rssi']}|{a['auth']}|{a['ssid'] or ''}"
                    for a in self.store.recent_aps(n)] + ["END"]
        if cmd == "UPLOAD":
            ok, msg = await self.upload_now(manual=True)
            return [("OK " if ok else "ERR ") + msg]
        if cmd == "NAME":
            name = re.sub(r"[^A-Za-z0-9 \-]", "", arg).strip()
            if not name:
                return ["ERR name must be letters, numbers, spaces"]
            if len(name) > friendsmod.NAME_MAX:
                return [f"ERR names can be up to {friendsmod.NAME_MAX} characters"]
            self.pet.name = name
            self.pet.save()
            self.pet.say(f"MY NAME IS {name}!", "happy", 20)
            return ["OK"]
        if cmd == "RATION":  # give him a ration: the PACK is filled completely
            if self.napping:
                return [f"ERR {self.pet.name} is napping: wake {self.pet.name} first"]
            room = self.pet.ration_room()
            why = self.pet.give_ration()
            if why:
                return [f"ERR {why}"]
            left = int(self.pet.rations + 1e-9)
            self.event("ration", f"You gave {self.pet.name} a ration: +{_n(room)} food, the pack is full "
                                 f"({left} ration{'s' if left != 1 else ''} left).")
            return [f"OK {self.pet.name}'s pack is full ({left} ration{'s' if left != 1 else ''} left)"]
        if cmd == "NAP":
            return [await self.nap()]
        if cmd == "WAKE":
            return [await self.wake_up()]
        if cmd in ("SLEEP", "REBOOT"):
            asyncio.get_running_loop().call_later(0.5, lambda: asyncio.ensure_future(self.shutdown(cmd)))
            return ["OK"]
        if cmd == "FRIENDS":  # id|name|level|near(0/1)|meetings|last_met
            near = {f["id"] for f in self.friends.nearby(now)}
            return [f"{f['id']}|{f['name']}|{f['level']}|{1 if f['id'] in near else 0}|{f['meetings']}|"
                    f"{int(f['last_met'])}" for f in self.friends.all()] + ["END"]
        if cmd == "UNFRIEND":
            self.friends.forget(arg.lower())
            return ["OK"]
        if cmd == "SEARCH":  # look for Classic devices in pairing mode, for 30 seconds
            if getattr(self, "_searching", False):
                return ["OK already searching"]
            asyncio.ensure_future(self.classic_search(30))
            return ["OK searching for 30 seconds"]
        if cmd == "DOT":  # the Echo Dot's state and settings, as key=value lines
            return [f"{k}={v}" for k, v in self.dot.status().items()] + ["END"]
        if cmd == "DOTSET":  # DOTSET <setting> <value>
            key, _, val = arg.partition(" ")
            err = self.dot.set(key, val.strip())
            return [f"ERR {err}"] if err else ["OK"]
        if cmd == "DOTSAY":  # say this now (a test from the den; ignores quiet hours)
            if self.dot.phone_route() in (None, "dot") and not (self.dot.connected and self.dot.ready):
                return [f"ERR the Dot isn't connected (and no phone is speaking for {self.pet.name})"]
            text = arg.strip()[:300]
            if not text:
                return ["ERR type something to say"]
            self.dot.say(text, force=True)
            return ["OK"]
        if cmd == "DOTRING":  # play one of the ring's animations (e.g. ev_test, ev_storm)
            if not (self.dot.connected and self.dot.ready):
                return ["ERR the Dot isn't connected"]
            name = re.sub(r"[^a-z0-9_]", "", arg.lower()) or "ev_test"
            self.dot._seq += 1
            await self.dot.sh(f"echo '{self.dot._seq} {name}' > /data/local/tmp/harald/once", 10)
            return ["OK"]
        if cmd == "ASK":  # a question in writing: the answer comes back (and is spoken, if the Dot is there)
            text = arg.strip()[:200]
            if not text:
                return ["ERR type a question"]
            reply = await self.dot.answer(text)
            self.dot.heard, self.dot.answered = text, reply
            if reply:
                self.pet.say(self.screen_answer(reply, getattr(self.dot, "screen_answer", None)), None, 30, speak=False)
            if reply:
                self.dot.say(reply, force=True)     # out loud through the Dot or the phone, if he has a voice
            return ["OK " + (reply or "(nothing to say)")]
        if cmd.startswith("SHOP"):  # the shopping list page: SHOPADD name, SHOPTOGGLE id, ...
            return self.shopping_command(cmd, arg)
        if cmd == "VOICES":         # id|name|samples|seconds of speech|last updated, then END
            return [f"{p['id']}|{p['name']}|{p['samples']}|{p['frames'] // 100}|{p['updated']}"
                    for p in self.dot.voices.items] + ["END"]
        if cmd in ("VOICENAME", "VOICEDEL"):
            pid, _, rest = arg.partition(" ")
            try:
                pid = int(pid)
            except ValueError:
                return ["ERR which voice?"]
            if cmd == "VOICEDEL":
                return ["OK" if self.dot.voices.delete(pid) else "ERR no such voice"]
            from .voices import clean_name
            name = clean_name(rest) or rest.strip()[:24]
            return ["OK" if name and self.dot.voices.rename(pid, name) else "ERR give a name"]
        if cmd == "CALSAVE":        # the calendar page: an event as JSON (with "id" to change one)
            try:
                ev, err = self.dot.calendar.put(json.loads(arg))
            except (ValueError, TypeError, KeyError):
                return ["ERR that doesn't look like an event"]
            return [f"OK {ev['id']}" if ev else f"ERR {err}"]
        if cmd == "CALDEL":
            try:
                return ["OK" if self.dot.calendar.delete(int(arg)) else "ERR no such event"]
            except ValueError:
                return ["ERR which event?"]
        if cmd == "TIMERS":  # name|seconds left|length, then END
            now = time.time()
            return [f"{t['name']}|{int(max(0, t['end'] - now))}|{int(t['length'])}"
                    for t in sorted(self.dot.timers.items, key=lambda t: t["end"])] + ["END"]
        if cmd == "TIMERCANCEL":  # TIMERCANCEL <name>, or "all"
            if arg.strip().lower() == "all":
                self.dot.timers.cancel(everything=True)
            else:
                self.dot.timers.items = [t for t in self.dot.timers.items if t["name"] != arg.strip()]
                self.dot.timers.save()
            return ["OK"]
        if cmd == "ALARMSTOP":
            self.dot.stop_alarm()
            return ["OK"]
        if cmd == "CVD":       # Color Blindness Mode: full, protanopia, deuteranopia or tritanopia
            from . import access
            if arg:
                if arg.lower() not in access.MODES:
                    return ["ERR choose full, protanopia, deuteranopia or tritanopia"]
                self.store.put("cvd", arg.lower())
                return ["OK"]
            return [self.cvd_mode()]
        if cmd == "SLEEPSCREEN":
            return [f"{k}={1 if v else 0}" for k, v in self.sleep_screens().items()] + ["END"]
        if cmd == "SLEEPSCREENSET":     # SLEEPSCREENSET nap on / SLEEPSCREENSET sleep off
            which, _, val = arg.lower().partition(" ")
            if which not in ("nap", "sleep") or val not in ("on", "off"):
                return ["ERR use: SLEEPSCREENSET nap|sleep on|off"]
            st = self.sleep_screens()
            st[which] = val == "on"
            self.store.put("sleep_screen", st)
            if which == "nap" and self.napping:
                self._nap_redraw = True          # napping now: show the change
            return ["OK"]
        if cmd == "ARTDEL":  # remove one of your pictures (that mood goes back to the drawn one)
            err = self.art.remove(arg.strip().lower())
            if not err and arg.strip().lower() == "nap-screen.png" and self.napping:
                self._nap_redraw = True
            return [f"ERR {err}" if err else "OK"]
        if cmd == "DOTRESCUE":  # hop onto the Dot's setup network now and switch its Wi-Fi back on
            if not self.dot.s["setup_network"] or not self.dot.s["serial"]:
                return [f"ERR set the Dot's setup network name first (and let {self.pet.name} find the Dot once)"]
            if self.dot.connected:
                # Don't take "connected" on trust: it may have restarted a moment ago. Asking
                # it settles that either way (a setup network in an old scan doesn't).
                if "ok" not in (await self.dot.sh("echo ok", 8) or ""):
                    self.dot.mark_lost("it didn't answer when asked to rescue it")
                else:
                    return ["ERR the Dot is already on the hotspot (it just answered)"]
            asyncio.ensure_future(self.dot.rescue())
            return [f"OK rescuing (the den will lose {self.pet.name} for up to a minute)"]
        if cmd == "DOTFIND":  # look for the Dot now instead of within the minute
            self.dot._last_scan = self.dot._last_full = 0.0
            return ["OK looking (give it a minute)"]
        if cmd == "DOTFORGET":  # give the Dot back to Amazon and forget it
            await self.dot.forget()
            return ["OK"]
        if cmd == "HELP":
            return ["HELLO STATUS LOG NEARBY PALS ADDPAL DELPAL TRACK STOP RSSI ALERTS DISMISS "
                    "SPECIES TREATS FRIENDS UNFRIEND SEARCH UPLOAD NAME SLEEP REBOOT", "END"]
        return ["ERR unknown command"]

    def shopping_command(self, cmd, arg):
        from .shopping import SECTIONS
        sl = self.dot.shopping
        if cmd == "SHOPADD":
            result, item = sl.add(arg[:60])
            return [f"OK {result} {item['id']}" if item else "ERR type an item"]
        try:
            item_id = int(arg.split(" ", 1)[0]) if cmd != "SHOPCLEAR" else None
        except ValueError:
            return ["ERR which item?"]
        if cmd == "SHOPTOGGLE":
            return ["OK" if sl.toggle(item_id) else "ERR no such item"]
        if cmd == "SHOPDEL":
            return ["OK" if sl.remove(item_id=item_id) else "ERR no such item"]
        if cmd == "SHOPEDIT":       # SHOPEDIT id {"qty": "2", "store": "The Market"}
            try:
                d = json.loads(arg.split(" ", 1)[1]) if " " in arg else {}
            except ValueError:
                return ["ERR that doesn't look right"]
            return ["OK" if sl.set_details(item_id, d.get("qty"), d.get("store")) else "ERR no such item"]
        if cmd == "SHOPMOVE":
            section = arg.split(" ", 1)[1].strip() if " " in arg else ""
            if section not in SECTIONS:
                return ["ERR no such section"]
            return ["OK" if sl.move(item_id, section) else "ERR no such item"]
        if cmd == "SHOPCLEAR":
            return [f"OK {sl.clear_done()}"]
        return ["ERR unknown command"]

    def calendar_data(self):
        import datetime as dt
        cal = self.dot.calendar
        return {"events": cal.events, "today": dt.date.today().isoformat(),
                "upcoming": [{"date": d.isoformat(), "ids": [e["id"] for e in evs]} for d, evs in cal.upcoming(90)]}

    def shopping_data(self):
        from .shopping import SECTIONS
        sl = self.dot.shopping
        return {"sections": SECTIONS, "items": sl.items, "changed": sl.changed, "stores": sl.known_stores()}

    # ================================================================ lifecycle
    async def _sleep(self, s):
        try:
            await asyncio.wait_for(self.stop.wait(), s)
        except asyncio.TimeoutError:
            pass

    async def nap(self):
        """As good as switched off, but still plugged in and wakeable from the den: no
        feeding, no Dot (dark and quiet), meters frozen, nothing written to the card."""
        if self.napping:
            return "OK already napping"
        log.info("going for a nap")
        self.event("sleep", f"{self.pet.name} went for a nap")
        try:
            await asyncio.wait_for(self.dot.release(), 10)   # the ring goes dark, the Dot quiet
        except Exception:
            pass
        self.pet.save()
        self.activity.save()
        self._save_ble()
        self.nap_since = time.time()
        self.store.put("napping", {"since": self.nap_since})    # so a restart doesn't wake him
        self.napping = True
        self.store.flush()
        await asyncio.to_thread(self._flush_to_card)
        return "OK napping"

    def _flush_to_card(self):
        """Everything onto the card now, so pulling the plug mid-nap loses nothing."""
        try:
            self.store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as e:
            log.warning("checkpoint: %s", e)
        try:
            os.sync()
        except (AttributeError, OSError):
            pass

    async def wake_up(self):
        if not self.napping:
            return "OK already awake"
        away = time.time() - self.nap_since if self.nap_since else 0
        self.napping = False
        self.store.put("napping", None)
        # the time asleep counts like time switched off: the meters catch up (once the clock
        # is known to be right) and the Dot gives a welcome-back recap
        self._mono_start, self._caught_up, self._from_nap = time.monotonic(), False, True
        self.started = time.time()
        from .pet import away_words
        self.event("wake", f"{self.pet.name} woke up from a nap" + (f" ({away_words(away).lower()})" if away >= 60 else ""))
        self.pet.say(["YAWN! HELLO!"], "happy", 20)
        self.store.flush()          # awake for sure, even if the power goes in the next minute
        return "OK awake"

    def _trip_view(self):
        t = self.activity.trip_now()
        if not t or t["meters"] < 10:
            return None
        return {"label": t["label"], "dist": actmod.km_mi(t["meters"]),
                "time": actmod.duration_words(t["seconds"], True),
                "start": time.strftime("%H:%M", time.localtime(t["start"]))}

    def _exercise_today(self):
        """Today's walks, runs and rides, for the den: ['Walk: 4.57 km (2.84 mi) in 1 h 24 min, from 15:20']."""
        lt = time.localtime()
        midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        out = []
        for r in self.store.exercise_since(midnight):
            label = {"walk": "Walk", "run": "Run", "ride": "Bike ride"}.get(r["kind"], "Walk")
            out.append(actmod.exercise_line({"label": label, "meters": r["meters"], "start": r["start"],
                                             "seconds": r["end"] - r["start"]}))
        return out

    def restart_soon(self, why):
        """Restart the program (not the Pi) in a moment: systemd stops him cleanly and
        starts him again."""
        log.info("restarting: %s", why)
        self.store.flush()
        if self.simulate:
            return
        asyncio.get_running_loop().call_later(
            1.0, lambda: subprocess.Popen(["systemctl", "--no-block", "restart", "bt-dragon"]))

    async def shutdown(self, how="SLEEP"):
        if self.pet.sleeping:
            return
        log.info("going to sleep (%s)", how)
        self.pet.sleeping = True
        self.event("sleep", f"{self.pet.name} went to sleep" if how == "SLEEP" else f"{self.pet.name} is restarting")
        try:
            await asyncio.wait_for(self.dot.release(), 10)   # the ring goes dark too
        except Exception:
            pass
        self.pet.save()
        self.activity.save()
        self._save_ble()
        self.store.flush()
        await asyncio.to_thread(self._flush_to_card)
        async with self._draw_lock:     # wait for any picture being drawn right now to finish first
            pic = (self.art.screen("sleep") if how == "SLEEP" and self.sleep_screens()["sleep"]
                   else render_sleep(self.view()))
            await asyncio.to_thread(self.display.sleep, pic)
        self.stop.set()
        if not self.simulate and how in ("SLEEP", "REBOOT"):
            subprocess.Popen(["systemctl", "poweroff" if how == "SLEEP" else "reboot"])

    def setup_home_wifi(self):
        if self.simulate:
            return
        hash_password_in_file(self.cfg)
        wifimod.ensure_profiles(config_networks(self.cfg))

    # ================================================================ which network
    def network_rank(self, ssid):
        """0 = the main hotspot, 1 = the first backup, ...; None = not one of ours."""
        for rank, (s, _) in enumerate(config_networks(self.cfg)):
            if s == ssid:
                return rank
        return None

    async def switch_to_best(self, visible=None, reason="asked"):
        """Connect to the best of our networks that's in range right now."""
        if self._switching:
            return "already switching networks"
        if visible is None:
            visible = {ap["ssid"] for ap in await self.wifi.scan()}
        nets = config_networks(self.cfg)
        best = next((rank for rank, (s, _) in enumerate(nets) if s in visible), None)
        if best is None:
            self.pet.say("NONE OF MY NETWORKS ARE IN RANGE")
            return "none of the networks are in range"
        ssid = nets[best][0]
        if ssid == self.home_ssid:
            self.pet.say(f"STAYING ON {ssid}: IT'S THE BEST ONE HERE")
            return f"already on {ssid}, the best network in range"
        self._switching = True
        try:
            self.pet.say(f"SWITCHING TO {ssid}...")
            self.event("network", f"Switching to {ssid} ({reason})")
            ok, msg = await wifimod.connect_profile(wifimod.profile_name(best))
            if ok:
                self.home_ssid = ssid
                self._join_errors.pop(ssid, None)
                self.pet.say(f"NOW ON {ssid}")
                return f"switched to {ssid}"
            self._join_errors[ssid] = msg
            self.event("network", f"Couldn't switch to {ssid}: {msg}")
            self.pet.say(f"COULDN'T JOIN {ssid}")
            return f"couldn't join {ssid}: {msg}"
        finally:
            self._switching = False

    async def _rejoin_if_lost(self, aps, now=None):
        """No network for half a minute: don't just wait for the Pi's network manager to pick
        one, join the best of ours that's in range (a backup, say), and keep trying each minute."""
        now = time.time() if now is None else now
        if self.home_ssid:
            self._lost_since = None
            return
        if getattr(self, "_lost_since", None) is None:
            self._lost_since = now
            return
        if self._switching or now - self._lost_since < 30 or now - getattr(self, "_rejoin_tried", float("-inf")) < 60:
            return
        visible = {ap["ssid"] for ap in aps}
        if not any(s in visible for s, _ in config_networks(self.cfg)):
            return
        self._rejoin_tried = now
        await self.switch_to_best(visible, "lost the network")

    def network_info(self):
        """For the den: each of our networks, whether it's in range, its security, and any
        reason he can't join it."""
        ts, aps = getattr(self, "_last_aps", (0, []))
        out = []
        for rank, (ssid, secret) in enumerate(config_networks(self.cfg)):
            seen = [a for a in aps if a.get("ssid") == ssid] if time.time() - ts < 120 else []
            sec = max((a.get("security", "") for a in seen), key=lambda x: x == "wpa3", default="")
            note = wifimod.PROFILE_ERRORS.get(ssid) or self._join_errors.get(ssid, "")
            if sec == "wpa3" and re.fullmatch(r"[0-9a-f]{64}", secret or ""):
                note = ("This hotspot only accepts WPA3, which needs the password itself rather than the "
                        "scrambled key. Set its security to WPA2/WPA3-Personal on the phone.")
            out.append({"rank": rank, "ssid": ssid, "connected": ssid == self.home_ssid,
                        "in_range": bool(seen), "security": sec, "note": note})
        return out

    def _maybe_return(self, aps):
        """On a backup network and a better one is back in range (seen in two scans in a
        row, with a decent signal)? Move over to it."""
        if not self.cfg["network"]["return_to_better"] or self._switching:
            return
        rank = self.network_rank(self.home_ssid)
        if rank is None or rank == 0:
            self._better_seen = 0
            return
        strong = {ap["ssid"] for ap in aps if ap.get("rssi", -100) >= -75}
        nets = config_networks(self.cfg)
        if any(s in strong for s, _ in nets[:rank]):
            self._better_seen += 1
            if self._better_seen >= 2:
                self._better_seen = 0
                asyncio.ensure_future(self.switch_to_best({ap["ssid"] for ap in aps}, "a better one is back"))
        else:
            self._better_seen = 0

    async def _awake_only(self, start):
        """Run start(stop_event) only while he's awake: a nap stops it, waking starts it again."""
        while not self.stop.is_set():
            if self.napping:
                await self._sleep(2)
                continue
            inner = asyncio.Event()
            task = asyncio.ensure_future(start(inner))
            while not (self.stop.is_set() or self.napping or task.done()):
                await self._sleep(2)
            inner.set()
            try:
                await asyncio.wait_for(task, 15)
            except Exception as e:
                log.warning("stopping for the nap: %s", e)
            if task.done() and not (self.stop.is_set() or self.napping):
                await self._sleep(5)          # it ended by itself: don't spin

    async def run(self, extra_tasks=()):
        from .server import serve_all
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self.shutdown("STOP")))
            except (NotImplementedError, RuntimeError):
                pass
        self.setup_home_wifi()
        if self.napping:
            log.info("still napping after a restart; wake up from the den")
        else:
            self.event("wake", f"{self.pet.name} woke up")
        tasks = [self.pet_loop(), self.display_loop(), self.wigle_loop(), self.activity_loop(), serve_all(self),
                 self.offline_map_loop()]
        a = self.cfg["activity"]
        if a["enabled"] and not self.simulate:
            host = a["steps_host"]
            tasks.append(self._awake_only(lambda s: self.steplink.run(lambda: host or wifimod.gateway_ip(), a["steps_port"], s)))
            if self.baro:
                tasks.append(self._awake_only(lambda s: self.baro_link.run(lambda: host or wifimod.gateway_ip(), a["steps_port"], s)))
            tasks.append(self._awake_only(lambda s: self.light_link.run(lambda: host or wifimod.gateway_ip(), a["steps_port"], s)))
        g = self.cfg["gps"]
        self.gps.prefer = "usb" if str(g.get("prefer", "phone")).lower() == "usb" else "phone"
        if str(g.get("usb", "auto")).lower() != "off" and not self.simulate:
            from .gps import run_usb
            dev = str(g.get("usb", "auto"))
            tasks.append(self._awake_only(lambda s: run_usb(self.gps, dev if dev.startswith("/") else "auto", s)))
        if g["source"] in ("auto", "udp"):
            tasks.append(self._awake_only(lambda s: self.gps.listen_udp(g["udp_port"], s)))
        if g["source"] in ("auto", "tcp"):
            gps_host = g["tcp_host"]
            tasks.append(self._awake_only(lambda s: self.gps.connect_tcp(lambda: gps_host or wifimod.gateway_ip(), g["tcp_port"], s)))
        if g["source"] in ("auto", "sensorserver") and not self.simulate:
            a_ = self.cfg["activity"]
            ss_host = a_["steps_host"]
            tasks.append(self._awake_only(lambda s: self.gps.connect_sensorserver(lambda: ss_host or wifimod.gateway_ip(),
                                                                                   a_["steps_port"], s)))
        if not self.simulate:
            from .ble import BleakScanner
            scanner = BleakScanner(self.on_advert)
            tasks.append(self._awake_only(scanner.run))      # the Bluetooth radio rests during a nap
            tasks.append(self.wifi_loop())
            tasks.append(self.dot.run())
            tasks.append(self._awake_only(self.radio.run))   # the radio stick rests during a nap too
            if self.cfg["friends"]["beacon"]:
                beacon = friendsmod.Beacon(self.beacon_payload, quiet=scanner.quiet)
                tasks.append(self._awake_only(beacon.run))
        if self.simulate:
            tasks.append(self.dot._timer_loop())   # timers work without the Dot too
        tasks.extend(extra_tasks)
        try:
            await asyncio.gather(*tasks)
        finally:
            self.store.flush()          # however he stops, nothing waiting is lost
