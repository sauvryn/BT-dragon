"""
Mobile Wi-Fi: networks that travel. Recognized by their names:

  vehicles   cars (an Audi's "Audi_MMI_1234", a Volkswagen's "VW_WLAN_5678", "InCarHotspot",
             wireless CarPlay), dashcams, buses, trams and trains;
  phones     phone hotspots ("Sam's iPhone", "AndroidAP1234", "Galaxy A52 1a2b", "Pixel_1234")
             and pocket routers ("VodafoneMobileWiFi-12AB", "MiFi").

A dragon by a road meets dozens of cars an hour, every one "new" and gone a moment later, and
a phone's hotspot goes wherever its owner goes, even if it's somebody's home internet too.
So they're a smaller treat of their own ("Mobile Wi-Fi": less food, XP and joy, set in
Developer Tools), they don't grow berries (they're not a bush that stays put), and they're
never uploaded to WiGLE: WiGLE maps where networks *are*, and these are somewhere else every
time, which would only blur the map.

It goes by the name alone, so it's a good guess, not a certainty: a renamed one is missed,
and an unlucky home network called "Audi Fan Club" would be counted as a car. Brand names
only count as whole words ("Ford", "FordPass", "Ford_1234"; not "Oxford"), and names that are
common words ("Smart", "Mini", "Seat", "Honor"...) are left out unless they come with something
car- or phone-like. Huawei's and ZTE's own names are left out too: they make phones, but
also the 4G routers that stay at home.
"""
import re

_WORDS = [
    # the ways in: wireless CarPlay and Android Auto, built-in hotspots
    r"carplay", r"android ?auto", r"in[- ]?car[ _-]?(?:hotspot|wi-?fi|wlan)?", r"car[ _-]?(?:hotspot|wi-?fi|wlan|net)",
    r"my ?car", r"onstar", r"mbux", r"mmi", r"fordpass", r"uconnect", r"sync ?\d",
    # makers whose cars broadcast their name
    r"audi", r"myaudi", r"vw", r"volkswagen", r"skoda", r"cupra", r"porsche", r"bentley", r"lamborghini",
    r"bmw", r"mybmw", r"mercedes(?:[- ]benz)?", r"mb ?(?:hotspot|wlan|wifi)", r"ford", r"vauxhall", r"opel",
    r"chevrolet", r"cadillac", r"buick", r"toyota", r"lexus", r"honda", r"nissan", r"mazda", r"subaru",
    r"mitsubishi", r"suzuki", r"hyundai", r"kia", r"renault", r"r-?link", r"dacia", r"peugeot",
    r"citro[eë]n", r"fiat", r"alfa ?romeo", r"jeep", r"chrysler", r"volvo", r"polestar", r"tesla",
    r"jaguar", r"land ?rover", r"range ?rover", r"jlr", r"byd", r"rivian", r"seat[ _-]?(?:wlan|wifi|hotspot|\d)",
    r"mini[ _-]?(?:wlan|wifi|hotspot|connected|\d{3,})",
    r"car",                      # "Car-1a2b", "Jamie's Car" (a whole word: not "Cardwell")
    # dashcams and fleet cameras (they ride along too)
    r"dash ?cam\w*", r"dash-\d+", r"\w*car ?cam\w*", r"70mai", r"viofo", r"ddpai", r"nextbase", r"blackvue",
    r"thinkware", r"vantrue", r"garmin ?dash", r"cameramatics", r"connectedcam", r"samsara\w*",
    # buses, trams and trains
    r"beenetwork\w*", r"stagecoach\w*", r"arriva\w*", r"first ?bus", r"northern ?wi-?fi", r"avanti\w*",
    r"transpennine\w*", r"lner\w*", r"crosscountry\w*", r"national ?express", r"megabus", r"tfgm_mobile",
    r"on-?board ?wi-?fi",
]
_PHONES = [
    r"\w*iphone\w*", r"ipad", r"android ?ap\w*", r"androidshare\w*", r"android_\w+", r"galaxy",
    r"samsung ?galaxy", r"pixel(?:[ _]\w+)?", r"redmi", r"xiaomi ?\d+\w*", r"poco ?[a-z]?\d\w*", r"oneplus\w*",
    r"oppo ?[a-z]\d+\w*", r"realme\w*", r"vivo ?[a-z]?\d+\w*", r"honor ?(?:magic|x?\d+)\w*", r"moto [a-z]\d*",
    r"motorola\w*", r"nokia ?[a-z]?\d+\w*", r"xperia", r"nothing ?phone\w*", r"fairphone\w*", r"huawei ?(?:p|mate|nova)\s?\d+\w*",
    r"[a-z]+'?s ?(?:phone|mobile)", r"mifi\w*", r"\w*mobile ?wi-?fi\w*", r"pocket ?wi-?fi\w*", r"4g ?mifi\w*",
    r"my ?hotspot", r"personal ?hotspot",
]
_RX = re.compile(r"(?<![a-z0-9])(?:" + "|".join(_WORDS) + r")(?![a-z])", re.IGNORECASE)
_RX_PHONE = re.compile(r"(?<![a-z0-9])(?:" + "|".join(_PHONES) + r")(?![a-z])", re.IGNORECASE)


def kind(ssid):
    """"vehicle", "phone" (a phone's hotspot or a pocket router) or None, by the network's name."""
    if not ssid:
        return None
    if _RX.search(ssid):
        return "vehicle"
    if _RX_PHONE.search(ssid):
        return "phone"
    return None


def is_mobile(ssid):
    """Does this network travel (a car's, a bus's, a phone's...)?"""
    return kind(ssid) is not None
