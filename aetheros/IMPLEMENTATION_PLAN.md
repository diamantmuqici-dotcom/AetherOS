# AetherOS Implementation Checklist (Phase 1 audit → phases)

Status key: DONE (verified here), CONFIG (changed and unit-tested, not built/booted), OPEN (not implemented).

## Verification summary (integration pass 2 — all ten follow-up workstreams)
- Full Python suite: `python -m unittest discover -s aetheros/tests -p 'test_*.py'` → **235 tests, OK (20 skips)**.
- Added suites: apt-policy 23, AV 23, mail-extras 23, backup 16, gamemode 16, clipboard 12, release-metadata 12, gtk-readiness 4 (+13 tolerant skips), iso 27, payload-sync 7.
- `python -m compileall -q aetheros` clean. CI YAML parses; GNOME schema XML, Chromium policy JSON, MV3 extension JSON all parse.
- 68/68 source→chroot payload pairs byte-identical (`scripts/sync-payloads.sh check`); 25/25 `.desktop` Exec targets resolve.
- No private keys/tokens in source; only a documented key path and a test fixture password.
- NOT verified: ISO build/boot, GNOME Shell extension load, Plymouth render, GTK UI runtime, live IMAP/SMTP — no Linux host/QEMU image on this bench. `scripts/test-iso.sh --self-test` validates boot-check logic without QEMU; `ci.yml` runs the real boot test on a Linux runner. `scripts/gtk-smoke.sh --all` validates headless modes; `docs/GTK-AUDIT.md` lists the owed desktop checks.

## 0. Branding, motion and preinstalled apps
- [x] Aether-only branding: os-release, MOTD, website, README, architecture/support/vault docs.
- [x] Real `/etc/os-release` hook generates Aether identity; functional `VERSION_CODENAME=trixie` / `ID_LIKE=debian` pinned against values-file override so apt stays working.
- [x] Aether Plymouth boot splash replaces upstream art; `quiet splash` on the live boot line; upstream splash themes removed at build.
- [x] Aether Animations extension: full/reduced/off + intensity/window/workspace/lock keys, settings panel, setup wired. Motion pass two adds window map/close, workspace, lock-screen motion.
- [x] Every Aether desktop entry resolves to a real launcher (25/25 checked statically).
- [x] Browser and Mail launch real preinstalled engines; App Center, Security Center, Doctor added.
- [x] `aether-fix` repairs launchers, permissions, schemas, services and boot theme; verified at build and on first boot.
- [x] One-command repair + beginner layer: `aether-doctor` (read-only), three-card guided tour, `docs/BEGINNERS.md`.

## 1. Repository audit and architecture
- [x] Branch `hardening/aetheros-phase-1`; findings in `SECURITY.md`.
- [x] Component boundaries introduced: `core/update/`, `core/mail/`, `core/vault/` keyfile/recovery/benchmark.
- [x] Payload single source of truth: `scripts/payload-manifest.txt` declares all 68 source→chroot mirror pairs; `scripts/sync-payloads.sh check|apply` verifies/copies byte-for-byte, cwd-independent (7 tests). Mirrors kept, now governed by the manifest.

## 2. Trixie base
- [x] Both `build-iso.yml` workflows: container `debian:trixie-slim`, `lb config --distribution trixie`, `--debian-installer none` kept functional.
- [x] codec-pack repointed bookworm → trixie; keyring → `debian-archive-keyring`.
- [x] Package list adds crypto/mail/update dependencies: `python3-cryptography`, `gnupg`, `cryptsetup`, `apparmor`, `apparmor-utils`, `flatpak`.
- [ ] Rebuild ISO on a Debian host/container and boot-test it. Logs under `iso/` are historical records, left untouched.
- [ ] Re-audit package availability in Trixie.

## 3. Security remediation
- [x] Vault crypto Argon2id + ChaCha20-Poly1305, atomic writes; 15 tests.
- [x] `shell=True` removed from factory-reset; argv subprocesses + target allow/deny lists; 9 hardening tests.
- [x] Ed25519 signature verification for release manifests, verified before any field is read; 13 tests.
- [x] Service hardening: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, scoped `ReadWritePaths` on all five aether services; AppArmor enforce profiles for Browser and Mail.
- [x] Security Center backed by real `aa-status`/`ufw`/`nft`/`systemctl`/`apt` state.

## 4. Aether Vault
- [x] Secure format, atomic writes, backup, migration, password change, CLI.
- [x] Argon2id benchmark/tuner (`aether-tune-vault`), keyfile factor + HKDF, 24-word recovery phrase with checksum, LUKS2 installer helper (`AETHER_CONFIRM` gate). 16 tests.
- [x] Clipboard auto-clear: pure timer logic, 30s default, deferred gi, no plaintext at rest; 12 tests (`docs/GTK-AUDIT.md` verifies structure statically).
- [ ] GTK UI runtime verification on a live desktop — owed on a Linux runner; `scripts/gtk-smoke.sh --all` + `docs/GTK-AUDIT.md` list the exact per-window/per-button checks. Also found and fixed a real import-time defect in `settings/aether-settings.py` (`Adw.Application` base evaluated while `Adw=None`; now built in `make_settings_class()` after gi is bound).

