"""
Developer Tools: every food, joy and XP number the dragon uses, adjustable while it runs.

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
    ("feast_food", "food", "Feast: a type of gadget never eaten before", 12, "food", ""),
    ("treat_food_wpa2", "food", "Treat: new WPA2 network", 4, "food", "The everyday kind."),
    ("treat_food_wpa3", "food", "Treat: new WPA3 network", 5, "food", ""),
    ("treat_food_enterprise", "food", "Treat: new office network", 5, "food", "WPA2/3-Enterprise."),
    ("treat_food_open", "food", "Treat: new open network", 6, "food", ""),
    ("treat_food_wep", "food", "Treat: new WEP network", 6, "food", ""),
    ("treat_food_mobile", "food", "Treat: mobile Wi-Fi (a car's, a bus's, a phone's...)", 1, "food",
     "Networks that travel (cars, dashcams, buses, trains, phone hotspots, pocket routers): a smaller treat, no "
     "berries, and never uploaded to WiGLE. Recognized by name (mobilewifi.py)."),
    ("berry_per_day", "food", "Berries: regrowth per day", 1, "food/day",
     "A known network regrows this much per day since it was last seen, up to its treat value."),
    ("pack_cap", "food", "PACK: how much it holds", 50, "food",
     "Berries and treats found while the belly is full go into the PACK, up to this much (at level 1: it grows as "
     "your dragon levels up, see Growing up)."),
    ("growth_pct", "food", "Growing up: bigger appetite each level", 5, "%",
     "Each level, the belly, joy and PACK hold this much more than at level 1 (each snack fills a smaller share). "
     "0 = the same at every level."),
    ("growth_max", "food", "Growing up: at most", 200, "% of level 1",
     "The limit, so a grown dragon somewhere quiet can still be kept fed. 200 = twice level 1."),
    ("garden_grows", "food", "Growing up: the Butterfly Garden's needs grow too", 0, "0/1",
     "1 = new larvae need more food at higher levels, in step with the growing appetite; 0 = the same at every level."),
    ("pack_trigger", "food", "PACK: eat from it when FOOD drops to", 25, "%", ""),
    ("pack_portion", "food", "PACK: how much of it gets eaten each time", 50, "%",
     "Never more than it takes to fill the belly back to 100."),
    ("ration_feast", "food", "Rations: earned for each feast", 1, "rations",
     "A ration fills the PACK completely, but only when you press Give Ration in the den: food for when you're "
     "stuck somewhere and can't take your dragon out. Fractions add up: 0.25 = one ration for every 4 feasts."),
    ("ration_land", "food", "Rations: earned for each land claimed", 1, "rations",
     "A new realm comes with its first land, so it earns the same. While riding in a vehicle, a land earns this "
     "much times 'Lands: rewards while riding' (under Detection). Fractions add up: 0.1 = one for every 10 lands."),
    ("ration_max", "food", "Rations: most that can be stored", 0, "rations",
     "0 = no limit: they can be stockpiled for lean times."),
    ("land_food", "food", "New land claimed", 3, "food", "A square of the map about 250 m across."),
    ("garden_food_common", "food", "Butterfly Garden: food to raise a Common one", 40, "food",
     "Snacks and feasts that don't fit in the BELLY, and treats and berries that fit in neither the BELLY nor the "
     "PACK, reach the garden, shared between the larvae there."),
    ("garden_food_uncommon", "food", "Butterfly Garden: food to raise an Uncommon one", 80, "food", ""),
    ("garden_food_rare", "food", "Butterfly Garden: food to raise a Rare one", 120, "food", ""),
    ("garden_pupa_hours", "food", "Butterfly Garden: hours as a pupa", 24, "hours",
     "A larva eats until it pupates; then it eats nothing, and the adult emerges by itself this long after."),
    ("realm_food", "food", "New realm claimed", 3, "food", "A square of the map about 1 km across."),
    ("star_food", "food", "A star (satellite) never seen before", 3, "food", ""),
    ("radio_food", "food", "Radio stick: each plane or little radio, once a day", 1, "food",
     "Sky Dragons and Radio Whispers (with an RTL-SDR stick)."),
    ("radio_kind_food", "food", "Radio stick: a new kind of aircraft or device", 6, "food", ""),
    ("constellation_food", "food", "The first star of a new constellation", 6, "food", ""),
    # ---------------------------------------------------------------- joy
    ("joy_empty_min", "joy", "Full joy empties in", 600, "min",
     "How long JOY takes to drop from 100 to 0 with nothing happening."),
    ("joy_off_drain", "joy", "JOY drain while switched off", 100, "%",
     "How fast JOY drops while your dragon is off, compared with awake. 25 = a quarter as fast."),
    ("snack_joy", "joy", "Snack", 0.02, "joy",
     "Tiny on purpose: a hundred snacks an hour is normal at home (phones change their Bluetooth address often)."),
    ("feast_joy", "joy", "Feast", 5, "joy", ""),
    ("treat_joy", "joy", "Treat (a new network)", 0.5, "joy", "A city has a few hundred new networks an hour."),
    ("treat_joy_mobile", "joy", "Treat: mobile Wi-Fi", 0.1, "joy", ""),
    ("berry_joy", "joy", "Berries, per point of food", 0.2, "joy", ""),
    ("walk_joy", "joy", "Walking or running together", 3, "joy/100 m", ""),
    ("cycle_joy", "joy", "Cycling together", 1.5, "joy/100 m", ""),
    ("ride_joy", "joy", "Riding in a vehicle together", 1, "joy/km", ""),
    ("adventure_bonus", "joy", "Adventure bonus at the end of a walk", 8, "joy",
     "Given when a trip ends with at least 200 m on foot."),
    ("story_joy", "joy", "Story: steps without your dragon", 1, "joy/100 m",
     '"You told your dragon about your adventure!"'),
    ("story_cap", "joy", "Story: most joy from one story", 30, "joy", ""),
    ("friend_new_joy", "joy", "Meeting a new dragon", 15, "joy", ""),
    ("friend_back_joy", "joy", "A dragon friend comes back", 8, "joy", ""),
    ("pal_joy", "joy", "Spotting one of your pals", 3, "joy", "At most once per pal every 10 minutes."),
    ("levelup_joy", "joy", "Leveling up", 5, "joy", ""),
    ("ecstatic_joy", "joy", "Big-joy face from", 8, "joy",
     "Any single joy boost at least this big shows the ecstatic face (big starry eyes); smaller ones show the excited face."),
    ("land_joy", "joy", "New land claimed", 4, "joy", ""),
    ("realm_joy", "joy", "New realm claimed", 10, "joy", ""),
    ("star_joy", "joy", "A star (satellite) never seen before", 2, "joy", ""),
    ("constellation_joy", "joy", "The first star of a new constellation", 12, "joy", ""),
    ("star_again_joy", "joy", "A known star rising again", 1, "joy/star",
     "When a satellite heard before comes back over the horizon."),
    ("storm_first_joy", "joy", "A storm coming: first of the day", 15, "joy", ""),
    ("storm_joy", "joy", "A storm coming: later ones that day", 4, "joy", ""),
    ("rise_joy", "joy", "Pressure rising fast: weather change", 3, "joy", ""),
    ("sun_joy", "joy", "Sunrise or sunset at the Lair", 2, "joy", "With the Lair's Local announcements on."),
    ("radio_kind_joy", "joy", "Radio stick: a new kind of aircraft or device", 8, "joy", ""),
    ("radio_find_joy", "joy", "Radio stick: a new airline, country, or make and model", 3, "joy", ""),
    ("aurora_joy", "joy", "Northern lights possible at the Lair", 10, "joy",
     "Once a night (again if the chance gets better), with the Lair's Local announcements on."),
    ("sunny_joy", "joy", "Sunshine on the phone's light sensor", 3, "joy",
     "\"Wow! It's sunny out today!\" At most once per Sunshine wait (Detection)."),
    ("climb_joy", "joy", "Climbing (stairs, hills)", 2, "joy/10 m", ""),
    ("landmark_joy", "joy", "A famous place never seen before", 6, "joy", ""),
    ("landmark_again_joy", "joy", "A famous place seen again", 2, "joy", "Once per place per day."),
    ("green_joy", "joy", "A green space never visited before", 5, "joy",
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
    ("feast_xp", "xp", "Feast", 5, "XP",
     "Small on purpose: a new type also earns Gadget Journal points, and a newborn dragon finds dozens in its first minutes."),
    ("radio_kind_xp", "xp", "Radio stick: a new kind of aircraft or device", 15, "XP", ""),
    ("radio_find_xp", "xp", "Radio stick: a new airline, country, or make and model", 5, "XP", ""),
    ("treat_xp_wpa2", "xp", "Treat: new WPA2 network", 5, "XP", ""),
    ("treat_xp_wpa3", "xp", "Treat: new WPA3 network", 8, "XP", ""),
    ("treat_xp_enterprise", "xp", "Treat: new office network", 5, "XP", ""),
    ("treat_xp_open", "xp", "Treat: new open network", 4, "XP",
     "Open networks are everywhere in a city (shops, buses, public Wi-Fi)."),
    ("treat_xp_wep", "xp", "Treat: new WEP network", 15, "XP", ""),
    ("treat_xp_mobile", "xp", "Treat: mobile Wi-Fi", 1, "XP", ""),
    ("berry_xp", "xp", "Berries, per point of food", 0.25, "XP", ""),
    ("walk_xp", "xp", "Walking or running together", 2, "XP/100 m", ""),
    ("cycle_xp", "xp", "Cycling together", 1, "XP/100 m", ""),
    ("ride_xp", "xp", "Riding in a vehicle together", 1, "XP/km", ""),
    ("adventure_xp", "xp", "Adventure bonus at the end of a walk", 5, "XP", ""),
    ("story_xp", "xp", "Story: steps without your dragon", 1, "XP/100 m", ""),
    ("friend_new_xp", "xp", "Meeting a new dragon", 50, "XP", ""),
    ("friend_back_xp", "xp", "A dragon friend comes back", 10, "XP", ""),
    ("pal_xp", "xp", "Spotting one of your pals", 0, "XP", ""),
    ("land_xp", "xp", "New land claimed", 10, "XP", ""),
    ("realm_xp", "xp", "New realm claimed", 15, "XP", ""),
    ("star_xp", "xp", "A star (satellite) never seen before", 5, "XP", ""),
    ("constellation_xp", "xp", "The first star of a new constellation", 25, "XP", ""),
    ("storm_xp", "xp", "A storm or weather change coming", 5, "XP", ""),
    ("climb_xp", "xp", "Climbing (stairs, hills)", 1, "XP/10 m", ""),
    ("landmark_xp", "xp", "A famous place never seen before", 10, "XP", ""),
    ("green_xp", "xp", "A green space never visited before", 8, "XP", ""),
    ("green_visit_xp", "xp", "A walk, run or ride in a green space", 5, "XP", "Once per green space per day."),
    ("moon_xp", "xp", "A major moon phase", 5, "XP", ""),
    ("garden_xp", "xp", "Butterfly Garden: an adult emerges", 10, "XP", ""),
    # ---------------------------------------------------------------- detection
    ("land_accuracy_m", "detect", "Lands: ignore GPS fixes less precise than", 30, "m",
     "Stops GPS wobble from claiming land while you sit still."),
    ("land_wifi_accuracy_m", "detect", "Lands: ignore Wi-Fi positions less precise than", 75, "m",
     "Only used when finding your dragon by Wi-Fi (no GPS). Larger claims more, but sometimes the square next door."),
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
     "How closely a voice must match a profile before your dragon will call you by name. Higher: surer, but "
     "you're recognized less often. The den shows how alike the last voice was."),
    ("wake_strict", "detect", "Wake word: how strict", 50, "%",
     "0 = the original, quickest wake word (most false alarms). Higher: more sound-alike words for "
     "\"hey dragon\" to lose to, then a second listen that must be this sure (from 20), and from 70 a "
     "pause before \"hey\". Too high and you'll be missed. The den shows how sure the last one was "
     "and how many near-misses were turned down."),
    ("name_chance", "detect", "Voice profiles: say your name in a reply", 50, "%",
     "How often a reply adds the name of whoever was recognized: \"It's 7:30 at night, Sam.\""),
    ("sunny_lux", "detect", "Sunshine: brightness that counts", 30000, "lux",
     "From the phone's light sensor. Indoors is about 100 to 500 lux, a grey day outside 1,000 to "
     "20,000, and sunshine 30,000 to 100,000."),
    ("sunny_hold_s", "detect", "Sunshine: bright for at least", 30, "s",
     "So a moment of glare (a lamp, a reflection) doesn't count."),
    ("sunny_every_h", "detect", "Sunshine: wait between cheers", 3, "h",
     "After a cheer about the sun, this long passes before the next one can happen."),
    ("green_walk_min", "detect", "Green spaces: a walk is at least", 10, "min",
     "Time on foot inside one (with at least 150 m of actual walking): \"Took a walk in Oakfield Country Park!\""),
    ("green_run_min", "detect", "Green spaces: a run is at least", 5, "min", "\"Went for a run in ...!\""),
    ("green_bike_min", "detect", "Green spaces: a bike ride is at least", 5, "min",
     "\"Biked through ...!\" Time in a vehicle never counts."),
    ("green_margin_m", "detect", "Green spaces: count as inside within", 20, "m",
     "Of the outline on the map, for GPS wobble and paths that run along the edge."),
    # ---------------------------------------------------------------- conquest points
    ("conquest_land", "points", "Conquest points: a new land", 10, "points", "A square of the map about 250 m across."),
    ("conquest_realm", "points", "Conquest points: a new realm", 50, "points", "About 1 km across."),
    ("conquest_green", "points", "Conquest points: a green space discovered", 50, "points", ""),
    ("conquest_landmark", "points", "Conquest points: a famous place seen for the first time", 100, "points", ""),
    ("conquest_star", "points", "Conquest points: a star (satellite) never seen before", 20, "points", ""),
    ("conquest_constellation", "points", "Conquest points: the first star of a new constellation", 80, "points",
     "On top of that star's own points."),
    ("card_save_min", "detect", "Memory card: save everything every", 10, "min",
     "Changes wait in memory and go onto the card together. Napping, sleeping and restarting always save first; "
     "pulling the plug without them loses at most this long. Smaller wears the card faster."),
    ("landmark_langs", "detect", "Landmarks: how famous", 10, "languages",
     "A place counts as famous when Wikipedia has an article about it in at least this many languages."),
    ("landmark_m", "detect", "Landmarks: point them out within", 250, "m",
     "How close you need to be for your dragon to say \"LOOK!\"."),
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
    if key == "growth_max" and v < 100:
        return "at least 100 (the same as level 1)"
    if key == "garden_grows" and v not in (0, 1):
        return "0 or 1"
    if key == "card_save_min" and v < 1:
        return "at least 1 minute"
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
