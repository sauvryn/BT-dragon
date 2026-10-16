"""The Star Chart's rarities for your own sky: satellites' heights above the horizon from the
Lair, worked out from their orbits."""
import tempfile

from bt_dragon import config, skygeo as g, starchart
from bt_dragon.app import Dragon

# heights above the horizon: overhead at the equator under it, and a known figure for Britain
assert abs(g.elevation(0, 0, 0, 0) - 90) < 1e-6
assert 30 < g.elevation(51.5, 0, 0, 0) < 32                 # a satellite over 0°E is about 31° up from London
assert g.elevation(51.5, 0, 0, 180) < -10                   # and one over the Pacific is far below the horizon
# a tilted one-day orbit swings north and south by its tilt, over its own longitude
pts = g.track(135, 43, 0)
assert abs(max(p[0] for p in pts) - 43) < 1 and abs(min(p[0] for p in pts) + 43) < 1
assert all(abs(p[1] - 135) < 10 for p in pts)

R = lambda c, la, lo: g.sky(c, la, lo)[0]                    # noqa: E731
for c in g.GLOBAL:
    assert R(c, -33.9, 151.2) == "Common" and R(c, 51.5, -0.1) == "Common"
# QZSS: everyday over Japan and Australia, never over Britain, Brazil or Canada
assert R("QZSS", 35.7, 139.7) == "Common" and R("QZSS", -33.9, 151.2) == "Common"
assert R("QZSS", 51.5, -0.1) == "Rare" and R("QZSS", -23.5, -46.6) == "Rare" and R("QZSS", 43.7, -79.4) == "Rare"
# NavIC: everyday around India; one satellite low over Britain; none over the Americas
assert R("NavIC", 28.6, 77.2) == "Common" and R("NavIC", 51.5, -0.1) == "Uncommon" and R("NavIC", 34, -118) == "Rare"
# SBAS: someone's correction satellites are in most skies
assert R("SBAS", 51.5, -0.1) == "Common" and R("SBAS", 43.7, -79.4) == "Common" and R("SBAS", -23.5, -46.6) == "Common"

# the words on the card
assert "never rise above your horizon" in g.reason("QZSS", *g.sky("QZSS", -23.5, -46.6)[0:1],
                                                   g.sky("QZSS", -23.5, -46.6)[2], 0)
assert g.reason("GPS", "Common", 90, 24).startswith("Common everywhere")

# the page: worked out for the Lair, or the usual rarities without one
items = {i["id"]: i for i in starchart.page_data("Ember", [], set(), where=(-33.9, 151.2))["groups"][0]["items"]}
assert items["QZSS"]["rarity"] == "Common" and items["QZSS"]["card"]["facts"][0][0] == "In your sky"
assert "Common at the Lair" in items["QZSS"]["card"]["facts"][0][1]
plain = {i["id"]: i for i in starchart.page_data("Ember", [], set())["groups"][0]["items"]}
assert plain["QZSS"]["rarity"] == "Rare" and "Set the Lair" in plain["QZSS"]["card"]["facts"][0][1]
cfg = config.load(None)
cfg["data_dir"] = tempfile.mkdtemp()
app = Dragon(cfg, simulate=True, out_dir=tempfile.mkdtemp())
app.lair.s = {"place": "Tokyo", "code": "JP", "lat": 35.7, "lon": 139.7, "label": "Tokyo"}
assert {i["id"]: i for i in app.star_chart_data()["groups"][0]["items"]}["QZSS"]["rarity"] == "Common"
print("skygeo ok")
