"""Ed25519 verification for signed AetherOS release manifests.

The signature covers the canonical JSON form of the manifest payload, so key
order and whitespace in the transported file never change what is verified.
Only a payload that passes signature, schema and expiry checks is returned.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

__all__ = [
    "SignatureError",
    "SCHEMA_VERSION",
    "MAX_MANIFEST_BYTES",
    "canonical_signing_input",
    "sign_release",
    "verify_release",
]

SCHEMA_VERSION = "aether-release/1"
MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_KEY_BYTES = 64 * 1024
_MAX_SIG_BYTES = 4096
_ED25519_SIG_LEN = 64


class SignatureError(Exception):
    """Raised on any failure to verify or produce a signed release."""


def _read_bounded(path, limit: int) -> bytes:
    p = pathlib.Path(path)
    # Read one byte past the cap so oversized files are rejected without buffering them.
    try:
        with p.open("rb") as fh:
            data = fh.read(limit + 1)
    except OSError as exc:
        raise SignatureError(f"cannot read {p}: {exc}") from exc
    if len(data) > limit:
        raise SignatureError(f"input exceeds {limit} bytes: {p}")
    return data


def canonical_signing_input(payload: dict) -> bytes:
    """Deterministic bytes signed by sign_release and checked by verify_release."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _parse_expires(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SignatureError("missing 'expires'")
    text = value.strip()
    # fromisoformat handles 'Z' on 3.11+; normalize for older runtimes as well.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SignatureError("malformed 'expires'") from exc
    if moment.tzinfo is None:
        raise SignatureError("'expires' must carry a UTC offset")
    return moment.astimezone(timezone.utc)


def verify_release(manifest_bytes: bytes, signature_path, public_key_path) -> dict:
    """Verify a signed manifest and return its payload; raise SignatureError on any failure."""
    if not isinstance(manifest_bytes, (bytes, bytearray)):
        raise SignatureError("manifest must be bytes")
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise SignatureError("manifest exceeds 1 MiB")

    try:
        payload = json.loads(bytes(manifest_bytes).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SignatureError("manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise SignatureError("manifest root must be an object")

    signature = _read_bounded(signature_path, _MAX_SIG_BYTES)
    if len(signature) != _ED25519_SIG_LEN:
        raise SignatureError("signature length is invalid")

    key_bytes = _read_bounded(public_key_path, _MAX_KEY_BYTES)
    try:
        public_key = serialization.load_pem_public_key(key_bytes)
    except Exception as exc:  # backend raises several distinct PEM errors
        raise SignatureError("public key is not valid PEM") from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise SignatureError("public key is not Ed25519")

    # Verify before trusting any field, so only authenticated bytes are interpreted.
    try:
        public_key.verify(signature, canonical_signing_input(payload))
    except InvalidSignature as exc:
        raise SignatureError("signature does not match manifest") from exc

    if payload.get("schema") != SCHEMA_VERSION:
        raise SignatureError(f"unsupported schema: {payload.get('schema')!r}")

    expires = _parse_expires(payload.get("expires"))
    if expires <= datetime.now(timezone.utc):
        raise SignatureError("release manifest has expired")

    return payload


def sign_release(payload: dict, private_key_path) -> bytes:
    """Sign the canonical form of a release payload with an Ed25519 private key."""
    if not isinstance(payload, dict):
        raise SignatureError("payload must be a dict")
    key_bytes = _read_bounded(private_key_path, _MAX_KEY_BYTES)
    try:
        private_key = serialization.load_pem_private_key(key_bytes, password=None)
    except Exception as exc:  # backend raises several distinct PEM errors
        raise SignatureError("private key is not valid PEM") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise SignatureError("private key is not Ed25519")
    try:
        return private_key.sign(canonical_signing_input(payload))
    except (TypeError, ValueError) as exc:
        raise SignatureError("payload is not canonicalizable") from exc
