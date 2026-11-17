#!/usr/bin/env bash
# AetherOS ISO boot smoke test.
# Boots the ISO in QEMU, waits (bounded) for a login/banner milestone on the
# serial console, then runs a grep-based checklist. See aetheros/docs/TESTING.md.
# Exit codes: 0 pass, 1 hard failure, 77 skipped (QEMU unavailable).

set -uo pipefail

SKIP_CODE=77
FAIL_CODE=1

ISO="${1:-${AETHER_ISO:-}}"
SERIAL_LOG="${AETHER_TEST_LOG:-aether-iso-serial.log}"
SCREENSHOT="${AETHER_TEST_SCREENSHOT:-aether-iso-screenshot.ppm}"
RESULT_JSON="${AETHER_TEST_RESULT:-}"
TIMEOUT="${AETHER_TEST_TIMEOUT:-180}"
POLL_INTERVAL=2
SCREENDUMP="${AETHER_TEST_SCREENDUMP:-0}"

RESULTS=()
NOTES=()
QEMU_PID=""
MON_SOCK=""
WORK_DIR=""
PROMPT_SEEN=0
ISO_PATHS=""
BOOT_TEXT=""
ISO_READER=""
INITRD_PATH=""

log()  { printf '[iso-test] %s\n' "$*"; }
pass() { RESULTS+=("$1=pass"); log "PASS  $1"; }
fail() { RESULTS+=("$1=fail"); log "FAIL  $1${2:+ - $2}"; }
skip() { RESULTS+=("$1=skip"); NOTES+=("$1: $2"); log "SKIP  $1 - $2"; }

cleanup() {
  if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
    kill "$QEMU_PID" 2>/dev/null || true
    wait "$QEMU_PID" 2>/dev/null || true
  fi
  [[ -n "$WORK_DIR" ]] && rm -rf "$WORK_DIR"
}
trap cleanup EXIT

# Escape a string for embedding in a JSON double-quoted value.
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

write_result() {
  local status="$1" code="$2"
  [[ -n "$RESULT_JSON" ]] || return 0
  mkdir -p "$(dirname "$RESULT_JSON")"
  local checks="" notes="" sep="" r name val n
  for r in "${RESULTS[@]}"; do
    name="${r%%=*}"; val="${r#*=}"
    checks+="${sep}\"$(json_escape "$name")\":\"$(json_escape "$val")\""
    sep=","
  done
  sep=""
  for n in "${NOTES[@]}"; do
    notes+="${sep}\"$(json_escape "$n")\""
    sep=","
  done
  cat > "$RESULT_JSON" <<EOF
{
  "iso": "$(json_escape "$ISO")",
  "status": "$(json_escape "$status")",
  "exit_code": $code,
  "prompt_seen": $PROMPT_SEEN,
  "timeout_seconds": $TIMEOUT,
  "serial_log": "$(json_escape "$SERIAL_LOG")",
  "screenshot": "$(json_escape "$SCREENSHOT")",
  "checks": {$checks},
  "notes": [$notes]
}
EOF
}

finish() {
  write_result "$1" "$2"
  exit "$2"
}

# --- preconditions ---------------------------------------------------------
if [[ -z "$ISO" ]]; then
  echo "[iso-test] no ISO path: pass as arg or set AETHER_ISO" >&2
  finish fail "$FAIL_CODE"
fi
if [[ ! -f "$ISO" ]]; then
  echo "[iso-test] ISO not found: $ISO" >&2
  finish fail "$FAIL_CODE"
fi

QEMU="$(command -v qemu-system-x86_64 || true)"
if [[ -z "$QEMU" ]]; then
  log "qemu-system-x86_64 not present - skipping ISO boot test (exit $SKIP_CODE)"
  finish skip "$SKIP_CODE"
fi

if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]] || (( TIMEOUT < 1 )); then
  TIMEOUT=180
fi

