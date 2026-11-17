# AetherOS Implementation Checklist (Phase 1 audit → phases)

Status key: DONE (verified here), CONFIG (changed and unit-tested, not built/booted), OPEN (not implemented).

## Verification summary (this integration)
- Full Python suite: `python -m unittest discover -s aetheros/tests -p 'test_*.py'` → **83 tests, OK (3 QEMU/ISO skips)**.
- Components: vault 15, vault-extras 16, update-signature 13, mail 19, hardening 9, iso 11 (3 skipped).
- `python -m compileall -q aetheros` clean. CI YAML parses; GNOME schema XML, Chromium policy JSON, MV3 extension JSON all parse.
- 25/25 `.desktop` Exec targets resolve to a launcher or whitelisted system tool.
- NOT verified: ISO build/boot, GNOME Shell extension load, Plymouth render, GTK UI runtime, live IMAP/SMTP — no Linux host/QEMU image on this bench. `scripts/test-iso.sh` + `ci.yml` run these in the build pipeline.

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
- [ ] Remove duplicated payloads under `iso/config/includes.chroot/usr/share/aether` in favour of a packaging step (mirrors kept byte-identical for now).

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
- [ ] GTK UI runtime verification on a live desktop; clipboard auto-clear timer.

## 5. Aether Mail
- [x] Account validation with TLS enforcement; IMAP sync (200-header/2 MiB caps, text/plain only), SMTP send with implicit/STARTTLS.
- [x] SecretService-first credentials with Argon2id + ChaCha20-Poly1305 local fallback, 0600, no plaintext.
- [x] Mail Lock: Argon2id verifier, inactivity predicate, suspend/lock hooks.
- [x] OpenPGP via gpg argv + stdin, fingerprint validation, fail-closed.
- [x] Allowlist HTML sanitizer, remote-image blocked by default.
- [x] GTK4 app with real account/sync/read/compose/lock actions, PGP status before send. 19 tests. Headless `--check`.
- [ ] Live IMAP/SMTP server integration; calendar/Exchange/attachments/OAuth2 browser flow (documented as out of scope in `MAIL.md`).

## 6. Update infrastructure
- [x] Signed release manifests (Ed25519), 1 MiB cap, schema + UTC expiry, fail closed.
- [x] Channels stable/beta/development with per-channel overrides; upgrade plan intersects only manifest-pinned versions.
- [x] Update Center UI reads real apt state; refuses apply unless signature VALID; snooze persisted. Headless `--check` JSON.
- [x] `sign-iso.sh` manifest signing with `AETHER_SIGNING_KEY` (private key never in repo); `docs/UPDATES.md`, `docs/RECOVERY.md`.
- [ ] Bake release public key into the ISO: staging dir `.../updates/` with `README.key`; drop `aether-release.pub.pem` before build. Held — no key generated on this bench.
- [ ] Authenticated APT policy check replacing `update-push.py` GitHub check.

## 7–16. Desktop, apps, gaming, privacy, backup, installer
- [x] Browser: Chromium managed policy (DoH, WebRTC, no sync/sign-in), MV3 filter extension, profile isolation, `--diagnose`.
- [x] App Center: Flatpak + dpkg listing, permission panel, install/remove, `--list` JSON.
- [x] Security Center: real system state, `--check` JSON.
- [ ] GameMode scoped to game PIDs with guaranteed restore; presets.
- [ ] Backup/recovery with integrity verification and non-destructive restore.
- [x] First-boot wizard + guided tour; Aether-only branding across boot, login, desktop.

## 17–23. Architecture, QA, docs, release
- [x] `SECURITY.md`, `IMPLEMENTATION_PLAN.md`, `docs/BROWSER.md`, `docs/MAIL.md`, `docs/UPDATES.md`, `docs/RECOVERY.md`, `docs/ENCRYPTION.md`, `docs/ANIMATIONS.md`, `docs/BEGINNERS.md`, `docs/TESTING.md`, `docs/HARDENING.md`, `docs/APPS.md`.
- [x] Automated OS tests staged: `scripts/test-iso.sh` (QEMU/OVMF boot smoke, exit 0/1/77) + `.github/workflows/ci.yml` (`static-checks`, `iso-boot-test`). CI runs the full unit matrix strictly.
- [ ] Execute `ci.yml` on GitHub runners and confirm the ISO boot test passes end to end.
- [ ] Reproducible build verification; checksums and signed release metadata (key held outside repo).
