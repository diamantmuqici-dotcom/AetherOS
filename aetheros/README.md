# AetherOS

AetherOS is one desktop built from the best of **Windows, Linux and macOS** — familiar layouts, a real app ecosystem, and gaming baked in. Original Aether shell, beginner-first setup, offline wallpaper gallery, and a full Aether app suite preinstalled.

**Sovereign edition** (`privacy/sovereign-edition`): no Aether telemetry, geolocation or MAC collection; DNS-over-TLS + MAC randomization; LUKS2 full-disk encryption with the key held off-image; Ed25519-signed updates; a real Windows/macOS-style taskbar. Open source stays open — no secret lives in the code, and that is what makes the no-tracking claim verifiable.

> Current build: reproducible container build on GitHub Actions (`ubuntu-24.04` runner). Produces a downloadable `.iso` (Actions artifact + Release on tags).

## Quick start (reproducible)

```bash
make iso        # via Docker (aetheros/builder)
make test-qemu  # boot ISO in QEMU/VirtIO
```

Or watch it build: https://github.com/diamantmuqici-dotcom/AetherOS/actions → latest run → Artifacts → `aetheros-live-iso`

## First-boot flow

Welcome → Language → Keyboard → Network → **Choose Your Aether** (cover-fit gallery, live desktop preview with dock/icons, Fill/Cover default, 4K variants) → Appearance → Privacy → Gaming → Your AetherOS Is Ready → Enter AetherOS (no reboot).

## Layout

```
aetheros/
  iso/       live-build config + payload (gsettings, wallpapers, hooks)
  core/      vault/, update/, mail/, backup/, privacy/, fde/, network/ — audited crypto, signed updates, real mail, verified restore, no-tracking policy, disk encryption, network hardening
  shell/     GNOME extensions: dock/ (real taskbar) launcher/ notifications/ animations/
  setup/     Aether Setup — GTK4 wizard (10 wallpapers, 4K, guided tour)
  settings/  Aether Settings — sidebar + Power/Gaming/Animations panels
  apps/      browser/ mail/ app-center/ security-center/ vault/ updater/ gaming-hub/ antivirus/ backup/
  scripts/   mk-thumbs, mk-4k, aether-fix, aether-doctor, aether-tune-vault, test-iso, sign-iso,
             sync-payloads, payload-manifest, generate-release-key, make-release-metadata,
             aether-privacy, luks2-setup, fde-verify, network-encrypt
  tests/     vault, update-signature, apt-policy, AV, mail (+extras), backup, gamemode,
             clipboard, release-metadata, gtk-readiness, payload-sync, hardening, iso,
             taskbar, privacy, fde, network-encryption (315 tests)
  assets/    wallpapers, logo, emblem, manifest (1080p + 4K)
  docs/      APPS, BROWSER, MAIL, UPDATES, RECOVERY, ENCRYPTION, ANIMATIONS, AV, BACKUP,
             BEGINNERS, TESTING, HARDENING, SUPPORT_MATRIX, INSTALL, PAYLOADS, RELEASE, GTK-AUDIT,
             PRIVACY, NETWORK, TASKBAR
```

Preinstalled: Aether Browser (Chromium + managed policy + MV3 filter), Mail
(IMAP/SMTP/PGP, attachments, IDLE push), Vault (keyfile + 30s clipboard auto-clear),
Updater (signed, authenticated APT policy), Antivirus (signed definitions,
fail-closed), Backup (verified non-destructive restore), App Center, Security Center,
Animations, Gaming Hub (PID-scoped GameMode), Doctor, Fix, plus the GNOME/gaming/media
stack. Everything launches without a download first.

Verification status: 315 tests pass (20 environment-gated skips); 84/84 payload
mirrors byte-identical. ISO boot, live GTK/taskbar rendering, live IMAP/SMTP and
live DNS-over-TLS remain owed on a Linux runner — see `docs/SUPPORT_MATRIX.md`
and `docs/GTK-AUDIT.md`. The download portal lives in `../website/`; verification
walkthroughs are at `../website/verify.html`.

## Docs & install

See `docs/APPS.md` for the full preinstalled app list and the one-command repair (`aether-fix`). `docs/BEGINNERS.md` is the plain-language help table; `aether-doctor` prints what's wrong and the exact command to fix it. `docs/INSTALL.md`, `docs/SUPPORT_MATRIX.md`, `docs/TESTING.md` cover flashing + verification.

## Design

Deep Obsidian `#0F131A`, Deep Void `#08090C`, Aether Blue `#00A3FF`, Indigo `#2B56FF`. Premium, minimal.

See `ARCHITECTURE.md` for the phase plan.
