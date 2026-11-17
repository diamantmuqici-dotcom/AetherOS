#!/usr/bin/env bash
# Aether Doctor - read-only diagnostics for the preinstalled Aether app suite.
# No writes, no chmod, no service changes. argv only (--json).
set -uo pipefail

BIN=/usr/local/bin
APPDIR=/usr/share/applications
EXT_DIR=/usr/share/gnome-shell/extensions/animations@aether
PLYMOUTH_THEME=/usr/share/plymouth/themes/aether
SIGNING_KEY=/usr/share/aether/updates/aether-release.pub.pem
VAULT_CORE=/usr/share/aether/core/vault/secure_vault.py
VAULT_APP=/usr/share/aether/aether-vault.py

JSON=0
[ "${1:-}" = "--json" ] && JSON=1

TIMEOUT_BIN="$(command -v timeout 2>/dev/null || true)"

# Bounded external command; argv only, never a shell string.
run_limited() {
  if [ -n "$TIMEOUT_BIN" ]; then
    "$TIMEOUT_BIN" 8 "$@" 2>/dev/null
  else
    "$@" 2>/dev/null
  fi
}

# Escape fixed, bounded detail strings for JSON output.
json_escape() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n' ' '
}

IDS=(); STATUSES=(); DETAILS=(); FIXES=()
add_check() {
  IDS+=("$1"); STATUSES+=("$2"); DETAILS+=("$3"); FIXES+=("$4")
}

# 1. Browser engine.
found=""
for c in chromium chromium-browser firefox firefox-esr; do
  if command -v "$c" >/dev/null 2>&1; then found="$c"; break; fi
done
if [ -n "$found" ]; then
  add_check browser_engine PASS "found $found on PATH" ""
else
  add_check browser_engine FAIL "none of chromium chromium-browser firefox firefox-esr on PATH" "aether-fix"
fi

# 2. Mail engine.
found=""
for c in thunderbird geary; do
  if command -v "$c" >/dev/null 2>&1; then found="$c"; break; fi
done
if [ -n "$found" ]; then
  add_check mail_engine PASS "found $found on PATH" ""
else
  add_check mail_engine FAIL "none of thunderbird geary on PATH" "aether-fix"
fi

# 3. Animations shell extension.
if [ -d "$EXT_DIR" ]; then
  add_check animations_extension PASS "$EXT_DIR present" ""
else
  add_check animations_extension FAIL "$EXT_DIR MISSING" "aether-animations full"
fi

# 4. Plymouth boot theme.
if [ -f "$PLYMOUTH_THEME/aether.plymouth" ] || [ -d "$PLYMOUTH_THEME" ]; then
  add_check plymouth_theme PASS "aether theme present at $PLYMOUTH_THEME" ""
else
  add_check plymouth_theme FAIL "$PLYMOUTH_THEME MISSING" "aether-fix"
fi

