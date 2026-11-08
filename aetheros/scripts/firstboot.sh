#!/usr/bin/env bash
# Aether first-boot launcher — runs aether-setup once per user.
set -euo pipefail

MARKER="$HOME/.config/aether/firstboot"
mkdir -p "$(dirname "$MARKER")"

if [ -f "$MARKER.done" ]; then
  exit 0
fi

# Launch setup in background after short delay so desktop/mouse come up first
# (prevents 60s wallpaper-screen freeze; Setup appears seconds later ready)
sleep 2 &
aether-setup
RC=$?
if [ $RC -eq 0 ]; then
  touch "$MARKER.done"
fi
# Async perf tune (non-blocking)
(adaptive-perf auto >/dev/null 2>&1 || true) &
exit $RC
