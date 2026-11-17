# Updates

AetherOS installs only upgrades that are both proposed by APT and pinned by a
signed release manifest. Unsigned, expired, or out-of-manifest packages are
never applied.

## Release manifest

A manifest is a JSON object with this shape:

```json
{
  "schema": "aether-release/1",
  "channel": "stable",
  "expires": "2026-12-01T00:00:00Z",
  "min_os_version": "1.0",
  "packages": {
    "aether-shell": "1.4-2",
    "aether-updater": "1.2-1"
  },
  "channels": {
    "beta": { "packages": { "aether-shell": "1.5~beta-1" } }
  }
}
```

- `schema` must be `aether-release/1`.
- `channel` is `stable`, `beta`, or `development`.
- `expires` is an ISO-8601 timestamp with a UTC offset; an absent or past value
  makes the manifest invalid.
- `min_os_version` is the oldest AetherOS version the manifest applies to.
- `packages` maps package names to exact versions. A package is installed only
  when APT proposes that same version.

The signature is a raw 64-byte Ed25519 signature stored next to the manifest as
`<manifest>.sig`. It covers the canonical JSON form of the manifest, so
formatting differences do not break verification. The public key is packaged at
`/usr/share/aether/updates/aether-release.pub.pem`.

## Verification flow

1. `core/update/signature.py` bounds the manifest at 1 MiB, parses it, loads the
   PEM public key, and verifies the signature.
2. It then checks the schema and expiry. Any failure raises `SignatureError` and
   no payload is returned.
3. `core/update/release.py` validates required fields, selects the channel, and
   intersects APT's simulated upgrades with the manifest pins.
4. `aether-updater` refuses to enable its Accept action unless the signature
   status is `VALID`, and re-checks the signature at apply time.

## Headless check

The updater exposes a JSON status mode used by tests and CI. It imports no GTK
modules:

```bash
python3 /usr/share/aether/updater/aether-updater.py --check
```

Example output:

```json
{
  "signature": "VALID",
  "channel": "stable",
  "expires": "2026-12-01T00:00:00Z",
  "min_os_version": "1.0",
  "apt_status": "ok",
  "upgrades": [
    {"package": "aether-shell", "version": "1.4-2", "current": "1.3-1", "origin": "Debian:13/stable"}
  ],
  "error": null
}
```

`signature` is `VALID`, `INVALID`, or `MISSING`. When it is not `VALID`,
`upgrades` is always empty. APT is invoked as `apt-get -s upgrade` and
`apt-cache policy <pkg>` with argument vectors and a 30-second timeout; no shell
is used.

Environment overrides:

- `AETHER_RELEASE_MANIFEST` — manifest path.
- `AETHER_RELEASE_SIGNATURE` — signature path.
- `AETHER_RELEASE_PUBLIC_KEY` — public key path.
- `AETHER_UPDATE_CHANNEL` — requested channel.

## Desktop interface

Launching `aether-updater` without arguments opens a GTK4/libadwaita window
showing the signature badge (`VALID`, `INVALID`, `MISSING`), the pinned upgrade
list, and three actions:

- **Accept** — enabled only for a valid signature; applies the exact pinned
  versions with `apt-get install -y --no-install-recommends`.
- **Decline** — records a declined timestamp.
- **Later** — records a snooze timestamp in `~/.config/aether/updater.json`.

## Signing

See `scripts/signing/README.md` for key generation and the signing command. The
private key never enters the repository or the built ISO.
