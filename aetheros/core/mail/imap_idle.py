"""IMAP IDLE push with bounded reads, cancellation and bounded reconnect."""

from __future__ import annotations

import imaplib
import re
import select
import ssl
import threading
import time
from typing import Any, Callable, Iterable

DEFAULT_IDLE_SECONDS = 60.0
MAX_IDLE_SECONDS = 1740.0
READ_SLICE_SECONDS = 1.0
CONTINUATION_TIMEOUT = 10.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
DEFAULT_TIMEOUT = 30

_UNSOLICITED_RE = re.compile(rb"^\*\s+(\d{1,10})\s+(EXISTS|RECENT|EXPUNGE)(?:\s|$)", re.I)


class IdleError(Exception):
    """Base class for IMAP IDLE failures."""


class IdleConnectionError(IdleError):
    """A transport-level IDLE failure that may be recoverable by reconnecting."""


def parse_idle_unsolicited(lines: Iterable[bytes | str]) -> list[dict[str, object]]:
    """Normalize untagged EXISTS/RECENT/EXPUNGE lines into event dicts."""
    events: list[dict[str, object]] = []
    for line in lines:
        if isinstance(line, str):
            raw = line.encode("utf-8", "replace")
        elif isinstance(line, (bytes, bytearray)):
            raw = bytes(line)
        else:
            continue
        match = _UNSOLICITED_RE.match(raw)
        if match is None:
            continue
        count = int(match.group(1))
        kind = match.group(2).decode("ascii").upper()
        if kind == "EXPUNGE":
            events.append({"event": kind, "seq": count})
        else:
            events.append({"event": kind, "count": count})
    return events


def _has_idle_protocol(connection: Any) -> bool:
    return all(
        callable(getattr(connection, name, None))
        for name in ("select", "issue_idle", "read_idle_line", "finish_idle", "close")
    )


class IMAPIdleAdapter:
    """Adapt a stdlib imaplib connection to the small IDLE protocol."""

    def __init__(self, connection: Any):
        self._conn = connection
        self._saved_timeout: float | None = None

    def select(self, mailbox: str) -> tuple[str, Any]:
        return self._conn.select(mailbox)

    def issue_idle(self) -> bytes:
        # imaplib has no IDLE command entry; register SELECTED as valid state.
        imaplib.Commands.setdefault("IDLE", ("SELECTED",))
        tag = self._conn._command("IDLE")
        sock = self._conn.socket()
        self._saved_timeout = sock.gettimeout()
        sock.settimeout(CONTINUATION_TIMEOUT)
        try:
            while self._conn.continuation_response is None:
                self._conn._get_response()
        except TimeoutError as exc:
            raise IdleConnectionError("IDLE continuation timed out") from exc
        except (OSError, imaplib.IMAP4.error) as exc:
            raise IdleConnectionError(f"IDLE command failed: {exc}") from exc
        return tag

    def read_idle_line(self, timeout_s: float) -> bytes | None:
        sock = self._conn.socket()
        sock.settimeout(max(0.05, timeout_s))
        try:
            return self._conn._get_response()
        except (TimeoutError, select.error):
            return None
        except (OSError, imaplib.IMAP4.error) as exc:
            raise IdleConnectionError(f"IDLE read failed: {exc}") from exc

    def finish_idle(self, tag: bytes) -> None:
        try:
            self._conn.send(b"DONE\r\n")
            self._conn._command_complete("IDLE", tag)
        except (OSError, imaplib.IMAP4.error) as exc:
            raise IdleError(f"could not terminate IDLE: {exc}") from exc
        finally:
            if self._saved_timeout is not None:
                try:
                    self._conn.socket().settimeout(self._saved_timeout)
                except OSError:
                    pass
                self._saved_timeout = None

    def close(self) -> None:
        try:
            self._conn.logout()
        except Exception:
            pass


