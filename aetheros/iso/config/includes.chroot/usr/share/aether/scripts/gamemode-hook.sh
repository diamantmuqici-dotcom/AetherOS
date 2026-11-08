#!/usr/bin/env bash
# Aether Game Mode hook — safe only. Never kills critical services.
# Called by gamemoded D-Bus (org.freedesktop.GameMode) when a game starts/stops.
# Start: higher CPU nice, notification suppress, balanced->performance if allowed.
# Stop: restore previous profile + notifications.
set -euo pipefail

STATE="$HOME/.config/aether/gamemode.state"
mkdir -p "$(dirname "$STATE")"

case "${1:-start}" in
  start)
    # Save current profile
    if command -v powerprofilesctl >/dev/null 2>&1; then
      powerprofilesctl get > "$STATE" 2>/dev/null || echo "balanced" > "$STATE"
      powerprofilesctl set performance 2>/dev/null || true
    fi
    # Suppress notifications (GNOME)
    gsettings get org.gnome.desktop.notifications show-banners > "$STATE.banners" 2>/dev/null || true
    gsettings set org.gnome.desktop.notifications show-banners false 2>/dev/null || true
    echo "Game Mode ON"
    ;;
  stop)
    if [ -f "$STATE" ] && command -v powerprofilesctl >/dev/null 2>&1; then
      powerprofilesctl set "$(cat "$STATE")" 2>/dev/null || true
    fi
    if [ -f "$STATE.banners" ]; then
      gsettings set org.gnome.desktop.notifications show-banners "$(cat "$STATE.banners")" 2>/dev/null || true
    fi
    echo "Game Mode OFF (restored)"
    ;;
  *) echo "usage: gamemode-hook.sh [start|stop]"; exit 1 ;;
esac
