#!/bin/sh
# Launcher everything search — tracker + apps. Calculator lives in the shell extension.
# Uses gnome-shell extension search provider (see shell/launcher/extension.js)
Q=${1:-}
[ -z "$Q" ] && echo "Usage: launcher-search.sh <query>" && exit 1
# apps
for d in /usr/share/applications/*.desktop; do grep -qi "$Q" "$d" && basename "$d" .desktop; done | head -20
# files via tracker
tracker3 search --files 2>/dev/null | grep -i "$Q" | head -20 || echo "(tracker not indexed yet)"
# No eval: arbitrary-expression evaluation was removed (unreachable, and an injection sink).
