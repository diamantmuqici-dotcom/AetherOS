#!/usr/bin/env bash
# Aether safe optimizations — no unsafe kernel tweaks. All changes via gsettings/sysctl documented paths.
set -euo pipefail
echo "Aether optimize: RAM"
# zram if present (safe swap compression)
if command -v zramctl >/dev/null 2>&1; then
  sudo zramctl --find --size 4096 --algorithm zstd 2>/dev/null || echo "zram not available (ok)"
else echo "zramctl not present (skip)"; fi
# cache pressure: drop clean caches only if idle (safe)
# No vm.swappiness rewrite beyond default without confirm; log current
sysctl vm.swappiness 2>/dev/null || true
echo "GPU"
env | grep -E "MESA_|VULKAN|__GL" || echo "Mesa default (no forced env)"
echo "CPU"
if command -v powerprofilesctl >/dev/null 2>&1; then powerprofilesctl set balanced || true; fi
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort -u || echo "governor: see power-profiles"
echo "Input (raw, no accel)"
gsettings set org.gnome.desktop.peripherals.mouse speed 0 2>/dev/null || true
gsettings set org.gnome.desktop.peripherals.mouse accel-profile 'flat' 2>/dev/null || true
gsettings set org.gnome.desktop.peripherals.mouse natural-scroll false 2>/dev/null || true
gsettings set org.gnome.desktop.peripherals.keyboard delay 250 2>/dev/null || true
gsettings set org.gnome.desktop.peripherals.keyboard repeat-interval 30 2>/dev/null || true
echo "Done. Restart recommended after input change."
