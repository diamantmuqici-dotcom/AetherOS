#!/usr/bin/env bash
# AetherOS payload mirror synchroniser.
# Source of truth: aetheros/{apps,core,scripts,settings,shell}.
# Mirrors: aetheros/iso/config/includes.chroot/... (existing pairs only).
# No shell=true, no eval; every value stays quoted and argv-driven.
set -u

MAX_PAIRS=4096

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 2
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd) || exit 2
default_manifest="$script_dir/payload-manifest.txt"

mode=check
manifest=$default_manifest

usage() {
  printf 'usage: %s [check|apply] [--manifest PATH]\n' "$0"
  printf '  check  verify each source and mirror are byte-identical (default)\n'
  printf '  apply  copy source over mirror, preserve mode, then re-check\n'
}

while [ "$#" -gt 0 ]; do
  case $1 in
    check|apply) mode=$1 ;;
    --manifest)
      shift
      if [ "$#" -eq 0 ]; then
        printf 'error: --manifest requires a path\n' >&2
        exit 2
      fi
      manifest=$1
      ;;
    --manifest=*) manifest=${1#--manifest=} ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'error: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [ ! -f "$manifest" ]; then
  printf 'error: manifest not found: %s\n' "$manifest" >&2
  exit 2
fi

pass=0
fail=0
seen=0

# IFS='|' splits a pair; trailing '|| [ -n "$src" ]' catches a final line
# that has no newline. Comments and blank lines are skipped.
while IFS='|' read -r src dst || [ -n "$src" ]; do
  case $src in
    ''|\#*) continue ;;
  esac
  seen=$((seen + 1))
  if [ "$seen" -gt "$MAX_PAIRS" ]; then
    printf 'error: manifest exceeds %d pairs\n' "$MAX_PAIRS" >&2
    exit 2
  fi
  case $dst in
    ''|*'|'*)
      printf 'FAIL malformed pair: %s|%s\n' "$src" "$dst"
      fail=$((fail + 1))
      continue
      ;;
  esac
  bad_path=0
  for value in "$src" "$dst"; do
    case $value in
      ../*|*/..|*/../*|/*) bad_path=1 ;;
    esac
  done
  if [ "$bad_path" -ne 0 ]; then
    printf 'FAIL path escapes repo root: %s|%s\n' "$src" "$dst"
    fail=$((fail + 1))
    continue
  fi

  sp=$repo_root/$src
  dp=$repo_root/$dst

  if [ ! -f "$sp" ]; then
    printf 'FAIL missing source: %s\n' "$src"
    fail=$((fail + 1))
    continue
  fi

  if [ "$mode" = apply ]; then
    if ! cp --preserve=mode -- "$sp" "$dp"; then
      printf 'FAIL copy failed: %s -> %s\n' "$src" "$dst"
      fail=$((fail + 1))
      continue
    fi
  fi

  if [ ! -f "$dp" ]; then
    printf 'FAIL missing destination: %s\n' "$dst"
    fail=$((fail + 1))
    continue
  fi

  if cmp -s -- "$sp" "$dp"; then
    printf 'PASS %s -> %s\n' "$src" "$dst"
    pass=$((pass + 1))
  else
    printf 'FAIL mismatch: %s -> %s\n' "$src" "$dst"
    fail=$((fail + 1))
  fi
done < "$manifest"

printf 'summary: %d PASS, %d FAIL (mode=%s, pairs=%d)\n' "$pass" "$fail" "$mode" "$seen"
[ "$fail" -eq 0 ] || exit 1
exit 0
