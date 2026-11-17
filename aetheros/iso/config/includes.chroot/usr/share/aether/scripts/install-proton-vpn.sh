#!/usr/bin/env bash
# Install Proton VPN (official repo deb) — https://protonvpn.com/download-linux
set -euo pipefail
if command -v protonvpn >/dev/null 2>&1; then echo "Proton VPN already installed"; exit 0; fi
# Private temp dir defeats the predictable /tmp race before dpkg runs maintainer scripts as root.
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
deb="$D/protonvpn.deb"
REPO_DEB="https://repo.protonvpn.com/debian/public/protonvpn-stable-release-1.0.3-1.noarch.deb"
if wget -q "$REPO_DEB" -O "$deb" 2>/dev/null; then
  # Optional operator-supplied pin; enforced when set, never fabricated here.
  if [ -n "${AETHER_PROTON_SHA256:-}" ]; then
    echo "$AETHER_PROTON_SHA256  $deb" | sha256sum -c - >/dev/null
  fi
  # Reject a corrupt or substituted archive before it reaches dpkg.
  dpkg-deb --info "$deb" >/dev/null
  sudo dpkg -i "$deb" || sudo apt-get install -f -y
  echo "Proton VPN repo added. Install: sudo apt install proton-vpn-gtk-app"
else
  echo "Download Proton VPN manually: https://protonvpn.com/download-linux"
fi
