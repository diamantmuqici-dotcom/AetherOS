"""IMAP retrieval with implicit TLS or STARTTLS and hard fetch caps."""

from __future__ import annotations

import imaplib
import re
import ssl
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from typing import Any

from .account import Account

MAX_HEADERS = 200
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_FETCH_BYTES = MAX_BODY_BYTES + 64 * 1024
DEFAULT_TIMEOUT = 30
_LIST_RE = re.compile(r'^\((?P<attrs>[^)]*)\)\s+"(?P<delim>.)"\s+(?P<name>.*)$')


class MailSyncError(Exception):
    """Base class for IMAP failures."""


class AuthError(MailSyncError):
    """IMAP authentication failed."""


class FetchError(MailSyncError):
    """A folder listing or message fetch failed."""


def _decode_header(value: Any) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(str(value))))
    except Exception:
        return str(value)[:512]


def _bounded_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise FetchError("limit must be an integer")
    if limit < 1:
        raise FetchError("limit must be at least 1")
    return min(limit, MAX_HEADERS)


def _first_bytes(data: Any) -> bytes:
    for item in data or ():
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
            return bytes(item[1])
    return b""


def _extract_plain(message: Any) -> tuple[str, bool]:
    chunks: list[str] = []
    total = 0
    truncated = False
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_type() != "text/plain":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, "replace")
        room = MAX_BODY_BYTES - total
        if room <= 0:
            truncated = True
            break
        if len(text) > room:
            text = text[:room]
            truncated = True
        chunks.append(text)
        total += len(text)
    return "".join(chunks), truncated


class IMAPMail:
    """Read-only IMAP session. Use as a context manager."""

    def __init__(
        self,
        account: Account,
        password: str,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        ssl_context: ssl.SSLContext | None = None,
    ):
        account.validate()
        mode = account.imap_mode
        if mode not in ("ssl", "starttls"):
            raise MailSyncError("IMAP requires implicit TLS or STARTTLS")
        if not isinstance(password, str) or not password:
            raise AuthError("a password or access token is required")
        ctx = ssl_context or ssl.create_default_context()
        try:
            if mode == "ssl":
                self._conn = imaplib.IMAP4_SSL(
                    account.imap_host, account.imap_port, timeout=timeout, ssl_context=ctx
                )
            else:
                self._conn = imaplib.IMAP4(account.imap_host, account.imap_port, timeout=timeout)
                self._conn.starttls(ssl_context=ctx)
            self._conn.socket().settimeout(timeout)
        except (OSError, ssl.SSLError, imaplib.IMAP4.error) as exc:
            if getattr(self, "_conn", None) is not None:
                try:
                    self._conn.logout()
                except Exception:
                    pass
            raise MailSyncError(f"IMAP connection failed: {exc}") from exc
        try:
            if account.auth_method.strip().lower() == "oauth2":
                token = f"user={account.username}\x01auth=Bearer {password}\x01\x01"
                self._conn.authenticate("XOAUTH2", lambda _: token.encode("utf-8"))
            else:
                self._conn.login(account.username, password)
        except imaplib.IMAP4.error as exc:
            self.close()
            raise AuthError(f"IMAP authentication failed: {exc}") from exc

    def __enter__(self) -> "IMAPMail":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._conn.logout()
        except Exception:
            pass

    def list_folders(self) -> list[dict[str, Any]]:
        typ, data = self._conn.list()
        if typ != "OK":
            raise FetchError("IMAP LIST failed")
        folders: list[dict[str, Any]] = []
        for raw in (data or ())[: MAX_HEADERS * 2]:
            if not isinstance(raw, (bytes, bytearray)):
                continue
            match = _LIST_RE.match(bytes(raw).decode("utf-8", "replace"))
            if not match:
                continue
            name = match.group("name").strip().strip('"')
            if not name:
                continue
            folders.append({
                "name": name,
                "attributes": match.group("attrs").split(),
                "delimiter": match.group("delim"),
            })
        return folders

    def fetch_headers(self, limit: int = MAX_HEADERS, mailbox: str = "INBOX") -> list[dict[str, Any]]:
        count = _bounded_limit(limit)
        typ, _ = self._conn.select(mailbox, readonly=True)
        if typ != "OK":
            raise FetchError(f"could not select mailbox {mailbox!r}")
        typ, data = self._conn.search(None, "ALL")
        if typ != "OK":
            raise FetchError("IMAP SEARCH failed")
        raw_uids = data[0].split() if data and data[0] else []
        uids = [int(value) for value in raw_uids if value.isdigit()][-count:]
        uids.reverse()
        headers: list[dict[str, Any]] = []
        for uid in uids:
            typ, part = self._conn.fetch(
                str(uid), "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE MESSAGE-ID)])"
            )
            if typ != "OK":
                continue
            raw = _first_bytes(part)
            if not raw:
                continue
            message = BytesParser(policy=policy.default).parsebytes(raw)
            headers.append({
                "uid": uid,
                "subject": _decode_header(message.get("Subject")),
                "from": _decode_header(message.get("From")),
                "to": _decode_header(message.get("To")),
                "date": _decode_header(message.get("Date")),
                "message_id": _decode_header(message.get("Message-ID")),
            })
        return headers

    def fetch_body(self, uid: int, mailbox: str = "INBOX") -> dict[str, Any]:
        if isinstance(uid, bool) or not isinstance(uid, int) or not 1 <= uid <= 0xFFFFFFFF:
            raise FetchError("uid must be a positive integer")
        typ, _ = self._conn.select(mailbox, readonly=True)
        if typ != "OK":
            raise FetchError(f"could not select mailbox {mailbox!r}")
        typ, data = self._conn.fetch(str(uid), f"(BODY.PEEK[]<0.{MAX_FETCH_BYTES}>)")
        if typ != "OK":
            raise FetchError(f"could not fetch uid {uid}")
        raw = _first_bytes(data)
        if not raw:
            return {"uid": uid, "body": "", "truncated": False}
        truncated = len(raw) >= MAX_FETCH_BYTES
        message = BytesParser(policy=policy.default).parsebytes(raw[:MAX_FETCH_BYTES])
        body, part_truncated = _extract_plain(message)
        return {"uid": uid, "body": body, "truncated": truncated or part_truncated}
