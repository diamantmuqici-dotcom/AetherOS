#!/usr/bin/env bash
# Headless LUKS2 FDE verifier. Emits canonical JSON; never prints key material.
set -euo pipefail

VERSION="1.0.0"

usage() {
    printf '%s\n' \
        "usage: aether-fde-verify [--check | --self-test | --version]" \
        "  --check                 read cryptsetup luksDump and emit canonical JSON" \
        "    --device DEV          device to inspect (or AETHER_DEVICE)" \
        "    --bootloader-encrypted  assert the ESP/boot chain is protected" \
        "    --swap-encrypted      assert swap is encrypted" \
        "    --keyfile-external    assert key material is off-image" \
        "  --self-test             run pure helper assertions (no cryptsetup needed)" \
        "  --version               print version and exit"
}

# Locate core/fde from source tree, chroot payload, or /usr/local/bin launcher.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
module_root=""
for root in "$script_dir/.." "/usr/share/aether" "$script_dir/../share/aether"; do
    if [ -f "$root/core/fde/status.py" ]; then module_root="$root"; break; fi
done

mode=""
device="${AETHER_DEVICE:-}"
bootloader=0
swap=0
keyext=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check) mode=check; shift ;;
        --self-test) mode=selftest; shift ;;
        --version) printf 'aether-fde-verify %s\n' "$VERSION"; exit 0 ;;
        --help|-h) usage; exit 0 ;;
        --device)
            [ "$#" -ge 2 ] || { echo "fde-verify: --device needs an argument" >&2; exit 2; }
            device="$2"; shift 2 ;;
        --device=*) device="${1#--device=}"; shift ;;
        --bootloader-encrypted) bootloader=1; shift ;;
        --swap-encrypted) swap=1; shift ;;
        --keyfile-external) keyext=1; shift ;;
        *)
            echo "fde-verify: unknown option: $1" >&2
            usage >&2
            exit 2 ;;
    esac
done

if [ "${AETHER_FDE_BOOTLOADER:-0}" = "1" ]; then bootloader=1; fi
if [ "${AETHER_FDE_SWAP:-0}" = "1" ]; then swap=1; fi
if [ "${AETHER_FDE_KEY_EXTERNAL:-0}" = "1" ]; then keyext=1; fi

run_selftest() {
    if [ -z "$module_root" ]; then
        echo "fde-verify: core/fde/status.py not found" >&2
        return 1
    fi
    PYTHONPATH="$module_root" python3 - <<'PY'
import json
from core.fde.status import (
    REQUIRED_LUKS2_FLAGS,
    fde_status,
    parse_luks_dump,
    render_report,
)

SAMPLE = """LUKS header information for /dev/nvme0n1p3

Version:       	2
UUID:          	2f6f0c2a-9b1d-4c3e-8f7a-1d2e3f4a5b6c
Data segments:
  0: crypt
	cipher: aes-xts-plain64
Keyslots:
  0: luks2
	PBKDF:      	argon2id
	Iteration:  	4
  1: luks2
	PBKDF:      	argon2id
	Iteration:  	4
"""

p = parse_luks_dump(SAMPLE)
assert p["version"] == 2, "version parse"
assert p["cipher"] == "aes-xts-plain64", "cipher parse"
assert p["pbkdf"] == "argon2id", "pbkdf parse"
assert p["iterations"] == 4, "iteration parse"
assert p["keyslots_enabled"] == 2, "slot count"
assert p["uuid"].startswith("2f6f0c2a"), "uuid parse"

good = fde_status(SAMPLE, True, True, True)
assert good["overall"] == "FDE_STRONG", "all good"
partial = fde_status(SAMPLE, False, False, True)
assert partial["overall"] == "FDE_PARTIAL", "partial coverage"
empty = fde_status("", False, False, False)
assert empty["overall"] == "NOT_ENCRYPTED", "no header"
no_ext = fde_status(SAMPLE, True, True, False)
assert "key material stored in image" in " ".join(no_ext["gaps"]), "external key gap"
assert render_report(good) == json.dumps(
    good, sort_keys=True, separators=(",", ":")
), "canonical json"
assert REQUIRED_LUKS2_FLAGS == ("--type luks2", "--pbkdf argon2id"), "flags"

print("fde-verify self-test: 13 assertions passed")
PY
}

run_check() {
    reason=""
    dump=""
    if [ -z "$module_root" ]; then
        reason="core/fde/status.py not found"
    elif ! command -v cryptsetup >/dev/null 2>&1; then
        reason="cryptsetup unavailable"
    elif [ -z "$device" ]; then
        reason="no device supplied"
    elif [ ! -b "$device" ]; then
        reason="device is not a block device: $device"
    else
        dump="$(cryptsetup luksDump "$device" 2>/dev/null)" \
            || reason="cryptsetup luksDump failed for $device"
    fi

    rc=0
    if [ -n "$reason" ]; then rc=1; fi
    printf '%s' "$dump" | PYTHONPATH="$module_root" python3 - \
        "$bootloader" "$swap" "$keyext" "$reason" <<'PY'
import sys
from core.fde.status import fde_status, render_report

boot, swp, ext, reason = sys.argv[1:5]
report = fde_status(sys.stdin.read(), boot == "1", swp == "1", ext == "1")
if reason:
    report["reason"] = reason
print(render_report(report))
PY
    return "$rc"
}

case "$mode" in
    check) run_check ;;
    selftest) run_selftest ;;
    *) usage >&2; exit 2 ;;
esac
