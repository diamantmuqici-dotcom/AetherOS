#!/usr/bin/env python3
"""Build reproducible release metadata and checksums for an AetherOS ISO."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.update.signature import (  # noqa: E402
    SignatureError,
    canonical_signing_input,
    sign_release,
)

METADATA_SCHEMA = "aether-release-metadata/1"
DEFAULT_PRODUCT = "AetherOS"
DEFAULT_VERSION = "1.0"
_CHUNK_SIZE = 1024 * 1024
_MAX_KEY_BYTES = 64 * 1024
_ED25519_SIG_LEN = 64


def sha256_file(path: pathlib.Path) -> str:
    """Hash a file in bounded chunks so large ISOs never buffer whole."""
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def resolve_timestamp(explicit: str | None) -> str:
    """Return a UTC Z timestamp; SOURCE_DATE_EPOCH gives reproducible builds."""
    if explicit:
        text = explicit.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid --timestamp: {explicit!r}") from exc
        if moment.tzinfo is None:
            raise ValueError("--timestamp must carry a UTC offset")
        moment = moment.astimezone(timezone.utc)
    else:
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        if epoch is not None:
            try:
                moment = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
            except ValueError as exc:
                raise ValueError(f"invalid SOURCE_DATE_EPOCH: {epoch!r}") from exc
        else:
            moment = datetime.now(timezone.utc)
    return moment.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def sign_payload(payload: dict, key: pathlib.Path) -> str:
    """Sign canonical JSON of every field except 'signature'."""
    unsigned = {name: value for name, value in payload.items() if name != "signature"}
    raw = sign_release(unsigned, key)
    return base64.b64encode(raw).decode("ascii")


def verify_metadata(payload: object, public_key_path: pathlib.Path) -> bool:
    """Fail closed unless status is signed and the canonical bytes verify."""
    if not isinstance(payload, dict) or payload.get("status") != "signed":
        return False
    encoded = payload.get("signature")
    if not isinstance(encoded, str):
        return False
    try:
        signature = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return False
    if len(signature) != _ED25519_SIG_LEN:
        return False
    try:
        key_bytes = pathlib.Path(public_key_path).read_bytes()[:_MAX_KEY_BYTES + 1]
        if len(key_bytes) > _MAX_KEY_BYTES:
            return False
        public_key = serialization.load_pem_public_key(key_bytes)
        if not isinstance(public_key, Ed25519PublicKey):
            return False
        unsigned = {name: value for name, value in payload.items() if name != "signature"}
        public_key.verify(signature, canonical_signing_input(unsigned))
    except Exception:  # any malformed key or failed verify is a non-verifiable artifact
        return False
    return True


def build_metadata(
    iso_path: pathlib.Path,
    *,
    timestamp: str,
    product: str = DEFAULT_PRODUCT,
    version: str = DEFAULT_VERSION,
    key: pathlib.Path | None = None,
) -> dict:
    """Build one metadata dict; 'signature' is null and status unsigned without a key."""
    iso = pathlib.Path(iso_path)
    if not iso.is_file():
        raise FileNotFoundError(f"ISO not found: {iso}")
    payload = {
        "schema": METADATA_SCHEMA,
        "product": product,
        "version": version,
        "timestamp": timestamp,
        "status": "signed" if key is not None else "unsigned",
        "iso": {
            "filename": iso.name,
            "size": iso.stat().st_size,
            "sha256": sha256_file(iso),
        },
        "signature": None,
    }
    if key is not None:
        payload["signature"] = sign_payload(payload, pathlib.Path(key))
    return payload


def write_outputs(out_dir: pathlib.Path, metadata: dict) -> tuple[pathlib.Path, pathlib.Path]:
    """Write canonical JSON plus a coreutils-format SHA256SUMS for the ISO."""
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta_path = out / "release-metadata.json"
    sums_path = out / "SHA256SUMS"
    meta_path.write_bytes(canonical_signing_input(metadata) + b"\n")
    iso = metadata["iso"]
    sums_path.write_text(f"{iso['sha256']}  {iso['filename']}\n", encoding="utf-8")
    return meta_path, sums_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit canonical, optionally signed AetherOS release metadata.",
        allow_abbrev=False,
    )
    parser.add_argument("--iso", required=True, help="path to the built ISO")
    parser.add_argument("--out", required=True, help="output directory for release artifacts")
    parser.add_argument("--key", default=None, help="Ed25519 private key PEM; omit for unsigned metadata")
    parser.add_argument("--product", default=DEFAULT_PRODUCT, help="product name")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="product version")
    parser.add_argument("--timestamp", default=None, help="explicit UTC ISO-8601 timestamp")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        timestamp = resolve_timestamp(args.timestamp)
        metadata = build_metadata(
            args.iso,
            timestamp=timestamp,
            product=args.product,
            version=args.version,
            key=args.key,
        )
        meta_path, sums_path = write_outputs(args.out, metadata)
    except (SignatureError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{meta_path}\n{sums_path}\nstatus={metadata['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
