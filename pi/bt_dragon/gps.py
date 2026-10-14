"""
Location from your phone's GPS, borrowed over the hotspot.

GPS receivers (including the one in your phone) speak NMEA 0183: plain-text lines such as
  $GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,...*47
GGA gives the position fix, its quality and altitude; RMC gives position plus date and time.
Phone apps like GPSd Forwarder (Android, sends UDP) or GPS2IP (iPhone, a TCP server) simply
stream those lines over the network. Harald reads them directly, so no gpsd is needed.

Latitude/longitude arrive as degrees+minutes ("4807.038" = 48° 07.038'), which is
converted to decimal degrees (48.1173).

A USB GPS receiver ("G-mouse" dongles such as the VK-162 or VK-172, built around a u-blox
chip) speaks exactly the same lines, over a serial port the Pi creates when it's plugged
in (/dev/ttyACM0). Plug it into the Pi's data port with a micro-USB OTG adapter. With both
it and the phone sending positions, one is preferred ([gps] prefer, the phone unless you
say otherwise) and the other only fills in while the preferred one has no fix, so the two
never take turns and make him zigzag.
"""
import glob
import os
import termios
import asyncio
import calendar
import logging
import time

log = logging.getLogger("gps")
STALE_S = 10


def _dm_to_deg(v, hemi):
    if not v:
        return None
    dot = v.index(".") if "." in v else len(v)
    deg = float(v[:dot - 2])
    minutes = float(v[dot - 2:])
    d = deg + minutes / 60.0
    return -d if hemi in ("S", "W") else d


def _checksum_ok(line):
    if "*" not in line:
        return True
    body, _, cs = line[1:].partition("*")
    try:
        want = int(cs[:2], 16)
    except ValueError:
        return False
    got = 0
    for ch in body:
        got ^= ord(ch)
    return got == want


