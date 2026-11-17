#!/usr/bin/env bash
# Aether Fix — one-command repair for the preinstalled Aether app suite.
set -uo pipefail

BIN=/usr/local/bin
APPDIR=/usr/share/applications
SCRIPTS=/usr/share/aether/scripts
repaired=0
missing=0
quiet=0

[ "${1:-}" = "--quiet" ] && quiet=1

log() {
  [ "$quiet" -eq 1 ] || printf 'aether-fix: %s\n' "$*"
}

restore_permissions() {
  if [ -d "$BIN" ]; then
    find "$BIN" -maxdepth 1 -type f -exec chmod 755 {} + 2>/dev/null || true
  fi
  repaired=$((repaired + 1))
}

compile_schemas() {
  if [ -d /usr/share/glib-2.0/schemas ]; then
    glib-compile-schemas /usr/share/glib-2.0/schemas 2>/dev/null || true
  fi
  repaired=$((repaired + 1))
}

ensure_wrapper() {
  name="$1"
  target="$2"
  if [ ! -e "$BIN/$name" ] && [ -f "$target" ]; then
    printf '#!/bin/sh\nexec %s "$@"\n' "$target" > "$BIN/$name"
    chmod 755 "$BIN/$name"
    log "created launcher $name"
    repaired=$((repaired + 1))
  fi
}

repair_launchers() {
  ensure_wrapper aether-browser "/usr/bin/python3 /usr/share/aether/browser/aether-browser.py"
  ensure_wrapper aether-mail "/usr/bin/python3 /usr/share/aether/aether-mail.py"
  ensure_wrapper aether-vault "/usr/bin/python3 /usr/share/aether/aether-vault.py"
  ensure_wrapper aether-gaming-hub "/usr/bin/python3 /usr/share/aether/apps/aether-gaming-hub.py"
  ensure_wrapper aether-factory-reset "/usr/bin/python3 /usr/share/aether/apps/aether-factory-reset.py"
  ensure_wrapper boot-net-tune "$SCRIPTS/boot-net-tune.sh"
  ensure_wrapper optimize-network-heavy "$SCRIPTS/optimize-network-heavy.sh"
  ensure_wrapper install-vscode "$SCRIPTS/install-vscode.sh"
}

enable_services() {
  systemctl daemon-reload 2>/dev/null || true
  systemctl enable aether-net-tune.service aether-vpn-auto.service aether-update-check.timer 2>/dev/null || true
  repaired=$((repaired + 1))
}

restore_boot_theme() {
  if command -v plymouth-set-default-theme >/dev/null 2>&1; then
    plymouth-set-default-theme -R aether 2>/dev/null || true
  fi
  repaired=$((repaired + 1))
}

verify_desktops() {
  local file exec_line cmd token
  for file in "$APPDIR"/aether-*.desktop "$APPDIR"/org.aether.*.desktop; do
    [ -f "$file" ] || continue
    exec_line="$(sed -n 's/^Exec=//p' "$file" | head -n1)"
    [ -n "$exec_line" ] || continue
    cmd="${exec_line%% *}"

    if [ "${cmd#/}" != "$cmd" ]; then
      [ -x "$cmd" ] || { log "missing target: $(basename "$file") -> $cmd"; missing=$((missing + 1)); }
    elif command -v "$cmd" >/dev/null 2>&1; then
      :
    elif [ -x "$BIN/$cmd" ]; then
      :
    else
      log "missing launcher: $(basename "$file") -> $cmd"
      missing=$((missing + 1))
    fi

    for token in $exec_line; do
      case "$token" in
        /*)
          if [ ! -e "$token" ]; then
            log "missing file: $(basename "$file") -> $token"
            missing=$((missing + 1))
          fi
          ;;
      esac
    done
  done
}

restore_permissions
compile_schemas
repair_launchers
enable_services
restore_boot_theme
verify_desktops

log "repaired $repaired subsystem(s); $missing unresolved desktop target(s)"
[ "$missing" -eq 0 ]
