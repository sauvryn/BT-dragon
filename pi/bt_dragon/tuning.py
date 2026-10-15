"""
Developer Tools: every food, joy and XP number the dragon uses, adjustable while he runs.

Each knob has a default (what's written in the code, or the config file for the belly
timer). The den can override any of them; overrides are saved in Harald's database, so
they survive restarts and updates until you reset them. Code reads a knob with
tuning.get("snack_food") at the moment it needs it, so a change takes effect at once.
"""

# key, section, label, default, unit, help
KNOBS = [
    # ---------------------------------------------------------------- food
    ("food_empty_min", "food", "Full belly empties in", 150, "min",
     "How long FOOD takes to drop from 100 to 0 with nothing to eat."),
    ("food_off_drain", "food", "FOOD drain while switched off", 100, "%",
     "How fast FOOD drops while your dragon is off, compared with awake. 25 = a quarter as fast."),
    ("snack_food", "food", "Snack: new gadget or new arrival", 2, "food", ""),
    ("feast_food", "food", "Feast: a species he's never eaten", 12, "food", ""),
    ("treat_food_wpa2", "food", "Treat: new WPA2 network", 4, "food", "The everyday kind."),
    ("treat_food_wpa3", "food", "Treat: new WPA3 network", 5, "food", ""),
    ("treat_food_enterprise", "food", "Treat: new office network", 5, "food", "WPA2/3-Enterprise."),
    ("treat_food_open", "food", "Treat: new open network", 6, "food", ""),
    ("treat_food_wep", "food", "Treat: new WEP network", 6, "food", ""),
    ("berry_per_day", "food", "Berries: regrowth per day", 1, "food/day",
     "A known network regrows this much per day since he last saw it, up to its treat value."),
    ("pack_cap", "food", "PACK: how much it holds", 50, "food",
     "Berries and treats he finds while his belly is full go into his PACK, up to this much."),
    ("pack_trigger", "food", "PACK: eat from it when FOOD drops to", 25, "%", ""),
    ("pack_portion", "food", "PACK: how much of it he eats each time", 50, "%",
     "Never more than it takes to fill his belly back to 100."),
    ("land_food", "food", "New land claimed", 3, "food", "A square of the map about 250 m across."),
    ("garden_food_common", "food", "Butterfly Garden: food to raise a Common one", 40, "food",
     "Only food that fits in neither his BELLY nor his PACK reaches the garden, shared between the larvae there."),
    ("garden_food_uncommon", "food", "Butterfly Garden: food to raise an Uncommon one", 80, "food", ""),
    ("garden_food_rare", "food", "Butterfly Garden: food to raise a Rare one", 120, "food", ""),
    ("realm_food", "food", "New realm claimed", 3, "food", "A square of the map about 1 km across."),
    ("star_food", "food", "A star (satellite) he's never seen", 3, "food", ""),
    ("constellation_food", "food", "His first star of a new constellation", 6, "food", ""),
    # ---------------------------------------------------------------- joy
    ("joy_empty_min", "joy", "Full joy empties in", 1000, "min",
     "How long JOY takes to drop from 100 to 0 with nothing happening."),
    ("joy_off_drain", "joy", "JOY drain while switched off", 100, "%",
     "How fast JOY drops while your dragon is off, compared with awake. 25 = a quarter as fast."),
    ("snack_joy", "joy", "Snack", 0.3, "joy", ""),
    ("feast_joy", "joy", "Feast", 8, "joy", ""),
    ("treat_joy", "joy", "Treat (any new network)", 2, "joy", ""),
    ("berry_joy", "joy", "Berries, per point of food", 0.2, "joy", ""),
    ("walk_joy", "joy", "Walking or running together", 3, "joy/100 m", ""),
    ("cycle_joy", "joy", "Cycling together", 1.5, "joy/100 m", ""),
    ("ride_joy", "joy", "Riding in a vehicle together", 1, "joy/km", ""),
    ("adventure_bonus", "joy", "Adventure bonus at the end of a walk", 8, "joy",
     "Given when a trip ends with at least 200 m on foot."),
    ("story_joy", "joy", "Story: steps without him", 1, "joy/100 m",
     '"You told your dragon about your adventure!"'),
    ("story_cap", "joy", "Story: most joy from one story", 30, "joy", ""),
    ("friend_new_joy", "joy", "Meeting a new dragon", 15, "joy", ""),
    ("friend_back_joy", "joy", "A dragon friend comes back", 8, "joy", ""),
    ("pal_joy", "joy", "Spotting one of your pals", 3, "joy", "At most once per pal every 10 minutes."),
    ("levelup_joy", "joy", "Leveling up", 5, "joy", ""),
    ("ecstatic_joy", "joy", "Big-joy face from", 8, "joy",
     "Any single joy boost at least this big shows his ecstatic face (big starry eyes); smaller ones show the excited face."),
    ("land_joy", "joy", "New land claimed", 4, "joy", ""),
    ("realm_joy", "joy", "New realm claimed", 10, "joy", ""),
    ("star_joy", "joy", "A star (satellite) he's never seen", 2, "joy", ""),
    ("constellation_joy", "joy", "His first star of a new constellation", 12, "joy", ""),
    ("star_again_joy", "joy", "A known star rising again", 1, "joy/star",
     "When a satellite he's heard before comes back over the horizon."),
    ("storm_first_joy", "joy", "A storm coming: first of the day", 15, "joy", ""),
    ("storm_joy", "joy", "A storm coming: later ones that day", 4, "joy", ""),
    ("rise_joy", "joy", "Pressure rising fast: weather change", 3, "joy", ""),
    ("sun_joy", "joy", "Sunrise or sunset at the Lair", 2, "joy", "With the Lair's Local announcements on."),
    ("sunny_joy", "joy", "Sunshine on the phone's light sensor", 3, "joy",
     "\"Wow! It's sunny out today!\" At most once per Sunshine wait (Detection)."),
    ("climb_joy", "joy", "Climbing (stairs, hills)", 2, "joy/10 m", ""),
    ("landmark_joy", "joy", "A famous place he's never seen", 6, "joy", ""),
    ("landmark_again_joy", "joy", "A famous place seen again", 2, "joy", "Once per place per day."),
    ("green_joy", "joy", "A green space he's never been in", 5, "joy",
     "Parks, woods, nature reserves, commons and gardens, from OpenStreetMap."),
    ("green_visit_joy", "joy", "A walk, run or ride in a green space", 6, "joy", "Once per green space per day."),
    ("moon_full_joy", "joy", "Full moon", 12, "joy", "Once, on the day of the full moon."),
    ("moon_phase_joy", "joy", "New moon or a quarter moon", 4, "joy", "Once, on the day of each."),
    ("garden_hatch_joy", "joy", "Butterfly Garden: an egg hatches", 3, "joy", ""),
    ("garden_pupate_joy", "joy", "Butterfly Garden: a larva pupates", 3, "joy", ""),
    ("garden_emerge_joy", "joy", "Butterfly Garden: an adult emerges", 10, "joy", "The big-joy face from 8."),
    # ---------------------------------------------------------------- XP
    ("xp_curve", "xp", "Level curve", 50, "XP",
     "Level 2 needs this much XP, level 3 four times it, level 4 nine times, level 5 sixteen "
     "times (level = 1 + square root of XP / this)."),
    ("snack_xp", "xp", "Snack", 1, "XP", ""),
    ("feast_xp", "xp", "Feast", 20, "XP", ""),
    ("treat_xp_wpa2", "xp", "Treat: new WPA2 network", 5, "XP", ""),
    ("treat_xp_wpa3", "xp", "Treat: new WPA3 network", 8, "XP", ""),
    ("treat_xp_enterprise", "xp", "Treat: new office network", 8, "XP", ""),
    ("treat_xp_open", "xp", "Treat: new open network", 10, "XP", ""),
    ("treat_xp_wep", "xp", "Treat: new WEP network", 15, "XP", ""),
    ("berry_xp", "xp", "Berries, per point of food", 0.25, "XP", ""),
    ("walk_xp", "xp", "Walking or running together", 2, "XP/100 m", ""),
    ("cycle_xp", "xp", "Cycling together", 1, "XP/100 m", ""),
    ("ride_xp", "xp", "Riding in a vehicle together", 1, "XP/km", ""),
    ("adventure_xp", "xp", "Adventure bonus at the end of a walk", 5, "XP", ""),
    ("story_xp", "xp", "Story: steps without him", 1, "XP/100 m", ""),
    ("friend_new_xp", "xp", "Meeting a new dragon", 50, "XP", ""),
    ("friend_back_xp", "xp", "A dragon friend comes back", 10, "XP", ""),
    ("pal_xp", "xp", "Spotting one of your pals", 0, "XP", ""),
    ("land_xp", "xp", "New land claimed", 10, "XP", ""),
    ("realm_xp", "xp", "New realm claimed", 15, "XP", ""),
    ("star_xp", "xp", "A star (satellite) he's never seen", 5, "XP", ""),
    ("constellation_xp", "xp", "His first star of a new constellation", 25, "XP", ""),
    ("storm_xp", "xp", "A storm or weather change coming", 5, "XP", ""),
    ("climb_xp", "xp", "Climbing (stairs, hills)", 1, "XP/10 m", ""),
    ("landmark_xp", "xp", "A famous place he's never seen", 10, "XP", ""),
    ("green_xp", "xp", "A green space he's never been in", 8, "XP", ""),
    ("green_visit_xp", "xp", "A walk, run or ride in a green space", 5, "XP", "Once per green space per day."),
    ("moon_xp", "xp", "A major moon phase", 5, "XP", ""),
    ("garden_xp", "xp", "Butterfly Garden: an adult emerges", 10, "XP", ""),
    # ---------------------------------------------------------------- detection
    ("land_accuracy_m", "detect", "Lands: ignore GPS fixes less precise than", 30, "m",
     "Stops GPS wobble from claiming land while you sit still."),
    ("land_wifi_accuracy_m", "detect", "Lands: ignore Wi-Fi positions less precise than", 75, "m",
     "Only used when he's finding himself by Wi-Fi (no GPS). Larger claims more, but sometimes the square next door."),
    ("land_reach_m", "detect", "Lands: claim neighboring squares within", 40, "m",
     "Passing this close to a square's edge claims it, so land behind a fence or wall can be claimed from the street. 0 = only the square you're in."),
    ("land_vehicle_pct", "detect", "Lands: rewards while riding in a vehicle", 25, "%",
     "Driving claims land fast, so it's worth less than walking."),
    ("star_min_snr", "detect", "Stars: weakest signal that counts", 15, "dB-Hz",
     "Phones list satellites they expect to see; only ones actually heard this strongly count."),
    ("star_rise_elev", "detect", "Stars: 'rising' means first heard below", 20, "°",
     "Height above the horizon. A satellite heard again this low, after being out of earshot, has just risen."),
    ("star_away_min", "detect", "Stars: out of earshot for at least", 60, "min",
     "So a satellite lost for a moment behind a building doesn't count as rising again."),
    ("climb_step_m", "detect", "Climbing: smallest climb that counts", 3, "m",
     "About one floor. Rising this much within 3 minutes counts as climbing."),
    ("storm_hpa", "detect", "Storm: pressure fall within 3 hours", 3, "hPa",
     "Forecasters treat a fall of about 3 hPa in 3 hours as a sign of wind and rain on the way."),
    ("rise_hpa", "detect", "Weather change: pressure rise within 3 hours", 3, "hPa", ""),
    ("lair_temp_every_h", "detect", "Lair: say how warm it is there every", 1, "hours",
     "On the hour. Not during the Dot's quiet hours."),
    ("adv_walk_km", "detect", "Adventure mode: say how far we've walked every", 0.5, "km",
     "Today's walking, out loud through the Dot in Adventure mode: \"We've walked 2.5 kilometres!\""),
    ("adv_climb_m", "detect", "Adventure mode: say how high we've climbed every", 20, "m",
     "Today's climbing, out loud in Adventure mode. 20 m is about six floors."),
    ("voice_match", "detect", "Voice profiles: how alike a voice must be", 60, "%",
     "How closely a voice must match a profile before he'll call you by name. Higher: surer, but he "
     "recognizes you less often. The den shows how alike the last voice was."),
    ("wake_strict", "detect", "Wake word: how strict", 50, "%",
     "0 = the original, quickest wake word (most false alarms). Higher: more sound-alike words for "
     "\"hey dragon\" to lose to, then a second listen that must be this sure (from 20), and from 70 a "
     "pause before \"hey\". Too high and he'll miss you. The den shows how sure he was last time "
     "and how many near-misses he turned down."),
    ("name_chance", "detect", "Voice profiles: say your name in a reply", 50, "%",
     "How often he adds the name of whoever he recognized: \"It's 7:30 at night, Sam.\""),
    ("sunny_lux", "detect", "Sunshine: brightness that counts", 30000, "lux",
     "From the phone's light sensor. Indoors is about 100 to 500 lux, a grey day outside 1,000 to "
     "20,000, and sunshine 30,000 to 100,000."),
    ("sunny_hold_s", "detect", "Sunshine: bright for at least", 30, "s",
     "So a moment of glare (a lamp, a reflection) doesn't count."),
    ("sunny_every_h", "detect", "Sunshine: wait between cheers", 3, "h",
     "After he's cheered about the sun, he waits this long before he can again."),
    ("green_walk_min", "detect", "Green spaces: a walk is at least", 10, "min",
     "Time on foot inside one (with at least 150 m of actual walking): \"Took a walk in Oakfield Country Park!\""),
    ("green_run_min", "detect", "Green spaces: a run is at least", 5, "min", "\"Went for a run in ...!\""),
    ("green_bike_min", "detect", "Green spaces: a bike ride is at least", 5, "min",
     "\"Biked through ...!\" Time in a vehicle never counts."),
    ("green_margin_m", "detect", "Green spaces: count as inside within", 20, "m",
     "Of the outline on the map, for GPS wobble and paths that run along the edge."),
    ("landmark_langs", "detect", "Landmarks: how famous", 10, "languages",
     "A place counts as famous when Wikipedia has an article about it in at least this many languages."),
    ("landmark_m", "detect", "Landmarks: point them out within", 250, "m",
     "How close you need to be for him to say \"LOOK!\"."),
]

