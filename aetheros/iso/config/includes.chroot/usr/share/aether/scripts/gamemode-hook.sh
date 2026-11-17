#!/usr/bin/env bash
# Aether GameMode hook — scoped PIDs, trap-backed restore, no process termination.
# All written state stays under $HOME/.config/aether/gamemode.
set -euo pipefail

# --- fixed policy -----------------------------------------------------------
SCHEMA="AETHER_GAMEMODE_STATE_V1"
MAX_PIDS=64
NICE_LEVEL=-5
ALLOWLIST=(steam steamwebhelper gamemoded gamemoderun game)
EXE_ALLOWLIST=(/usr/games/ /usr/share/games/ /opt/steam/ /usr/lib/steam/)
DENYLIST=(systemd init dbus-daemon sshd Xorg Xwayland NetworkManager)

CONFIG_DIR="${HOME}/.config/aether/gamemode"
STATE="${CONFIG_DIR}/state"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u 2>/dev/null || echo 0)}"
GAMEMODE_DIR="${RUNTIME_DIR}/gamemode"
GSCHEMA="org.gnome.desktop.notifications"
GKEY="show-banners"

ARMED=0
TMP_STATE=""
PIDS=()

has() { command -v "$1" >/dev/null 2>&1; }

run_bounded() {
  local seconds="$1"; shift
  if has timeout; then timeout "$seconds" "$@"; else "$@"; fi
}

# --- state helpers ----------------------------------------------------------
state_valid() {
  local file="$1"
  [ -f "$file" ] || return 1
  [ "$(sed -n '1p' "$file" 2>/dev/null)" = "$SCHEMA" ] || return 1
  grep -q '^ts=[0-9][0-9]*$' "$file" 2>/dev/null || return 1
  grep -q '^preset=' "$file" 2>/dev/null || return 1
  grep -q '^profile=' "$file" 2>/dev/null || return 1
  grep -q '^banners=' "$file" 2>/dev/null || return 1
}

state_get() {
  sed -n "s/^$1=//p" "$STATE" 2>/dev/null | head -n 1
}

restore_from_state() {
  local profile banners
  profile="$(state_get profile)"
  banners="$(state_get banners)"
  if [ "$profile" != "unset" ] && [ -n "$profile" ] && has powerprofilesctl; then
    run_bounded 5 powerprofilesctl set "$profile" >/dev/null 2>&1 || true
  fi
  if [ "$banners" != "unset" ] && [ -n "$banners" ] && has gsettings; then
    run_bounded 5 gsettings set "$GSCHEMA" "$GKEY" "$banners" >/dev/null 2>&1 || true
  fi
}

# Guaranteed restore: fires on normal exit and on error/signal while armed.
cleanup() {
  trap - EXIT INT TERM
  local status=$?
  if [ "$ARMED" -eq 1 ]; then
    if state_valid "$STATE"; then restore_from_state; fi
    rm -f "$STATE"
  fi
  [ -n "$TMP_STATE" ] && rm -f "$TMP_STATE"
  exit "$status"
}
trap cleanup EXIT INT TERM

# --- PID scoping ------------------------------------------------------------
# need_allow=1 (pgrep fallback) requires comm/exe match; explicit/gamemode
# PIDs are already scoped by source. DENYLIST applies to every candidate.
accept_pid() {
  local pid="$1" need_allow="$2" comm="" exe="" name prefix existing ok=0
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  [ "$pid" -gt 1 ] 2>/dev/null || return 0
  [ -d "/proc/$pid" ] || return 0
  [ "$pid" != "$$" ] || return 0
  IFS= read -r comm < "/proc/$pid/comm" 2>/dev/null || comm=""
  for name in "${DENYLIST[@]}"; do [ "$comm" = "$name" ] && return 0; done
  if [ "$need_allow" -eq 1 ]; then
    for name in "${ALLOWLIST[@]}"; do
      if [ "$comm" = "$name" ]; then ok=1; break; fi
    done
    if [ "$ok" -eq 0 ]; then
      exe="$(readlink "/proc/$pid/exe" 2>/dev/null || true)"
      for prefix in "${EXE_ALLOWLIST[@]}"; do
        case "$exe" in "$prefix"*) ok=1; break;; esac
      done
    fi
    [ "$ok" -eq 1 ] || return 0
  fi
  if [ "${#PIDS[@]}" -gt 0 ]; then
    for existing in "${PIDS[@]}"; do [ "$existing" = "$pid" ] && return 0; done
  fi
  [ "${#PIDS[@]}" -lt "$MAX_PIDS" ] || return 0
  PIDS+=("$pid")
}

