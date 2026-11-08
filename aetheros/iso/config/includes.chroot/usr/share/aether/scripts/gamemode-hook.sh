#!/usr/bin/env bash
# Aether GameMode hook — safe only. Never kills critical services.
# Start: higher CPU nice, notification suppress, balanced->performance if allowed.
# Stop: restore previous profile + notifications.
# Steam download: detect steam download process, raise niceness? (lower nice = higher prio)
# Do NOT kill Steam critical services. Only adjust process nice/affinity for game PIDs.
set -euo pipefail

STATE="$HOME/.config/aether/gamemode.state"
mkdir -p "$(dirname "$STATE")"

case "${1:-start}" in
  start)
    if command -v powerprofilesctl >/dev/null 2>&1; then
      powerprofilesctl get > "$STATE" 2>/dev/null || echo "balanced" > "$STATE"
      powerprofilesctl set performance 2>/dev/null || true
    fi
    gsettings get org.gnome.desktop.notifications show-banners > "$STATE.banners" 2>/dev/null || true
    gsettings set org.gnome.desktop.notifications show-banners false 2>/dev/null || true
    # Game/Steam priority: found PIDs via pgrep (safe read-only list, then nice)
    for pat in steam game gamemode; do
      for pid in $(pgrep -f "$pat" 2>/dev/null || true); do
        # raise priority (lower nice) to -5 if permitted, else renice to 0; never kill
        sudo nice -n -5 -p "$pid" 2>/dev/null || renice 0 "$pid" 2>/dev/null || true
      done
    done
    # Steam download special: detect network-heavy steam process, boost IO? only nice
    for pid in $(pgrep -x steam 2>/dev/null || pgrep -f "steamwebhelper" 2>/dev/null || true); do
      sudo nice -n -5 -p "$pid" 2>/dev/null || true
    done
    echo "Game Mode ON (priority boosted for game/steam PIDs)"
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
