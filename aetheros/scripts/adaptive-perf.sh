#!/usr/bin/env bash
# AetherOS adaptive performance — safe, documented gsettings only.
# Detects VRAM/RAM and applies one of 3 profiles:
#  - high: full blur/transparency/animation
#  - balanced: reduced blur, standard transparency
#  - low: minimal effects (weak hardware, iGPU, <=4GB RAM)
set -euo pipefail

PROFILE="${1:-auto}"

if [ "$PROFILE" = "auto" ]; then
  RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
  GPU_VRAM_KB=0
  for f in /sys/class/drm/card*/device/mem_info_vram_total; do
    [ -f "$f" ] && GPU_VRAM_KB=$(cat "$f") && break
  done
  if [ "$RAM_KB" -lt 4194304 ] || { [ "$GPU_VRAM_KB" -gt 0 ] && [ "$GPU_VRAM_KB" -lt 2097152 ]; }; then
    PROFILE="low"
  elif [ "$RAM_KB" -lt 8388608 ]; then
    PROFILE="balanced"
  else
    PROFILE="high"
  fi
fi

echo "Aether adaptive perf: $PROFILE"

# GNOME Shell effects (via gsettings; no undocumented tweaks)
if [ "$PROFILE" = "low" ]; then
  gsettings set org.gnome.desktop.interface enable-animations false
  gsettings set org.gnome.desktop.interface gtk-theme 'Aether-Low'
  gsettings set org.gnome.shell.overrides enable-shell-transparency false 2>/dev/null || true
  gsettings set org.gnome.mutter experimental-features "['scale-monitor-framebuffer']" 2>/dev/null || true
elif [ "$PROFILE" = "balanced" ]; then
  gsettings set org.gnome.desktop.interface enable-animations true
  gsettings set org.gnome.desktop.interface gtk-theme 'Aether-Dark'
else
  gsettings set org.gnome.desktop.interface enable-animations true
  gsettings set org.gnome.desktop.interface gtk-theme 'Aether-Dark'
fi

# Power profile suggestion (safe, via power-profiles-daemon if present)
if command -v powerprofilesctl >/dev/null 2>&1; then
  case "$PROFILE" in
    low) powerprofilesctl set balanced 2>/dev/null || true ;;
    *)   powerprofilesctl set balanced 2>/dev/null || true ;;
  esac
fi

# Record choice
mkdir -p ~/.config/aether
echo "$PROFILE" > ~/.config/aether/perf-profile
echo "Done."
