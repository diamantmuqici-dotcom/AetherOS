# Recovery

Use these steps when an update is interrupted, a signature fails, or a pinned
package leaves the system in a bad state.

## Signature is INVALID or MISSING

The updater will not apply anything in this state. Check the inputs before
changing packages:

```bash
python3 /usr/share/aether/updater/aether-updater.py --check
```

- `MISSING` — the manifest, `.sig`, or public key is absent from
  `/usr/share/aether/updates/`. Restore them from the signed release payload.
- `INVALID` — the files exist but verification failed: a tampered manifest, a
  mismatched signature, an expired `expires`, or an unknown `schema`.

Do not replace the public key with one from an untrusted source. The correct key
is the one shipped in the installation ISO and listed in the release record.

## Reverting a pinned upgrade

Every planned upgrade records the currently installed version. To roll a package
back to that version, use the value from the last `--check` report or APT state:

```bash
sudo apt-get install --allow-downgrades -y --no-install-recommends <package>=<current-version>
```

APT history lists the exact transaction:

```bash
zgrep -h 'Commandline:' /var/log/apt/history.log*
```

## APT state is inconsistent

```bash
sudo dpkg --configure -a
sudo apt-get -f install -y
apt-cache policy <package>
```

`apt-cache policy` prints `Installed` and `Candidate`. A candidate that differs
from the manifest pin is excluded from planning, so the updater will not install
it. Resolve the repository mismatch before accepting an update again.

## Snooze and declined state

The desktop updater stores its local decision state in
`~/.config/aether/updater.json`:

```json
{"snoozed_at": 1763000000.0}
```

Remove this file to clear a snooze or declined marker:

```bash
rm -f ~/.config/aether/updater.json
```

This affects only the local prompt; it does not change package state or
signature verification.

## Restore from backup

Restores must be verified before they are applied. Check the backup manifest or
checksum that shipped with the backup, then restore to a mounted target rather
than over a running system. After a restore, reboot and run `--check` again to
confirm the manifest, signature, and pinned versions agree with the restored
state.