## 5. Aether Mail
- [x] Account validation with TLS enforcement; IMAP sync (200-header/2 MiB caps, text/plain only), SMTP send with implicit/STARTTLS.
- [x] SecretService-first credentials with Argon2id + ChaCha20-Poly1305 local fallback, 0600, no plaintext.
- [x] Mail Lock: Argon2id verifier, inactivity predicate, suspend/lock hooks.
- [x] OpenPGP via gpg argv + stdin, fingerprint validation, fail-closed.
- [x] Allowlist HTML sanitizer, remote-image blocked by default.
- [x] GTK4 app with real account/sync/read/compose/lock actions, PGP status before send. 19 tests. Headless `--check`.
- [x] Attachments (bounded 10 MiB/file, 20 MiB total, extension+magic agreement, executable blocklist, base64 MIME) and IMAP IDLE push (bounded reads, cancel, max 3 reconnects); 23 tests.
- [ ] Live IMAP/SMTP server integration; calendar/Exchange/OAuth2 browser flow — owed on a live server; no mail server on this bench.

## 6. Update infrastructure
- [x] Signed release manifests (Ed25519), 1 MiB cap, schema + UTC expiry, fail closed.
- [x] Channels stable/beta/development with per-channel overrides; upgrade plan intersects only manifest-pinned versions.
- [x] Update Center UI reads real apt state; refuses apply unless signature VALID; snooze persisted. Headless `--check` JSON.
- [x] `sign-iso.sh` manifest signing with `AETHER_SIGNING_KEY` (private key never in repo); `docs/UPDATES.md`, `docs/RECOVERY.md`.
- [x] Release key scaffolding: `scripts/signing/generate-release-key.sh` (offline Ed25519, 0600/0644, fingerprint-only output, refuses repo writes) + `make-release-metadata.py` (canonical signed JSON + SHA256SUMS, fail-closed unsigned); 12 tests. Staging notes: `README.av-key`, `docs/RELEASE.md`.
- [ ] Bake release public key into the ISO: drop `aether-release.pub.pem` + `aether-av.pub.pem` into `.../updates/` before a signed build. Held — no key generated on this bench by design.
- [x] Authenticated APT policy replacing the `update-push.py` GitHub check: signature-verified manifest pins only; `--check`/`--apply-plan` emit argv lists, execute nothing; 23 tests.

## 7–16. Desktop, apps, gaming, privacy, backup, installer
- [x] Browser: Chromium managed policy (DoH, WebRTC, no sync/sign-in), MV3 filter extension, profile isolation, `--diagnose`.
- [x] App Center: Flatpak + dpkg listing, permission panel, install/remove, `--list` JSON.
- [x] Security Center: real system state, `--check` JSON.
- [x] GameMode PID-scoped (`--pids`/runtime dir/`pgrep -x` allowlist, `/proc` verified, cap 64) with `trap EXIT INT TERM` guaranteed restore and performance/balanced/quiet presets; 16 tests, three copies byte-identical.
- [x] Backup/recovery: canonical sha256 manifest, **no `--delete`**, dry-run default, non-destructive hash-verified restore with source/target path-containment guards; 16 tests.
- [x] First-boot wizard + guided tour; Aether-only branding across boot, login, desktop.

## 17–23. Architecture, QA, docs, release
- [x] `SECURITY.md`, `IMPLEMENTATION_PLAN.md`, `docs/BROWSER.md`, `docs/MAIL.md`, `docs/UPDATES.md`, `docs/RECOVERY.md`, `docs/ENCRYPTION.md`, `docs/ANIMATIONS.md`, `docs/BEGINNERS.md`, `docs/TESTING.md`, `docs/HARDENING.md`, `docs/APPS.md`, plus pass 2: `docs/AV.md`, `docs/BACKUP.md`, `docs/PAYLOADS.md`, `docs/RELEASE.md`, `docs/GTK-AUDIT.md`.
- [x] Automated OS tests staged: `scripts/test-iso.sh` (QEMU/OVMF boot smoke, exit 0/1/77) + `.github/workflows/ci.yml` (`static-checks`, `iso-boot-test`). CI runs the full unit matrix strictly.
- [x] ISO/CI robustness: `test-iso.sh --self-test` (12 pure assertions, no QEMU), `--timeout 30..900`, os-release payload check, complete result JSON on every exit path; `ci.yml` fails explicitly on skip-77, strict unittest retained; 27 ISO tests.
- [ ] Execute `ci.yml` on GitHub runners and confirm the ISO boot test passes end to end — owed on a Linux runner.
- [x] Reproducible metadata: `make-release-metadata.py` canonical signed JSON + `SHA256SUMS`, `SOURCE_DATE_EPOCH` support; signing key held outside repo. Full reproducible ISO bit-for-bit verification still owed on a Linux runner.
