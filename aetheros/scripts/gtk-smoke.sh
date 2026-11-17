#!/usr/bin/env bash
# Headless GTK smoke harness: CLI modes only, never starts a desktop app.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3 2>/dev/null || true)"

if [[ -z "$PY" ]]; then
    echo "SKIP: python3 not found on PATH"
    exit 0
fi
if ! command -v timeout >/dev/null 2>&1; then
    echo "SKIP: coreutils timeout not found on PATH"
    exit 0
fi

discover() {
    find "$ROOT/apps" -mindepth 2 -maxdepth 2 -type f -name 'aether-*.py' 2>/dev/null | sort
    for extra in "$ROOT/settings/aether-settings.py" "$ROOT/setup/aether-setup.py"; do
        [[ -f "$extra" ]] && echo "$extra"
    done
}

pick_flag() {
    # argv-only: use the first headless mode the source advertises.
    local app="$1" flag
    for flag in --check --list --diagnose --version; do
        if grep -q -e "$flag" "$app"; then
            echo "$flag"
            return 0
        fi
    done
    return 1
}

run_one() {
    local app="$1" rel flag out rc first
    rel="${app#"$ROOT"/}"
    flag="$(pick_flag "$app" || true)"
    if [[ -z "$flag" ]]; then
        echo "SKIP $rel (no headless mode flag)"
        return 0
    fi
    out="$(mktemp)"
    timeout 10s "$PY" "$app" "$flag" >"$out" 2>&1
    rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "FAIL $rel (exit=$rc flag=$flag): $(head -c 200 "$out")"
        rm -f "$out"
        return 1
    fi
    if [[ ! -s "$out" ]]; then
        echo "FAIL $rel (empty output flag=$flag)"
        rm -f "$out"
        return 1
    fi
    first="$(head -c 1 "$out")"
    if [[ "$first" == "{" || "$first" == "[" ]]; then
        if ! "$PY" -m json.tool "$out" >/dev/null 2>&1; then
            echo "FAIL $rel (invalid JSON flag=$flag)"
            rm -f "$out"
            return 1
        fi
        echo "PASS $rel (flag=$flag, json=ok)"
    else
        echo "PASS $rel (flag=$flag, text=ok)"
    fi
    rm -f "$out"
    return 0
}

failures=0
if [[ "${1:-}" == "--all" ]]; then
    while IFS= read -r app; do
        [[ -z "$app" ]] && continue
        run_one "$app" || failures=$((failures + 1))
    done < <(discover)
elif [[ $# -eq 1 && -f "$1" ]]; then
    run_one "$1" || failures=$((failures + 1))
else
    echo "Usage: $0 <app.py> | --all"
    exit 2
fi

if [[ $failures -gt 0 ]]; then
    echo "RESULT: $failures FAIL"
    exit 1
fi
echo "RESULT: all PASS/SKIP"
exit 0
