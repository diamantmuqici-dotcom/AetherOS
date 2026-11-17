# Aether Antivirus

Aether AV is a signature-gated hash scanner. Definition data is inert until an
Ed25519 signature, schema check and expiry check all pass; only then is any
hash used to match or quarantine a file.

## Components

| Path | Role |
|---|---|
| `aetheros/apps/antivirus/aether-av.py` | Front-end: headless modes plus deferred GTK4/libadwaita UI |
| `aetheros/apps/antivirus/aether-av-light.py` | CLI-only variant; reuses the same core by import |
| `iso/config/includes.chroot/usr/share/aether/apps/aether-av.py` | Byte-identical installed copy |
| `iso/config/includes.chroot/usr/local/bin/aether-av` | Launcher: `exec python3 /usr/share/aether/apps/aether-av.py "$@"` |
| `iso/config/includes.chroot/usr/share/applications/org.aether.Antivirus.desktop` | Desktop entry |
| `iso/config/includes.chroot/usr/share/aether/updates/README.av-key` | Public-key staging note |

## Definition format

Signed JSON, schema `aether-av-sigs/1`:

```json
{
  "schema": "aether-av-sigs/1",
  "generated_utc": "2026-11-17T00:00:00Z",
  "expires_utc": "2026-12-17T00:00:00Z",
  "hashes": [
    {"sha256": "<64 lowercase hex characters>", "name": "known-malware-name"}
  ]
}
```

The signature covers `canonical_signing_input(payload)` from
`core/update/signature.py`: `json.dumps(payload, sort_keys=True,
separators=(",", ":"))`, UTF-8. `core.update.signature.sign_release` produces a
compatible signature; `aether-av.py` reuses `canonical_signing_input` and
`SignatureError` rather than reimplementing canonicalisation.

Verification order in `verify_definitions`:

1. Bound definition bytes (1 MiB) and signature length (64 bytes).
2. Parse JSON and load the staged Ed25519 public key.
3. Verify the signature over the canonical payload — before any field is trusted.
4. Enforce schema, parse `generated_utc` / `expires_utc`, reject expiry.
5. Normalize `hashes`: lowercase 64-hex digests, bounded name length, bounded
   count (20000), duplicate digests collapsed.

Any failure raises `SignatureError`; no hash escapes this function.

## Key staging

Public key: `/usr/share/aether/updates/aether-av.pub.pem` (override with
`AETHER_AV_PUBLIC_KEY`). Only the public key is stored in the repo or ISO. A
missing key reports `SIGNATURE_MISSING`; an unreadable or non-Ed25519 key
reports `SIGNATURE_INVALID`.

## Network

`--update` downloads the definition JSON and its detached `.sig` over HTTPS
only. Pinned release assets:

- `https://github.com/diamantmuqici-dotcom/AetherOS/releases/latest/download/aether-av-sigs.json`
- the same URL with `.sig` appended

Both transfers use a 10-second timeout and a 1 MiB cap enforced from
`Content-Length` and by reading at most `MAX_DEFS_BYTES + 1` bytes. Verification
happens in memory; files are written atomically only after it succeeds. A
failed fetch or failed verification leaves the previous definitions untouched.
No shell is used. `gpg`, when enabled with `AETHER_AV_GPG=1` and a sibling
`.asc`, runs via an argv list with a bounded timeout.

## Scanning and quarantine

`scan()` walks the given roots (default `/tmp` and `~/Downloads`) with
`os.scandir`, skipping symlinks, the quarantine dir and AV state/definition
files. Bounds: 20000 files, 4096 directories, 32 MiB per file. Files are hashed
in 1 MiB chunks and matched only against the verified hash set.

On a match, `_quarantine_file` copies the file into
`~/.config/aether/av/quarantine`, hashes the copy, and removes the original
only when the copy's sha256 equals the matched digest. A failed or partial copy
leaves the original in place. Report lists are capped at 200 entries.

## Modes

```
aether-av --check                 # JSON status, no gi import
aether-av --scan [PATH ...]       # bounded scan, JSON summary
aether-av --update                # fetch + verify or fail closed, JSON result
aether-av --verify-file PATH      # one-file check against verified hashes
aether-av --version               # version string
aether-av                         # GTK4/libadwaita interface
```

`aether-av-light` supports `--check`, `--scan`, `--verify-file` and `--version`
with no GTK import at all.

`--check` reports `signature` (`VALID`, `SIGNATURE_INVALID` or
`SIGNATURE_MISSING`), `generated_utc`, `expires_utc`, `age_seconds`,
`hash_count`, `definitions_path`, `public_key_path`, `quarantine_dir`,
`last_scan` (from the bounded state file) and `error`. JSON is emitted with
`sort_keys=True`.

## Environment overrides

| Variable | Default |
|---|---|
| `AETHER_AV_DEFS` | `~/.config/aether/av/definitions.json` |
| `AETHER_AV_SIGNATURE` | `~/.config/aether/av/definitions.sig` |
| `AETHER_AV_PUBLIC_KEY` | `/usr/share/aether/updates/aether-av.pub.pem` |
| `AETHER_AV_STATE` | `~/.config/aether/av/state.json` |
| `AETHER_AV_QUARANTINE` | `~/.config/aether/av/quarantine` |
| `AETHER_AV_DEFS_URL` | pinned release JSON URL (HTTPS enforced) |
| `AETHER_AV_SIGNATURE_URL` | pinned release `.sig` URL (HTTPS enforced) |
| `AETHER_AV_GPG` | `1` to check an optional sibling `.asc` via argv-only gpg |

## Tests

```
python -m unittest discover -s aetheros/tests -p 'test_av.py' -v
```

Tests mock the download function, generate a throwaway Ed25519 keypair, and
cover valid, tampered, expired, missing-key and oversized cases plus the
copy-before-delete guarantee. No live network calls are made.
