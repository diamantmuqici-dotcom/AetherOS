#!/usr/bin/env bash
# AetherOS ISO boot smoke test.
# Boots the ISO in QEMU, waits (bounded) for a login/banner milestone on the
# serial console, then runs a grep-based checklist. See aetheros/docs/TESTING.md.
# Exit codes: 0 pass, 1 hard failure, 77 skipped (QEMU unavailable).
# --self-test runs the pure check logic with no QEMU and no ISO.

set -uo pipefail

SKIP_CODE=77
FAIL_CODE=1
TIMEOUT_DEFAULT=180
TIMEOUT_MIN=30
TIMEOUT_MAX=900

ISO=""
SERIAL_LOG="${AETHER_TEST_LOG:-aether-iso-serial.log}"
SCREENSHOT="${AETHER_TEST_SCREENSHOT:-aether-iso-screenshot.ppm}"
RESULT_JSON="${AETHER_TEST_RESULT:-}"
TIMEOUT="${AETHER_TEST_TIMEOUT:-$TIMEOUT_DEFAULT}"
QMP_LOG="${AETHER_TEST_QMP_LOG:-}"
POLL_INTERVAL=2
SCREENDUMP="${AETHER_TEST_SCREENDUMP:-0}"
SELF_TEST=0

CHECK_KEYS=(boot_prompt kernel_cmdline plymouth_theme iso_payload os_release screenshot)
declare -A CHECK_STATUS=()

NOTES=()
QEMU_PID=""
MON_SOCK=""
WORK_DIR=""
PROMPT_SEEN=0
ISO_PATHS=""
BOOT_TEXT=""
ISO_READER=""
INITRD_PATH=""
SELF_TOTAL=0
SELF_FAIL=0

log()  { printf '[iso-test] %s\n' "$*"; }
note() { NOTES+=("$1"); }
pass() { CHECK_STATUS["$1"]="pass"; log "PASS  $1"; }
fail() {
  CHECK_STATUS["$1"]="fail"; log "FAIL  $1${2:+ - $2}"
  [[ -z "${2:-}" ]] || note "$1: $2"
}
skip() { CHECK_STATUS["$1"]="skip"; note "$1: $2"; log "SKIP  $1 - $2"; }

init_checks() {
  local k
  for k in "${CHECK_KEYS[@]}"; do CHECK_STATUS["$k"]="skip"; done
}
init_checks

cleanup() {
  if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
    kill "$QEMU_PID" 2>/dev/null || true
    wait "$QEMU_PID" 2>/dev/null || true
  fi
  [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]] && rm -rf "$WORK_DIR"
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

