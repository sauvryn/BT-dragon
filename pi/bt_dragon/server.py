"""
How other devices talk to Harald over the hotspot.

  * Discovery (UDP 5150): every 5 seconds Harald broadcasts one short line,
        BTDRAGON 1 port=5151 web=8080 name=Harald
    to everyone on the network. A client doesn't need to know the Pi's address in
    advance; it just waits for this shout and connects back to the sender.
  * Control link (TCP 5151): plain text, one command per line, e.g. "STATUS". Answers are
    "OK ..." / "ERR ..." or several lines ending with "END". Harald also pushes
    "EVT kind|text" lines when something happens.
  * The den (HTTP 8080): a small web page for your phone's browser that uses the same
    commands, so you can manage your dragon from your phone.

Anyone on your hotspot can reach these. A phone hotspot normally has only your own
devices on it, which is the assumption here.

Web pages on the internet are kept out, though. A page you open on your phone can try to
send requests to devices on your own network, three ways, and each is closed:
  * Cross-site requests: a page on another site POSTs a command to the Den. Browsers say
    where a request came from (the Origin header), so the Den turns away any change that
    didn't come from its own pages.
  * DNS rebinding: a site points its own name at the Pi's address, so the browser thinks
    the Den *is* that site and lets the page read the answers. Every request names the site
    it's for (the Host header); the Den only answers to an address, a .local name or a
    one-word name, never to a site on the internet.
  * Cross-protocol: a page sends an ordinary web request to the control link's port, hoping
    the lines of its body are run as commands. The control link hangs up on anything that
    starts like a web request.
"""
import asyncio
import gzip
import json
import logging
import os
import re
import socket
import threading
import time
import urllib.parse

log = logging.getLogger("server")
HERE = os.path.dirname(os.path.abspath(__file__))


