"""Mail Lock — passphrase-gated access to Aether Mail credentials.

The verifier is an Argon2id-derived key digest.  The derived key itself is
never stored.  Auto-lock is driven by a pure timeout predicate and by system
sleep/screen-lock signals, both of which call lock().
"""

from __future__ import annotations

import hashlib
import hmac
import math
import os
import threading
import time

from ..vault.secure_vault import Argon2Params, derive_key

DEFAULT_TIMEOUT_S = 300.0


class LockedError(RuntimeError):
    """Raised when a locked lock is asked for its passphrase."""


class LockError(RuntimeError):
    """Raised when a passphrase does not unlock the lock."""


def should_lock(last_activity: float | None, now: float, timeout_s: float) -> bool:
    """Pure inactivity predicate used by the UI loop and D-Bus hooks."""
    try:
        timeout = float(timeout_s)
        current = float(now)
    except (TypeError, ValueError):
        return True
    if not math.isfinite(timeout) or not math.isfinite(current):
        return True
    if timeout <= 0:
        return True
    if last_activity is None:
        return True
    try:
        previous = float(last_activity)
    except (TypeError, ValueError):
        return True
    if not math.isfinite(previous):
        return True
    delta = current - previous
    if delta < 0:  # clock went backwards; do not lock spuriously
        return False
    return delta >= timeout


class MailLock:
    def __init__(
        self,
        passphrase: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        params: Argon2Params | None = None,
        now_fn=time.monotonic,
    ):
        if not isinstance(passphrase, str) or not passphrase:
            raise ValueError("passphrase must be a non-empty string")
        self._params = params or Argon2Params()
        self._params.validate()
        self._salt = os.urandom(self._params.salt_len)
        digest = hashlib.sha256(derive_key(passphrase, self._params, self._salt)).digest()
        self._verifier = digest
        self._timeout_s = float(timeout_s)
        self._now_fn = now_fn
        self._last_activity = now_fn()
        self._passphrase: str | None = None
        self._locked = True
        self._mutex = threading.RLock()
        self._dbus_subscriptions: list[tuple[object, int]] = []

    @property
    def locked(self) -> bool:
        with self._mutex:
            return self._locked

    @property
    def timeout_s(self) -> float:
        return self._timeout_s

    def unlock(self, passphrase: str) -> None:
        if not isinstance(passphrase, str) or not passphrase:
            raise LockError("passphrase must be a non-empty string")
        with self._mutex:
            digest = hashlib.sha256(derive_key(passphrase, self._params, self._salt)).digest()
            if not hmac.compare_digest(digest, self._verifier):
                raise LockError("invalid mail passphrase")
            self._passphrase = passphrase
            self._last_activity = self._now_fn()
            self._locked = False

    def lock(self) -> None:
        with self._mutex:
            self._locked = True
            self._passphrase = None

    def passphrase(self) -> str:
        with self._mutex:
            if self._locked or self._passphrase is None:
                raise LockedError("mail is locked")
            self._last_activity = self._now_fn()
            return self._passphrase

    def note_activity(self, now: float | None = None) -> None:
        with self._mutex:
            self._last_activity = self._now_fn() if now is None else float(now)

    def check_auto_lock(self, now: float | None = None) -> bool:
        with self._mutex:
            current = self._now_fn() if now is None else float(now)
            if self._locked:
                return True
            if should_lock(self._last_activity, current, self._timeout_s):
                self.lock()
                return True
            return False

    def on_system_lock(self) -> None:
        self.lock()

    def on_system_sleep(self) -> None:
        self.lock()


def install_dbus_hooks(mail_lock: MailLock) -> bool:
    """Subscribe to logind sleep and screen-lock signals; no-op without gi."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        gi.require_version("GLib", "2.0")
        from gi.repository import Gio
    except Exception:
        return False

    def on_signal(connection, sender, path, interface, signal, params):
        try:
            if signal == "PrepareForSleep" and bool(params[0]):
                mail_lock.on_system_sleep()
            elif signal == "ActiveChanged" and bool(params[0]):
                mail_lock.on_system_lock()
        except Exception:
            pass

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except Exception:
        return False

    subscriptions: list[tuple[object, int]] = []
    targets = (
        ("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "PrepareForSleep"),
        ("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver", "ActiveChanged"),
    )
    for sender, path, interface, signal in targets:
        try:
            sid = bus.signal_subscribe(sender, interface, signal, path, None, Gio.DBusSignalFlags.NONE, on_signal)
            subscriptions.append((bus, sid))
        except Exception:
            continue
    if not subscriptions:
        return False
    mail_lock._dbus_subscriptions = subscriptions
    return True