class IdleSession:
    """One authenticated IMAP connection dedicated to IDLE notifications."""

    def __init__(
        self,
        connection: Any,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_s: float = DEFAULT_BACKOFF_SECONDS,
        connect_fn: Callable[[], Any] | None = None,
        cancel_event: threading.Event | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 8:
            raise IdleError("max_attempts must be an integer in 1..8")
        try:
            backoff = float(backoff_s)
        except (TypeError, ValueError) as exc:
            raise IdleError("backoff_s must be numeric") from exc
        if not 0.0 <= backoff <= MAX_BACKOFF_SECONDS:
            raise IdleError(f"backoff_s must be in 0..{MAX_BACKOFF_SECONDS}")
        self.max_attempts = max_attempts
        self.backoff_s = backoff
        self._connect_fn = connect_fn
        self._cancel = cancel_event if cancel_event is not None else threading.Event()
        self._sleep = sleep_fn
        self._conn = connection if _has_idle_protocol(connection) else IMAPIdleAdapter(connection)
        self._selected: str | None = None
        self._idle = False
        self._token: Any = None

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()

    def select(self, mailbox: str) -> None:
        if not isinstance(mailbox, str) or not mailbox or len(mailbox) > 255:
            raise IdleError("mailbox must be a name of 1..255 characters")
        try:
            typ, _ = self._conn.select(mailbox)
        except (OSError, imaplib.IMAP4.error) as exc:
            raise IdleConnectionError(f"SELECT failed: {exc}") from exc
        if str(typ).upper() != "OK":
            raise IdleError(f"could not select mailbox {mailbox!r}")
        self._selected = mailbox

    def idle(
        self,
        timeout_s: float = DEFAULT_IDLE_SECONDS,
        on_event: Callable[[dict[str, object]], None] | None = None,
    ) -> list[dict[str, object]]:
        """Listen for unsolicited events for at most timeout_s seconds."""
        try:
            timeout = float(timeout_s)
        except (TypeError, ValueError) as exc:
            raise IdleError("timeout_s must be numeric") from exc
        if not 0.0 < timeout <= MAX_IDLE_SECONDS:
            raise IdleError(f"timeout_s must be in (0, {MAX_IDLE_SECONDS}]")
        if self._idle:
            raise IdleError("IDLE is already active")
        if self._selected is None:
            raise IdleError("select() a mailbox before idle()")

        try:
            return self._idle_once(timeout, on_event)
        except IdleConnectionError as first:
            self._abort_idle()
            if self._connect_fn is None:
                raise IdleError(str(first)) from first
            mailbox = self._selected
            self.reconnect()
            if mailbox is not None:
                self.select(mailbox)
            try:
                return self._idle_once(timeout, on_event)
            except IdleConnectionError as second:
                self._abort_idle()
                raise IdleError(str(second)) from second

    def _idle_once(
        self,
        timeout: float,
        on_event: Callable[[dict[str, object]], None] | None,
    ) -> list[dict[str, object]]:
        self._token = self._conn.issue_idle()
        self._idle = True
        events: list[dict[str, object]] = []
        try:
            deadline = time.monotonic() + timeout
            while not self._cancel.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                line = self._conn.read_idle_line(min(remaining, READ_SLICE_SECONDS))
                if line is None:
                    continue
                for event in parse_idle_unsolicited([line]):
                    events.append(event)
                    if on_event is not None:
                        on_event(event)
        finally:
            self.done()
        return events

    def _backoff(self, attempt: int) -> None:
        if self.backoff_s > 0:
            self._sleep(min(self.backoff_s * (2 ** attempt), MAX_BACKOFF_SECONDS))

    def _abort_idle(self) -> None:
        if not self._idle:
            return
        token = self._token
        self._idle = False
        self._token = None
        try:
            self._conn.finish_idle(token)
        except Exception:
            pass

    def done(self) -> None:
        if not self._idle:
            return
        token = self._token
        self._idle = False
        self._token = None
        self._conn.finish_idle(token)

    def reconnect(self) -> Any:
        if self._connect_fn is None:
            raise IdleError("no connection factory configured")
        last: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                connection = self._connect_fn()
                self._conn = (
                    connection if _has_idle_protocol(connection) else IMAPIdleAdapter(connection)
                )
                self._selected = None
                self._idle = False
                self._token = None
                return self._conn
            except Exception as exc:
                last = exc
                if attempt + 1 < self.max_attempts:
                    self._backoff(attempt)
        raise IdleError(
            f"reconnect failed after {self.max_attempts} attempts: {last}"
        ) from last

    def close(self) -> None:
        self._abort_idle()
        try:
            self._conn.close()
        except Exception:
            pass


def connect(
    account: Any,
    password: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    ssl_context: ssl.SSLContext | None = None,
) -> Any:
    """Open an authenticated TLS IMAP connection for IDLE use."""
    mode = getattr(account, "imap_mode", "").strip().lower()
    if mode not in ("ssl", "starttls"):
        raise IdleError("IMAP IDLE requires implicit TLS or STARTTLS")
    if not isinstance(password, str) or not password:
        raise IdleError("a password or access token is required")
    ctx = ssl_context or ssl.create_default_context()
    connection: Any = None
    try:
        if mode == "ssl":
            connection = imaplib.IMAP4_SSL(
                account.imap_host, account.imap_port, timeout=timeout, ssl_context=ctx
            )
        else:
            connection = imaplib.IMAP4(account.imap_host, account.imap_port, timeout=timeout)
            connection.starttls(ssl_context=ctx)
        connection.socket().settimeout(timeout)
        if getattr(account, "auth_method", "password").strip().lower() == "oauth2":
            token = f"user={account.username}\x01auth=Bearer {password}\x01\x01"
            connection.authenticate("XOAUTH2", lambda _: token.encode("utf-8"))
        else:
            connection.login(account.username, password)
        return connection
    except (OSError, ssl.SSLError, imaplib.IMAP4.error) as exc:
        if connection is not None:
            try:
                connection.logout()
            except Exception:
                pass
        raise IdleError(f"IDLE connection failed: {exc}") from exc
