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
"""
import asyncio
import json
import logging
import os
import re
import socket
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

def _response(status, body, ctype="text/plain; charset=utf-8", extra=None):
    if isinstance(body, str):
        body = body.encode()
    head = [f"HTTP/1.1 {status}", f"Content-Type: {ctype}", f"Content-Length: {len(body)}",
            "Cache-Control: no-store", "Connection: close"]
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
    # The page draws runes from Harald's own stroke font, so it doesn't depend on the
    # phone having a font with the Runic Unicode block.
    page = page.replace("/*RUNEFONT*/", json.dumps({"strokes": RUNES, "letters": _LETTERS, "digraphs": _DIGRAPHS}))
    # A fingerprint of this version of the page. An open den compares it with what Harald
    # reports and reloads itself after an update, so it never runs stale code.
    import hashlib
    page_id = hashlib.sha1(page.encode()).hexdigest()[:10]
    page = page.replace("__PAGEID__", page_id)

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
            limit = 210 * 1024 if path == "/api/art" else 4096          # a picture, or a command
            n = min(int(headers.get("content-length", "0") or 0), limit)
            if n and path != "/api/restore":
                body = await asyncio.wait_for(reader.readexactly(n), 30)
            if path.startswith("/api/") and path != "/api/phone":
                app.den_seen = time.time()   # an open den (or map) page checks in every few seconds
            if path == "/":
                out = _response("200 OK", page, "text/html; charset=utf-8")
            elif path == "/map":
                out = _response("200 OK", map_page.replace("__NAME__", app.pet.name), "text/html; charset=utf-8")
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
                out = _response("200 OK" if not err else "400 Bad Request",
                                json.dumps({"ok": not err, "error": err or ""}), "application/json")
            elif path == "/api/art":
                from .art import MOOD_NOTES, EVERYDAY
                out = _response("200 OK", json.dumps({
                    "rows": app.art.table(), "notes": MOOD_NOTES, "everyday": EVERYDAY,
                    "folder": app.art.user_dir or "",
                    "other_problems": {k: v for k, v in app.art.problems.items()
                                       if k.lower() not in {r["name"] for r in app.art.table()}}}),
                    "application/json")
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
            elif path == "/phone/harald_voice.py":
                from .phonevoice import script
                host = headers.get("host") or f"{app.my_ip or '127.0.0.1'}:{app.cfg['link']['web_port']}"
                out = _response("200 OK", script(re.sub(r"[^A-Za-z0-9.:\-\[\]]", "", host)),
                                "text/x-python; charset=utf-8",
                                ['Content-Disposition: attachment; filename="harald_voice.py"'])
            elif path == "/api/backup":
                from . import backup
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
                                ['Content-Disposition: attachment; filename="harald-wigle.csv"'])
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
