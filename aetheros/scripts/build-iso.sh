#!/usr/bin/env bash
# AetherOS live-build — reproducible ISO (must run as root or via sudo inside builder)
set -euo pipefail
cd "$(dirname "$0")/.."

DISTRO_CODENAME="trixie"
ARCH="amd64"
HOSTNAME="aetheros-live"
USER="aether"
PASSWORD="aether"

echo "== AetherOS ISO build (${DISTRO_CODENAME}/${ARCH}) =="

# Sync wallpapers into ISO payload (idempotent)
make wallpapers

cd iso

# Clean previous
rm -rf .build build.log
echo "Configuring live-build..."
lb config \
  --distribution "$DISTRO_CODENAME" \
  --architectures "$ARCH" \
  --binary-images iso-hybrid \
  --bootappend-live "boot=live components hostname=${HOSTNAME} username=${USER} union=overlay apparmor=1" \
  --hostname "$HOSTNAME" \
  --username "$USER" \
  --image-name "aetheros-live" \
  --debian-installer none \
  --archive-areas "main contrib non-free non-free-firmware" \
  2>&1 | tee build.log

echo "Building..."
sudo lb build 2>&1 | tee -a build.log

ISO="$(ls -1 *.iso 2>/dev/null | grep -E 'aetheros-live.*\.iso' | head -n1 || true)"
if [ -n "$ISO" ]; then
  echo "OK: $(pwd)/$ISO"
  sha256sum "$ISO" > "$ISO.sha256"
  echo "SHA256: $(cat "$ISO.sha256")"
else
  echo "ERROR: ISO not produced. See build.log"
  exit 1
fi
