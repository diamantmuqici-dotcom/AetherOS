#!/bin/sh
# Installer helper: format block devices as LUKS2 with tuned Argon2id KDF.
set -eu

usage() {
    printf '%s\n' \
        "usage: luks2-setup [--check] [--device DEV] [DEV]" \
        "  --check            read-only: report cryptsetup and mapping status" \
        "  --device DEV       target block device (or AETHER_DEVICE)" \
        "  AETHER_CONFIRM     must equal LUKS before any destructive write" \
        "  AETHER_SWAP_DEVICE optional device to encrypt for swap"
}

do_check() {
    if command -v cryptsetup >/dev/null 2>&1; then
        echo "cryptsetup: available ($(cryptsetup --version 2>/dev/null | head -n 1))"
    else
        echo "cryptsetup: unavailable"
    fi
    if [ -n "$device" ]; then
        if [ -b "$device" ]; then
            if command -v cryptsetup >/dev/null 2>&1; then
                if cryptsetup isLuks "$device" 2>/dev/null; then
                    echo "device: $device has a LUKS header"
                else
                    echo "device: $device has no LUKS header"
                fi
            fi
        else
            echo "device: $device is not a block device"
        fi
    else
        echo "device: none supplied (use --device or AETHER_DEVICE)"
    fi
    echo "active mappings:"
    found=0
    for mapping in /dev/mapper/*; do
        [ -e "$mapping" ] || continue
        echo "  $mapping"
        found=1
    done
    if [ "$found" -eq 0 ]; then echo "  (none)"; fi
}

mode=format
device=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --check) mode=check; shift ;;
        --help|-h) usage; exit 0 ;;
        --device)
            [ "$#" -ge 2 ] || { echo "luks2-setup: --device needs an argument" >&2; exit 2; }
            device="$2"; shift 2 ;;
        --device=*) device="${1#--device=}"; shift ;;
        -*)
            echo "luks2-setup: unknown option: $1" >&2
            usage >&2
            exit 2 ;;
        *)
            [ -z "$device" ] || { echo "luks2-setup: too many devices" >&2; exit 2; }
            device="$1"; shift ;;
    esac
done
if [ -z "$device" ]; then device="${AETHER_DEVICE:-}"; fi

if [ "$mode" = check ]; then
    do_check
    exit 0
fi

if [ "${AETHER_CONFIRM:-}" != "LUKS" ]; then
    echo "luks2-setup: set AETHER_CONFIRM=LUKS to authorize formatting" >&2
    exit 2
fi
if [ -z "$device" ]; then
    echo "luks2-setup: target device required (argv, --device, or AETHER_DEVICE)" >&2
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

swap_device="${AETHER_SWAP_DEVICE:-}"
if [ -n "$swap_device" ]; then
    if [ ! -b "$swap_device" ]; then
        echo "luks2-setup: AETHER_SWAP_DEVICE=$swap_device is not a block device" >&2
        exit 2
    fi
    keyfile=/crypto_keyfile.bin
    # Runtime keyfile lives on the encrypted target root, never in the ISO tree.
    umask 077
    dd if=/dev/urandom of="$keyfile" bs=512 count=8 status=none
    chmod 600 "$keyfile"
    chown root:root "$keyfile" 2>/dev/null || :
    cryptsetup luksFormat --type luks2 --pbkdf argon2id --iter-time "$iter_ms" \
        --key-file "$keyfile" "$swap_device"
    if [ -n "${AETHER_LUKS_UNLOCK_KEYFILE:-}" ]; then
        cryptsetup luksAddKey --key-file "$AETHER_LUKS_UNLOCK_KEYFILE" "$device" "$keyfile"
    else
        cryptsetup luksAddKey "$device" "$keyfile"
    fi
fi

printf '%s\n' \
    "LUKS2 header written to $device" \
    "External key handling (never embed key material in the image):" \
    "  1. Store the passphrase and any recovery key on separate physical media." \
    "  2. Verify the passphrase: cryptsetup luksOpen --test-passphrase $device" \
    "  3. Add or replace keys: cryptsetup luksAddKey $device" \
    "  4. Back up the header: cryptsetup luksHeaderBackup $device --header-backup-file <safe-path>"
if [ -n "$swap_device" ]; then
    printf '%s\n' \
        "Encrypted swap configured on $swap_device using /crypto_keyfile.bin (0600, root-only)." \
        "The keyfile is written on the installed root, not into the ISO payload." \
        "Ensure /crypto_keyfile.bin is referenced in crypttab for boot-time swap unlock."
fi
