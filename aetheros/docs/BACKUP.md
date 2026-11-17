# Aether Backup — integrity and non-destructive restore

Aether Backup stores dated snapshots and verifies them with a canonical,
optionally signed manifest. Snapshots are additive: no operation removes files
from the source or from an existing restore target unless replacement is
explicitly requested and every file is verified.

## Snapshot format

A snapshot is a directory containing a copy of the source tree plus:

```
aether-backup-manifest.json
```

The manifest is canonical JSON (`sort_keys`, compact separators). Its entries
are sorted by relative path and each entry carries:

| field    | meaning                                   |
|----------|-------------------------------------------|
| `path`   | POSIX relative path, traversal rejected   |
| `size`   | byte length                               |
| `sha256` | digest of the file contents               |
| `mtime`  | modification time in nanoseconds          |
| `type`   | `file` for regular files                  |

Top-level fields are `schema` (`aether-backup/1`), `created`, `root`, `count`,
`total_bytes`, `entries` and `signature`.

### Signing

When an Ed25519 PEM private key is available, `save_manifest` records the
SHA-256 of the canonical unsigned payload and signs that digest. The signature
block is `{algorithm, digest, signature}`; without a key it is `null`.
Verification recomputes the digest and rejects a manifest whose recorded digest
or signature does not match. The canonicalization primitive is shared with the
update subsystem (`core.update.signature.canonical_signing_input`).

### Limits and skip list

Reads are bounded at 1 MiB per chunk. A manifest is capped at 64 MiB, 250,000
entries, 2 GiB per file and 512 GiB total. Directories named `.cache`, `.git`,
`__pycache__`, `node_modules`, `Trash`, `.thumbnails` and files with `.pyc`,
`.pyo`, `.swap`, `.tmp` suffixes are not tracked, along with symlinks and the
manifest file itself.

## Command line

```
aether-backup --check
aether-backup --snapshot DIR [--source DIR] [--dry-run] [--sign-key FILE]
aether-backup --verify SNAPSHOT [--public-key FILE]
aether-backup --plan-restore SNAPSHOT --target DIR [--overwrite] [--public-key FILE]
```

`--check`, `--verify` and `--plan-restore` print JSON and never import GTK.
`--check` reports rsync availability, configured paths, key presence, the most
recent snapshot and its verification status.

`--snapshot` copies into a dated child of `DIR` using `rsync -a` with no
`--delete`; if rsync is missing it falls back to bounded `shutil.copy2` with a
post-copy hash check. A manifest is written and re-verified before success.

`--plan-restore` verifies the snapshot first, then emits an argv-style list of
`["copy2", src, dst, sha256]` operations. It never emits a shell string. The
plan targets an empty directory; `--overwrite` is required to replace existing
files.

## Environment

| variable                    | purpose                                |
|-----------------------------|----------------------------------------|
| `AETHER_BACKUP_SOURCE`      | source tree (default: home)            |
| `AETHER_BACKUP_ROOT`        | backup root (default: `~/Backups`)     |
| `AETHER_BACKUP_SIGNING_KEY` | Ed25519 PEM private key for signing    |
| `AETHER_BACKUP_PUBLIC_KEY`  | Ed25519 PEM public key for verification|

## Restore safety

- Restore is executed by `core.backup.restore.execute_plan`, dry-run by
  default; a real write requires `dry_run=False`.
- Every source and destination path is resolved and must remain inside its
  root; `..` and absolute manifest paths are rejected.
- The source hash is checked before the copy and again on the temporary file
  before an atomic `os.replace` into place.
- Nothing is deleted, and existing targets are untouched without
  `overwrite=True`.

## Tests

```
python -m unittest discover -s aetheros/tests -p 'test_backup.py' -v
```
