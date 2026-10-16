"""
Points and titles for the collections (the Gadget Journal, Sky Dragons and Radio Whispers),
in the same way as Conquest points (conquest.py): each score is counted from what's been
found, so it's always right, and each title is announced once, the first time it's reached.

How the points compare, across everything: an insect raised in the Butterfly Garden is worth
100 to 300, a landmark 100. A Rare find in any collection is worth about the same as a
landmark or more, because it's about as hard to come by; Common ones turn up on most outings,
so they're worth a fraction of that.
"""

POINTS = {"Common": 20, "Uncommon": 60, "Rare": 150}

JOURNAL_TITLES = [(0, "j0", "Nibbling Newling"), (100, "j1", "Byte-Biting Bairn"),
                  (250, "j2", "Gadget-Gnawing Glutton"), (500, "j3", "Signal-Sniffing Sleuth"),
                  (800, "j4", "Beacon-Bolting Bard"), (1200, "j5", "Tracker-Tasting Thane"),
                  (1700, "j6", "Rune-Reading Loremaster"), (2300, "j7", "Saga-Scribing Skald"),
                  (3000, "j8", "Keeper of the Codex Draconis"), (4000, "j9", "Huginn's Equal")]
SKY_TITLES = [(0, "s0", "Grounded Gazer"), (100, "s1", "Contrail Chaser"), (300, "s2", "Wing-Watching Wanderer"),
              (700, "s3", "Sky-Road Scout"), (1500, "s4", "Jetstream Jarl"), (3000, "s5", "Valkyrie's Lookout"),
              (6000, "s6", "Stormrider of the High Roads"), (10000, "s7", "Sleipnir's Peer")]
WHISPER_TITLES = [(0, "w0", "Faint-Eared Fledgling"), (100, "w1", "Static-Sifting Sprout"),
                  (300, "w2", "Chirp-Collecting Cub"), (700, "w3", "Weather-Wise Wyrm"),
                  (1500, "w4", "Seiðr-Sensing Seer"), (3000, "w5", "Heimdall's Apprentice"),
                  (6000, "w6", "Ear of Heimdall")]


def title(titles, s):
    return [t for t in titles if s >= t[0]][-1][2]


def next_title(titles, s):
    return next(((n, name) for n, _, name in titles if n > s), None)


def new_titles(store, key, titles, s):
    """Titles reached since last time (each announced once)."""
    got = store.get(key) or {}
    fresh = [(tid, name) for n, tid, name in titles if n > 0 and s >= n and tid not in got]
    if fresh:
        got.update({tid: True for tid, _ in fresh})
        store.put(key, got)
    return [name for _, name in fresh]


def view(titles, s):
    """For the Den and the pages: score, title, and the next one."""
    nxt = next_title(titles, s)
    return {"points": s, "title": title(titles, s), "next": nxt[1] if nxt else "", "next_at": nxt[0] if nxt else 0}
