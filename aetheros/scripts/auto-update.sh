#!/usr/bin/env bash
# Aether Auto Updater — safe, documented. No blind distro switches.
# pkexec shows the polkit GUI auth dialog (agent: polkit-gnome-authentication-agent-1).
set -euo pipefail
echo "==> Aether Updater: checking repository..."
pkexec apt-get update -y || true
echo "==> Upgrading (safe defaults, no breaking changes)..."
pkexec apt-get upgrade -y || true
pkexec apt-get autoremove -y || true
echo "==> Flatpak updates (if flatpak present)..."
command -v flatpak >/dev/null 2>&1 && flatpak update -y || echo "(no flatpak)"
echo "==> Firmware (fwupdmgr, if present)..."
command -v fwupdmgr >/dev/null 2>&1 && sudo fwupdmgr update || echo "(no fwupdmgr)"
echo "Done. Reboot recommended if kernel was upgraded."
