"""
The Garden Collection and Habitats pages: Bookworm's own page (garden/bookworm.html, kept
exactly as Bookworm ships it), served by Harald with a few additions:

  - shim.js, first thing in <head>: writes the save Bookworm reads (Harald's raised insects,
    your sightings and titles) into this browser's storage before Bookworm starts, and sends
    "I've Seen It!" ticks back to the Pi;
  - hook.js, inside Bookworm's script: small hooks into its data (the species list, field
    notes for any species);
  - den.css and mode.js: the Den's colors and type, and only the Collection and Habitats
    showing, with "See Habitats" and "Go back to Collection" buttons.

Bookworm's Google Fonts link is removed, so the page needs nothing from the internet (the
Den uses the phone's own fonts).
"""
import json
import os
import re

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "garden")
END = "})();\n</script>"


def _read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def build(data, mode=True, source=None):
    """The page, ready to serve. `data` is what shim.js writes in: {country, lang, key, saves, titles, ...}.
    data=None: the art-only copy the Den loads unseen to draw larvae (the same for everyone, so
    browsers can keep it; it never writes to Bookworm's storage)."""
    html = source if source is not None else _read("bookworm.html")
    if data is None:
        shim, mode = _read("artshim.js"), False
    else:
        shim = _read("shim.js").replace("__GARDEN_DATA__", json.dumps(data).replace("</", "<\\/"))
    html = html.replace("<head>", "<head>\n<script>\n" + shim + "\n</script>", 1)
    html = re.sub(r'<link rel="(?:stylesheet|preconnect)" href="https://fonts\.(?:googleapis|gstatic)\.com[^>]*>\n?', "", html)
    i = html.rfind(END)
    if i < 0:
        raise ValueError("this doesn't look like Bookworm's page (its script ending wasn't found)")
    html = html[:i] + _read("hook.js") + "\n" + html[i:]
    if mode:
        html = html.replace("</head>", "<style>\n" + _read("den.css") + "\n</style>\n"
                            '<link rel="stylesheet" href="/theme.css">\n</head>', 1)   # Color Blindness Mode
        j = html.rfind("</body>")
        html = html[:j] + "<script>\n" + _read("mode.js") + "\n</script>\n" + html[j:]
    return html
