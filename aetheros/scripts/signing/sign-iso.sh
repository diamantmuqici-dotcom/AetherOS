#!/usr/bin/env bash
# Sign ISO checksum with GPG (newman plan: checksum signing).
set -euo pipefail
ISO="${1:-}"
if [ -z "$ISO" ]; then echo "usage: sign-iso.sh <file.iso>"; exit 1; fi
if [ -z "${GPG_KEY_ID:-}" ] && [ -z "${GPG_PRIVATE_KEY:-}" ]; then
  echo "No GPG key. Using SHA256 only (sha256sum -c to verify)."
  sha256sum "$ISO" > "$ISO.sha256"
  exit 0
fi
sha256sum "$ISO" > "$ISO.sha256"
gpg --batch --yes --detach-sign --armor --local-user "$GPG_KEY_ID" -o "$ISO.sha256.asc" "$ISO.sha256"
echo "Signed: $ISO.sha256 + $ISO.sha256.asc"
