#!/usr/bin/env bash
# Tune Argon2id for this host and persist the chosen parameters (0600).
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -f /usr/share/aether/vault/benchmark.py ]; then
    bench=/usr/share/aether/vault/benchmark.py
else
    bench="$script_dir/../core/vault/benchmark.py"
fi
if [ ! -f "$bench" ]; then
    echo "aether-tune-vault: benchmark.py not found" >&2
    exit 3
fi

target_ms="${1:-250}"
case "$target_ms" in
    ''|*[!0-9.]*) echo "usage: aether-tune-vault [target_ms]" >&2; exit 2 ;;
esac

if command -v timeout >/dev/null 2>&1; then
    raw="$(timeout 30 python3 "$bench" --json --target-ms "$target_ms")"
else
    raw="$(python3 "$bench" --json --target-ms "$target_ms")"
fi

config_dir="${HOME:-/root}/.config/aether"
config_file="$config_dir/vault-params.json"
mkdir -p "$config_dir"
tmp="$(mktemp "$config_dir/.vault-params.XXXXXX")"
chmod 600 "$tmp"
printf '%s\n' "$raw" > "$tmp"
mv -f "$tmp" "$config_file"

printf '%s' "$raw" | python3 -c 'import json,sys; print(json.load(sys.stdin)["recommendation"])'
