"""
Rebuild pi/bt_dragon/garden/species.json from Bookworm's page, for all four countries.

Harald's Butterfly Garden runs on the Pi, so it needs Bookworm's species list (names,
rarity, months in season, when each one pupates, its forms and habitats) as plain data.
That list lives inside Bookworm's page, after its fact-checked values and each country's
names and rarities have been applied, so this opens the page in a headless browser once per
country and asks it.

Run after replacing garden/bookworm.html with a newer Bookworm:
    python3 tools/garden/extract.py
Needs Playwright (pip install playwright, then playwright install chromium).
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "pi"))
from bt_dragon import garden_page  # noqa: E402

KEYS = {"gb": "bookworm-proto-v1", "ie": "bookworm-proto-v1-ie", "us": "bookworm-proto-v1-us", "ca": "bookworm-proto-v1-ca"}
LANG = {"gb": "gb", "ie": "gb", "us": "us", "ca": "ca"}


def main():
    from playwright.sync_api import sync_playwright
    out = {"countries": {}}
    tmp = tempfile.mkdtemp()
    with sync_playwright() as p:
        kw = {}
        if os.path.exists("/opt/pw-browsers/chromium"):
            kw["executable_path"] = "/opt/pw-browsers/chromium"
        browser = p.chromium.launch(**kw)
        for c in ("gb", "ie", "us", "ca"):
            data = {"country": c, "lang": LANG[c], "key": KEYS[c],
                    "save": {"books": [], "waiting": [], "collection": [], "seen": {}, "achievements": {}, "offset": 0},
                    "titles": {}}
            path = os.path.join(tmp, f"{c}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(garden_page.build(data, mode=False))
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort() if not route.request.url.startswith("file:") else route.continue_())
            page.goto("file://" + path)
            page.wait_for_function("window.__garden && window.__garden.country === '%s'" % c)
            species = page.evaluate("window.__garden.dump()")
            unlocks = page.evaluate("window.__garden.unlocks")
            habitats = page.evaluate("window.__garden.habitatNames()")
            out["countries"][c] = {"key": KEYS[c], "lang": LANG[c], "unlocks": unlocks, "habitats": habitats,
                                   "species": species}
            print(c, len(species), "species")
            page.close()
        browser.close()
    out["points"] = {"Common": 100, "Uncommon": 200, "Rare": 300}
    dest = os.path.join(ROOT, "pi", "bt_dragon", "garden", "species.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote", dest, os.path.getsize(dest), "bytes")


if __name__ == "__main__":
    main()
