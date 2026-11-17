#!/usr/bin/env bash
# Install Steam (Valve official deb). Run on AetherOS live or installed system.
set -euo pipefail
if command -v steam >/dev/null 2>&1; then echo "Steam already installed"; exit 0; fi
# Private temp dir defeats the predictable /tmp race before dpkg runs maintainer scripts as root.
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
deb="$D/steam.deb"
wget -q "https://cdn.akamai.steamstatic.com/client/installer/steam.deb" -O "$deb"
# Optional operator-supplied pin; enforced when set, never fabricated here.
if [ -n "${AETHER_STEAM_SHA256:-}" ]; then
  echo "$AETHER_STEAM_SHA256  $deb" | sha256sum -c - >/dev/null
fi
# Reject a corrupt or substituted archive before it reaches dpkg.
dpkg-deb --info "$deb" >/dev/null
sudo dpkg -i "$deb" || sudo apt-get install -f -y
echo "Steam installed. Launch with: steam"