# 5. Desktop Exec targets (same resolution rules as aether-fix, read-only).
missing=0
first_missing=""
for file in "$APPDIR"/aether-*.desktop "$APPDIR"/org.aether.*.desktop; do
  [ -f "$file" ] || continue
  exec_line="$(sed -n 's/^Exec=//p' "$file" | head -n1)"
  [ -n "$exec_line" ] || continue
  cmd="${exec_line%% *}"
  bad=""
  if [ "${cmd#/}" != "$cmd" ]; then
    [ -x "$cmd" ] || bad="missing target: $(basename "$file") -> $cmd"
  elif command -v "$cmd" >/dev/null 2>&1; then
    :
  elif [ -x "$BIN/$cmd" ]; then
    :
  else
    bad="missing launcher: $(basename "$file") -> $cmd"
  fi
  if [ -n "$bad" ]; then
    missing=$((missing + 1))
    [ -z "$first_missing" ] && first_missing="$bad"
  fi
  for token in $exec_line; do
    case "$token" in
      /*)
        if [ ! -e "$token" ]; then
          missing=$((missing + 1))
          [ -z "$first_missing" ] && first_missing="missing file: $(basename "$file") -> $token"
        fi
        ;;
    esac
  done
done
if [ "$missing" -eq 0 ]; then
  add_check desktop_targets PASS "all desktop Exec targets resolve" ""
else
  add_check desktop_targets FAIL "$missing unresolved desktop target(s); first: $first_missing" "aether-fix"
fi

# 6. Vault module.
if [ -f "$VAULT_CORE" ] || [ -f "$VAULT_APP" ]; then
  add_check vault_module PASS "vault module present ($VAULT_CORE, $VAULT_APP)" ""
else
  add_check vault_module FAIL "vault module MISSING ($VAULT_CORE, $VAULT_APP)" "aether-tune-vault"
fi

# 7. Update signing key (report only; never create).
if [ -f "$SIGNING_KEY" ]; then
  add_check signature_key PASS "$SIGNING_KEY present" ""
else
  add_check signature_key FAIL "$SIGNING_KEY MISSING" "restore the Aether release public key"
fi

# 8. AppArmor status (bounded aa-status call).
if ! command -v aa-status >/dev/null 2>&1; then
  add_check apparmor SKIP "aa-status not available" ""
else
  aa_out="$(run_limited aa-status)"
  if [ -z "$aa_out" ]; then
    add_check apparmor SKIP "aa-status returned no output" ""
  else
    loaded=0; enforce=0
    while IFS= read -r line; do
      case "$line" in
        *"profiles are loaded"*) loaded="${line%% *}" ;;
        *"profiles are in enforce mode"*) enforce="${line%% *}" ;;
      esac
    done <<< "$aa_out"
    case "$loaded" in ''|*[!0-9]*) loaded=0 ;; esac
    case "$enforce" in ''|*[!0-9]*) enforce=0 ;; esac
    detail="$loaded profiles loaded, $enforce enforcing"
    if [ "$loaded" -gt 0 ]; then
      add_check apparmor PASS "$detail" ""
    else
      add_check apparmor FAIL "$detail" "aether-fix"
    fi
  fi
fi

# 9. Pending security upgrades (bounded apt-get simulation, parse only).
if ! command -v apt-get >/dev/null 2>&1; then
  add_check security_upgrades SKIP "apt-get not available" ""
else
  up_out="$(run_limited apt-get -s upgrade)"
  if [ -z "$up_out" ]; then
    add_check security_upgrades SKIP "apt-get simulation unavailable" ""
  else
    total=0; sec=0
    while IFS= read -r line; do
      case "$line" in
        "Inst "*)
          total=$((total + 1))
          case "$line" in *-security*) sec=$((sec + 1)) ;; esac
          ;;
      esac
    done <<< "$up_out"
    if [ "$sec" -gt 0 ]; then
      add_check security_upgrades FAIL "$sec security upgrade(s) pending ($total total)" "aether-updater --check"
    else
      add_check security_upgrades PASS "0 security upgrades pending ($total total pending)" ""
    fi
  fi
fi

# Counters and overall state.
PASSES=0; FAILS=0; SKIPS=0
for s in "${STATUSES[@]}"; do
  case "$s" in
    PASS) PASSES=$((PASSES + 1)) ;;
    FAIL) FAILS=$((FAILS + 1)) ;;
    SKIP) SKIPS=$((SKIPS + 1)) ;;
  esac
done
OVERALL=ok
[ "$FAILS" -gt 0 ] && OVERALL=fail

emit_row_json() {
  local i="$1"
  printf '  "%s": {"detail": "%s", "fix": "%s", "status": "%s"}' \
    "${IDS[$i]}" "$(json_escape "${DETAILS[$i]}")" \
    "$(json_escape "${FIXES[$i]}")" "${STATUSES[$i]}"
}

emit_summary_json() {
  printf '  "summary": {"fail": %d, "pass": %d, "skip": %d, "status": "%s"}' \
    "$FAILS" "$PASSES" "$SKIPS" "$OVERALL"
}

# Row lookup by stable check id for sort_keys-style JSON output.
row_index() {
  local want="$1" i
  for i in "${!IDS[@]}"; do
    if [ "${IDS[$i]}" = "$want" ]; then printf '%s' "$i"; return 0; fi
  done
  printf '%s' "-1"
}

emit_json() {
  local key first=1 idx
  printf '{\n'
  for key in animations_extension apparmor browser_engine desktop_targets mail_engine plymouth_theme security_upgrades signature_key summary vault_module; do
    [ "$first" -eq 0 ] && printf ',\n'
    if [ "$key" = "summary" ]; then
      emit_summary_json
    else
      idx="$(row_index "$key")"
      emit_row_json "$idx"
    fi
    first=0
  done
  printf '\n}\n'
}

emit_text() {
  local i
  for i in "${!IDS[@]}"; do
    printf 'CHECK: %s: %s — %s\n' "${IDS[$i]}" "${STATUSES[$i]}" "${DETAILS[$i]}"
  done
  printf 'FIX:\n'
  for i in "${!IDS[@]}"; do
    [ "${STATUSES[$i]}" = "FAIL" ] && printf '%s\n' "${FIXES[$i]}"
  done
}

if [ "$JSON" -eq 1 ]; then
  emit_json
else
  emit_text
fi

[ "$FAILS" -eq 0 ]
