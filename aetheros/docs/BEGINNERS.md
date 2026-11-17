# AetherOS for Beginners

Plain language for the first days on AetherOS. No jargon, no guessing. Every
problem below has one exact command or one click path.

## The three tools you will use most

| Tool | What it does | How to open it |
|---|---|---|
| Super key | Opens the overview. Type the name of any app to launch it. | Press the Super key |
| Aether Fix | Repairs broken launchers, permissions, services and the boot theme. | Super key, type `Aether Fix`, press Enter — or run `aether-fix` in a terminal |
| Aether Doctor | Reads the system and prints the one command that fixes each problem. | Super key, type `Aether Doctor`, press Enter — or run `aether-doctor` in a terminal |

Aether Doctor never changes anything. It only reports. Aether Fix does the
repair.

## Common problems

| Problem | Exact command or click path | What Aether Doctor reports |
|---|---|---|
| An app icon does nothing when clicked | Run `aether-fix` | `desktop_targets` FAIL with the first unresolved Exec target, then `aether-fix` in the FIX section |
| The browser will not open | Run `aether-fix` | `browser_engine` FAIL when no chromium or firefox is on PATH |
| Mail will not open | Run `aether-fix` | `mail_engine` FAIL when neither thunderbird nor geary is on PATH |
| Window animations stopped working | Run `aether-animations full` | `animations_extension` FAIL with the missing extension path |
| The boot splash is not the Aether theme | Run `aether-fix` | `plymouth_theme` FAIL with the missing theme path |
| The vault will not start | Run `aether-tune-vault` | `vault_module` FAIL with the missing module paths |
| Update signatures are rejected | Run `aether-updater --check` | `signature_key` FAIL — reports `MISSING` for `/etc/apt/trusted.gpg.d/aether.gpg` |
| Security updates are waiting | Run `aether-updater --check` | `security_upgrades` FAIL with the count of pending security upgrades |
| AppArmor reports no loaded profiles | Run `aether-fix` | `apparmor` FAIL with loaded and enforcing profile counts; SKIP when `aa-status` is unavailable |

## Reading Aether Doctor output

Run `aether-doctor` in a terminal. It prints one line per check:

```
CHECK: <check name>: PASS|FAIL|SKIP — <detail>
```

After the checks, the `FIX:` section lists the exact one-line command for each
failing check. Run those commands in the order shown, then run `aether-doctor`
again. Exit status is 0 when every check is PASS or SKIP, 1 if any check FAILs.

For scripts and tooling, `aether-doctor --json` prints the same checks as JSON
with stable key ordering and a `summary` object.

What Aether Fix repairs: launcher wrappers under `/usr/local/bin`, executable
permissions, compiled GLib schemas, the enabled Aether services, and the
Plymouth boot theme. It also reports any desktop Exec target it could not
resolve.

## Where the guided tour appears

The three-card tour is the last step of Aether Setup, after the
**Your AetherOS Is Ready** page and before the **Enter AetherOS** button. It
shows once. Setup writes `~/.config/aether/tour.done`; on later boots the tour
is skipped.

The cards are:

1. **Super key opens everything** — press Super, then type to find any app or file.
2. **Aether Fix repairs anything** — run `aether-fix` when something looks broken.
3. **Aether Doctor tells you what to do** — run `aether-doctor` for the exact fix command.

To see the tour again after the first boot, delete `~/.config/aether/tour.done`
and run `aether-setup`.
