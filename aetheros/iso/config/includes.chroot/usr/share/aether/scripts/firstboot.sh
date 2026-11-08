#!/usr/bin/env bash
# Aether first-boot launcher — runs aether-setup once per user.
set -euo pipefail

MARKER="$HOME/.config/aether/firstboot"
mkdir -p "$(dirname "$MARKER")"

if [ -f "$MARKER.done" ]; then
  exit 0
fi

# Launch setup (Wayland native). If it exits non-zero, keep marker for retry.
aether-setup
RC=$?
if [ $RC -eq 0 ]; then
  touch "$MARKER.done"
fi
exit $RC
