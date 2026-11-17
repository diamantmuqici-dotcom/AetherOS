"""Aether Vault secure storage core.

On-disk format (version 2)
--------------------------
    magic       12 bytes  b"AETHERVAULT2"
    version      1 byte   2
    reserved     1 byte   0
    mem_cost     4 bytes  uint32 LE, Argon2id memory cost in KiB
    iterations   4 bytes  uint32 LE, Argon2id time cost
    parallelism  4 bytes  uint32 LE, Argon2id parallelism
    salt_len     2 bytes  uint16 LE
    nonce_len    2 bytes  uint16 LE (12)
    ct_len       8 bytes  uint64 LE
    salt         salt_len bytes, CSPRNG-generated, unique per write
    nonce        nonce_len bytes, CSPRNG-generated, unique per write
    ciphertext   ct_len bytes (ChaCha20-Poly1305, tag included)

The complete header (magic through nonce) is passed as AEAD associated data.
Any change to the version, KDF parameters, salt, or nonce invalidates the
authentication tag, so parameter downgrades and header tampering are detected.

Design rules enforced here:
  * A fresh 96-bit random nonce is generated for every encryption. Nonces are
    never derived from the password, the salt, a counter, or reused data.
  * Argon2id derives the wrapping key from the master password with a fresh
    256-bit salt on every write.
  * Plaintext is released only after ChaCha20-Poly1305 authentication succeeds.
  * Writes are atomic: a fully written and verified temp file replaces the
    target with os.replace(). The previous file is optionally kept as a backup.
  * A new ciphertext is decrypted and compared with the intended payload before
    it is allowed to replace existing data.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import struct
import tempfile
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

__all__ = [
    "Argon2Params",
    "SecureVault",
    "VaultError",
    "WrongPasswordError",
    "IntegrityError",
    "UnsupportedFormatError",
    "MigrationError",
    "encrypt_payload",
    "decrypt_payload",
    "migrate_legacy_vault",
]

MAGIC = b"AETHERVAULT2"
VERSION = 2
HEADER_STRUCT = struct.Struct("<12sBBIIIHHQ")
NONCE_LEN = 12

class VaultError(Exception):
    """Base class for all vault errors."""


class WrongPasswordError(VaultError):
    """The master password failed authentication."""


class IntegrityError(VaultError):
    """The encrypted container failed authentication or structural validation."""


class UnsupportedFormatError(VaultError):
    """The container uses an unknown magic or version."""


class MigrationError(VaultError):
    """A legacy vault could not be migrated without data loss."""


@dataclass(frozen=True)
class Argon2Params:
    memory_cost_kib: int = 65_536
    iterations: int = 3
    parallelism: int = 4
    salt_len: int = 32

    def validate(self) -> None:
        if self.memory_cost_kib < 8 * self.parallelism:
            raise ValueError("memory_cost_kib must be >= 8 * parallelism")
        if self.iterations < 1 or self.parallelism < 1:
            raise ValueError("iterations and parallelism must be >= 1")
        if self.salt_len < 16:
            raise ValueError("salt_len must be at least 16 bytes")


# Baseline for a desktop-class x86_64 machine: 64 MiB, 3 passes, 4 lanes.
# Benchmark on target hardware (VAULT.md) and store chosen values in the header
# so existing vaults keep opening after parameters change.
DEFAULT_PARAMS = Argon2Params()


def derive_key(master: str | bytes, params: Argon2Params, salt: bytes) -> bytes:
    """Derive a 256-bit wrapping key with Argon2id."""
    params.validate()
    secret = master.encode("utf-8") if isinstance(master, str) else master
    if not secret:
        raise ValueError("master password must not be empty")
    if len(salt) != params.salt_len:
        raise ValueError("salt length does not match parameters")
    kdf = Argon2id(
        salt=salt,
        length=32,
        iterations=params.iterations,
        lanes=params.parallelism,
        memory_cost=params.memory_cost_kib,
    )
    return kdf.derive(secret)


def _pack_header(params: Argon2Params, salt: bytes, nonce: bytes, ct_len: int) -> bytes:
    return HEADER_STRUCT.pack(
        MAGIC,
        VERSION,
        0,
        params.memory_cost_kib,
        params.iterations,
        params.parallelism,
        len(salt),
        len(nonce),
        ct_len,
    )


def _parse_header(blob: bytes) -> tuple[bytes, Argon2Params, bytes, bytes, bytes]:
    """Validate the container and return (aad, params, salt, nonce, ciphertext)."""
    if len(blob) < HEADER_STRUCT.size:
        raise IntegrityError("container is shorter than the header")
    fields = HEADER_STRUCT.unpack_from(blob, 0)
    magic, version, reserved, mem, iters, lanes, salt_len, nonce_len, ct_len = fields
    if magic != MAGIC:
        raise UnsupportedFormatError("not an Aether Vault container")
    if version != VERSION:
        raise UnsupportedFormatError(f"unsupported container version {version}")
    if reserved != 0 or nonce_len != NONCE_LEN:
        raise IntegrityError("invalid reserved byte or nonce length")
    if salt_len < 16 or salt_len > 64:
        raise IntegrityError("invalid salt length")
    try:
        params = Argon2Params(mem, iters, lanes, salt_len)
        params.validate()
    except ValueError as exc:
        raise IntegrityError(str(exc)) from exc
    header_len = HEADER_STRUCT.size + salt_len + nonce_len
    expected = header_len + ct_len
    if len(blob) != expected:
        raise IntegrityError("container length does not match header")
    salt = blob[HEADER_STRUCT.size : HEADER_STRUCT.size + salt_len]
    nonce = blob[HEADER_STRUCT.size + salt_len : header_len]
    ciphertext = blob[header_len:]
    return blob[:header_len], params, salt, nonce, ciphertext


def encrypt_payload(master: str | bytes, payload: dict[str, Any], params: Argon2Params | None = None) -> bytes:
    """Encrypt a JSON-serialisable payload into a version 2 container."""
    params = params or Argon2Params()
    params.validate()
    plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    salt = os.urandom(params.salt_len)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(master, params, salt)
    aad = _pack_header(params, salt, nonce, len(plaintext) + 16) + salt + nonce
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    return aad + ciphertext


def decrypt_payload(master: str | bytes, blob: bytes) -> dict[str, Any]:
    """Authenticate and decrypt a container. Never returns partial plaintext."""
    aad, params, salt, nonce, ciphertext = _parse_header(blob)
    key = derive_key(master, params, salt)
    try:
        plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise WrongPasswordError("wrong password or tampered container") from exc
    try:
        payload = json.loads(plaintext)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError("authenticated payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise IntegrityError("authenticated payload is not an object")
    return payload


def empty_payload() -> dict[str, Any]:
    return {"format": "aether-vault-records", "version": 1, "records": []}


def _fsync_dir(path: pathlib.Path) -> None:
    # Directory fsync is a POSIX durability primitive; Windows rejects opening
    # a directory handle. The target platform is Debian, where this always runs.
    if os.name == "nt":
        return
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: pathlib.Path, data: bytes) -> None:
    """Durably replace path with data, or leave path untouched on any failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class SecureVault:
    """Password-protected, integrity-checked local vault."""

    def __init__(self, path: pathlib.Path | str, master: str, params: Argon2Params | None = None):
        self.path = pathlib.Path(path)
        self.master = master
        self.params = params or Argon2Params()
        self.backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        self._payload: dict[str, Any] | None = None

    # -- lifecycle ---------------------------------------------------------
    def exists(self) -> bool:
        return self.path.is_file()

    def create(self, overwrite: bool = False) -> None:
        if self.exists() and not overwrite:
            raise VaultError("vault already exists")
        payload = empty_payload()
        blob = encrypt_payload(self.master, payload, self.params)
        if decrypt_payload(self.master, blob) != payload:  # verify before committing
            raise IntegrityError("new container failed self-verification")
        _atomic_write(self.path, blob)

    def unlock(self) -> dict[str, Any]:
        blob = self.path.read_bytes()
        self._payload = decrypt_payload(self.master, blob)
        return self._payload

    def lock(self) -> None:
        self._payload = None

    @property
    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            raise VaultError("vault is locked")
        return self._payload

    def save(self) -> None:
        """Persist the in-memory payload atomically, keeping a verified backup."""
        payload = self.payload
        old = self.path.read_bytes() if self.exists() else None
        new_blob = encrypt_payload(self.master, payload, self.params)
        if decrypt_payload(self.master, new_blob) != payload:
            raise IntegrityError("new container failed self-verification")
        if old is not None:
            decrypt_payload(self.master, old)  # never back up an unreadable container
            _atomic_write(self.backup_path, old)
        _atomic_write(self.path, new_blob)

    def change_password(self, new_master: str) -> None:
        if not new_master:
            raise ValueError("new master password must not be empty")
        payload = self.payload
        old = self.path.read_bytes()
        new_blob = encrypt_payload(new_master, payload, self.params)
        if decrypt_payload(new_master, new_blob) != payload:
            raise IntegrityError("new container failed self-verification")
        _atomic_write(self.backup_path, old)
        _atomic_write(self.path, new_blob)
        self.master = new_master

    # -- records -----------------------------------------------------------
    def add(self, record: dict[str, Any]) -> int:
        records = self.payload.setdefault("records", [])
        records.append(record)
        return len(records) - 1

    def delete(self, index: int) -> None:
        records = self.payload["records"]
        if not 0 <= index < len(records):
            raise IndexError("record index out of range")
        del records[index]

    def search(self, needle: str) -> list[dict[str, Any]]:
        needle = needle.casefold()
        return [
            r
            for r in self.payload.get("records", [])
            if any(needle in str(v).casefold() for v in r.values() if isinstance(v, (str, int)))
        ]

    # -- backup / restore --------------------------------------------------
    def restore_backup(self) -> None:
        if not self.backup_path.is_file():
            raise VaultError("no backup available")
        backup = self.backup_path.read_bytes()
        payload = decrypt_payload(self.master, backup)
        current = self.path.read_bytes() if self.exists() else b""
        _atomic_write(self.path.with_suffix(self.path.suffix + ".pre-restore"), current)
        _atomic_write(self.path, backup)
        self._payload = payload

    def export(self, destination: pathlib.Path | str) -> None:
        """Export the authenticated container bytes verbatim."""
        data = self.path.read_bytes()
        decrypt_payload(self.master, data)
        _atomic_write(pathlib.Path(destination), data)

    def import_container(self, source: pathlib.Path | str) -> None:
        data = pathlib.Path(source).read_bytes()
        payload = decrypt_payload(self.master, data)
        if self.exists():
            _atomic_write(self.backup_path, self.path.read_bytes())
        _atomic_write(self.path, data)
        self._payload = payload


