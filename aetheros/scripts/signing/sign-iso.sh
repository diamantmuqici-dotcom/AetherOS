#!/usr/bin/env bash
# Sign ISO checksums with GPG and release manifests with Ed25519.
set -euo pipefail
ISO="${1:-}"
if [ -z "$ISO" ]; then echo "usage: sign-iso.sh <file.iso>"; exit 1; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

sign_release_manifest() {
  local manifest="${AETHER_RELEASE_MANIFEST:-}"
  local key="${AETHER_SIGNING_KEY:-}"
  local outdir="${AETHER_RELEASE_OUTDIR:-}"
  [ -n "$manifest" ] || return 0
  [ -n "$key" ] || return 0
  if [ ! -f "$manifest" ]; then echo "release manifest not found: $manifest" >&2; return 1; fi
  if [ ! -f "$key" ]; then echo "signing key not found: $key" >&2; return 1; fi
  if [ -z "$outdir" ]; then outdir="$(dirname "$manifest")"; fi
  mkdir -p "$outdir"

  # Inline tool: reuses the canonical signer so signing and verification agree byte for byte.
  PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - "$manifest" "$key" "$outdir" <<'PY'
import json
import pathlib
import sys

from cryptography.hazmat.primitives import serialization
from core.update.signature import SCHEMA_VERSION, sign_release

manifest, key, outdir = (pathlib.Path(p) for p in sys.argv[1:4])
payload = json.loads(manifest.read_text(encoding="utf-8"))
if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
    raise SystemExit(f"unsupported release schema in {manifest}")
signature = sign_release(payload, key)
manifest.with_name(manifest.name + ".sig").write_bytes(signature)
private = serialization.load_pem_private_key(key.read_bytes(), password=None)
public = private.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
)
(outdir / "aether-release.pub.pem").write_bytes(public)
print(f"signed {manifest} -> {manifest}.sig; public key -> {outdir}/aether-release.pub.pem")
PY

  # An externally supplied public key overrides the derived one when provided.
  if [ -n "${AETHER_SIGNING_PUBKEY:-}" ]; then
    if [ ! -f "$AETHER_SIGNING_PUBKEY" ]; then
      echo "public key not found: $AETHER_SIGNING_PUBKEY" >&2
      return 1
    fi
    cp -- "$AETHER_SIGNING_PUBKEY" "$outdir/aether-release.pub.pem"
  fi
}

sha256sum "$ISO" > "$ISO.sha256"
if [ -z "${GPG_KEY_ID:-}" ] && [ -z "${GPG_PRIVATE_KEY:-}" ]; then
  echo "No GPG key. Using SHA256 only (sha256sum -c to verify)."
else
  gpg --batch --yes --detach-sign --armor --local-user "${GPG_KEY_ID:-}" -o "$ISO.sha256.asc" "$ISO.sha256"
  echo "Signed: $ISO.sha256 + $ISO.sha256.asc"
fi

sign_release_manifest