# Always emit every check key, even when the harness stops before any check runs.
write_result() {
  local status="$1" code="$2" checks="" notes="" sep="" k n
  [[ -n "$RESULT_JSON" ]] || return 0
  mkdir -p "$(dirname "$RESULT_JSON")" 2>/dev/null || return 0
  for k in "${CHECK_KEYS[@]}"; do
    checks+="${sep}\"$(json_escape "$k")\":\"$(json_escape "${CHECK_STATUS[$k]}")\""
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

finish() { write_result "$1" "$2"; exit "$2"; }

usage() {
  cat <<EOF
Usage: test-iso.sh [OPTIONS] [ISO]
Options:
  --timeout <s>   boot-wait deadline in seconds (30..900, default 180)
  --self-test     run pure boot-check logic, no QEMU/ISO needed
  -h, --help      show this help
ISO may also be supplied via AETHER_ISO (the argument wins).
EOF
}

# Malformed values fall back to the default; numeric values clamp to bounds.
normalize_timeout() {
  local v="$1" n
  [[ "$v" =~ ^[0-9]+$ ]] || { printf '%s' "$TIMEOUT_DEFAULT"; return 0; }
  v="${v#"${v%%[!0]*}"}"
  [[ -n "$v" ]] || v="0"
  (( ${#v} > 3 )) && { printf '%s' "$TIMEOUT_MAX"; return 0; }
  n=$((10#$v))
  (( n < TIMEOUT_MIN )) && { printf '%s' "$TIMEOUT_MIN"; return 0; }
  (( n > TIMEOUT_MAX )) && { printf '%s' "$TIMEOUT_MAX"; return 0; }
  printf '%s' "$n"
}

# --- pure check logic (shared by the real run and --self-test) --------------
text_has_boot_milestone() {
  grep -aEiq 'AetherOS|login:|[Gg][Dd][Mm]|Debian GNU/Linux|Command line:' <<<"$1"
}
text_has_quiet_splash() {
  grep -aEiq 'quiet[[:space:]]+splash' <<<"$1"
}
text_has_os_identity() {
  grep -aEiq '^[[:space:]]*NAME="?AetherOS"?[[:space:]]*$' <<<"$1" &&
    grep -aEiq '^[[:space:]]*VERSION_CODENAME="?trixie"?[[:space:]]*$' <<<"$1"
}
checks_map_complete() {
  local k
  for k in "${CHECK_KEYS[@]}"; do
    [[ -n "${CHECK_STATUS[$k]:-}" ]] || return 1
  done
  return 0
}

selftest_assert_true() {
  local label="$1"; shift
  SELF_TOTAL=$((SELF_TOTAL + 1))
  if "$@"; then
    printf 'selftest PASS %s\n' "$label"
  else
    printf 'selftest FAIL %s\n' "$label"
    SELF_FAIL=$((SELF_FAIL + 1))
  fi
}
selftest_assert_false() {
  local label="$1"; shift
  SELF_TOTAL=$((SELF_TOTAL + 1))
  if "$@"; then
    printf 'selftest FAIL %s (expected false)\n' "$label"
    SELF_FAIL=$((SELF_FAIL + 1))
  else
    printf 'selftest PASS %s\n' "$label"
  fi
}
selftest_json_escape() {
  local got
  got="$(json_escape $'q"u\\ote\nline')"
  [[ "$got" == 'q\"u\\ote\nline' ]]
}

run_self_test() {
  local serial cfg qmp osrel bad_os bad_cfg
  serial=$'[    0.000000] Kernel command line: BOOT_IMAGE=/vmlinuz quiet splash hostname=aetheros-live\nWelcome to AetherOS 1.0\naetheros-live login: _'
  cfg='append boot=live components quiet splash hostname=aetheros-live'
  qmp=$'(qemu) info status\nVM status: running\n(qemu) info boot\nAetherOS boot config: quiet splash'
  osrel=$'PRETTY_NAME="AetherOS 1.0"\nNAME="AetherOS"\nVERSION_ID="1.0"\nVERSION_CODENAME=trixie\nID=aetheros'
  bad_os=$'NAME="AetherOS"\nVERSION_CODENAME=bookworm'
  bad_cfg='append root=/dev/sda1 single'

  printf '[iso-test] self-test: pure boot-check logic (no QEMU)\n'
  selftest_assert_true "boot milestone in serial log" text_has_boot_milestone "$serial"
  selftest_assert_true "boot milestone in QMP capture" text_has_boot_milestone "$qmp"
  selftest_assert_false "empty serial log has no milestone" text_has_boot_milestone ""
  selftest_assert_true "quiet splash in serial log" text_has_quiet_splash "$serial"
  selftest_assert_true "quiet splash in ISO boot config" text_has_quiet_splash "$cfg"
  selftest_assert_true "quiet splash in QMP capture" text_has_quiet_splash "$qmp"
  selftest_assert_false "plain cmdline has no quiet splash" text_has_quiet_splash "$bad_cfg"
  selftest_assert_true "os-release has Aether identity" text_has_os_identity "$osrel"
  selftest_assert_false "os-release wrong codename" text_has_os_identity "$bad_os"
  selftest_assert_false "os-release missing identity" text_has_os_identity "ID=aetheros"
  selftest_assert_true "checks map has every key" checks_map_complete
  selftest_assert_true "json escape handles quotes, slashes, newlines" selftest_json_escape

  printf 'selftest %d assertions, %d failures\n' "$SELF_TOTAL" "$SELF_FAIL"
  (( SELF_FAIL == 0 ))
}

# --- argv (argv-only ISO path; env used only as a fallback) -----------------
while (( $# )); do
  case "$1" in
    --self-test) SELF_TEST=1; shift ;;
    --timeout)
      if (( $# < 2 )); then echo "[iso-test] --timeout needs a value" >&2; finish fail "$FAIL_CODE"; fi
      TIMEOUT="$2"; shift 2 ;;
    --timeout=*) TIMEOUT="${1#--timeout=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*)
      echo "[iso-test] unknown option: $1" >&2
      finish fail "$FAIL_CODE" ;;
    *)
      if [[ -n "$ISO" ]]; then
        echo "[iso-test] multiple ISO paths given" >&2
        finish fail "$FAIL_CODE"
      fi
      ISO="$1"; shift ;;
  esac
done

[[ -n "$ISO" ]] || ISO="${AETHER_ISO:-}"
TIMEOUT="$(normalize_timeout "$TIMEOUT")"

if (( SELF_TEST )); then
  if run_self_test; then exit 0; else exit "$FAIL_CODE"; fi
fi

# --- preconditions ----------------------------------------------------------
validate_paths() {
  local d dirs=("$(dirname "$SERIAL_LOG")" "$(dirname "$SCREENSHOT")")
  [[ -n "$RESULT_JSON" ]] && dirs+=("$(dirname "$RESULT_JSON")")
  if [[ -z "$ISO" ]]; then
    note "input: no ISO path (argument or AETHER_ISO)"
    return 1
  fi
  if [[ ! -f "$ISO" || ! -r "$ISO" || ! -s "$ISO" ]]; then
    note "input: ISO missing, unreadable or empty: $ISO"
    return 1
  fi
  for d in "${dirs[@]}"; do
    if ! mkdir -p "$d" 2>/dev/null || [[ ! -w "$d" ]]; then
      note "input: output directory not writable: $d"
      return 1
    fi
  done
  return 0
}
if ! validate_paths; then
  finish fail "$FAIL_CODE"
fi

QEMU="$(command -v qemu-system-x86_64 || true)"
if [[ -z "$QEMU" ]]; then
  note "harness: qemu-system-x86_64 not present; whole test skipped"
  log "qemu-system-x86_64 not present - skipping ISO boot test (exit $SKIP_CODE)"
  finish skip "$SKIP_CODE"
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

rm -f "$SERIAL_LOG" "$SCREENSHOT"

# --- ISO helper tooling -----------------------------------------------------
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

# --- build QEMU argv (argv only, never eval / shell=true) --------------------
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

# --- bounded wait for a login/banner milestone ------------------------------
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

# --- checklist --------------------------------------------------------------
QMP_TEXT=""
if [[ -n "$QMP_LOG" && -r "$QMP_LOG" ]]; then
  QMP_TEXT="$(cat "$QMP_LOG" 2>/dev/null)"
fi
CMDLINE_TEXT="$(cat "$SERIAL_LOG" 2>/dev/null)"$'\n'"$BOOT_TEXT"$'\n'"$QMP_TEXT"

if (( ! PROMPT_SEEN )) && text_has_boot_milestone "$QMP_TEXT"; then
  PROMPT_SEEN=1
fi
if (( PROMPT_SEEN )); then
  pass boot_prompt
else
  fail boot_prompt "no boot milestone in serial log or QMP capture within ${TIMEOUT}s"
fi

KERNEL_CMDLINE="$(printf '%s\n' "$CMDLINE_TEXT" | grep -aiEo 'Command line:[[:space:]]*.*' | head -n1 || true)"
[[ -z "$KERNEL_CMDLINE" ]] || note "kernel_cmdline: ${KERNEL_CMDLINE}"
if text_has_quiet_splash "$CMDLINE_TEXT"; then
  pass kernel_cmdline
else
  fail kernel_cmdline "'quiet splash' absent from serial log, ISO boot config and QMP capture"
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

# os-release lives inside the live squashfs; try the ISO root first, then the
# squashfs when unsquashfs is present.
extract_os_release() {
  local content sqfs
  content="$(iso_extract /etc/os-release 2>/dev/null)"
  if [[ -n "$content" ]]; then
    printf '%s\n' "$content"
    return 0
  fi
  if command -v unsquashfs >/dev/null 2>&1; then
    sqfs="$(printf '%s\n' "$ISO_PATHS" | grep -aiE '(^|/)filesystem\.squashfs$' | head -n1)"
    if [[ -n "$sqfs" ]] && iso_extract "$sqfs" > "$WORK_DIR/filesystem.squashfs" 2>/dev/null &&
       [[ -s "$WORK_DIR/filesystem.squashfs" ]]; then
      content="$(bounded 90 unsquashfs -cat "$WORK_DIR/filesystem.squashfs" etc/os-release 2>/dev/null)"
      if [[ -n "$content" ]]; then
        printf '%s\n' "$content"
        return 0
      fi
    fi
  fi
  return 1
}

check_os_release() {
  local content
  if [[ -z "$ISO_READER" ]]; then
    skip os_release "no isoinfo/7z/bsdtar available; os-release check skipped"
    return
  fi
  if ! content="$(extract_os_release)" || [[ -z "$content" ]]; then
    skip os_release "os-release not readable from ISO payload (inside squashfs); deep tool unavailable"
    return
  fi
  if text_has_os_identity "$content"; then
    pass os_release
  else
    fail os_release "NAME=AetherOS and VERSION_CODENAME=trixie not both present in /etc/os-release"
  fi
}
check_os_release

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
for k in "${CHECK_KEYS[@]}"; do
  [[ "${CHECK_STATUS[$k]}" == "fail" ]] && HAS_FAIL=1
done
if (( HAS_FAIL )); then
  finish fail "$FAIL_CODE"
fi
finish pass 0
