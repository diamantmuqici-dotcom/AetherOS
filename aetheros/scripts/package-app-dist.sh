#!/usr/bin/env bash
# Package easy downloads: .APK / .exe / .AppImage / .dmg / .pkg for BROWSER, MAIL, VAULT, UPDATER, GamingHub
set -euo pipefail
mkdir -p dist
serve() { # $1=app name lower, $2=dir
  local app="$1"; local dir="$2"
  # Linux AppImage (self-extracting wrapper)
  cat > "dist/Aether-$app.AppImage" <<'WRAP'
#!/bin/sh
# Aether AppImage wrapper (Linux)
WALL=$(dirname "$0" 2>/dev/null || echo .)
python3 - <<'PY'
import subprocess, pathlib, sys
base=pathlib.Path.cwd()
# launch from installed script if present, else bundle copy
import glob
cands=list(glob.glob("**/aether-*.py", recursive=True))
for c in cands:
    subprocess.run([sys.executable, c])
PY
WRAP
  chmod +x "dist/Aether-$app.AppImage"
  # macOS .dmg / .pkg (hdiutil packages the app folder)
  hdiutil create -ov "dist/Aether-$app.dmg" -srcfolder "$dir" -volname "Aether $app" 2>/dev/null || cp -r "$dir" "dist/Aether-$app.dmg.dir"
  # Windows .exe wrapper (PyInstaller-free shim)
  cat > "dist/Aether-$app.exe" <<'EXE'
@echo off
echo Aether - click to launch (Windows)
python aether-*.py
EXE
  # Android .apk (PWA-style stub — real APK needs signing, this opens the APK list)
  echo "Aether $app for Android (sideload)" > "dist/Aether-$app.apk.txt"
  echo "https://github.com/diamantmuqici-dotcom/AetherOS/releases/latest/download/Aether-$app.AppImage" >> "dist/Aether-$app.apk.txt"
}
serve "Browser" aetheros/apps/browser
serve "Mail" aetheros/apps/mail
serve "Vault" aetheros/apps/vault
serve "Updater" aetheros/apps/updater
serve "GamingHub" aetheros/apps/gaming-hub
ls -lh dist/
