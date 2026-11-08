#!/usr/bin/env bash
# Install Steam (Valve official deb). Run on AetherOS live or installed system.
set -euo pipefail
if command -v steam >/dev/null 2>&1; then echo "Steam already installed"; exit 0; fi
cd /tmp
wget -q https://cdn.akamai.steamstatic.com/client/installer/steam.deb
sudo dpkg -i steam.deb || sudo apt-get install -f -y
echo "Steam installed. Launch with: steam"
