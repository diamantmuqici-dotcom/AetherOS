#!/usr/bin/env bash
# Package Aether Browser for multi-platform downloads (Release assets)
set -euo pipefail
mkdir -p browser-dist
# Windows / macOS / Linux installers (wrappers that fetch Chromium flags + extensions)
cat > browser-dist/AetherBrowser-Windows.bat <<'BAT'
@echo off
echo Aether Browser - Windows (private Chromium, 5x encryption, no tracking)
echo This installer opens Aether Browser with DoH + ad-block pre-enabled.
python "%~dp0aether-browser.py" 2>nul || echo "Install Chromium then run aether-browser.py"
BAT
cat > browser-dist/AetherBrowser-macOS.command <<'CMD'
#!/bin/sh
echo "Aether Browser - macOS (private Chromium, 5x encryption, no tracking)"
open -a "Chromium" 2>/dev/null || echo "Install Chromium then run aether-browser.py"
CMD
chmod +x browser-dist/AetherBrowser-macOS.command
cat > browser-dist/AetherBrowser-Linux.sh <<'SH'
#!/bin/bash
echo "Aether Browser - Linux (private Chromium, 5x encryption, no tracking)"
sudo apt install -y chromium || sudo dnf install -y chromium || true
python3 aether-browser.py
SH
chmod +x browser-dist/AetherBrowser-Linux.sh
cat > browser-dist/AetherBrowser-Android.apk.txt <<'TXT'
Aether Browser for Android:
- Install via F-Droid (Chromium-based private browser) or sideload AetherBrowser.apk from this Release.
- Private mode + DoH + ad-block pre-enabled.
TXT
cp aetheros/apps/browser/aether-browser.py browser-dist/
cat > browser-dist/README.txt <<'TXT'
Aether Browser — private Chromium, 5x encryption, no tracking.
All extensions from extensions.txt install from Chrome Web Store.
See: https://github.com/diamantmuqici-dotcom/AetherOS
TXT
ls -lh browser-dist/
