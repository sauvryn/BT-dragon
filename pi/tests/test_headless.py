"""No e-ink panel: he finds out by himself (a panel never busy, or busy forever) and runs
headless, the den showing his screen; a real panel is still found; one that stops
answering later doesn't freeze him."""
import os
import sys
import tempfile
import time

from PIL import Image

tmp = tempfile.mkdtemp()
pkg = os.path.join(tmp, "waveshare_epd")
os.makedirs(pkg)
open(os.path.join(pkg, "__init__.py"), "w").write("")
# a pretend Waveshare driver, written the way the real ones are
open(os.path.join(pkg, "epdconfig.py"), "w").write('''
import time
BUSY_PIN = 24
MODE = "present"          # present / absent / stuck
busy_until = 0.0
exited = False
def digital_read(pin):
    if MODE == "absent":
        return 0
    if MODE == "stuck":
        return 1
    return 1 if time.monotonic() < busy_until else 0
def work(seconds):
    global busy_until
    busy_until = time.monotonic() + seconds
def module_exit():
    global exited
    exited = True
''')
open(os.path.join(pkg, "epd2in13_V4.py"), "w").write('''
from . import epdconfig
class EPD:
    def __init__(self):
        self.busy_pin = epdconfig.BUSY_PIN
        self.frames = 0
    def ReadBusy(self):
        while epdconfig.digital_read(self.busy_pin) == 1:
            pass          # the real driver waits like this, forever if need be
    def init(self):
        epdconfig.work(0.02); self.ReadBusy()
    def Clear(self, color):
        epdconfig.work(0.6); self.ReadBusy()          # a full refresh: busy for a while
    def getbuffer(self, img):
        return b""
    def displayPartBaseImage(self, data):
        epdconfig.work(0.6); self.ReadBusy(); self.frames += 1
    def displayPartial(self, data):
        epdconfig.work(0.05); self.ReadBusy(); self.frames += 1
    def sleep(self):
        pass
''')
sys.path.insert(0, tmp)

from bt_dragon.display import Display  # noqa: E402
import waveshare_epd.epdconfig as cfg  # noqa: E402

Display.FIRST_WAIT_S = 1.5
Display.WAIT_S = 2
img = Image.new("1", (250, 122), 1)

# a real panel: found, and drawn on
cfg.MODE = "present"
d = Display(True, png_path=None)
assert not d.headless and d.headless_why == "", d.headless_why
d.show(img)
d.show(img)
assert d.epd.frames == 2 and d.png.startswith(b"\x89PNG")

# nothing attached (the pin reads "not busy"): headless, straight away
cfg.MODE, cfg.exited = "absent", False
t0 = time.monotonic()
d = Display(True)
assert d.headless and "never got busy" in d.headless_why and cfg.exited and time.monotonic() - t0 < 1
d.show(img)                                   # still draws, for the den
assert d.png.startswith(b"\x89PNG")

# a pin stuck "busy": the wait gives up instead of freezing him
cfg.MODE, cfg.exited = "stuck", False
t0 = time.monotonic()
d = Display(True)
assert d.headless and "stayed busy" in d.headless_why and 1.4 < time.monotonic() - t0 < 4, d.headless_why

# unplugged later: carries on headless
cfg.MODE = "present"
d = Display(True)
assert not d.headless
cfg.MODE = "stuck"
t0 = time.monotonic()
d.show(img)
assert d.headless and "stopped answering" in d.headless_why and time.monotonic() - t0 < 4
d.show(img)
d.sleep(img)

# switched off in the settings
d = Display(False)
assert d.headless and d.headless_why == "the screen is switched off in the settings"
print("headless ok")