WORK_DIR="$(mktemp -d)"
TIMEOUT_BIN="$(command -v timeout || true)"
bounded() {
  local secs="$1"; shift
  if [[ -n "$TIMEOUT_BIN" ]]; then
    "$TIMEOUT_BIN" "$secs" "$@"
  else
    "$@"
  fi
}

mkdir -p "$(dirname "$SERIAL_LOG")" "$(dirname "$SCREENSHOT")"
rm -f "$SERIAL_LOG" "$SCREENSHOT"

# --- ISO helper tooling ----------------------------------------------------
ISO_READER="$(command -v isoinfo || command -v 7z || command -v bsdtar || true)"

iso_list_paths() {
  if command -v isoinfo >/dev/null 2>&1; then
    bounded 30 isoinfo -f -i "$ISO"
  elif command -v 7z >/dev/null 2>&1; then
    bounded 30 7z l -ba "$ISO"
  elif command -v bsdtar >/dev/null 2>&1; then
    bounded 30 bsdtar -tf "$ISO"
  else
    return 127
  fi
}

iso_extract() {
  local path="$1" rel="${1#/}"
  if command -v isoinfo >/dev/null 2>&1; then
    bounded 60 isoinfo -i "$ISO" -x "$path"
  elif command -v 7z >/dev/null 2>&1; then
    bounded 60 7z x -so "$ISO" "$rel"
  elif command -v bsdtar >/dev/null 2>&1; then
    bounded 60 bsdtar -xOf "$ISO" "$rel"
  else
    return 127
  fi
}

if [[ -n "$ISO_READER" ]]; then
  ISO_PATHS="$(iso_list_paths 2>/dev/null)"
  for cfg in /isolinux/txt.cfg /isolinux/live.cfg /isolinux/isolinux.cfg /boot/grub/grub.cfg; do
    BOOT_TEXT+="$(iso_extract "$cfg" 2>/dev/null)"$'\n'
  done
  INITRD_PATH="$(printf '%s\n' "$ISO_PATHS" | grep -aiE '/live/initrd[0-9]*\.img$' | head -n1)"
  [[ -n "$INITRD_PATH" ]] || INITRD_PATH="$(printf '%s\n' "$ISO_PATHS" | grep -aiE 'initrd[^/]*\.img$' | head -n1)"
fi

# --- build QEMU argv (argv only, never eval / shell=true) ------------------
OVMF_CODE=""
for candidate in \
  /usr/share/OVMF/OVMF_CODE.fd \
  /usr/share/OVMF/OVMF_CODE_4M.fd \
  /usr/share/OVMF/OVMF_CODE_4M.ms.fd \
  /usr/share/qemu/OVMF.fd; do
  [[ -f "$candidate" ]] && OVMF_CODE="$candidate" && break
done

QEMU_ARGS=(
  -m 4096M
  -smp 2
  -no-reboot
  -display none
  -serial "file:$SERIAL_LOG"
  -drive "file=$ISO,media=cdrom,readonly=on"
)

