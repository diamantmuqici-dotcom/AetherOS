#!/usr/bin/env bash
# Install Zen Browser (official deb, MPL). Official distribution, not rebranded.
set -euo pipefail
if command -v zen-browser >/dev/null 2>&1 || command -v zen >/dev/null 2>&1; then echo "Zen already installed"; exit 0; fi
cd /tmp
# Zen Browser official .deb (update URL from zen-browser.app if changed)
ZEN_DEB="https://github.com/zen-browser/desktop/releases/latest/download/zen-browser-amd64.deb"
if wget -q "$ZEN_DEB" -O zen.deb; then
  sudo dpkg -i zen.deb || sudo apt-get install -f -y
  echo "Zen Browser installed (official deb)."
else
  echo "Download Zen Browser manually from https://zen-browser.app (official) and install the .deb"
  exit 1
fi
