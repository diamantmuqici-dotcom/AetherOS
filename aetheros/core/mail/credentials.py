"""Credential storage for Aether Mail.

SecretService (libsecret over D-Bus) is preferred when available.  The
fallback is an Argon2id + ChaCha20-Poly1305 container written with 0600
permissions, reusing the authenticated container format of core.vault.
No plaintext password is ever written to disk.
"""

from __future__ import annotations

import os
import pathlib
import re
import tempfile
from typing import Any

from ..vault.secure_vault import (
    Argon2Params,
    VaultError,
    decrypt_payload,
    encrypt_payload,
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_SECRET_CHARS = 4096


class CredentialError(Exception):
    """Base class for credential backend failures."""


class LockedError(CredentialError):
    """Credential access was attempted while locked."""


class BackendUnavailableError(CredentialError):
    """No usable credential backend is available."""


def default_credentials_path() -> pathlib.Path:
    root = os.environ.get("XDG_DATA_HOME") or str(pathlib.Path.home() / ".local" / "share")
    return pathlib.Path(root) / "aether" / "mail" / "credentials.enc"


def _check_id(account_id: Any) -> str:
    if not isinstance(account_id, str) or not _ID_RE.fullmatch(account_id):
        raise CredentialError("account_id must be 1..128 characters of [A-Za-z0-9._-]")
    return account_id


def _check_secret(secret: Any) -> str:
    if not isinstance(secret, str) or not secret:
        raise CredentialError("secret must be a non-empty string")
    if len(secret) > _MAX_SECRET_CHARS:
        raise CredentialError("secret exceeds the maximum length")
    if any(ord(ch) < 0x20 for ch in secret):
        raise CredentialError("secret contains control characters")
    return secret


def _load_secret_module() -> Any:
    try:
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
        return Secret
    except Exception:
        return None


def secret_service_available() -> bool:
    return _load_secret_module() is not None


def _atomic_write(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".credentials.", dir=str(path.parent))
    tmp = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class _EncryptedFileBackend:
    name = "encrypted-file"

    def __init__(self, path: pathlib.Path, params: Argon2Params):
        self.path = path
        self.params = params
        self._secrets: dict[str, str] = {}
        self._passphrase: str | None = None

    def unlock(self, passphrase: str | None) -> None:
        if not isinstance(passphrase, str) or not passphrase:
            raise CredentialError("a passphrase is required for the local credential store")
        if self.path.exists():
            payload = decrypt_payload(passphrase, self.path.read_bytes())
            stored = payload.get("secrets")
            if not isinstance(stored, dict):
                raise VaultError("credential container has an invalid shape")
            self._secrets = {str(k): str(v) for k, v in stored.items() if isinstance(k, str) and isinstance(v, str)}
        else:
            self._secrets = {}
        self._passphrase = passphrase

    def lock(self) -> None:
        self._secrets.clear()
        self._passphrase = None

    def _save(self) -> None:
        if self._passphrase is None:
            raise LockedError("credential store is locked")
        payload: dict[str, Any] = {
            "format": "aether-mail-credentials",
            "version": 1,
            "secrets": dict(self._secrets),
        }
        blob = encrypt_payload(self._passphrase, payload, self.params)
        if decrypt_payload(self._passphrase, blob) != payload:
            raise VaultError("new credential container failed self-verification")
        _atomic_write(self.path, blob)

    def store(self, account_id: str, secret: str) -> None:
        self._secrets[_check_id(account_id)] = _check_secret(secret)
        self._save()

    def get(self, account_id: str) -> str | None:
        return self._secrets.get(_check_id(account_id))

    def delete(self, account_id: str) -> bool:
        existed = _check_id(account_id) in self._secrets
        if existed:
            del self._secrets[account_id]
            self._save()
        return existed


class _SecretServiceBackend:
    name = "secret-service"

    def __init__(self, secret_module: Any):
        self.secret = secret_module
        try:
            self.schema = secret_module.Schema.new(
                "org.aetheros.mail.account",
                {"account_id": secret_module.SchemaAttributeType.STRING},
                secret_module.SchemaFlags.NONE,
            )
        except Exception as exc:
            raise BackendUnavailableError(f"SecretService schema setup failed: {exc}") from exc

    def unlock(self, passphrase: str | None) -> None:
        try:
            service = self.secret.Service.get_sync(self.secret.ServiceFlags.LOAD_COLLECTIONS, None)
            collection = service.get_default_collection()
            if collection is not None and collection.get_locked():
                service.unlock_sync([collection], None)
        except Exception:
            # A locked keyring surfaces on the first lookup; that is handled there.
            pass

    def lock(self) -> None:
        # Keyring sessions are managed by the daemon; the app-level gate is
        # CredentialStore._unlocked.
        return None

    def store(self, account_id: str, secret: str) -> None:
        _check_id(account_id)
        _check_secret(secret)
        try:
            self.secret.password_store_sync(
                self.schema,
                {"account_id": account_id},
                self.secret.COLLECTION_DEFAULT,
                f"Aether Mail: {account_id}",
                secret,
                None,
            )
        except Exception as exc:
            raise CredentialError(f"SecretService store failed: {exc}") from exc

    def get(self, account_id: str) -> str | None:
        _check_id(account_id)
        try:
            value = self.secret.password_lookup_sync(self.schema, {"account_id": account_id}, None)
        except Exception as exc:
            raise CredentialError(f"SecretService lookup failed: {exc}") from exc
        return value if isinstance(value, str) and value else None

    def delete(self, account_id: str) -> bool:
        _check_id(account_id)
        try:
            return bool(self.secret.password_clear_sync(self.schema, {"account_id": account_id}, None))
        except Exception as exc:
            raise CredentialError(f"SecretService delete failed: {exc}") from exc


class CredentialStore:
    """Passphrase-gated credential access with a keyring-first backend."""

    def __init__(
        self,
        path: pathlib.Path | str | None = None,
        passphrase: str | None = None,
        prefer_secret_service: bool = True,
        params: Argon2Params | None = None,
    ):
        self.path = pathlib.Path(path) if path is not None else default_credentials_path()
        self.prefer_secret_service = bool(prefer_secret_service)
        self.params = params or Argon2Params()
        self.params.validate()
        self._backend: Any = None
        self._unlocked = False
        if passphrase is not None:
            self.unlock(passphrase)

    @property
    def unlocked(self) -> bool:
        return self._unlocked

    @property
    def backend_name(self) -> str:
        return self._backend.name if self._backend is not None else "none"

    def unlock(self, passphrase: str | None, *, prefer_secret_service: bool | None = None) -> None:
        prefer = self.prefer_secret_service if prefer_secret_service is None else bool(prefer_secret_service)
        backend: Any = None
        if prefer:
            module = _load_secret_module()
            if module is not None:
                try:
                    backend = _SecretServiceBackend(module)
                    backend.unlock(passphrase)
                except Exception:
                    backend = None
        if backend is None:
            backend = _EncryptedFileBackend(self.path, self.params)
            backend.unlock(passphrase)
        self._backend = backend
        self._unlocked = True

    def lock(self) -> None:
        if self._backend is not None:
            self._backend.lock()
        self._unlocked = False

    def _require_unlocked(self) -> Any:
        if not self._unlocked or self._backend is None:
            raise LockedError("credential store is locked")
        return self._backend

    def store(self, account_id: str, secret: str) -> None:
        self._require_unlocked().store(account_id, secret)

    def get(self, account_id: str) -> str | None:
        return self._require_unlocked().get(account_id)

    def delete(self, account_id: str) -> bool:
        return self._require_unlocked().delete(account_id)
