# AetherOS Implementation Checklist (Phase 1 audit → phases)

Status key: DONE (verified here), CONFIG (changed and unit-tested, not built/booted), OPEN (not implemented).

## Verification summary (sovereign-edition integration — branch `privacy/sovereign-edition`)
- Full Python suite: `python -m unittest discover -s aetheros/tests -p 'test_*.py'` → **315 tests, OK (20 skips)**.
- Base suites (235): vault 15, vault-extras 16, update-signature 13, mail 19, hardening 9, iso 27, apt-policy 23, AV 23, mail-extras 23, backup 16, gamemode 16, clipboard 12, release-metadata 12, gtk-readiness 4, payload-sync 7.
- Sovereign-edition suites: taskbar 13, privacy 25, FDE 17, network-encryption 25.
- `python -m compileall -q aetheros` clean. 12 JSON, 2 XML, 3 workflow YAML parse; secret scan clean (no private keys/tokens).
- **84/84** source→chroot payload pairs byte-identical (`scripts/sync-payloads.sh check`), including 16 new mirror pairs added on this branch.
- NOT verified on this bench: ISO build/boot, GNOME Shell taskbar render, GTK UI runtime, live IMAP/SMTP, live DNS-over-TLS / MAC randomization / sysctl effect — no Linux host/QEMU/GNOME desktop here. `scripts/test-iso.sh --self-test` validates boot-check logic without QEMU; `ci.yml` runs the real boot test on a Linux runner.

## 0. Branding, motion and preinstalled apps
- [x] Aether-only branding: os-release, MOTD, website, README, architecture/support/vault docs.
- [x] Real `/etc/os-release` hook generates Aether identity; functional `VERSION_CODENAME=trixie` / `ID_LIKE=debian` pinned against values-file override so apt stays working.
- [x] Aether Plymouth boot splash replaces upstream art; `quiet splash` on the live boot line; upstream splash themes removed at build.
- [x] Aether Animations extension: full/reduced/off + intensity/window/workspace/lock keys, settings panel, setup wired. Motion pass two adds window map/close, workspace, lock-screen motion.
- [x] Every Aether desktop entry resolves to a real launcher (25/25 checked statically).
- [x] Browser and Mail launch real preinstalled engines; App Center, Security Center, Doctor added.
- [x] `aether-fix` repairs launchers, permissions, schemas, services and boot theme; verified at build and on first boot.
- [x] One-command repair + beginner layer: `aether-doctor` (read-only), three-card guided tour, `docs/BEGINNERS.md`.
- [x] Real GNOME Shell taskbar/dock (`shell/dock/extension.js`, `dock@aether`): Show Apps button, favorites + running icons, active-window indicators, clock; clean signal/timer teardown; 13 static tests, `node --check` clean. Owed: live GNOME render check (`docs/TASKBAR.md`).

## 1. Repository audit and architecture
- [x] Branches `hardening/aetheros-phase-1` then `privacy/sovereign-edition`; findings in `SECURITY.md`.
- [x] Component boundaries introduced: `core/update/`, `core/mail/`, `core/vault/`, plus `core/privacy/`, `core/fde/`, `core/network/`.
- [x] Payload single source of truth: `scripts/payload-manifest.txt` now declares 84 source→chroot mirror pairs; `scripts/sync-payloads.sh check|apply` verifies/copies byte-for-byte, cwd-independent. 84/84 pass.

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
- [x] Sovereign-edition audit (2026-11-17): F-1 installer `/tmp` race fixed; V-2/V-3 `eval` sites removed; V-1 backup unsigned mode documented. Full report outside repo.

