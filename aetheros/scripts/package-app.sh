#!/usr/bin/env bash
# Package a single Aether app into a release-ready bundle.
#
# These apps are native AetherOS components: Python 3 + PyGObject (GTK4 +
# libadwaita). They ship as part of the AetherOS ISO and also as standalone
# bundles for people running a GNOME/GTK4 Linux desktop outside AetherOS.
# This script produces one honestly-labeled artifact per app instead of
# pretending there are real Windows/macOS/Android builds.
#
# Usage: package-app.sh <id> "<Display Name>" <source-dir> [desktop-file]
set -euo pipefail

ID="${1:?usage: package-app.sh <id> \"<Display Name>\" <source-dir> [desktop-file]}"
NAME="${2:?display name required}"
SRC="${3:?source dir required}"
DESKTOP_FILE="${4:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="dist/$ID"
BUNDLE="$OUT/Aether${NAME// /}-linux-x86_64"

rm -rf "$OUT"
mkdir -p "$BUNDLE"

cp -r "$SRC"/. "$BUNDLE/"

ENTRY="$(find "$SRC" -maxdepth 1 -name 'aether-*.py' | sort | head -n1)"
ENTRY_NAME="$(basename "${ENTRY:-aether-$ID.py}")"

cat > "$BUNDLE/run.sh" <<SH
#!/usr/bin/env bash
# Launches Aether $NAME. Requires Python 3 + PyGObject (GTK4, libadwaita 1).
# Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
set -euo pipefail
DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
exec python3 "\$DIR/$ENTRY_NAME" "\$@"
SH
chmod +x "$BUNDLE/run.sh"

if [ -n "$DESKTOP_FILE" ] && [ -f "$ROOT/$DESKTOP_FILE" ]; then
  cp "$ROOT/$DESKTOP_FILE" "$BUNDLE/"
fi

cat > "$BUNDLE/README.md" <<MD
# Aether $NAME

Part of [AetherOS](https://github.com/diamantmuqici-dotcom/AetherOS) — ships
preinstalled on AetherOS. This bundle lets you run it standalone on any
GNOME/GTK4 Linux desktop.

## Requirements

- Python 3.9+
- PyGObject with GTK4 and libadwaita 1 (\`python3-gi gir1.2-gtk-4.0 gir1.2-adw-1\` on Debian/Ubuntu)

## Run

\`\`\`sh
./run.sh
\`\`\`

Not Linux/GTK? Aether $NAME is a native AetherOS component, not a
cross-platform binary — there is no Windows, macOS, or Android build. Install
AetherOS itself to get it (and everything else) preinstalled; see the main
README for ISO downloads.

Source: \`$SRC\` in the AetherOS repo. License: MIT (same as AetherOS).
MD

(cd "$OUT" && zip -rq "$(basename "$BUNDLE").zip" "$(basename "$BUNDLE")")
rm -rf "$BUNDLE"
sha256sum "$OUT"/*.zip > "$OUT"/SHA256SUMS
ls -lh "$OUT"