# ---------------------------------------------------------------------------
# Migration from the legacy (v1) format.
# ---------------------------------------------------------------------------
def _legacy_derive(master: str, salt: bytes, layers: int = 5) -> bytes:
    """Reproduce the v1 PBKDF2 chain exactly so old vaults remain readable."""
    key = master.encode()
    for _ in range(layers):
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=200_000,
        )
        key = kdf.derive(base64.b64encode(key))
    return key[:32]


def migrate_legacy_vault(
    master: str,
    legacy_path: pathlib.Path | str,
    new_path: pathlib.Path | str,
    params: Argon2Params | None = None,
) -> dict[str, Any]:
    """Migrate a v1 vault to v2 without deleting or overwriting the original.

    The legacy file is renamed to ``*.v1`` only after the new container has been
    written and decrypted successfully. If anything fails, both files remain.
    """
    legacy = pathlib.Path(legacy_path)
    target = pathlib.Path(new_path)
    raw = legacy.read_bytes()
    if len(raw) < 28:
        raise MigrationError("legacy container is too short")
    salt, ct = raw[:16], raw[16:]
    key = _legacy_derive(master, salt)
    try:
        plaintext = ChaCha20Poly1305(key).decrypt(b"\x00" * 12, ct, salt)
        data = json.loads(plaintext)
    except (InvalidTag, ValueError, json.JSONDecodeError) as exc:
        raise MigrationError("legacy container could not be decrypted") from exc
    if not isinstance(data, dict):
        raise MigrationError("legacy payload is not an object")

    payload = empty_payload()
    payload["records"] = list(data.get("passwords", []))
    payload["history"] = list(data.get("history", []))
    payload["migrated_from"] = "v1"

    new_blob = encrypt_payload(master, payload, params or Argon2Params())
    if decrypt_payload(master, new_blob) != payload:
        raise MigrationError("new container failed verification; original left intact")
    if target.exists():
        raise MigrationError("target already exists; refusing to overwrite")
    _atomic_write(target, new_blob)
    if decrypt_payload(master, target.read_bytes()) != payload:
        raise MigrationError("on-disk container failed verification")

    archived = legacy.with_suffix(legacy.suffix + ".v1")
    if not archived.exists():
        legacy.rename(archived)
    return {"target": str(target), "records": len(payload["records"]), "legacy_backup": str(archived)}
