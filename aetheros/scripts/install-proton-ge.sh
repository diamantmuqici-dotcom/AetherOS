#!/usr/bin/env bash
# Install Proton-GE (runtime fetch, not bundled). Prints honest compatibility note.
set -euo pipefail
echo "Proton-GE is fetched at runtime by Steam (Compatibility > GE-Proton). No universal compatibility promised."
echo "See: https://github.com/GloriousEggroll/proton-ge-custom (GloriousEggroll releases)."
echo "Steam will prompt to download selected Proton version on first game launch."