class Gps:
    def __init__(self):
        self.fix = None          # dict(lat, lon, alt, acc, ts, utc)
        self.last_sentence = 0.0
        self.source = None
        self.on_gsv = None       # callback(talker, fields) for satellites-in-view lines
        self.prefer = "phone"    # or "usb": which receiver wins when both have a fix
        self._fixed_by = {}      # "phone" / "usb" -> when it last gave a fix
        self.usb_device = None   # the USB receiver's port, while one is plugged in

    @staticmethod
    def _kind(source):
        return "usb" if str(source).startswith("usb") else "phone"

    def _accept(self, source):
        """A fix from this source counts unless the preferred receiver has a fresh one."""
        kind = self._kind(source)
        if kind == self.prefer:
            return True
        return time.time() - self._fixed_by.get(self.prefer, 0) >= STALE_S

    def _fixed(self, source):
        self._fixed_by[self._kind(source)] = time.time()
        self.fix["via"] = self._kind(source)
        self.source = source

    def state(self):
        """'FIX', 'WAIT' (data arriving, no fresh fix) or 'OFF' (nothing arriving)."""
        now = time.time()
        if self.fix and now - self.fix["ts"] < STALE_S:
            return "FIX"
        if now - self.last_sentence < STALE_S:
            return "WAIT"
        return "OFF"

    def current(self):
        return self.fix if self.state() == "FIX" else None

    def feed(self, line, source="?"):
        line = line.strip()
        if not line.startswith("$") or not _checksum_ok(line):
            return
        self.last_sentence = time.time()
        f = line.split("*")[0].split(",")
        kind = f[0][3:]
        try:
            if kind == "GSV":
                if self.on_gsv:
                    self.on_gsv(f[0][1:3], f)
                return
            if kind in ("GGA", "RMC") and not self._accept(source):
                return
            if kind == "GGA" and len(f) >= 10:
                if f[6] in ("", "0"):
                    return
                lat, lon = _dm_to_deg(f[2], f[3]), _dm_to_deg(f[4], f[5])
                hdop = float(f[8] or 0)
                alt = float(f[9] or 0)
                prev = self.fix or {}
                self.fix = {"lat": lat, "lon": lon, "alt": alt,
                            "acc": round(max(hdop, 0.5) * 5.0, 1),  # rough meters from HDOP
                            "ts": time.time(), "utc": prev.get("utc"), "speed": prev.get("speed")}
                self._fixed(source)
            elif kind == "RMC" and len(f) >= 10:
                if f[2] != "A":
                    return
                lat, lon = _dm_to_deg(f[3], f[4]), _dm_to_deg(f[5], f[6])
                utc = None
                if f[1] and f[9]:
                    hh, mm, ss = int(f[1][0:2]), int(f[1][2:4]), int(float(f[1][4:]))
                    dd, mo, yy = int(f[9][0:2]), int(f[9][2:4]), int(f[9][4:6])
                    yy += 2000 if yy < 80 else 1900
                    utc = calendar.timegm((yy, mo, dd, hh, mm, ss))
                speed = float(f[7]) * 0.514444 if f[7] else None  # knots -> m/s
                prev = self.fix or {}
                self.fix = {"lat": lat, "lon": lon, "alt": prev.get("alt", 0.0),
                            "acc": prev.get("acc", 10.0), "ts": time.time(), "utc": utc,
                            "speed": speed}
                self._fixed(source)
        except (ValueError, IndexError):
            pass

    # ---------------------------------------------------------------- network sources
    async def listen_udp(self, port, stop):
        gps = self

        class Proto(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                for ln in data.decode(errors="replace").splitlines():
                    gps.feed(ln, f"udp:{addr[0]}")

        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(Proto, local_addr=("0.0.0.0", port))
        except OSError as e:
            log.warning("cannot listen for GPS on UDP %d: %s", port, e)
            return
        log.info("listening for NMEA on UDP %d", port)
        try:
            await stop.wait()
        finally:
            transport.close()

    async def connect_tcp(self, host_fn, port, stop):
        """Keep a TCP connection to the phone's NMEA server (e.g. GPS2IP)."""
        while not stop.is_set():
            host = host_fn()
            if host:
                try:
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 5)
                    log.info("NMEA over TCP from %s:%d", host, port)
                    while not stop.is_set():
                        line = await asyncio.wait_for(reader.readline(), 30)
                        if not line:
                            break
                        self.feed(line.decode(errors="replace"), f"tcp:{host}")
                    writer.close()
                except (OSError, asyncio.TimeoutError):
                    pass
            try:
                await asyncio.wait_for(stop.wait(), 15)
            except asyncio.TimeoutError:
                pass

    # ---------------------------------------------------------------- SensorServer app
    def feed_location(self, loc, source="sensorserver"):
        """A location as JSON from the SensorServer app (decimal degrees, m/s, ms epoch)."""
        try:
            lat, lon = float(loc["latitude"]), float(loc["longitude"])
        except (KeyError, TypeError, ValueError):
            return
        self.last_sentence = time.time()
        if not self._accept(source):
            return
        t = loc.get("time")
        # "Last known location" can be minutes old if the phone has stopped updating GPS
        # (screen off, battery saver). Both clocks are set from the internet, so compare
        # them: an old position must not be logged as where networks are heard *now*.
        if t and abs(time.time() - int(t) / 1000) > 30:
            self.stale_seen = time.time()
            return
        self.fix = {"lat": lat, "lon": lon, "alt": float(loc.get("altitude") or 0.0),
                    "acc": float(loc.get("accuracy") or 10.0), "ts": time.time(),
                    "utc": int(t) // 1000 if t else None,
                    "speed": float(loc["speed"]) if loc.get("speed") is not None else None}
        self._fixed(source)

    async def connect_sensorserver(self, host_fn, port, stop):
        """
        SensorServer streams GPS over a WebSocket at ws://phone:port/gps, but only when
        the location changes, so a phone lying still goes quiet. Harald politely asks
        "getLastKnownLocation" every few seconds to keep the fix fresh.
        """
        import json
        import os
        import base64
        from .activity import read_frame, make_frame
        while not stop.is_set():
            host = host_fn()
            if host:
                writer = None
                try:
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 5)
                    key = base64.b64encode(os.urandom(16)).decode()
                    writer.write((f"GET /gps HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                                  f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                                  f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
                    await writer.drain()
                    status = await asyncio.wait_for(reader.readline(), 5)
                    if b" 101 " not in status:
                        raise ValueError(status)
                    while (await asyncio.wait_for(reader.readline(), 5)) not in (b"\r\n", b""):
                        pass
                    log.info("GPS from SensorServer at %s:%d", host, port)

                    async def ask():
                        while not stop.is_set():
                            writer.write(make_frame(0x1, b"getLastKnownLocation"))
                            await writer.drain()
                            await asyncio.sleep(3)
                    asker = asyncio.create_task(ask())
                    try:
                        while not stop.is_set():
                            op, payload = await asyncio.wait_for(read_frame(reader), 30)
                            if op == 0x8:
                                break
                            if op == 0x9:
                                writer.write(make_frame(0xA, payload))
                            elif op in (0x1, 0x2):
                                try:
                                    msg = json.loads(payload.decode())
                                except ValueError:
                                    continue
                                if isinstance(msg, dict):
                                    # replies to the request are wrapped; spelled two ways in the docs
                                    loc = msg.get("lastKnownLocation") or msg.get("lastKnowLocation") or msg
                                    if isinstance(loc, dict):
                                        self.feed_location(loc)
                    finally:
                        asker.cancel()
                except (OSError, asyncio.TimeoutError, ValueError, ConnectionError,
                        asyncio.IncompleteReadError) as e:
                    log.debug("SensorServer GPS: %s", e)
                finally:
                    if writer:
                        writer.close()
            try:
                await asyncio.wait_for(stop.wait(), 15)
            except asyncio.TimeoutError:
                pass


# ---------------------------------------------------------------- a USB receiver
USB_PATTERNS = ("/dev/serial/by-id/*u-blox*", "/dev/serial/by-id/*GPS*", "/dev/serial/by-id/*GNSS*",
                "/dev/ttyACM*", "/dev/ttyUSB*")


def usb_candidates(patterns=USB_PATTERNS):
    """Serial ports that might be a GPS receiver, the likeliest first (named ones, then any)."""
    out = []
    for pat in patterns:
        for p in sorted(glob.glob(pat)):
            real = os.path.realpath(p)
            if real not in [os.path.realpath(x) for x in out]:
                out.append(p)
    return out


def open_serial(path, baud=9600):
    """Open a serial port raw (no echo, no line editing), for reading only."""
    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attrs = termios.tcgetattr(fd)
        speed = getattr(termios, f"B{baud}", termios.B9600)
        attrs[0] = 0                                        # input flags
        attrs[1] = 0                                        # output flags
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0                                        # local flags: raw
        attrs[4] = attrs[5] = speed
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except termios.error:
        pass                                                # not a tty (a test file): fine
    return fd


async def run_usb(gps, device, stop, patterns=USB_PATTERNS, probe_s=5.0, retry_s=10.0):
    """Read a USB GPS receiver for as long as it's plugged in, finding it again if it's
    unplugged and replugged. `device` is "auto" or a path like /dev/ttyACM0. With "auto",
    a port only counts as a GPS receiver once it sends a valid NMEA line within a few
    seconds, so another serial gadget (a Flipper Zero, say) is let go again."""
    loop = asyncio.get_running_loop()
    rejected = {}
    while not stop.is_set():
        paths = [device] if device != "auto" else usb_candidates(patterns)
        paths = [p for p in paths if time.time() - rejected.get(p, 0) > 120]
        for path in paths:
            if stop.is_set():
                break
            try:
                fd = open_serial(path)
            except OSError:
                continue
            got_nmea = await _read_port(gps, fd, path, stop, loop, probe_s if device == "auto" else None)
            os.close(fd)
            if got_nmea:
                log.info("USB GPS receiver on %s unplugged or stopped", path)
                gps.usb_device = None
            elif device == "auto":
                rejected[path] = time.time()                # not a GPS: leave it alone a while
        try:
            await asyncio.wait_for(stop.wait(), retry_s)
        except asyncio.TimeoutError:
            pass


async def _read_port(gps, fd, path, stop, loop, probe_s):
    """Feed lines from an open port into `gps` until it goes quiet or away. Returns
    whether it ever sent NMEA."""
    buf, got, started, last = b"", False, time.monotonic(), time.monotonic()
    ready = asyncio.Event()
    loop.add_reader(fd, ready.set)
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(ready.wait(), 1.0)
            except asyncio.TimeoutError:
                pass
            ready.clear()
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                chunk = None
            except OSError:
                return got                                  # unplugged
            now = time.monotonic()
            if chunk == b"" and not os.isatty(fd):
                chunk = None                                # (a plain file in tests: wait for more)
            if chunk:
                last = now
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    text = ln.decode("ascii", errors="replace").strip()
                    if text.startswith("$") and _checksum_ok(text) and "*" in text:
                        if not got:
                            got = True
                            gps.usb_device = path
                            log.info("USB GPS receiver on %s", path)
                        gps.feed(text, f"usb:{os.path.basename(path)}")
                buf = buf[-1024:]
            if not got and probe_s is not None and now - started > probe_s:
                return False
            if got and now - last > 10:
                return got                                  # gone quiet: look again
    finally:
        loop.remove_reader(fd)
    return got
