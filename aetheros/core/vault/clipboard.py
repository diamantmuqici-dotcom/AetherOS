"""Clipboard auto-clear for copied vault secrets.

Pure logic module: no GUI toolkit is imported at load time. Time is injected as
a monotonic float so expiry is deterministic and headless-testable.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Protocol

__all__ = [
    "MIN_TIMEOUT_S",
    "MAX_TIMEOUT_S",
    "DEFAULT_TIMEOUT_S",
    "FINGERPRINT_BYTES",
    "ClipboardTimer",
    "ClipboardBackend",
    "GtkBackend",
    "NullBackend",
    "redact_fingerprint",
    "validate_timeout",
    "timeout_from_env",
    "arm_secret",
    "schedule_clear",
]

MIN_TIMEOUT_S = 1
MAX_TIMEOUT_S = 300
DEFAULT_TIMEOUT_S = 30
FINGERPRINT_BYTES = 16  # 128-bit SHA-256 prefix for state logs
TIMEOUT_ENV = "AETHER_CLIPBOARD_TIMEOUT"


def validate_timeout(value: int | float | str) -> int:
    """Coerce to whole seconds in [1, 300], else raise ValueError."""
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("clipboard timeout must be whole seconds")
    try:
        seconds = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("clipboard timeout must be an integer number of seconds") from exc
    if not MIN_TIMEOUT_S <= seconds <= MAX_TIMEOUT_S:
        raise ValueError(f"clipboard timeout must be {MIN_TIMEOUT_S}..{MAX_TIMEOUT_S} seconds")
    return seconds


def timeout_from_env(environ=None, *, default: int = DEFAULT_TIMEOUT_S) -> int:
    """Read the configured timeout; invalid values fall back to default."""
    env = os.environ if environ is None else environ
    raw = env.get(TIMEOUT_ENV)
    if raw is None or raw == "":
        return validate_timeout(default)
    try:
        return validate_timeout(raw)
    except ValueError:
        return validate_timeout(default)


def redact_fingerprint(text: bytes | bytearray | str) -> str:
    """Return a SHA-256 prefix for state logs; never the secret itself."""
    raw = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    return hashlib.sha256(raw).hexdigest()[: FINGERPRINT_BYTES * 2]


@dataclass
class ClipboardTimer:
    """Monotonic expiry state for the most recently copied secret."""

    timeout_s: int = field(default=DEFAULT_TIMEOUT_S)
    clear_armed: bool = field(default=False, init=False)
    expiry_at: float = field(default=0.0, init=False)
    owner: int = field(default=0, init=False)
    fingerprint: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.timeout_s = validate_timeout(self.timeout_s)

    @property
    def expires_at(self) -> float:
        """Alias for the armed deadline."""
        return self.expiry_at

    def arm(self, now: float, text_fingerprint: str) -> int:
        """Arm or re-arm expiry; return the new owner token."""
        self.owner += 1
        self.clear_armed = True
        self.expiry_at = now + self.timeout_s
        self.fingerprint = text_fingerprint
        return self.owner

    def should_clear(self, now: float, token: int) -> bool:
        """True only for the current owner once its deadline has passed."""
        return self.clear_armed and token == self.owner and now >= self.expiry_at

    def is_expired(self, now: float) -> bool:
        """True once the armed deadline has passed, regardless of owner."""
        return self.clear_armed and now >= self.expiry_at

    def disarm(self, token: int | None = None) -> None:
        """Cancel expiry, optionally only for a matching owner token."""
        if token is None or token == self.owner:
            self.clear_armed = False
            self.fingerprint = ""

    def plan_clear(self, text_fingerprint: str, timeout_s: int) -> dict:
        """State snapshot for logging; contains a fingerprint, never plaintext."""
        return {
            "armed": True,
            "timeout_s": validate_timeout(timeout_s),
            "fingerprint": text_fingerprint,
            "next_owner": self.owner + 1,
        }


class ClipboardBackend(Protocol):
    """Minimal clipboard surface used by the auto-clear helpers."""

    def set_text(self, text: str) -> None: ...

    def claim(self, token: int) -> None: ...

    def clear(self) -> None: ...

    def owner_token(self) -> int | None: ...


class NullBackend:
    """In-memory clipboard for tests and non-GUI runs."""

    def __init__(self) -> None:
        self._text: str | None = None
        self._owner: int | None = None
        self.clear_calls = 0

    def set_text(self, text: str) -> None:
        self._text = text

    def get_text(self) -> str | None:
        return self._text

    def claim(self, token: int) -> None:
        self._owner = token

    def clear(self) -> None:
        self._text = None
        self._owner = None
        self.clear_calls += 1

    def owner_token(self) -> int | None:
        return self._owner


class GtkBackend:
    """Gtk backend; gi is imported inside methods to keep module load headless."""

    def __init__(self) -> None:
        self._owner: int | None = None

    def _boards(self):
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        from gi.repository import Gdk, Gtk

        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("no default Gdk display")
        boards = []
        if hasattr(display, "get_primary_clipboard"):
            boards.append(display.get_primary_clipboard())
        if hasattr(display, "get_clipboard"):
            boards.append(display.get_clipboard())
        if not boards and hasattr(Gtk, "Clipboard"):
            boards = [
                Gtk.Clipboard.get_for_display(display, Gdk.SELECTION_PRIMARY),
                Gtk.Clipboard.get_for_display(display, Gdk.SELECTION_CLIPBOARD),
            ]
        if not boards:
            raise RuntimeError("no clipboard available on this display")
        return boards

    @staticmethod
    def _set_text(board, text: str) -> None:
        if hasattr(board, "set_text"):
            try:
                board.set_text(text, -1)
            except TypeError:
                board.set_text(text)
        if hasattr(board, "store"):
            board.store()

    @staticmethod
    def _clear(board) -> None:
        board.clear()
        if hasattr(board, "store"):
            board.store()

    def set_text(self, text: str) -> None:
        for board in self._boards():
            self._set_text(board, text)

    def claim(self, token: int) -> None:
        self._owner = token

    def clear(self) -> None:
        for board in self._boards():
            self._clear(board)
        self._owner = None

    def owner_token(self) -> int | None:
        return self._owner


def arm_secret(
    backend: ClipboardBackend,
    text: str,
    timer: ClipboardTimer,
    now: float,
) -> int:
    """Copy a secret, claim the board for a fresh token, and arm expiry."""
    token = timer.arm(now, redact_fingerprint(text))
    backend.set_text(text)
    backend.claim(token)
    return token


def schedule_clear(
    backend: ClipboardBackend,
    timer: ClipboardTimer,
    token: int,
    now: float | None = None,
) -> bool:
    """GLib.timeout_add callback: clear once when due and still owned.

    Returns True to keep the source alive, False to have GLib remove it.
    """
    if now is None:
        now = time.monotonic()
    if backend.owner_token() != token:
        return False
    if not timer.should_clear(now, token):
        return True
    backend.clear()
    return False
