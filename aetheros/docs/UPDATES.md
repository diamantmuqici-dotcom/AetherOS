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
5. `update-push.py` builds the same policy in `core/update/apt_policy.py`. Its
   plan mode revalidates every entry against the signed pins and emits APT argv
   without executing anything.

## Authenticated APT policy (update-push.py)

`update-push.py` replaced the old unverified GitHub release check. It fetches no
release data over the network. APT actions (`install`, `upgrade`, `hold`) are
permitted only for packages pinned at an exact version in a manifest that has
already passed `verify_release`. Anything not pinned is denied; a missing,
invalid, or expired manifest allows nothing.

The CLI is argv-only and offline:

```bash
python3 /usr/share/aether/scripts/update-push.py --check
python3 /usr/share/aether/scripts/update-push.py --apply-plan plan.json
python3 /usr/share/aether/scripts/update-push.py --version
```

- `--check` emits a JSON status report containing `policy_source`, `signature`,
  `allowed_packages`, `pending_upgrades` (APT's simulated upgrades intersected
  with the signed pins), `apt_status`, and `error`. When the signature is not
  `VALID`, `allowed_packages` and `pending_upgrades` are empty. On a host without
  `apt-get`/`apt-cache` it reports `apt_status: "apt-unavailable"` and no state
  is fabricated.
- `--apply-plan <plan.json>` validates every entry against the signed manifest
  and prints an APT argument-vector plan to stdout. It never runs APT. A plan is
  a list, or an object with an `entries` list, whose entries are
  `{"package": ..., "version": ..., "action": "install"|"upgrade"|"hold"}`.
  Any unpinned package, version mismatch, or unknown action denies the whole
  plan (`status: "denied"`, empty `argv`, non-zero exit). Valid argv are lists
  of strings such as `["apt-get", "install", "-y", "--no-install-recommends",
  "aether-shell=1.4-2"]`.
- `--version` prints the tool version.

Example `--check` output:

```json
{
  "version": "update-push 1.0",
  "policy_source": "signed-manifest",
  "signature": "VALID",
  "channel": "stable",
  "allowed_packages": ["aether-shell", "aether-updater"],
  "pending_upgrades": [
    {"package": "aether-shell", "current": "1.3-1", "version": "1.4-2", "origin": "Debian:13/stable"}
  ],
  "apt_status": "ok",
  "expires": "2026-12-01T00:00:00Z",
  "min_os_version": "1.0",
  "error": null
}
```

`signature` is `VALID`, `INVALID`, or `MISSING`. APT is invoked only through the
argument-vector helper in `core/update/apt_policy.py` (`apt-get -s upgrade`,
`apt-cache policy <pkg>`) with a bounded 30-second timeout; no shell is used.

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
