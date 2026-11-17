"""Keyfile support for the Aether Vault second factor."""

from __future__ import annotations

import os
import pathlib
import stat
import tempfile
from typing import NamedTuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

__all__ = [
    "KeyfileError",
    "LoadedKeyfile",
    "SUPPORTED_KEY_BYTES",
    "DOMAIN_SALT",
    "generate_keyfile",
    "load_keyfile",
    "combine_passphrase_keyfile",
]

SUPPORTED_KEY_BYTES = frozenset({16, 24, 32, 64})
KEYFILE_MODE = 0o600
DOMAIN_SALT = b"aether-vault/keyfile-combine/v1\n"
_INFO = b"aether-vault factor binding v1"


class KeyfileError(Exception):
    """A keyfile failed structural validation."""


class LoadedKeyfile(NamedTuple):
    key: bytes
    perms_ok: bool


def _permissions_ok(mode: int) -> bool:
    """True for a regular file with no group/other permission bits set."""
    return bool(stat.S_ISREG(mode)) and (stat.S_IMODE(mode) & 0o077) == 0


def _atomic_write(target: pathlib.Path, key: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    tmp = pathlib.Path(tmp_name)
    try:
        os.chmod(tmp_name, KEYFILE_MODE)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, KEYFILE_MODE)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def generate_keyfile(path: pathlib.Path | str, bits: int = 256, *, force: bool = False) -> None:
    """Write a fresh CSPRNG keyfile atomically, never clobbering an existing one."""
    if bits % 8 or bits // 8 not in SUPPORTED_KEY_BYTES:
        raise ValueError(f"bits must yield one of {sorted(SUPPORTED_KEY_BYTES)} bytes")
    target = pathlib.Path(path)
    if target.exists() and not force:
        raise FileExistsError(f"keyfile already exists: {target}")
    _atomic_write(target, os.urandom(bits // 8))


def load_keyfile(path: pathlib.Path | str, max_bytes: int = 4096) -> LoadedKeyfile:
    """Load and validate a keyfile; report loose perms via ``perms_ok``."""
    if max_bytes < min(SUPPORTED_KEY_BYTES):
        raise ValueError("max_bytes is below the smallest supported key size")
    source = pathlib.Path(path)
    with source.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise KeyfileError("keyfile exceeds max_bytes")
    if len(data) not in SUPPORTED_KEY_BYTES:
        raise KeyfileError("keyfile length is not a supported key size")
    info = source.stat()
    if not stat.S_ISREG(info.st_mode):
        raise KeyfileError("keyfile is not a regular file")
    return LoadedKeyfile(data, _permissions_ok(info.st_mode))


def _hkdf(passphrase: bytes, keyfile: bytes, salt: bytes, info: bytes) -> bytes:
    if not isinstance(passphrase, (bytes, bytearray)) or not isinstance(keyfile, (bytes, bytearray)):
        raise TypeError("passphrase and keyfile must be bytes")
    secret = bytes(passphrase)
    material = bytes(keyfile)
    if not secret:
        raise ValueError("passphrase must not be empty")
    if len(material) not in SUPPORTED_KEY_BYTES:
        raise ValueError("keyfile length is not a supported key size")
    # Length prefixes bind both factors without delimiter ambiguity.
    ikm = (
        len(secret).to_bytes(4, "big")
        + secret
        + len(material).to_bytes(4, "big")
        + material
    )
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(ikm)


def combine_passphrase_keyfile(passphrase: bytes, keyfile: bytes) -> bytes:
    """Derive a 256-bit vault factor from passphrase + keyfile via HKDF-SHA256."""
    return _hkdf(passphrase, keyfile, DOMAIN_SALT, _INFO)
