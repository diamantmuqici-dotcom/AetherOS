#!/usr/bin/env bash
# Install Zen Browser (official deb, MPL). Official distribution, not rebranded.
set -euo pipefail
if command -v zen-browser >/dev/null 2>&1 || command -v zen >/dev/null 2>&1; then echo "Zen already installed"; exit 0; fi
# Private temp dir defeats the predictable /tmp race before dpkg runs maintainer scripts as root.
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
deb="$D/zen.deb"
# Zen Browser official .deb (update URL from zen-browser.app if changed)
ZEN_DEB="https://github.com/zen-browser/desktop/releases/latest/download/zen-browser-amd64.deb"
if wget -q "$ZEN_DEB" -O "$deb"; then
  # Optional operator-supplied pin; enforced when set, never fabricated here.
  if [ -n "${AETHER_ZEN_SHA256:-}" ]; then
    echo "$AETHER_ZEN_SHA256  $deb" | sha256sum -c - >/dev/null
  fi
  # Reject a corrupt or substituted archive before it reaches dpkg.
  dpkg-deb --info "$deb" >/dev/null
  sudo dpkg -i "$deb" || sudo apt-get install -f -y
  echo "Zen Browser installed (official deb)."
else
  echo "Download Zen Browser manually from https://zen-browser.app (official) and install the .deb"
  exit 1
fi
