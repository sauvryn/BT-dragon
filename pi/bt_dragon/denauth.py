"""
A password for the Den (optional: Den → Care and Accessibility → Den password).

How it's kept: never the password itself. It's stretched into a key with PBKDF2 (SHA-256, a
random "salt", 200,000 rounds), and only that key is kept; logging in does the same stretch
and compares. The stretch takes a moment on purpose: harmless for one login, but it makes
guessing millions of passwords painfully slow for anyone who copied the database. Wrong
guesses are slowed down further: after 5 in 10 minutes, logins wait a minute (doubling each
time after that).

Logging in gives the browser a long random ticket in a cookie (HttpOnly, so scripts on the
page can't read it; SameSite=Strict, so other sites can't send it). Only a fingerprint of each
ticket (its SHA-256) is kept, so the database can't be used to log in. Tickets last 30 days,
and changing the password throws them all away.

The phone voice (Termux) can't log in, so its download carries a ticket of its own, used only
for asking what to say. Changing the password replaces it too: download the script again.

Ways back in, if the password is ever lost or a bug locks you out:
  * the testing failsafe (a tick box next to it): the password switches itself off five
    minutes after it was switched on;
  * a file named "forget-den-password" on the card's boot partition (bootfs): on his next
    start, the password is switched off and the file deleted;
  * on the Pi itself (over SSH), the control link doesn't ask for it:
        echo "DENAUTHSET off" | nc -q1 localhost 5151
"""
import hashlib
import hmac
import os
import secrets
import time

ITERS = 200_000
SESSION_S = 30 * 86400
FAILSAFE_S = 300
MIN_LEN = 8
COOKIE = "btdragon_den"
RESET_FILE = "forget-den-password"
BOOT_DIRS = ("/boot/firmware", "/boot")


def _stretch(pw, salt, iters):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iters)


def _fp(token):
    return hashlib.sha256(token.encode()).hexdigest()


class DenAuth:
    def __init__(self, store, boot_dirs=BOOT_DIRS):
        self.store = store
        self.s = store.get("den_auth") or {}
        self._fails = []              # times of recent wrong passwords (in memory)
        self._locked_until = 0.0
        self._lock_s = 60
        self.news = []                # things for the diary ("switched off by the failsafe")
        for d in boot_dirs:           # the escape hatch: a file on the boot partition
            p = os.path.join(d, RESET_FILE)
            if os.path.exists(p):
                self.s["on"] = False
                self._save()
                self.news.append("The Den password was switched off (by the forget-den-password file)")
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _save(self):
        self.store.put("den_auth", self.s)

    # ---- the settings
    @property
    def has_password(self):
        return bool(self.s.get("hash"))

    def enabled(self, now=None):
        """Is the password needed right now? (Runs the failsafe.)"""
        if not self.s.get("on"):
            return False
        now = now or time.time()
        if self.s.get("failsafe") and now - self.s.get("on_since", now) >= FAILSAFE_S:
            self.s["on"] = False
            self._save()
            self.news.append("The Den password was switched off by the failsafe (five minutes after it was "
                             "switched on)")
            return False
        return True

    def failsafe_at(self):
        """When the failsafe will switch the password off, or None."""
        if self.s.get("on") and self.s.get("failsafe"):
            return self.s.get("on_since", 0) + FAILSAFE_S
        return None

    def set_password(self, pw):
        if len(pw) < MIN_LEN:
            return f"use at least {MIN_LEN} characters"
        if pw.strip() != pw:
            return "no spaces at the start or end"
        salt = os.urandom(16)
        self.s.update(salt=salt.hex(), hash=_stretch(pw, salt, ITERS).hex(), iters=ITERS)
        self.store.put("den_sessions", {})              # everyone logs in again
        self.store.put("phone_token", secrets.token_urlsafe(24))
        self._save()
        return None

    def set_on(self, on, now=None):
        if on and not self.has_password:
            return "set a password first"
        self.s["on"] = bool(on)
        if on:
            self.s["on_since"] = now or time.time()     # (the failsafe counts from here)
        self._save()
        return None

    def set_failsafe(self, on, now=None):
        self.s["failsafe"] = bool(on)
        if on and self.s.get("on"):
            self.s["on_since"] = now or time.time()     # five minutes from now
        self._save()

    # ---- logging in
    def check(self, pw, now=None):
        """True for the right password; wrong ones are slowed down."""
        now = now or time.time()
        if now < self._locked_until or not self.has_password:
            return False
        good = hmac.compare_digest(_stretch(pw, bytes.fromhex(self.s["salt"]), self.s.get("iters", ITERS)),
                                   bytes.fromhex(self.s["hash"]))
        if good:
            self._fails, self._lock_s = [], 60
            return True
        self._fails = [t for t in self._fails if now - t < 600] + [now]
        if len(self._fails) >= 5:
            self._locked_until, self._fails = now + self._lock_s, []
            self._lock_s = min(self._lock_s * 2, 3600)
        return False

    def locked_for(self, now=None):
        return max(0, int(self._locked_until - (now or time.time())))

    def login(self, pw, now=None):
        """A new ticket for the right password, or None."""
        now = now or time.time()
        if not self.check(pw, now):
            return None
        token = secrets.token_urlsafe(32)
        sessions = {k: v for k, v in (self.store.get("den_sessions") or {}).items() if v > now}
        sessions[_fp(token)] = now + SESSION_S
        self.store.put("den_sessions", sessions)
        return token

    def logout(self, cookie_header):
        token = self.cookie(cookie_header)
        if token:
            sessions = self.store.get("den_sessions") or {}
            sessions.pop(_fp(token), None)
            self.store.put("den_sessions", sessions)

    @staticmethod
    def cookie(header):
        for part in (header or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE and v:
                return v
        return None

    def session_ok(self, cookie_header, now=None):
        token = self.cookie(cookie_header)
        if not token:
            return False
        exp = (self.store.get("den_sessions") or {}).get(_fp(token))
        return bool(exp and exp > (now or time.time()))

    # ---- the phone voice's own ticket
    def phone_token(self):
        t = self.store.get("phone_token")
        if not t:
            t = secrets.token_urlsafe(24)
            self.store.put("phone_token", t)
        return t

    def phone_ok(self, header):
        return bool(header) and hmac.compare_digest(header.encode(), self.phone_token().encode())

    def lines(self, now=None):
        """For the Den."""
        now = now or time.time()
        on = self.enabled(now)
        fs = self.failsafe_at()
        return [f"on={int(on)}", f"has_password={int(self.has_password)}", f"failsafe={int(bool(self.s.get('failsafe')))}",
                f"failsafe_in={max(0, int(fs - now)) if fs else ''}"]
