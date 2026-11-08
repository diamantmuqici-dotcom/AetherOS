#!/usr/bin/env bash
# Aether self-repair on crash/boot failure (safe, no data wipe)
set -euo pipefail
echo "[aether-repair] $(date -u) start" >> /var/log/aether-repair.log
# Re-create user dirs if missing
mkdir -p ~/.config/aether ~/.local/share/Trash/files ~/.local/share/Trash/info 2>/dev/null || true
# Repair GNOME monitor config if corrupt (safe: move aside, fresh)
if ! gsettings list-keys org.gnome.desktop.interface >/dev/null 2>&1; then
  mv ~/.config/monitors.xml ~/.config/monitors.xml.bak 2>/dev/null || true
  gsettings reset -f org.gnome.desktop.interface 2>/dev/null || true
  echo "repaired monitors config" >> /var/log/aether-repair.log
fi
# Verify PipeWire (restart if down)
systemctl --user restart pipewire wireplumber 2>/dev/null || systemctl restart pipewire 2>/dev/null || true
# Log bundle for support (no auto-send unless user opts in)
journalctl --no-pager -n 200 > ~/.config/aether/crash-bundle.log 2>/dev/null || true
echo "[aether-repair] done" >> /var/log/aether-repair.log
