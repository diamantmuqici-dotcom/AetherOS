# Release

A signed AetherOS release ships three artifacts: the ISO, a canonical metadata
file, and a checksum file. The private signing key is generated on an offline or
secured host and never enters the repository or an ISO.

## 1. Generate the release key

```bash
./scripts/signing/generate-release-key.sh \
  --priv /secure/aether-release.ed25519.pem \
  --pub  /secure/aether-release.pub.pem
```

- Backend: `openssl genpkey -algorithm ED25519`. If `openssl` is absent the
  script exits `77` without writing anything.
- Defaults to `${AETHER_KEY_DIR:-$HOME/.config/aether/release-keys}` with the
  filenames `aether-release.ed25519.pem` and `aether-release.pub.pem`. Explicit
  `--priv` / `--pub` paths override the defaults.
- Private key mode `0600`, public key mode `0644`. Existing keys are never
  overwritten without `--force`.
- The script derives the public key from the private key and compares SPKI DER
  bytes before installing either file, so a mismatched pair is rejected.
- Standard output is a single line: `SHA256:<hex>` — the SHA-256 fingerprint of
  the public SPKI DER. No key bytes, seed, or passphrase is printed.
- The script refuses any target inside the repository tree.

## 2. Stage the public key

Before building an ISO, copy the public PEM into the build staging tree:

```text
iso/config/includes.chroot/usr/share/aether/updates/aether-release.pub.pem
```

live-build copies it to `/usr/share/aether/updates/aether-release.pub.pem`,
the path read by the updater verifier and Aether Doctor. With no public key in
the image, signed updates report `MISSING` and the updater refuses to apply
upgrades.

## 3. Build metadata and checksums

```bash
python3 ./scripts/signing/make-release-metadata.py \
  --iso /build/aetheros-live.iso \
  --out /build/out \
  --key /secure/aether-release.ed25519.pem
```

Omit `--key` to emit unsigned metadata. Optional `--product` and `--version`
default to `AetherOS` and `1.0`. `--timestamp` takes an explicit UTC ISO-8601
value; otherwise `SOURCE_DATE_EPOCH` (integer seconds) is used when set, and the
current UTC time otherwise. Set `SOURCE_DATE_EPOCH` for byte-identical output.

Outputs in `--out`:

- `release-metadata.json` — canonical JSON: sorted keys, no whitespace, UTF-8.
- `SHA256SUMS` — one coreutils-format line: `<sha256>  <iso-filename>`.

ISO hashing reads the file in 1 MiB chunks; the ISO is never buffered whole.

## 4. Metadata format

```json
{
  "iso": {"filename": "aetheros-live.iso", "size": 0, "sha256": "..."},
  "product": "AetherOS",
  "schema": "aether-release-metadata/1",
  "signature": "<base64 Ed25519 signature>",
  "status": "signed",
  "timestamp": "2026-01-02T03:04:05Z",
  "version": "1.0"
}
```

- `status` is `signed` or `unsigned`. Without a key, `signature` is `null` and
  `status` is `unsigned`; consumers must treat that as unverified and fail
  closed even though `SHA256SUMS` is still produced.
- The signature is a raw 64-byte Ed25519 signature, base64-encoded into the
  `signature` field. It covers `json.dumps(payload_without_signature,
  sort_keys=True, separators=(',', ':'))` as UTF-8 — identical to the canonical
  form in `core/update/signature.py`. The `status` field is inside the signed
  bytes, so it cannot be flipped without invalidating the signature.
- Verification: load the public PEM at
  `/usr/share/aether/updates/aether-release.pub.pem`, reject anything whose
  `status` is not `signed`, decode `signature`, and verify it against the
  canonical bytes of the payload with the `signature` field removed.

## 5. ISO checksums and manifest signing

```bash
sha256sum -c SHA256SUMS
```

The separate Ed25519 release-manifest flow (`scripts/signing/sign-iso.sh`,
`core/update/signature.py`) is unchanged. It signs a `aether-release/1` APT pin
manifest and writes `<manifest>.sig` plus the public key to its output
directory. `aether-release-metadata/1` is a distinct schema and is not accepted
by the update verifier.

## 6. Key rotation

Generate a new keypair, publish the new public key in the next ISO and update
channel, and keep the previous public key available for one release cycle so
older installations can verify the transition. Retire the old key only after
the last artifact signed with it is no longer served.
