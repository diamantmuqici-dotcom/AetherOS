#!/bin/sh
# Installer helper: format a block device as LUKS2 with tuned Argon2id KDF.
set -eu

if [ "${AETHER_CONFIRM:-}" != "LUKS" ]; then
    echo "luks2-setup: set AETHER_CONFIRM=LUKS to authorize formatting" >&2
    exit 2
fi

device="${1:-${AETHER_DEVICE:-}}"
if [ -z "$device" ]; then
    echo "luks2-setup: target device required (argv or AETHER_DEVICE)" >&2
    exit 2
fi
if [ ! -b "$device" ]; then
    echo "luks2-setup: $device is not a block device" >&2
    exit 2
fi

command -v cryptsetup >/dev/null 2>&1 || {
    echo "luks2-setup: cryptsetup not found" >&2
    exit 3
}

params_file="${AETHER_VAULT_PARAMS:-${HOME:-/root}/.config/aether/vault-params.json}"
iter_ms=250
if [ -f "$params_file" ]; then
    iter_ms="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(max(100, min(10000, int(d.get("measured_ms", 250)))))' "$params_file")"
fi

cryptsetup luksFormat --type luks2 --pbkdf argon2id --iter-time "$iter_ms" "$device"

printf '%s\n' \
    "LUKS2 header written to $device" \
    "Recovery key handling:" \
    "  1. Store the passphrase and the generated recovery key on separate physical media." \
    "  2. Verify the passphrase: cryptsetup luksOpen --test-passphrase $device" \
    "  3. Add or replace keys: cryptsetup luksAddKey $device" \
    "  4. Back up the header: cryptsetup luksHeaderBackup $device --header-backup-file <safe-path>"
