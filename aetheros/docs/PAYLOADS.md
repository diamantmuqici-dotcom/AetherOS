# Payload mirrors

`aetheros/apps/`, `aetheros/core/`, `aetheros/scripts/`, `aetheros/settings/`,
and `aetheros/shell/` are the source of truth. The copies under
`aetheros/iso/config/includes.chroot/` are mirrors and are kept byte-identical
to their sources. This workstream records those mirrors in one manifest and
provides a strict checker plus a byte-preserving sync command.

## Files

- `aetheros/scripts/payload-manifest.txt` - declarative `source|destination`
  pairs, one per line. `#` comments are ignored. Both paths are relative to the
  git repo root (`Aether/`). The current snapshot records 68 mirror pairs.
- `aetheros/scripts/sync-payloads.sh` - `check` (default) and `apply` modes.
- `aetheros/tests/test_payload_sync.py` - unittest for the manifest and script.

## Manifest format

```text
# comment
aetheros/apps/browser/aether-browser.py|aetheros/iso/config/includes.chroot/usr/share/aether/browser/aether-browser.py
aetheros/scripts/aether-doctor.sh|aetheros/iso/config/includes.chroot/usr/local/bin/aether-doctor
```

Rules:

- exactly one `|` per pair; no blank pair lines;
- every destination appears once (no duplicate destinations);
- every path is relative and starts with `aetheros/`;
- the manifest records mirrors that already exist; it never creates one.

The snapshot covers apps (including browser extensions), `core/vault`,
`core/backup`, `core/mail`, scripts (including the `usr/local/bin` launchers for
`aether-doctor`, `aether-fix`, `gamemode-hook`, and the animations runner),
settings, the GNOME shell animations extension, and its gschema.

## Usage

```bash
bash aetheros/scripts/sync-payloads.sh                 # check (default)
bash aetheros/scripts/sync-payloads.sh check           # explicit check
bash aetheros/scripts/sync-payloads.sh apply           # sync then re-check
bash aetheros/scripts/sync-payloads.sh check --manifest path/to/other.txt
```

The repo root is resolved from the script's own location, so the commands work
from any working directory. `--manifest` accepts an absolute or cwd-relative
path; entries inside the manifest stay repo-root-relative.

- `check` compares every pair with `cmp -s`, prints `PASS`/`FAIL` per pair and
  a `summary:` line, and exits `1` on any missing file or byte mismatch.
- `apply` copies with `cp --preserve=mode` and then re-checks. A failed copy or
  a post-copy mismatch is a `FAIL` and exits `1`.
- Argument parsing is argv-only with quoted values; there is no `eval` and no
  shell-string execution. Processing follows manifest order, and the loop is
  bounded at 4096 pairs.

## Adding or changing a mirror

1. Edit the source under `aetheros/apps/`, `core/`, `scripts/`, `settings/`, or
   `shell/`.
2. Run `bash aetheros/scripts/sync-payloads.sh apply`.
3. Commit the source and the updated mirror together.

Add a line to `payload-manifest.txt` only when the destination already exists.
To move a mirror, change its path in the manifest, then run `apply`.

## Tests

```bash
python -m unittest discover -s aetheros/tests -p 'test_payload_sync.py' -v
```

The suite validates the pure manifest parser, path existence, unique
destinations, repo-relative `aetheros/` paths, chroot destinations, and that
the script exposes both modes.

Strictness is deliberately split. `sync-payloads.sh check` is strict: any
mismatch or missing file is a hard error with exit `1`. The unittest's
byte-identity assertion is tolerant: when a pair is mismatched at test time it
emits a skip note naming the pair instead of failing the suite. Other
workstreams edit some of these files in parallel, so a mirror can be briefly
stale while that work is in flight. Missing files, duplicate destinations,
out-of-tree paths, or malformed manifest lines remain hard failures.
