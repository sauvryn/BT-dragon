"""
Which English Harald writes in: British, American or Canadian.

The rules come from Bookworm (the project author's reading tracker, whose insects live in the
Butterfly Garden): lang.json is read out of Bookworm's page by tools/garden/extract.py, so both
projects spell the same way. They cover spellings ("metre"/"meter", "colour"/"color", "grey"/
"gray", "-ise"/"-ize") and a few words ("autumn"/"fall", "pavement"/"sidewalk"). Canadian English
keeps British spellings but uses "-ize" and North American words.

Only text that's shown is converted: his screen (convert() here) and the Den and its pages
(lang.js, the same rules in the browser). What he says out loud, the README and the code
itself are left alone.

The setting: "Language matches the Lair automatically" (on to start with) picks the Lair's
country's English; with no Lair, or one in another country, the Pi's own country (set in
Raspberry Pi Imager); and failing that, British English. Untick it to choose one yourself.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LANGS = ("gb", "us", "ca")
NAMES = {"gb": "British English", "us": "American English", "ca": "Canadian English"}
OF_COUNTRY = {"GB": "gb", "IE": "gb", "US": "us", "CA": "ca"}     # the countries with an English here

_RULES = None


def rules():
    global _RULES
    if _RULES is None:
        with open(os.path.join(HERE, "lang.json"), encoding="utf-8") as f:
            raw = json.load(f)
        r = {}
        # names that are never converted (as in Bookworm): every insect species' name, longest first
        keep = raw.get("keep") or []
        r["keep"] = re.compile("(?<![A-Za-z])(?:" + "|".join(re.escape(n) for n in keep) + ")(?![A-Za-z])", re.I) if keep else None
        for k, v in raw.items():
            if k in ("names", "keep"):
                continue
            r[k] = [(re.compile(x[0], re.I if "i" in x[1] else 0),) + tuple(x[2:]) for x in v]
        _RULES = r
    return _RULES


def _fix(m, frm, to):
    """Bookworm's case-keeping swap: COLOUR -> COLOR, Colour -> Color, colour -> color."""
    s = m.group(0)
    r = to + s[len(frm):]
    if len(s) > 1 and s == s.upper():
        return r.upper()
    if s[0] != s[0].lower():
        return r[0].upper() + r[1:]
    return r


def _js_repl(a):
    """A JavaScript replacement ("$1n the fall") for Python's re.sub."""
    return re.sub(r"\$(\d)", r"\\\1", a)


def convert(text, lang):
    """`text` in British, American or Canadian English (whichever it was written in). Insect
    names are left exactly as they are, as in Bookworm: they're swapped for placeholders first
    and put back afterwards, so "GREY DAGGER" stays a Grey Dagger in American English."""
    if not isinstance(text, str) or not text or lang not in LANGS:
        return text
    keep = rules()["keep"]
    if keep is not None:
        kept = []

        def hide(m):
            kept.append(m.group(0))
            return "\x01%d\x02" % (len(kept) - 1)
        masked = keep.sub(hide, text)
        if kept:
            out = _convert(masked, lang)
            return re.sub("\x01(\\d+)\x02", lambda m: kept[int(m.group(1))], out)
    return _convert(text, lang)


def _convert(text, lang):
    if text == text.upper() and text != text.lower():
        # his screen is all capitals, and the word lists are written in lower case
        return _convert(text.lower(), lang).upper()
    R = rules()
    if lang == "us":
        for rx, b, a in R["us"]:
            text = rx.sub(lambda m: _fix(m, b, a), text)
        words = R["us_words"]
    elif lang == "ca":
        for rx, a, b in R["ca_gb"]:
            text = rx.sub(lambda m: _fix(m, a, b), text)
        for rx, b, a in R["ca_ize"]:
            text = rx.sub(lambda m: _fix(m, b, a), text)
        words = R["ca_words"]
    else:
        for rx, a, b in R["gb"]:
            text = rx.sub(lambda m: _fix(m, a, b), text)
        words = R["gb_words"]
    for rx, a in words:
        text = rx.sub(_js_repl(a), text)
    return text


# ---------------------------------------------------------------- the Pi's own country
def os_country(root="/"):
    """The country the Pi was set up for, as a two-letter code, or None. Raspberry Pi Imager
    (and raspi-config) set the Wi-Fi country, which ends up on the kernel command line or in
    wpa_supplicant's settings; failing those, the system's locale (en_GB, en_US...)."""
    def read(p):
        try:
            with open(os.path.join(root, p.lstrip("/")), encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""
    for p in ("/boot/firmware/cmdline.txt", "/boot/cmdline.txt"):
        m = re.search(r"cfg80211\.ieee80211_regdom=([A-Za-z]{2})\b", read(p))
        if m:
            return m.group(1).upper()
    m = re.search(r"^\s*country=([A-Za-z]{2})\s*$", read("/etc/wpa_supplicant/wpa_supplicant.conf"), re.M)
    if m:
        return m.group(1).upper()
    m = re.search(r"^\s*(?:LANG|LC_ALL)=\"?[a-z]{2}_([A-Z]{2})", read("/etc/default/locale"), re.M)
    if m:
        return m.group(1)
    return None


class Language:
    """The Den's setting, kept in Harald's database."""

    def __init__(self, store, os_code=None):
        self.store = store
        self.os_code = os_code
        s = store.get("language") or {}
        self.auto = s.get("auto", True)
        self.chosen = s.get("lang") if s.get("lang") in LANGS else None

    def save(self):
        self.store.put("language", {"auto": self.auto, "lang": self.chosen})

    def default(self):
        """Without the Lair: the Pi's country, if it's one with an English here; else British."""
        return OF_COUNTRY.get((self.os_code or "").upper(), "gb")

    def current(self, lair_code=None):
        if self.auto:
            return OF_COUNTRY.get((lair_code or "").upper()) or self.default()
        return self.chosen or self.default()

    def set(self, auto=None, lang=None, lair_code=None):
        if lang is not None and lang not in LANGS:
            return "choose British, American or Canadian English"
        if auto is not None:
            if not auto and lang is None:
                lang = self.current(lair_code)      # unticking keeps what's showing now
            self.auto = bool(auto)
        if lang is not None:
            self.chosen = lang
        self.save()
        return None