_defaults = {k[0]: k[3] for k in KNOBS}
_info = {k[0]: k for k in KNOBS}
_over = {}
_store = None


def load(store, config_defaults=None):
    """Connect to the database and read saved overrides."""
    global _store
    _store = store
    for k, v in (config_defaults or {}).items():
        if k in _defaults:
            _defaults[k] = v
    _over.clear()
    for k, v in (store.get("tuning", {}) or {}).items():
        if k in _defaults:
            _over[k] = float(v)


def get(key):
    return _over.get(key, _defaults[key])


def default(key):
    return _defaults[key]


def set_value(key, value):
    """Override one knob. Returns an error message, or None."""
    if key not in _defaults:
        return "no such knob"
    try:
        v = float(value)
    except ValueError:
        return "not a number"
    if v != v or v < 0 or v > 100000:
        return "must be between 0 and 100000"
    if key.endswith("_empty_min") and v < 1:
        return "must be at least 1 minute"
    if key in ("pack_trigger", "pack_portion", "land_vehicle_pct") and v > 100:
        return "must be a percentage, 0 to 100"
    if key in ("xp_curve", "climb_step_m", "storm_hpa", "rise_hpa") and v < 0.5:
        return "too small"
    if key == "lair_temp_every_h" and (v < 1 or v != int(v)):
        return "a whole number of hours, at least 1"
    if key == "xp_curve" and v < 1:
        return "must be at least 1"
    if v == float(_defaults[key]):
        _over.pop(key, None)
    else:
        _over[key] = v
    _save()
    return None


def reset(section=None):
    for k in list(_over):
        if section in (None, "all") or _info[k][1] == section:
            del _over[k]
    _save()


def _save():
    if _store is not None:
        _store.put("tuning", dict(_over))


def listing():
    """One line per knob: key|section|label|value|default|unit|help"""
    out = []
    for key, section, label, dflt, unit, help_ in KNOBS:
        out.append("|".join(str(x) for x in (key, section, label, _num(get(key)), _num(_defaults[key]),
                                             unit, help_.replace("|", "/"))))
    return out


def _num(v):
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"