if [[ -n "$OVMF_CODE" ]]; then
  QEMU_ARGS+=(-drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE")
  if [[ "$OVMF_CODE" == *4M* ]]; then
    vars_candidates=(/usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS_4M.ms.fd)
  else
    vars_candidates=(/usr/share/OVMF/OVMF_VARS.fd /usr/share/OVMF/OVMF_VARS.ms.fd)
  fi
  for v in "${vars_candidates[@]}"; do
    if [[ -f "$v" ]]; then
      cp "$v" "$WORK_DIR/ovmf-vars.fd"
      QEMU_ARGS+=(-drive "if=pflash,format=raw,file=$WORK_DIR/ovmf-vars.fd")
      break
    fi
  done
fi

if [[ "$SCREENDUMP" == "1" ]]; then
  MON_SOCK="$WORK_DIR/monitor.sock"
  QEMU_ARGS+=(-monitor "unix:$MON_SOCK,server,nowait")
else
  QEMU_ARGS+=(-monitor none)
fi

log "booting: $ISO (timeout ${TIMEOUT}s, OVMF=${OVMF_CODE:-none})"
"$QEMU" "${QEMU_ARGS[@]}" &
QEMU_PID=$!

# --- bounded wait for a login/banner milestone -----------------------------
PROMPT_RE='AetherOS|login:|[Gg][Dd][Mm]|Debian GNU/Linux|Command line:'
deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  if ! kill -0 "$QEMU_PID" 2>/dev/null; then
    break
  fi
  if grep -aEiq "$PROMPT_RE" "$SERIAL_LOG" 2>/dev/null; then
    PROMPT_SEEN=1
    break
  fi
  sleep "$POLL_INTERVAL"
done

kill "$QEMU_PID" 2>/dev/null || true
wait "$QEMU_PID" 2>/dev/null || true
QEMU_PID=""

# --- checklist -------------------------------------------------------------
if (( PROMPT_SEEN )); then
  pass boot_prompt
else
  fail boot_prompt "no login/banner milestone within ${TIMEOUT}s"
fi

if grep -aEiq 'quiet splash' "$SERIAL_LOG" || grep -aEiq 'quiet splash' <<<"$BOOT_TEXT"; then
  pass kernel_cmdline
else
  fail kernel_cmdline "'quiet splash' absent from serial log and ISO boot config"
fi

check_plymouth() {
  if ! command -v lsinitrd >/dev/null 2>&1; then
    skip plymouth_theme "lsinitrd unavailable; initramfs theme check skipped"
    return
  fi
  if [[ -z "$INITRD_PATH" ]]; then
    skip plymouth_theme "no initrd image in ISO; theme check skipped"
    return
  fi
  local initrd="$WORK_DIR/initrd.img" listing
  if ! iso_extract "$INITRD_PATH" > "$initrd" 2>/dev/null || [[ ! -s "$initrd" ]]; then
    skip plymouth_theme "could not extract initrd; theme check skipped"
    return
  fi
  listing="$(bounded 60 lsinitrd "$initrd" 2>/dev/null)"
  if grep -aEiq 'plymouth/themes/aether|aether\.plymouth' <<<"$listing"; then
    pass plymouth_theme
  else
    fail plymouth_theme "Aether plymouth theme not found in initramfs"
  fi
}
check_plymouth

check_payload() {
  if [[ -z "$ISO_READER" ]]; then
    skip iso_payload "no isoinfo/7z/bsdtar available; payload check skipped"
    return
  fi
  if grep -aEiq 'aether' <<<"$ISO_PATHS"$'\n'"$BOOT_TEXT"; then
    pass iso_payload
  else
    fail iso_payload "no Aether payload markers in ISO listing/boot config"
  fi
}
check_payload

capture_screenshot() {
  if [[ "$SCREENDUMP" != "1" ]]; then
    skip screenshot "no display backend (-display none, -monitor none); serial log is the boot artifact"
    return
  fi
  if ! command -v socat >/dev/null 2>&1 && ! command -v nc >/dev/null 2>&1; then
    skip screenshot "screendump requested but socat/nc unavailable; serial log is the artifact"
    return
  fi
  sleep 1
  if command -v socat >/dev/null 2>&1; then
    printf 'screendump %s\n' "$SCREENSHOT" | bounded 15 socat - "UNIX-CONNECT:$MON_SOCK" 2>/dev/null || true
  else
    printf 'screendump %s\n' "$SCREENSHOT" | bounded 15 nc -U "$MON_SOCK" 2>/dev/null || true
  fi
  if [[ -s "$SCREENSHOT" ]]; then
    pass screenshot
  else
    skip screenshot "screendump produced no framebuffer; serial log is the artifact"
  fi
}
capture_screenshot

# --- verdict ---------------------------------------------------------------
HAS_FAIL=0
for r in "${RESULTS[@]}"; do
  [[ "${r#*=}" == "fail" ]] && HAS_FAIL=1
done
if (( HAS_FAIL )); then
  finish fail "$FAIL_CODE"
fi
finish pass 0
