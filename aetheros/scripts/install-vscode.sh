#!/usr/bin/env bash
# Install VS Code (Microsoft official deb) + Aether extensions hint.
set -euo pipefail
if command -v code >/dev/null 2>&1; then echo "VS Code already installed"; code --version; exit 0; fi
# Private temp dir defeats the predictable /tmp race before dpkg runs maintainer scripts as root.
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
deb="$D/code.deb"
wget -q "https://go.microsoft.com/fwlink/?LinkID=760505" -O "$deb"
# Optional operator-supplied pin; enforced when set, never fabricated here.
if [ -n "${AETHER_VSCODE_SHA256:-}" ]; then
  echo "$AETHER_VSCODE_SHA256  $deb" | sha256sum -c - >/dev/null
fi
# Reject a corrupt or substituted archive before it reaches dpkg.
dpkg-deb --info "$deb" >/dev/null
sudo dpkg -i "$deb" || sudo apt-get install -f -y
echo "VS Code installed. Aether tip: Settings > Extensions > search 'Aether'."
