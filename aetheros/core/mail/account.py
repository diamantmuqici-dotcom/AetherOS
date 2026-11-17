"""Account model and on-disk account registry for Aether Mail.

The registry holds metadata only. Passwords and OAuth tokens live in the
credential backend (core.mail.credentials) and never in this JSON file.
"""

from __future__ import annotations

import ipaddress
import json
import os
import pathlib
import re
import tempfile
from dataclasses import dataclass
from typing import Any

TLS_MODES = frozenset({"ssl", "starttls"})
AUTH_METHODS = frozenset({"password", "oauth2"})
INSECURE_MODES = frozenset({"", "none", "plain", "cleartext", "off"})

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class AccountError(ValueError):
    """An account description is invalid or incomplete."""


def default_accounts_path() -> pathlib.Path:
    root = os.environ.get("XDG_CONFIG_HOME") or str(pathlib.Path.home() / ".config")
    return pathlib.Path(root) / "aether" / "mail" / "accounts.json"


def _validate_host(value: Any, label: str) -> None:
    if not isinstance(value, str) or not (1 <= len(value) <= 253):
        raise AccountError(f"{label} must be a hostname or IP of 1..253 characters")
    if any(ord(ch) < 0x20 or ch.isspace() for ch in value):
        raise AccountError(f"{label} contains whitespace or control characters")
    try:
        ipaddress.ip_address(value)
        return
    except ValueError:
        pass
    labels = value.rstrip(".").split(".")
    if not labels or len(labels) > 127:
        raise AccountError(f"{label} has too many DNS labels")
    for part in labels:
        if not part or len(part) > 63 or not _LABEL_RE.fullmatch(part):
            raise AccountError(f"{label} is not a valid hostname")


def _validate_port(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AccountError(f"{label} must be an integer")
    if not 1 <= value <= 65535:
        raise AccountError(f"{label} must be in 1..65535")


@dataclass(frozen=True)
class Account:
    id: str
    email: str
    imap_host: str
    imap_port: int
    imap_tls: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    username: str
    auth_method: str = "password"

    def validate(self) -> "Account":
        if not isinstance(self.id, str) or not _ID_RE.fullmatch(self.id):
            raise AccountError("id must be 1..128 characters of [A-Za-z0-9._-]")
        if not isinstance(self.email, str) or len(self.email) > 254 or not _EMAIL_RE.fullmatch(self.email):
            raise AccountError("email is not a valid address")
        _validate_host(self.imap_host, "imap_host")
        _validate_host(self.smtp_host, "smtp_host")
        _validate_port(self.imap_port, "imap_port")
        _validate_port(self.smtp_port, "smtp_port")

        imap_mode = self.imap_tls.strip().lower() if isinstance(self.imap_tls, str) else ""
        smtp_mode = self.smtp_security.strip().lower() if isinstance(self.smtp_security, str) else ""
        if imap_mode in INSECURE_MODES or smtp_mode in INSECURE_MODES:
            raise AccountError("cleartext IMAP/SMTP transport is not allowed")
        if imap_mode not in TLS_MODES or smtp_mode not in TLS_MODES:
            raise AccountError("imap_tls and smtp_security must be 'ssl' or 'starttls'")

        method = self.auth_method.strip().lower() if isinstance(self.auth_method, str) else ""
        if method not in AUTH_METHODS:
            raise AccountError("auth_method must be 'password' or 'oauth2'")
        if method == "password" and (imap_mode not in TLS_MODES or smtp_mode not in TLS_MODES):
            raise AccountError("password authentication requires TLS on both transports")
        if not isinstance(self.username, str) or not (1 <= len(self.username) <= 256):
            raise AccountError("username must be 1..256 characters")
        if any(ord(ch) < 0x20 for ch in self.username):
            raise AccountError("username contains control characters")
        return self

    @property
    def imap_mode(self) -> str:
        return self.imap_tls.strip().lower()

    @property
    def smtp_mode(self) -> str:
        return self.smtp_security.strip().lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "imap_tls": self.imap_tls,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_security": self.smtp_security,
            "username": self.username,
            "auth_method": self.auth_method,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Account":
        if not isinstance(data, dict):
            raise AccountError("account entry must be an object")
        keys = (
            "id", "email", "imap_host", "imap_port", "imap_tls",
            "smtp_host", "smtp_port", "smtp_security", "username",
        )
        missing = [key for key in keys if key not in data]
        if missing:
            raise AccountError(f"account is missing fields: {', '.join(missing)}")
        return cls(
            id=data["id"],
            email=data["email"],
            imap_host=data["imap_host"],
            imap_port=data["imap_port"],
            imap_tls=data["imap_tls"],
            smtp_host=data["smtp_host"],
            smtp_port=data["smtp_port"],
            smtp_security=data["smtp_security"],
            username=data["username"],
            auth_method=data.get("auth_method", "password"),
        ).validate()


def _atomic_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".accounts.", dir=str(path.parent))
    tmp = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class AccountStore:
    """JSON account registry with 0600 permissions and fail-closed loading."""

    def __init__(self, path: pathlib.Path | str | None = None):
        self.path = pathlib.Path(path) if path is not None else default_accounts_path()
        self.max_accounts = 256

    def load(self) -> list[Account]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AccountError("account registry is unreadable") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("accounts"), list):
            raise AccountError("account registry has an invalid shape")
        entries = raw["accounts"]
        if len(entries) > self.max_accounts:
            raise AccountError("account registry exceeds the account limit")
        return [Account.from_dict(entry) for entry in entries]

    def save(self, accounts: list[Account]) -> None:
        if len(accounts) > self.max_accounts:
            raise AccountError("too many accounts")
        validated = [account.validate() for account in accounts]
        seen: set[str] = set()
        for account in validated:
            if account.id in seen:
                raise AccountError(f"duplicate account id: {account.id}")
            seen.add(account.id)
        _atomic_json(self.path, {"format": "aether-mail-accounts", "version": 1, "accounts": [a.to_dict() for a in validated]})

    def add(self, account: Account) -> None:
        accounts = self.load()
        if any(existing.id == account.id for existing in accounts):
            raise AccountError(f"account already exists: {account.id}")
        accounts.append(account)
        self.save(accounts)

    def get(self, account_id: str) -> Account | None:
        for account in self.load():
            if account.id == account_id:
                return account
        return None

    def remove(self, account_id: str) -> bool:
        accounts = self.load()
        remaining = [account for account in accounts if account.id != account_id]
        if len(remaining) == len(accounts):
            return False
        self.save(remaining)
        return True
