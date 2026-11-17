# AetherOS Implementation Checklist (Phase 1 audit → phases)

Status key: DONE (verified here), CONFIG (changed but not built/tested), OPEN (not implemented).

## 0. Branding, motion and preinstalled apps (this pass)
- [x] Aether-only branding: os-release, MOTD, website, README, architecture/support/vault docs.
- [x] Aether Plymouth boot splash replaces upstream art; `quiet splash` on the live boot line; upstream splash themes removed at build.
- [x] Aether Animations extension with full/reduced/off presets, installable schema, wired into setup.
- [x] Every Aether desktop entry resolves to a real launcher (22/22 checked statically).
- [x] Browser and Mail launch real preinstalled engines instead of printing flags / notification stubs.
- [x] `aether-fix` repairs launchers, permissions, schemas, services and boot theme; verified at build and available on first boot.
- [ ] ISO rebuild and boot test to verify splash, extension and app launching at runtime.

## 1. Repository audit and architecture
- [x] Inspect working tree, branch, history, tags — created `hardening/aetheros-phase-1`.
- [x] Read critical apps, workflows, systemd units, privileged scripts.
- [x] Document findings — `SECURITY.md`.
- [ ] Restore component boundaries: dedicated `core/`, `services/`, `apps/` packages per section 17.
- [ ] Remove duplicated payloads under `iso/config/includes.chroot/usr/share/aether` in favour of packaging.

## 2. Debian 13 Trixie base
- [x] Both `build-iso.yml` workflows: container `debian:trixie-slim`, `lb config --distribution trixie`.
- [x] Package-list comment, README, SUPPORT_MATRIX, website docs.
- [ ] Rebuild ISO on a Debian host/container and boot-test it. Logs under `iso/` are historical Bookworm records and were left untouched.
- [ ] Re-audit package availability in Trixie; remove packages deleted from Trixie.

## 3. Security remediation
- [x] Vault crypto rewritten and tested (15 tests).
- [ ] Replace `shell=True` destructive commands with argument-vector subprocesses and explicit path validation.
- [ ] Signature verification for all update/AV/metadata fetches.
- [ ] Service least-privilege review, AppArmor profiles, firewall defaults.
- [ ] Security Center backed by real system state.

## 4. Aether Vault
- [x] Secure format, atomic writes, backup, migration, password change, CLI.
- [ ] GTK UI runtime verification on Debian, Argon2 parameter benchmark, keyfile/recovery flow, clipboard auto-clear.

## 5. Aether Mail — OPEN
- [ ] Core: IMAP sync, SMTP send, TLS enforcement, OAuth2, multi-account.
- [ ] Secret Service credential storage; no plaintext provider passwords.
- [ ] Mail Lock: Argon2id-derived key, auto-lock, inactivity/suspend lock, recovery.
- [ ] OpenPGP via GnuPG/GPGME; key management, PGP/MIME, status before send.
- [ ] Safe HTML rendering, remote-image controls, phishing/link warnings.
- [ ] Full settings panel and mock-server test suite.

## 6. Update infrastructure — OPEN (design required)
- [ ] Signed APT repository (`deb [signed-by=...]`) for Aether packages; Debian security via unattended-upgrades.
- [ ] Release channels stable/beta/development, staged rollout, pause/rollback.
- [ ] CI: format, lint, SAST, dependency scan, unit/integration tests, package build, signed repo metadata with key held outside the repo.
- [ ] Replace `update-push.py` GitHub check with authenticated APT policy check.
- [ ] Update Center UI with real `apt` state and changelogs.

## 7–16. Desktop, apps, gaming, privacy, backup, installer — OPEN
- [ ] Settings type/callback audit; Security/Privacy/Update/About panels.
- [ ] Browser: real Zen integration with official update mechanism; no sandbox weakening.
- [ ] App Center on trusted Debian/Flatpak sources with permission visibility.
- [ ] GameMode scoped to game PIDs with guaranteed restore; presets.
- [ ] Backup/recovery with integrity verification and non-destructive restore.
- [ ] Installer and first-boot wizard; consistent Aether-only branding across boot, login and desktop.

## 17–23. Architecture, QA, docs, release — PARTIAL
- [x] `SECURITY.md`, `IMPLEMENTATION_PLAN.md` added.
- [ ] `README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `RELEASE.md`, `UPDATES.md`, `PRIVACY.md`, `INSTALL.md`, `RECOVERY.md`, `MAIL.md`, `VAULT.md`, `GAMING.md`, `SUPPORT_MATRIX.md` — author/refresh in repo root.
- [ ] Automated OS tests (ISO boot, installer, first boot, update, recovery) on a Debian VM host.
- [ ] Reproducible build from clean environment; checksums and signed release metadata.