async def discovery(app):
    port = app.cfg["link"]["discovery_port"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    try:
        while not app.stop.is_set():
            # the name goes last: it may contain spaces, so it runs to the end of the line
            msg = (f"BTDRAGON 1 port={app.cfg['link']['port']} web={app.cfg['link']['web_port']} "
                   f"name={app.pet.name}\n").encode()
            try:
                sock.sendto(msg, ("255.255.255.255", port))
            except OSError:
                pass  # no network yet
            await app._sleep(5)
    finally:
        sock.close()


async def control_server(app):
    async def handle(reader, writer):
        app.clients.add(writer)
        peer = writer.get_extra_info("peername")
        log.info("link client %s connected", peer)
        try:
            while not app.stop.is_set():
                line = await reader.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if not text:
                    continue
                if looks_like_http(text):
                    # a web request sent to the wrong port (by a web page, on purpose or not):
                    # never run the lines of its body as commands
                    log.info("link client %s sent a web request; hanging up", peer)
                    break
                for out in await app.command(text, writer):
                    writer.write((out + "\n").encode())
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            app.clients.discard(writer)
            app.tracking.pop(writer, None)
            writer.close()
            log.info("link client %s left", peer)

    server = await asyncio.start_server(handle, "0.0.0.0", app.cfg["link"]["port"])
    async with server:
        await app.stop.wait()


# ---------------------------------------------------------------- the den (HTTP)

_LOCAL_SUFFIXES = (".local", ".lan", ".home", ".home.arpa", ".internal", ".localdomain")


def host_ok(host):
    """Is this Host header a name for the Pi on your own network? An IP address, a one-word
    name ("bt-dragon"), or a local-only name ("bt-dragon.local") is; a site on the internet
    ("example.com", which could have been pointed at the Pi's address) isn't."""
    h = (host or "").strip().lower()
    if h.startswith("["):                              # an IPv6 address, [fe80::1]:8080
        return "]" in h
    h = h.rsplit(":", 1)[0] if h.count(":") == 1 else h
    if not h:
        return True                                   # HTTP/1.0 without a Host: not a browser
    if re.fullmatch(r"[0-9.]+", h) or ":" in h:
        return True
    return "." not in h.rstrip(".") or h.rstrip(".").endswith(_LOCAL_SUFFIXES)


def origin_ok(origin, host):
    """A change (POST) is only taken from the Den's own pages: no Origin (not a browser), or
    an Origin naming the same host and port."""
    if not origin:
        return True
    o = urllib.parse.urlparse(origin)
    return bool(o.netloc) and o.netloc.lower() == (host or "").strip().lower()


def looks_like_http(line):
    return bool(re.match(r"^[A-Z]{3,10} \S+ HTTP/\d", line))


def _response(status, body, ctype="text/plain; charset=utf-8", extra=None, cache="no-store"):
    if isinstance(body, str):
        body = body.encode()
    head = [f"HTTP/1.1 {status}", f"Content-Type: {ctype}", f"Content-Length: {len(body)}",
            f"Cache-Control: {cache}", "Connection: close"]
    head += extra or []
    return ("\r\n".join(head) + "\r\n\r\n").encode() + body


async def _receive_restore(app, reader, length):
    """A backup sent from the den: saved next to his database, checked, and if it's good,
    he restarts and puts it in place before anything else."""
    from . import backup
    if not 0 < length <= backup.MAX_BYTES:
        return _response("400 Bad Request", json.dumps({"error": "That file is empty or far too big."}),
                         "application/json")
    tmp = os.path.join(app.data_dir, "restore-upload.tmp")
    try:
        with open(tmp, "wb") as f:
            left = length
            while left:
                chunk = await asyncio.wait_for(reader.read(min(65536, left)), 30)
                if not chunk:
                    raise ConnectionError("the upload stopped part way")
                f.write(chunk)
                left -= len(chunk)
        _, manifest = await asyncio.to_thread(backup.read, tmp)
    except backup.BadBackup as e:
        os.remove(tmp)
        return _response("400 Bad Request", json.dumps({"error": f"Not restoring: {e}."}), "application/json")
    except (OSError, ConnectionError, asyncio.TimeoutError) as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return _response("400 Bad Request", json.dumps({"error": f"The upload didn't arrive whole ({e})."}),
                         "application/json")
    os.replace(tmp, os.path.join(app.data_dir, backup.PENDING))
    app.restart_soon("restoring a backup")
    return _response("200 OK", json.dumps({"ok": True, "made": manifest.get("made"), "name": manifest.get("name")}),
                     "application/json")


async def web_server(app):
    from .fonts import RUNES, _DIGRAPHS, _LETTERS
    with open(os.path.join(HERE, "den.html"), encoding="utf-8") as f:
        page = f.read()
    with open(os.path.join(HERE, "map.html"), encoding="utf-8") as f:
        map_page = f.read()
    with open(os.path.join(HERE, "shopping.html"), encoding="utf-8") as f:
        shop_page = f.read()
    with open(os.path.join(HERE, "calendar.html"), encoding="utf-8") as f:
        cal_page = f.read()
    with open(os.path.join(HERE, "art.html"), encoding="utf-8") as f:
        art_page = f.read()
    with open(os.path.join(HERE, "collection.html"), encoding="utf-8") as f:
        coll_page = f.read()

    def collection(data):
        """The Star Chart or the Gadget Journal: one page, its data written into it."""
        from html import escape
        return (coll_page.replace("__TITLE__", escape(data["title"]))
                .replace("__DATA__", json.dumps(data).replace("</", "<\\/")))
    # The page draws runes from Harald's own stroke font, so it doesn't depend on the
    # phone having a font with the Runic Unicode block.
    page = page.replace("/*RUNEFONT*/", json.dumps({"strokes": RUNES, "letters": _LETTERS, "digraphs": _DIGRAPHS}))
    # A fingerprint of this version of the page. An open den compares it with what Harald
    # reports and reloads itself after an update, so it never runs stale code.
    import hashlib
    page_id = hashlib.sha1(page.encode()).hexdigest()[:10]
    page = page.replace("__PAGEID__", page_id)

    with open(os.path.join(HERE, "lang.js"), encoding="utf-8") as f:
        lang_js = f.read()
    with open(os.path.join(HERE, "lang.json"), encoding="utf-8") as f:
        lang_js = lang_js.replace("__RULES__", f.read().replace("</", "<\\/"))

    art_cache, art_lock = [], threading.Lock()

    def garden_art():
        with art_lock:
            return _garden_art()

    def _garden_art():
        if not art_cache:
            from . import garden_page
            html = garden_page.build(None).encode()
            art_cache.append((html, gzip.compress(html, 9), hashlib.sha1(html).hexdigest()[:10]))
        return art_cache[0]
    # built once, in the background, when he starts (the Den waits for it before drawing larvae)
    app.garden_art_version = lambda: art_cache[0][2] if art_cache else ""
    asyncio.get_running_loop().run_in_executor(None, garden_art)

    async def handle(reader, writer):
        try:
            request = await asyncio.wait_for(reader.readline(), 10)
            method, target, _ = request.decode(errors="replace").split(" ", 2)
            headers = {}
            while True:
                h = await asyncio.wait_for(reader.readline(), 10)
                if h in (b"\r\n", b"\n", b""):
                    break
                k, _, v = h.decode(errors="replace").partition(":")
                headers[k.strip().lower()] = v.strip()
            body = b""
            path = urllib.parse.urlparse(target).path
            if not host_ok(headers.get("host")):
                writer.write(_response("421 Misdirected Request",
                                       "The Den only answers to its own address on your network."))
                await writer.drain()
                return
            if method != "GET" and not origin_ok(headers.get("origin"), headers.get("host")):
                writer.write(_response("403 Forbidden", "Changes only come from the Den's own pages."))
                await writer.drain()
                return
            limit = (210 * 1024 if path == "/api/art" else 256 * 1024 if path == "/api/garden/seen"
                     else 4096)                                          # a picture, sightings, or a command
            n = min(int(headers.get("content-length", "0") or 0), limit)
            if n and path != "/api/restore":
                body = await asyncio.wait_for(reader.readexactly(n), 30)
            if path.startswith("/api/") and path != "/api/phone":
                app.den_seen = time.time()   # an open den (or map) page checks in every few seconds
            if path == "/":
                out = _response("200 OK", page, "text/html; charset=utf-8")
            elif path == "/map":
                out = _response("200 OK", map_page.replace("__NAME__", app.pet.name), "text/html; charset=utf-8")
            elif path == "/theme.css":
                # Color Blindness Mode: loaded last by every Den page (see access.py)
                from . import access
                out = _response("200 OK", access.theme_css(app.cvd_mode()), "text/css; charset=utf-8")
            elif path == "/lang.js":
                # the Den's pages in his English (British, American or Canadian): see lang.py
                out = _response("200 OK", lang_js.replace("__LANG__", app.lang()), "text/javascript; charset=utf-8")
            elif path == "/garden":
                # Bookworm's page is big (about 1.4 MB), so it goes compressed when the browser can take it
                q = urllib.parse.parse_qs(urllib.parse.urlparse(target).query)
                html = await asyncio.to_thread(app.garden_page, (q.get("c") or [""])[0])
                if "gzip" in headers.get("accept-encoding", ""):
                    out = _response("200 OK", await asyncio.to_thread(gzip.compress, html.encode(), 6),
                                    "text/html; charset=utf-8", ["Content-Encoding: gzip"])
                else:
                    out = _response("200 OK", html, "text/html; charset=utf-8")
            elif path == "/garden/art":
                # the art-only copy, drawn from by the Den: the same until an update, so the browser keeps it
                plain, packed, version = await asyncio.to_thread(garden_art)
                gz = "gzip" in headers.get("accept-encoding", "")
                out = _response("200 OK", packed if gz else plain, "text/html; charset=utf-8",
                                ["Content-Encoding: gzip"] if gz else None, cache="max-age=31536000, immutable")
            elif path == "/api/garden/seen" and method == "POST":
                try:
                    d = json.loads(body.decode(errors="replace"))
                    err = app.garden.set_seen(d.get("country"), d.get("seen"), d.get("seenDates"))
                except ValueError:
                    err = "not JSON"
                out = _response("200 OK" if not err else "400 Bad Request",
                                json.dumps({"ok": not err, "error": err or ""}), "application/json")
            elif path == "/stars":
                out = _response("200 OK", collection(app.star_chart_data()), "text/html; charset=utf-8")
            elif path == "/sky":
                out = _response("200 OK", collection(app.sky_data()), "text/html; charset=utf-8")
            elif path == "/whispers":
                out = _response("200 OK", collection(app.whispers_data()), "text/html; charset=utf-8")
            elif path == "/journal":
                out = _response("200 OK", collection(app.journal_data()), "text/html; charset=utf-8")
            elif path == "/shopping":
                out = _response("200 OK", shop_page.replace("__NAME__", app.pet.name), "text/html; charset=utf-8")
            elif path == "/calendar":
                out = _response("200 OK", cal_page.replace("__NAME__", app.pet.name), "text/html; charset=utf-8")
            elif path == "/api/calendar":
                out = _response("200 OK", json.dumps(app.calendar_data()), "application/json")
            elif path == "/api/shopping":
                out = _response("200 OK", json.dumps(app.shopping_data()), "application/json")
            elif path == "/api/lands":
                out = _response("200 OK", json.dumps(app.map_data()), "application/json")
            elif path == "/api/diary-files":
                files = app.diary_files.files() if app.diary_files else []
                out = _response("200 OK", json.dumps([{"name": n, "bytes": b} for n, b in files]),
                                "application/json")
            elif path.startswith("/diary/"):
                name = path[len("/diary/"):]
                data = app.diary_files.read(name) if app.diary_files else None
                out = (_response("200 OK", data, "text/csv; charset=utf-8",
                                 [f'Content-Disposition: attachment; filename="{name}"'])
                       if data is not None else _response("404 Not Found", "no such diary file"))
            elif path == "/screen.png":
                out = _response("200 OK", app.display.png or b"", "image/png")
            elif path == "/api/status":
                out = _response("200 OK", json.dumps(dict(app.view(), page=page_id)), "application/json")
            elif path == "/api/cmd" and method == "POST":
                lines = await app.command(body.decode(errors="replace"))
                out = _response("200 OK", json.dumps({"lines": lines}), "application/json")
            elif path == "/art":
                out = _response("200 OK", art_page.replace("__NAME__", app.pet.name), "text/html; charset=utf-8")
            elif path == "/api/art" and method == "POST":
                q = urllib.parse.parse_qs(urllib.parse.urlparse(target).query)
                err = app.art.save((q.get("name") or [""])[0].lower(), body)
                if not err and (q.get("name") or [""])[0].lower() == "nap-screen.png" and app.napping:
                    app._nap_redraw = True          # napping now: show the new picture
                out = _response("200 OK" if not err else "400 Bad Request",
                                json.dumps({"ok": not err, "error": err or ""}), "application/json")
            elif path == "/api/art":
                from .art import MOOD_NOTES, EVERYDAY
                out = _response("200 OK", json.dumps({
                    "rows": app.art.table(), "notes": MOOD_NOTES, "everyday": EVERYDAY,
                    "screens": app.art.screen_rows(), "folder": app.art.user_dir or "",
                    "other_problems": {k: v for k, v in app.art.problems.items()
                                       if k.lower() not in {r["name"] for r in app.art.table() + app.art.screen_rows()}}}),
                    "application/json")
            elif path in ("/art/screen.png", "/art/screen-template.png"):
                # the nap and sleep screens: as shown (yours or drawn), or the drawn one to draw over
                q = urllib.parse.parse_qs(urllib.parse.urlparse(target).query)
                kind = (q.get("kind") or [""])[0]
                if kind not in ("nap", "sleep"):
                    out = _response("404 Not Found", "no such screen")
                elif path == "/art/screen.png":
                    out = _response("200 OK", app.art.screen_png(kind, scale=2), "image/png")
                else:
                    out = _response("200 OK", app.art.screen_png(kind, drawn=True), "image/png",
                                    [f'Content-Disposition: attachment; filename="{kind}-screen.png"'])
            elif path in ("/art/preview.png", "/art/template.png"):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(target).query)
                mood = (q.get("mood") or ["content"])[0]
                frame = 1 if (q.get("frame") or ["0"])[0] == "1" else 0
                belly = (q.get("belly") or [""])[0] or None
                from .dragon import MOODS
                if mood not in MOODS or belly not in (None, "hungry", "stuffed"):
                    out = _response("404 Not Found", "no such mood")
                elif path == "/art/preview.png":
                    out = _response("200 OK", app.art.preview(mood, frame, belly), "image/png")
                else:
                    name = f"{mood}{'-' + belly if belly else ''}{'_1' if frame else ''}.png"
                    out = _response("200 OK", app.art.drawn_png(mood, frame, belly), "image/png",
                                    [f'Content-Disposition: attachment; filename="{name}"'])
            elif path == "/api/phone":
                # the phone's Termux helper, waiting for something to say (see phonevoice.py)
                q = urllib.parse.parse_qs(urllib.parse.urlparse(target).query)
                try:
                    after = int((q.get("after") or ["-1"])[0])
                except ValueError:
                    after = -1
                reply = await app.dot.phone.wait(after)
                reply["rate"] = float(app.dot.s.get("speed", 1.0))
                reply["pitch"] = round(2 ** (float(app.dot.s.get("pitch", 0.0)) / 12), 3)   # semitones -> factor
                out = _response("200 OK", json.dumps(reply), "application/json")
            elif path in ("/phone/bt_dragon_voice.py", "/phone/harald_voice.py"):   # (the older name too)
                from .phonevoice import script
                host = headers.get("host") or f"{app.my_ip or '127.0.0.1'}:{app.cfg['link']['web_port']}"
                out = _response("200 OK", script(re.sub(r"[^A-Za-z0-9.:\-\[\]]", "", host)),
                                "text/x-python; charset=utf-8",
                                [f'Content-Disposition: attachment; filename="{path.rsplit("/", 1)[1]}"'])
            elif path == "/api/backup":
                from . import backup
                app.store.flush()                    # the backup reads the card: everything onto it first
                data = await asyncio.to_thread(backup.make, app.data_dir, app.cfg.get("_path"), app.pet.name)
                out = _response("200 OK", data, "application/gzip",
                                [f'Content-Disposition: attachment; filename="{backup.filename()}"'])
            elif path == "/api/restore" and method == "POST":
                out = await _receive_restore(app, reader, int(headers.get("content-length", "0") or 0))
            elif path == "/api/export.csv":
                from . import wigle
                p = app.cfg["privacy"]
                csv = wigle.build_csv(app.store.pending_obs(p["skip_nomap"], p["upload_hidden"]))
                out = _response("200 OK", csv, "text/csv",
                                ['Content-Disposition: attachment; filename="bt-dragon-wigle.csv"'])
            else:
                out = _response("404 Not Found", "not here")
            writer.write(out)
            await writer.drain()
        except (asyncio.TimeoutError, ValueError, ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", app.cfg["link"]["web_port"])
    async with server:
        await app.stop.wait()


async def serve_all(app):
    await asyncio.gather(discovery(app), control_server(app), web_server(app))
