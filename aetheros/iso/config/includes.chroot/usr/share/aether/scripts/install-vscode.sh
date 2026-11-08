#!/usr/bin/env bash
# Install VS Code (Microsoft official deb) + Aether extensions hint.
set -euo pipefail
if command -v code >/dev/null 2>&1; then echo "VS Code already installed"; code --version; exit 0; fi
cd /tmp
wget -q "https://go.microsoft.com/fwlink/?LinkID=760505" -O code.deb
sudo dpkg -i code.deb || sudo apt-get install -f -y
echo "VS Code installed. Aether tip: Settings > Extensions > search 'Aether'."
