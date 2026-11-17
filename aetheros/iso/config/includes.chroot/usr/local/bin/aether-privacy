#!/usr/bin/env bash
# AetherOS privacy enforcement: policy check, source audit and dconf lockdown.
# argv only; every value stays quoted. No dynamic command execution, no network.
set -euo pipefail

VERSION="aether-privacy 1.0"
SYSTEM_DCONF="/etc/dconf/db/aether.d/00-aether-privacy"
KEYFILE_NAME="00-aether-privacy"

usage() {
  printf 'usage: aether-privacy --check | --audit [root] | --apply [--dest PATH] [--force] | --version\n' >&2
}

core_root() {
  local here root
  here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  for root in "$here/.." "/usr/share/aether" "/usr/lib/aether"; do
    if [[ -f "$root/core/privacy/policy.py" ]]; then
      printf '%s\n' "$root"
      return 0
    fi
  done
  printf 'aether-privacy: privacy core not found\n' >&2
  return 1
}

default_target() {
  if [[ -n "${DEST:-}" ]]; then
    printf '%s\n' "$DEST"
  elif [[ "$EUID" -eq 0 ]]; then
    printf '%s\n' "$SYSTEM_DCONF"
  else
    printf '%s\n' "${HOME:-$PWD}/.config/dconf/$KEYFILE_NAME"
  fi
}

py_check() {
  python3 -c '
import json, pathlib, sys
root, dconf = sys.argv[1], pathlib.Path(sys.argv[2])
sys.path.insert(0, root)
from core.privacy.policy import ALLOWED_ENDPOINTS, PRIVACY_KEYS, render_dconf_keyfile
from core.privacy.audit import scan_sources
findings = scan_sources(pathlib.Path(root))
counts = {"INFO": 0, "MEDIUM": 0, "HIGH": 0}
for item in findings:
    counts[item["severity"]] = counts.get(item["severity"], 0) + 1
present = dconf.is_file()
matches = False
if present:
    try:
        matches = dconf.read_text(encoding="utf-8") == render_dconf_keyfile()
    except OSError:
        matches = False
report = {
    "privacy_keys": len(PRIVACY_KEYS),
    "allowlist": [{"host": host, "purpose": purpose} for host, purpose in ALLOWED_ENDPOINTS],
    "dconf": {"target": str(dconf), "present": present, "matches_policy": matches},
    "audit": {
        "scanned_root": str(root),
        "count": len(findings),
        "by_severity": counts,
        "findings": findings,
    },
}
print(json.dumps(report, sort_keys=True))
' "$1" "$2"
}

py_audit() {
  python3 -c '
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from core.privacy.audit import scan_sources
root = pathlib.Path(sys.argv[2])
findings = scan_sources(root)
print(json.dumps({"root": str(root), "count": len(findings), "findings": findings}, sort_keys=True))
' "$1" "$2"
}

py_render() {
  python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
from core.privacy.policy import render_dconf_keyfile
# Bytes on stdout keep LF endings on every host; text mode adds CRLF on Windows.
sys.stdout.buffer.write(render_dconf_keyfile().encode("utf-8"))
' "$1"
}

cmd_apply() {
  local root target parent tmp content
  root="$(core_root)"
  target="$(default_target)"
  parent="$(dirname -- "$target")"
  if [[ -e "$target" && "$FORCE" -ne 1 ]]; then
    printf 'aether-privacy: refusing to overwrite %s (use --force)\n' "$target" >&2
    return 1
  fi
  content="$(py_render "$root")"
  mkdir -p -- "$parent"
  tmp="$(mktemp "${parent}/${KEYFILE_NAME}.tmp.XXXXXX")"
  printf '%s\n' "$content" > "$tmp"
  chmod 0644 "$tmp"
  mv -f -- "$tmp" "$target"
  printf 'aether-privacy: wrote %s\n' "$target"
}

main() {
  local sub="${1:-}" root="" scan_root="" DEST="" FORCE=0
  case "$sub" in
    --version)
      shift
      [[ $# -eq 0 ]] || { usage; return 2; }
      printf '%s\n' "$VERSION"
      ;;
    --check)
      shift
      [[ $# -eq 0 ]] || { usage; return 2; }
      root="$(core_root)"
      py_check "$root" "$(default_target)"
      ;;
    --audit)
      shift
      [[ $# -le 1 ]] || { usage; return 2; }
      root="$(core_root)"
      if [[ $# -eq 1 ]]; then scan_root="$1"; else scan_root="$root"; fi
      py_audit "$root" "$scan_root"
      ;;
    --apply)
      shift
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --dest)
            [[ $# -ge 2 ]] || { usage; return 2; }
            DEST="$2"
            shift 2
            ;;
          --force)
            FORCE=1
            shift
            ;;
          *)
            usage
            return 2
            ;;
        esac
      done
      cmd_apply
      ;;
    *)
      usage
      return 2
      ;;
  esac
}

main "$@"