collect_pids() {
  local pid entry name part
  PIDS=()
  if [ -n "$EXPLICIT_PIDS" ]; then
    IFS=',' read -ra PARTS <<< "$EXPLICIT_PIDS"
    for part in "${PARTS[@]}"; do accept_pid "$part" 0; done
  else
    if [ -d "$GAMEMODE_DIR" ]; then
      for entry in "$GAMEMODE_DIR"/*; do
        [ -e "$entry" ] || continue
        entry="${entry##*/}"
        case "$entry" in
          *.pid)
            pid="$(head -n 1 "$GAMEMODE_DIR/$entry" 2>/dev/null || true)"
            accept_pid "$pid" 0
            ;;
          *) accept_pid "$entry" 0 ;;
        esac
      done
    fi
    if [ "${#PIDS[@]}" -eq 0 ]; then
      for name in "${ALLOWLIST[@]}"; do
        while IFS= read -r pid; do accept_pid "$pid" 1; done \
          < <(run_bounded 5 pgrep -x "$name" 2>/dev/null || true)
      done
    fi
  fi
}

boost_pids() {
  local pid
  for pid in "${PIDS[@]}"; do
    [ -d "/proc/$pid" ] || continue
    if has sudo && sudo -n renice -n "$NICE_LEVEL" -p "$pid" >/dev/null 2>&1; then
      continue
    fi
    renice -n 0 -p "$pid" >/dev/null 2>&1 || true
  done
}

# --- presets ----------------------------------------------------------------
apply_preset() {
  local preset="$1" do_profile=0 do_nice=0 do_banners=0
  local profile="unset" banners="unset"
  case "$preset" in
    performance) do_profile=1; do_nice=1; do_banners=1 ;;
    balanced) do_nice=1 ;;
    quiet) do_banners=1 ;;
  esac

  # Snapshot first: no prior value means no change, so nothing can be lost.
  if [ "$do_profile" -eq 1 ] && has powerprofilesctl; then
    profile="$(run_bounded 5 powerprofilesctl get 2>/dev/null || true)"
    [ -n "$profile" ] || { echo "gamemode: no profile snapshot; refusing" >&2; exit 1; }
  fi
  if [ "$do_banners" -eq 1 ] && has gsettings; then
    banners="$(run_bounded 5 gsettings get "$GSCHEMA" "$GKEY" 2>/dev/null || true)"
    [ -n "$banners" ] || { echo "gamemode: no banner snapshot; refusing" >&2; exit 1; }
  fi

  TMP_STATE="${STATE}.tmp.$$"
  {
    printf '%s\n' "$SCHEMA"
    printf 'ts=%s\n' "$(date +%s)"
    printf 'preset=%s\n' "$preset"
    printf 'profile=%s\n' "$profile"
    printf 'banners=%s\n' "$banners"
  } > "$TMP_STATE"
  if ! state_valid "$TMP_STATE"; then
    echo "gamemode: invalid state snapshot; refusing" >&2
    exit 1
  fi
  mv -f "$TMP_STATE" "$STATE"
  TMP_STATE=""
  ARMED=1

  if [ "$do_profile" -eq 1 ] && [ "$profile" != "unset" ] && has powerprofilesctl; then
    run_bounded 5 powerprofilesctl set performance >/dev/null 2>&1 || true
  fi
  if [ "$do_banners" -eq 1 ] && [ "$banners" != "unset" ] && has gsettings; then
    run_bounded 5 gsettings set "$GSCHEMA" "$GKEY" false >/dev/null 2>&1 || true
  fi
  if [ "$do_nice" -eq 1 ]; then
    collect_pids
    boost_pids
  fi
  ARMED=0
}

# --- argument parsing -------------------------------------------------------
CMD="" PRESET="performance" EXPLICIT_PIDS=""
while [ $# -gt 0 ]; do
  case "$1" in
    start|stop|status) CMD="$1"; shift ;;
    performance|balanced|quiet) PRESET="$1"; shift ;;
    --pids) EXPLICIT_PIDS="${2:-}"; shift 2 ;;
    --pids=*) EXPLICIT_PIDS="${1#--pids=}"; shift ;;
    -h|--help)
      echo "usage: gamemode-hook.sh [start|stop|status] [performance|balanced|quiet] [--pids N,N,...]"
      exit 0
      ;;
    *) echo "gamemode: unknown argument: $1" >&2; exit 2 ;;
  esac
done
CMD="${CMD:-start}"

case "$PRESET" in
  performance|balanced|quiet) ;;
  *) echo "gamemode: invalid preset" >&2; exit 2 ;;
esac

mkdir -p "$CONFIG_DIR"

case "$CMD" in
  start)
    if state_valid "$STATE"; then
      echo "Game Mode: already active (preset=$(state_get preset))"
      exit 0
    fi
    rm -f "$STATE"
    apply_preset "$PRESET"
    echo "Game Mode ON (preset=$PRESET, scoped PIDs=${#PIDS[@]})"
    ;;
  stop)
    if ! state_valid "$STATE"; then
      echo "Game Mode: not active"
      exit 0
    fi
    ARMED=1
    echo "Game Mode OFF (restoring prior settings)"
    ;;
  status)
    if state_valid "$STATE"; then
      echo "Game Mode: ACTIVE (preset=$(state_get preset), ts=$(state_get ts))"
    else
      echo "Game Mode: INACTIVE"
    fi
    ;;
esac
exit 0
