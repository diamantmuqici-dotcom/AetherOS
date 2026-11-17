# Release signing

AetherOS release manifests are signed with Ed25519. The private signing key is
held outside this repository; only the public key is shipped to installations.

## Key generation

Run once on an offline or secured signing host:

```bash
umask 077
openssl genpkey -algorithm ED25519 -out aether-release.ed25519.pem
openssl pkey -in aether-release.ed25519.pem -pubout -out aether-release.pub.pem
```

- `aether-release.ed25519.pem` — private key, mode `0600`, never committed.
- `aether-release.pub.pem` — public key, packaged into ISOs at
  `/usr/share/aether/updates/aether-release.pub.pem`.

Store the private key in a CI secret or a hardware-backed keystore. The
signing job exposes it to the script as a path via `AETHER_SIGNING_KEY`.
No private key, passphrase, or seed belongs in this repository, a workflow
file, or an ISO.

## Signing a release manifest

```bash
AETHER_SIGNING_KEY=/secure/aether-release.ed25519.pem \
AETHER_RELEASE_MANIFEST=/build/release-manifest.json \
AETHER_RELEASE_OUTDIR=/build/out \
./sign-iso.sh /build/aether.iso
```

Environment inputs:

- `AETHER_SIGNING_KEY` — path to the Ed25519 private key PEM. Required for
  manifest signing.
- `AETHER_RELEASE_MANIFEST` — path to the JSON release manifest. Required for
  manifest signing.
- `AETHER_RELEASE_OUTDIR` — destination for the public key. Defaults to the
  manifest's directory.
- `AETHER_SIGNING_PUBKEY` — optional path to a public key PEM. When set, it is
  copied to the output directory instead of the key derived from the private key.
- `GPG_KEY_ID` / `GPG_PRIVATE_KEY` — existing ISO checksum signing behavior,
  unchanged.

Outputs:

- `<manifest>.sig` — raw 64-byte Ed25519 signature over the canonical manifest.
- `aether-release.pub.pem` — SPKI PEM public key for installed verifiers.

The signed bytes are `json.dumps(payload, sort_keys=True, separators=(',',':'))`
encoded as UTF-8. Verification in `core/update/signature.py` uses the same
canonical form, so JSON key order and whitespace in the transported manifest
do not affect the result.

## Rotation

Generate a new keypair, publish the new public key in the next ISO and update
channel, and keep the previous public key available for one release cycle so
older installations can verify the transition manifest. Retire the old key only
after the last manifest signed with it has expired.
