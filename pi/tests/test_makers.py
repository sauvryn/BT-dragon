"""Manufacturer codes: real companies by name, made-up codes as one "Unbranded gadget"
species, and old life-list and diary entries renamed to match."""
import os
import tempfile

from bt_dragon import ble
from bt_dragon.store import Store

C = ble.classify
assert C(None, {0x0075: b"\x01"}, [], {})[1] == "Samsung device"
for code in (0xA106, 0xFFFF, 0x1C03, 0x1D03, 0x2502, 0x6D53):
    key, label, kind = C(None, {code: b"\x00\x01"}, [], {})
    assert label == "Unbranded gadget" and kind == "maker", (hex(code), label)
assert C(None, {0x0C98: b"\x00"}, [], {})[1] == "Maker 0x0C98 gadget"      # might be a new company
assert C(None, {0xF8F8: b"", 0x0075: b""}, [], {})[1] == "Samsung device"   # a real one wins
assert ble.NEWEST_ID >= 0x1130 and ble.unbranded(0xFFFF) and not ble.unbranded(0x1130)

store = Store(os.path.join(tempfile.mkdtemp(), "m.db"))
for code in (0xA106, 0x1C03, 0x0C98):
    store.db.execute("INSERT INTO species (key, label, kind, first_seen, last_seen, meals) VALUES (?,?,?,?,?,?)",
                     (f"maker-0x{code:04x}-gadget", f"Maker 0x{code:04X} gadget", "maker", 100 + code, 200, 3))
store.event("species", "New species: Maker 0xA106 gadget")
store.event("species", "New species: Maker 0x0C98 gadget")
assert store.rename_maker_species(ble.maker_label) == 2
labels = {r["label"]: r["meals"] for r in store.species_list()}
assert labels == {"Unbranded gadget": 6, "Maker 0x0C98 gadget": 3}, labels       # two merged into one
assert store.rename_maker_events(ble.maker_label) == 1
texts = [e["text"] for e in store.events(5)]
assert "New species: Unbranded gadget" in texts and "New species: Maker 0x0C98 gadget" in texts
assert store.rename_maker_species({0x0075: "Samsung"}) == 0           # the old way (a dict) still works
# broadcast names that are only codes once the numbers are hidden don't make species
S = ble.species_from_name
assert S("TS0A-a") is None and S("1mai_3SE_2") is None and S("G5(ID-3)") is None and S("HC-08") is None
assert S("JBL Flip 5") == "JBL Flip #" and S("ELK-BLEDOM") == "ELK-BLEDOM" and S("LG TV") == "LG TV"
assert C("TS0A-a", {0xA106: b""}, [], {})[1] == "Unbranded gadget"          # falls back to its maker code
# ...and old code-named species fold into one, diary entries too
for lab in ("TS#A-a", "#mai_#SE_#", "JBL Flip #"):
    store.db.execute("INSERT INTO species (key, label, kind, first_seen, last_seen, meals) VALUES (?,?,?,?,?,?)",
                     (ble._key(lab), lab, "named", 50, 60, 2))
    store.event("species", f"New species: {lab}")
assert store.tidy_code_names(ble.meaningful, ble.UNBRANDED, ble._key(ble.UNBRANDED)) == 2
labels = {r["label"]: r["meals"] for r in store.species_list()}
assert labels["Unbranded gadget"] == 10 and "JBL Flip #" in labels and "TS#A-a" not in labels, labels
texts = [e["text"] for e in store.events(10)]
assert "New species: TS#A-a" not in texts and "New species: JBL Flip #" in texts
print("makers ok")
