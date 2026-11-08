#!/usr/bin/env bash
# Install Proton VPN (official deb) — http://protonvpn.com/download-linux
set -euo pipefail
if command -v protonvpn >/dev/null 2>&1; then echo "Proton VPN already installed"; exit 0; fi
cd /tmp
Z="/tmp/protonvpn-stable-release-1.0.3-1.noarch.rpm"
# Official: apt repo script
wget -q https://repo.protonvpn.com/debian/public/protonvpn-stable-release-1.0.3-1.noarch.deb -O protonvpn.deb 2>/dev/null || true
if [ -f protonvpn.deb ]; then
  sudo dpkg -i protonvpn.deb || sudo apt-get install -f -y
  echo "Proton VPN repo added. Install: sudo apt install proton-vpn-gtk-app"
else
  echo "Download Proton VPN manually: https://protonvpn.com/download-linux"
fi
