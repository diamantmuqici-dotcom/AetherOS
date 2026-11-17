# AetherOS Phase 1 — Code Hygiene & Service Hardening

Scope: `aetheros/` only. No changes to app launchers, shell scripts, setup,
identity scripts, or documentation outside this file.

## Factory reset

`aether-factory-reset.py` (both the source copy under `apps/factory-reset/`
and the chroot copy under `usr/share/aether/apps/`) now:

- requires the typed `RESET` confirmation and a click on the destructive
  button before any command runs;
- resolves every destructive target through `_validate_target()`: absolute
  path, exists, under `ALLOWED_ROOTS` (`$HOME`), and not equal to or beneath
  any entry in `DENY_PATHS` (`/`, `/etc`, `/usr`, `/var`, `/boot`, `/proc`,
  `/sys`, `/dev`);
- runs `rm -rf --` in bounded 100-child batches via
  `subprocess.run([argv], check=False, timeout=15)` — no shell interpolation,
  no `~` expansion by a shell;
- toggles the firstboot markers with explicit argv and validates
  `firstboot.done` before removing it.

The GTK4/Adw window, label, entry, destructive button, and confirmation flow
are unchanged.

## systemd units

All `aether-*.service` units under `etc/systemd/system/` receive
`NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`,
`ProtectHome=read-only`, `RestrictSUIDSGID=true`, and `LockPersonality=true`.
`MemoryDenyWriteExecute=true` is applied to all five: the units are bash/sh
scripts or stock CPython (no JIT), so denying W^X memory does not break them.
`ExecStart`, `Install`, and `WantedBy` are untouched.
`aether-update-check.timer` has no `[Service]` section and is left unchanged.

System services without `User=` run as root, so `~` in the scripts resolves
to `/root`; `ReadWritePaths` use `/root/...` accordingly. `ReadWritePaths` is
additive over `ProtectSystem=strict` and `ProtectHome=read-only` for the named
paths only.

| Unit | ReadWritePaths | Justification |
|---|---|---|
| aether-update-check.service | `/root/.config/aether`, `/var/cache/apt`, `/var/lib/apt`, `/etc/apt` | writes `updater-last-check`; `apt-get update` refreshes list/cache metadata |
| aether-vpn-auto.service | (none) | reads `~/.config/protonvpn/profile.conf` only; `protonvpn`/`wg-quick` failures are tolerated by `\|\| true` |
| aether-net-tune.service | `/etc/aether`, `/etc/NetworkManager`, `/var/lib/NetworkManager`, `/var/log/aether-boot.log` | writes `best-dns`; `nmcli connection modify` persists to NetworkManager; appends boot log |
| aether-av.service | `/root/.config/aether`, `/usr/share/aether/antivirus` | quarantine files under `~/.config/aether/av`; `sigs.json` updates beside the script |
| aether-self-repair.service | `/root/.config/aether`, `/root/.config/monitors.xml`, `/root/.config/monitors.xml.bak`, `/root/.local/share/Trash`, `/var/log/aether-repair.log` | recreates user dirs, rotates corrupt monitors config, writes crash bundle and log |

## AppArmor

New enforcement profiles (no `flags=(complain)`):

- `etc/apparmor.d/usr.local.bin.aether-browser`
- `etc/apparmor.d/usr.local.bin.aether-mail`

Both anchor on the `/usr/local/bin/aether-*` launcher, include
`<tunables/global>` and `<abstractions/base>` (plus X/fonts/dbus-session for
the GUI), permit `network inet stream`, `network inet6 stream`, `network unix`,
grant read access to `/usr/share/aether`, `/etc/chromium/policies`,
`/usr/lib/chromium`, `/usr/lib/thunderbird`, and read/write only to
`@{HOME}/.config/aether` (plus the app's own cache/profile dir). They carry a
blanket `deny /etc/** w,` with the read-only policy paths above it, and
`audit deny` rules on `~/.ssh`, `~/.gnupg`, `~/.aws`, and
`~/.config/aether/vault`. Enforce mode ships because the executable paths are
stable shell launchers; no learning mode is required.

## Intentionally skipped

- `aether-update-check.timer` — timers have no `[Service]` section.
- `ProtectKernelTunables` and write access to `/proc/sys/...` — net-tune's BBR
  sysctl write is best-effort (`|| true`); granting kernel-tunable writes would
  defeat the hardening, so it is left denied.
- `sudo` under `NoNewPrivileges` in the updater — setuid elevation is blocked,
  but the script runs as root already and guards the call with `|| true`, so
  the unit stays green. Removing `sudo` from that script belongs to the shell
  workstream, not this one.
- `aether-av.service` launcher — `/usr/local/bin/aether-av` is referenced by
  the unit but not present in this tree (pre-existing gap owned by another
  workstream); the `ReadWritePaths` entry assumes install at
  `/usr/share/aether/antivirus`.
- `MemoryDenyWriteExecute` on browser/mail — those are confined by AppArmor
  profiles, not units; Chromium's V8 JIT is handled at the profile layer
  rather than by a unit directive.

## Verification

Run on a host with systemd and AppArmor tooling:

```bash
systemd-analyze verify etc/systemd/system/aether-*.service etc/systemd/system/aether-*.timer
apparmor_parser -Q etc/apparmor.d/usr.local.bin.aether-browser
apparmor_parser -Q etc/apparmor.d/usr.local.bin.aether-mail
python -m unittest discover -s aetheros/tests -p 'test_hardening.py' -v
```