## 4. Aether Vault
- [x] Secure format, atomic writes, backup, migration, password change, CLI.
- [x] Argon2id benchmark/tuner (`aether-tune-vault`), keyfile factor + HKDF, 24-word recovery phrase with checksum, LUKS2 installer helper (`AETHER_CONFIRM` gate). 16 tests.
- [x] Clipboard auto-clear: pure timer logic, 30s default, deferred gi, no plaintext at rest; 12 tests.
- [x] Full-disk encryption: extended LUKS2 setup (external key model, encrypted swap via 0600 root keyfile, `--check` mode), fail-closed `fde-verify` CLI, pure `core/fde/status.py`; 17 tests + 13 self-test assertions. Honest ESP limitation documented (`docs/ENCRYPTION.md`). Owed: real cryptsetup run on a Linux host.

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
- [x] Release key scaffolding: `scripts/signing/generate-release-key.sh` + `make-release-metadata.py`; 12 tests.
- [ ] Bake release public key into the ISO: drop `aether-release.pub.pem` + `aether-av.pub.pem` into `.../updates/` before a signed build. Held — no key generated on this bench by design.
- [x] Authenticated APT policy replacing the `update-push.py` GitHub check: signature-verified manifest pins only; argv-only plan output; 23 tests.

## 7–23. Desktop, apps, gaming, privacy, backup, installer
- [x] Browser: Chromium managed policy (DoH, WebRTC, no sync/sign-in), MV3 filter extension, profile isolation, `--diagnose`.
- [x] App Center: Flatpak + dpkg listing, permission panel, install/remove, `--list` JSON.
- [x] Security Center: real system state, `--check` JSON.
- [x] GameMode PID-scoped with guaranteed restore and presets; 16 tests, three copies byte-identical.
- [x] Backup/recovery: canonical sha256 manifest, no `--delete`, dry-run default, non-destructive hash-verified restore with path-containment guards; 16 tests.
- [x] First-boot wizard + guided tour; Aether-only branding across boot, login, desktop.
- [x] No-telemetry enforcement: explicit URL allowlist + `classify_url` (HTTPS/IP-literal/userinfo/port rules), bounded static source scanner, dconf lockdown (location off, no problem reporting/metrics), headless `aether-privacy` CLI; 25 tests (`docs/PRIVACY.md`). No geolocation/MAC/telemetry in Aether code.
- [x] Network encryption: DNS-over-TLS (systemd-resolved), WiFi/eth MAC randomization (NetworkManager), anti-spoof sysctls, fail-closed `network-encrypt` CLI and pure `core/network/policy.py`; 25 tests, config files byte-match renderers (`docs/NETWORK.md`). Owed: live network verification.

## 17–23. Architecture, QA, docs, release
- [x] Docs: `SECURITY.md`, `IMPLEMENTATION_PLAN.md`, `docs/BROWSER.md`, `MAIL.md`, `UPDATES.md`, `RECOVERY.md`, `ENCRYPTION.md`, `ANIMATIONS.md`, `BEGINNERS.md`, `TESTING.md`, `HARDENING.md`, `APPS.md`, `AV.md`, `BACKUP.md`, `PAYLOADS.md`, `RELEASE.md`, `GTK-AUDIT.md`, plus `PRIVACY.md`, `NETWORK.md`, `TASKBAR.md`.
- [x] Website: AetherOS download portal at `website/` (index/download/privacy/verify + self-contained CSS/JS), real GitHub Releases links, verification walkthroughs, zero trackers/external requests, no fabricated checksums.
- [x] Automated OS tests staged: `scripts/test-iso.sh` + `.github/workflows/ci.yml`; CI runs the full unit matrix strictly.
- [x] ISO/CI robustness: `test-iso.sh --self-test`, timeout bounds, complete result JSON; 27 ISO tests.
- [ ] Execute `ci.yml` on GitHub runners and confirm the ISO boot test passes end to end — owed on a Linux runner.
- [x] Reproducible metadata: `make-release-metadata.py` canonical signed JSON + `SHA256SUMS`, `SOURCE_DATE_EPOCH`; signing key held outside repo. Full reproducible ISO bit-for-bit verification owed on a Linux runner.
