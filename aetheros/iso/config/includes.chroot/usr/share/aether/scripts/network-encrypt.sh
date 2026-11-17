#!/usr/bin/env bash
# AetherOS whole-stack network encryption policy CLI (headless, argv-only).
# --check reads config only; --apply writes under an explicit root; no network.
set -euo pipefail

HERE="${AETHER_NETWORK_SCRIPT_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)}"
CORE_PARENT="${AETHER_NETWORK_CORE_PARENT:-$(dirname -- "$HERE")}"
PYTHON="${AETHER_NETWORK_PYTHON:-python3}"

export AETHER_NETWORK_SCRIPT_DIR="$HERE"
export AETHER_NETWORK_CORE_PARENT="$CORE_PARENT"
export PYTHONPATH="${CORE_PARENT}${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON" -c 'from core.network import main; raise SystemExit(main())' "$@"
