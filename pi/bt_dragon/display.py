"""
The Waveshare 2.13" e-ink panel, as used in Pwnagotchis.

Tested with the V4 panel. V3 and V2 (the other 2.13" versions Pwnagotchis shipped with)
are supported through the same Waveshare driver but haven't been tested on real hardware;
choose yours with  model = "V4" / "V3" / "V2"  under [display] in bt-dragon.toml. The
version is printed on the back of the panel's circuit board.

E-ink pixels are tiny capsules of black and white pigment moved by an electric field.
A *full* refresh drives every pixel through black and white a few times (the flash you
see) to reset them cleanly; a *partial* refresh just nudges the pixels that changed, which
is quick and quiet but slowly leaves faint "ghosts". So Harald uses partial refreshes for
everyday changes and a full one every 20 minutes to wipe the ghosts away.

The panel keeps its picture with no power at all, which is why the sleeping screen stays
up after the Pi is unplugged.

No panel (a "headless" dragon): every frame is drawn in memory first and the den shows
that copy, so he works the same without one. He notices by himself. The panel has a
BUSY wire it holds up while it's working, and a full refresh keeps it busy for a second
or two. The Pi's pin for that wire is pulled down inside the Pi, so with nothing attached
it never reads busy: if the first full refresh "finishes" without the panel ever being
busy, there's no panel. If instead the pin reads busy forever (a loose or odd connection),
the Waveshare driver would wait forever; here every wait gives up after a while, and he
carries on headless instead of freezing.
"""
import io
import logging
import os
import sys
import threading
import time

log = logging.getLogger("display")
VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")


class PanelMissing(Exception):
    pass


class Display:
    MODELS = {"V4": "epd2in13_V4", "V3": "epd2in13_V3", "V2": "epd2in13_V2"}
    FIRST_WAIT_S = 10       # longest a wait may take while finding out if there's a panel
    WAIT_S = 30             # ...and afterwards (a full refresh takes about 3 s)
    MIN_BUSY_S = 0.3        # a real panel is busy for well over this during a full refresh

    def __init__(self, enabled=True, full_every_s=1200, png_path=None, rotate=180, model="V4"):
        self.enabled = enabled
        self.rotate = rotate  # Pwnagotchi cases mount the panel upside down, hence 180
        self.full_every_s = full_every_s
        self.png_path = png_path
        self.epd = None
        self.model = "V4"
        self.last_full = 0.0
        self.png = b""
        self._lock = threading.Lock()
        self.headless_why = "the screen is switched off in the settings" if not enabled else ""
        self._busy_s = 0.0
        self._wait_limit = self.FIRST_WAIT_S
        self._cfg_module = None
        if enabled:
            try:
                sys.path.insert(0, VENDOR)
                import importlib
                self.model = str(model).upper()
                if self.model not in self.MODELS:
                    log.warning("unknown display model %r; using V4", model)
                    self.model = "V4"
                driver = importlib.import_module("waveshare_epd." + self.MODELS[self.model])
                self._cfg_module = getattr(driver, "epdconfig", None)
                self.epd = driver.EPD()
                self.epd.ReadBusy = self._read_busy          # waits that give up
                self._init(full=True)
                self.epd.Clear(0xFF)
                if self._cfg_module and self._busy_s < self.MIN_BUSY_S:
                    raise PanelMissing("it never got busy during the first refresh")
                self._wait_limit = self.WAIT_S
                log.info("e-ink ready (2.13in %s)", self.model)
            except Exception as e:
                self._headless(f"no e-ink panel found ({e})")

    @property
    def headless(self):
        return self.epd is None

    def _headless(self, why):
        log.warning("%s: running headless (the den shows the screen)", why)
        self.headless_why = why
        epd, self.epd = self.epd, None
        if epd is not None and self._cfg_module is not None:
            try:
                self._cfg_module.module_exit()               # let go of the pins
            except Exception:
                pass

    def _read_busy(self):
        """The Waveshare driver's wait for the panel, but one that gives up."""
        cfg, pin = self._cfg_module, getattr(self.epd, "busy_pin", None)
        if cfg is None or pin is None:
            return
        t0 = time.monotonic()
        while cfg.digital_read(pin) == 1:
            if time.monotonic() - t0 > self._wait_limit:
                raise PanelMissing(f"it stayed busy for over {self._wait_limit} s")
            time.sleep(0.01)
        self._busy_s += time.monotonic() - t0

    def show(self, img, force_full=False):
        """Blocking: call from a worker thread."""
        with self._lock:
            buf = io.BytesIO()
            img.convert("L").save(buf, "PNG")
            self.png = buf.getvalue()
            if self.png_path:
                tmp = self.png_path + ".tmp"
                try:
                    with open(tmp, "wb") as f:
                        f.write(self.png)
                    os.replace(tmp, self.png_path)
                except OSError:
                    pass
            if not self.epd:
                return
            now = time.time()
            panel = img.rotate(self.rotate) if self.rotate in (90, 180, 270) else img
            if panel.size != img.size:  # 90/270 would need a portrait layout
                panel = img
            try:
                data = self.epd.getbuffer(panel)
                if force_full or now - self.last_full > self.full_every_s:
                    self._init(full=True)
                    self.epd.displayPartBaseImage(data)  # full refresh + base for partials
                    if self.model == "V2":
                        self._init(full=False)  # V2 needs switching into partial mode
                    self.last_full = now
                else:
                    self.epd.displayPartial(data)
            except Exception as e:                       # unplugged, or a loose cable
                self._headless(f"the e-ink panel stopped answering ({e})")

    def _init(self, full):
        # V2's init takes a mode (full or partial refresh); V3 and V4 don't
        if self.model == "V2":
            self.epd.init(self.epd.FULL_UPDATE if full else self.epd.PART_UPDATE)
        else:
            self.epd.init()

    def sleep(self, img):
        """Draw a last full frame and power the panel down."""
        self.show(img, force_full=True)
        if self.epd:
            try:
                self.epd.sleep()
            except Exception:
                pass
