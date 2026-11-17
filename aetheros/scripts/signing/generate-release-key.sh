#!/usr/bin/env bash
# Offline Ed25519 release keypair generator. Emits the public fingerprint only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PRIV=""
PUB=""
KEY_DIR="${AETHER_KEY_DIR:-$HOME/.config/aether/release-keys}"
FORCE=0

usage() {
  cat <<'EOF'
usage: generate-release-key.sh [--priv PATH] [--pub PATH] [--key-dir DIR] [--force]

Generates an Ed25519 release keypair with openssl. No key bytes are printed.
Defaults write outside the repository to:
  ${AETHER_KEY_DIR:-$HOME/.config/aether/release-keys}/
    aether-release.ed25519.pem  (private, 0600)
    aether-release.pub.pem      (public,  0644)
EOF
}

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --priv)    [ $# -ge 2 ] || die "--priv needs a path"; PRIV="$2"; shift 2 ;;
    --pub)     [ $# -ge 2 ] || die "--pub needs a path"; PUB="$2"; shift 2 ;;
    --key-dir) [ $# -ge 2 ] || die "--key-dir needs a path"; KEY_DIR="$2"; shift 2 ;;
    --force)   FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

if [ -z "$PRIV" ]; then PRIV="$KEY_DIR/aether-release.ed25519.pem"; fi
if [ -z "$PUB" ]; then PUB="$KEY_DIR/aether-release.pub.pem"; fi

resolve_path() {
  if command -v realpath >/dev/null 2>&1; then realpath -m -- "$1" 2>/dev/null || printf '%s\n' "$1"; else printf '%s\n' "$1"; fi
}
ABS_PRIV="$(resolve_path "$PRIV")"
ABS_PUB="$(resolve_path "$PUB")"
[ "$ABS_PRIV" != "$ABS_PUB" ] || die "private and public paths must differ"
case "$ABS_PRIV" in
  "$REPO_ROOT"|"$REPO_ROOT"/*) die "refusing to write inside the repository: $PRIV" ;;
esac
case "$ABS_PUB" in
  "$REPO_ROOT"|"$REPO_ROOT"/*) die "refusing to write inside the repository: $PUB" ;;
esac

if ! command -v openssl >/dev/null 2>&1; then
  printf '%s\n' "openssl not found; key generation skipped" >&2
  exit 77
fi

for target in "$PRIV" "$PUB"; do
  if [ -e "$target" ] && [ "$FORCE" -eq 0 ]; then
    die "refusing to overwrite existing key: $target (use --force)"
  fi
done

mkdir -p -- "$(dirname "$PRIV")" "$(dirname "$PUB")"
[ -d "$(dirname "$PRIV")" ] || die "private key directory is not usable: $PRIV"
[ -d "$(dirname "$PUB")" ] || die "public key directory is not usable: $PUB"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aether-keygen.XXXXXX")"
trap 'rm -rf -- "$TMP_DIR"' EXIT
TMP_PRIV="$TMP_DIR/private.pem"
TMP_PUB="$TMP_DIR/public.pem"
DERIVED_DER="$TMP_DIR/derived.der"
PUBLIC_DER="$TMP_DIR/public.der"

umask 077
openssl genpkey -algorithm ED25519 -out "$TMP_PRIV"
chmod 600 "$TMP_PRIV"
openssl pkey -in "$TMP_PRIV" -pubout -out "$TMP_PUB"
chmod 644 "$TMP_PUB"

# Compare SPKI DER bytes so PEM formatting never affects the pair check.
openssl pkey -in "$TMP_PRIV" -pubout -outform DER -out "$DERIVED_DER"
openssl pkey -pubin -in "$TMP_PUB" -outform DER -out "$PUBLIC_DER"
cmp -s -- "$DERIVED_DER" "$PUBLIC_DER" || die "generated keypair does not match"

FINGERPRINT="$(sha256sum "$DERIVED_DER")"
FINGERPRINT="${FINGERPRINT%% *}"
[ ${#FINGERPRINT} -eq 64 ] || die "could not compute public key fingerprint"

mv -f -- "$TMP_PRIV" "$PRIV"
mv -f -- "$TMP_PUB" "$PUB"
chmod 600 "$PRIV"
chmod 644 "$PUB"
printf 'SHA256:%s\n' "$FINGERPRINT"
