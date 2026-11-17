"""Canonical, bounded backup snapshot manifests with optional Ed25519 signing.

A manifest is a canonical JSON document describing every backed-up file by
relative path, byte size, SHA-256, mtime and type. Verification is fail-closed:
a tampered manifest, a changed file, or any extra/missing file is reported as a
discrepancy. Signing is optional; when a signing key is present the digest of
the canonical payload is recorded and signed with Ed25519.

The Ed25519 canonicalization primitive is reused from core.update.signature;
that module is never modified here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
from datetime import datetime, timezone
from pathlib import PurePosixPath

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from core.update.signature import canonical_signing_input

__all__ = [
    "SCHEMA_VERSION",
    "MANIFEST_NAME",
    "MAX_MANIFEST_BYTES",
    "MAX_FILES",
    "MAX_FILE_BYTES",
    "MAX_TOTAL_BYTES",
    "SKIP_DIRS",
    "SKIP_SUFFIXES",
    "SKIP_FILES",
    "ManifestError",
    "normalize_rel",
    "sha256_file",
    "iter_snapshot_files",
    "build_manifest",
    "manifest_digest",
    "sign_manifest",
    "save_manifest",
    "load_manifest",
    "verify_manifest",
]

SCHEMA_VERSION = "aether-backup/1"
MANIFEST_NAME = "aether-backup-manifest.json"

MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_FILES = 250_000
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
MAX_KEY_BYTES = 64 * 1024

SKIP_DIRS = frozenset({
    ".cache", ".git", "__pycache__", "node_modules", "Trash", ".thumbnails",
})
SKIP_SUFFIXES = (".pyc", ".pyo", ".swap", ".tmp")
SKIP_FILES = frozenset({MANIFEST_NAME, MANIFEST_NAME + ".tmp"})


class ManifestError(ValueError):
    """Raised for malformed, oversized, or unverifiable manifests."""


def _read_bounded(path, limit: int) -> bytes:
    p = pathlib.Path(path)
    try:
        with p.open("rb") as fh:
            data = fh.read(limit + 1)
    except OSError as exc:
        raise ManifestError(f"cannot read {p}: {exc}") from exc
    if len(data) > limit:
        raise ManifestError(f"input exceeds {limit} bytes: {p}")
    return data


def normalize_rel(value) -> str:
    """Validate and normalize a manifest-relative POSIX path; reject traversal."""
    if isinstance(value, pathlib.PurePath):
        text = value.as_posix()
    elif isinstance(value, str):
        text = value
    else:
        raise ManifestError("relative path must be a string")
    if not text or "\x00" in text or ":" in text or "\\" in text:
        raise ManifestError(f"invalid relative path: {text!r}")
    if text.startswith("/"):
        raise ManifestError(f"absolute path rejected: {text!r}")
    parts = PurePosixPath(text).parts
    if any(part in ("", ".", "..") for part in parts):
        raise ManifestError(f"unsafe path component: {text!r}")
    return PurePosixPath(*parts).as_posix()


def _contained(base: pathlib.Path, candidate: pathlib.Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def sha256_file(path) -> str:
    """Hash a file with bounded reads; never buffer more than CHUNK_SIZE."""
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def iter_snapshot_files(root):
    """Yield tracked regular files under root, applying skip list and size cap."""
    root = pathlib.Path(root).resolve()
    if not root.is_dir():
        raise ManifestError(f"snapshot root is not a directory: {root}")
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            name for name in dirnames
            if name not in SKIP_DIRS
            and not (pathlib.Path(dirpath) / name).is_symlink()
        ]
        for name in filenames:
            if name in SKIP_FILES or name.endswith(SKIP_SUFFIXES):
                continue
            path = pathlib.Path(dirpath) / name
            if path.is_symlink() or not path.is_file():
                continue
            if not _contained(root, path):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            count += 1
            if count > MAX_FILES:
                raise ManifestError(f"snapshot exceeds {MAX_FILES} files")
            yield path


def build_manifest(root, files) -> dict:
    """Build a canonical manifest for the given root-relative files."""
    root = pathlib.Path(root).resolve()
    entries: list[dict] = []
    seen: set[str] = set()
    total = 0
    for raw in files:
        rel = normalize_rel(raw)
        if rel in seen:
            continue
        full = root / rel
        if not _contained(root, full):
            raise ManifestError(f"path escapes root: {rel}")
        if full.is_symlink() or not full.is_file():
            raise ManifestError(f"not a regular file: {rel}")
        if len(entries) >= MAX_FILES:
            raise ManifestError(f"manifest exceeds {MAX_FILES} entries")
        st = full.stat()
        if st.st_size > MAX_FILE_BYTES:
            raise ManifestError(f"file exceeds size cap: {rel}")
        total += st.st_size
        if total > MAX_TOTAL_BYTES:
            raise ManifestError("manifest exceeds total byte cap")
        entries.append({
            "path": rel,
            "size": int(st.st_size),
            "sha256": sha256_file(full),
            "mtime": int(st.st_mtime_ns),
            "type": "file",
        })
        seen.add(rel)
    entries.sort(key=lambda entry: entry["path"])
    created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "schema": SCHEMA_VERSION,
        "created": created,
        "root": root.name,
        "count": len(entries),
        "total_bytes": total,
        "entries": entries,
        "signature": None,
    }


def _unsigned(manifest: dict) -> dict:
    return {key: value for key, value in manifest.items() if key != "signature"}


def manifest_digest(manifest: dict) -> str:
    """Return the SHA-256 of the canonical unsigned manifest payload."""
    return hashlib.sha256(canonical_signing_input(_unsigned(manifest))).hexdigest()


def sign_manifest(manifest: dict, private_key_path) -> dict:
    """Record and Ed25519-sign the manifest digest; returns a signed copy."""
    if not isinstance(manifest, dict):
        raise ManifestError("manifest must be a dict")
    digest = bytes.fromhex(manifest_digest(manifest))
    key_bytes = _read_bounded(private_key_path, MAX_KEY_BYTES)
    try:
        private_key = serialization.load_pem_private_key(key_bytes, password=None)
    except Exception as exc:
        raise ManifestError("signing key is not valid PEM") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ManifestError("signing key is not Ed25519")
    signature = private_key.sign(digest)
    signed = dict(manifest)
    signed["signature"] = {
        "algorithm": "ed25519",
        "digest": digest.hex(),
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    return signed


def _check_signature(manifest: dict, public_key_path=None) -> list[str]:
    """Return signature-related discrepancies; fail closed on any tampering."""
    record = manifest.get("signature")
    key_requested = public_key_path is not None and pathlib.Path(public_key_path).is_file()
    if not isinstance(record, dict):
        return ["manifest is unsigned"] if key_requested else []
    if _unsigned(manifest).get("schema") != SCHEMA_VERSION:
        return ["unsupported manifest schema"]
    actual_digest = manifest_digest(manifest)
    if record.get("digest") != actual_digest:
        return ["manifest digest mismatch"]
    if record.get("algorithm") != "ed25519":
        return ["unsupported signature algorithm"]
    if not key_requested:
        return []
    try:
        key_bytes = _read_bounded(public_key_path, MAX_KEY_BYTES)
        public_key = serialization.load_pem_public_key(key_bytes)
        if not isinstance(public_key, Ed25519PublicKey):
            return ["public key is not Ed25519"]
        signature = base64.b64decode(record.get("signature", ""), validate=True)
        public_key.verify(signature, bytes.fromhex(actual_digest))
    except Exception as exc:  # backend raises several distinct PEM/base64 errors
        return [f"manifest signature invalid: {type(exc).__name__}"]
    return []


def save_manifest(path, manifest: dict, *, private_key_path=None) -> dict:
    """Write canonical JSON atomically, signing when a key file is available."""
    if not isinstance(manifest, dict):
        raise ManifestError("manifest must be a dict")
    result = manifest
    if private_key_path is not None and pathlib.Path(private_key_path).is_file():
        result = sign_manifest(manifest, private_key_path)
    raw = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    with temp.open("wb") as fh:
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, target)
    return result


def load_manifest(path, *, public_key_path=None) -> dict:
    """Load a bounded canonical manifest, failing closed on bad signature."""
    raw = _read_bounded(path, MAX_MANIFEST_BYTES)
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ManifestError("manifest is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be an object")
    if manifest.get("schema") != SCHEMA_VERSION:
        raise ManifestError(f"unsupported schema: {manifest.get('schema')!r}")
    problems = _check_signature(manifest, public_key_path)
    if problems:
        raise ManifestError("; ".join(problems))
    return manifest


def verify_manifest(root, manifest: dict, *, public_key_path=None) -> tuple[bool, list[str]]:
    """Verify every entry against disk and detect extra/missing files."""
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA_VERSION:
        return False, ["unsupported manifest schema"]
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return False, ["manifest entries missing"]

    problems = _check_signature(manifest, public_key_path)

    expected: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append("malformed manifest entry")
            continue
        try:
            rel = normalize_rel(entry.get("path"))
        except ManifestError as exc:
            problems.append(str(exc))
            continue
        expected[rel] = entry

    seen: set[str] = set()
    for path in iter_snapshot_files(root):
        rel = path.relative_to(pathlib.Path(root).resolve()).as_posix()
        seen.add(rel)
        entry = expected.get(rel)
        if entry is None:
            problems.append(f"extra file: {rel}")
            continue
        try:
            st = path.stat()
        except OSError as exc:
            problems.append(f"stat failed: {rel}: {exc}")
            continue
        if entry.get("type") != "file":
            problems.append(f"type mismatch: {rel}")
        if st.st_size != entry.get("size"):
            problems.append(f"size mismatch: {rel}")
        elif sha256_file(path) != entry.get("sha256"):
            problems.append(f"sha256 mismatch: {rel}")

    for rel in expected:
        if rel not in seen:
            problems.append(f"missing file: {rel}")

    return (not problems), problems
