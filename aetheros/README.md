# AetherOS

AetherOS is one desktop built from the best of **Windows, Linux and macOS** — familiar layouts, a real app ecosystem, and gaming baked in. Original Aether shell, beginner-first setup, offline wallpaper gallery, and a full Aether app suite preinstalled.

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
  core/      vault/, update/, mail/, backup/ — audited crypto, signed updates, real mail, verified restore
  shell/     GNOME extensions: dock/ launcher/ notifications/ animations/
  setup/     Aether Setup — GTK4 wizard (10 wallpapers, 4K, guided tour)
  settings/  Aether Settings — sidebar + Power/Gaming/Animations panels
  apps/      browser/ mail/ app-center/ security-center/ vault/ updater/ gaming-hub/ antivirus/ backup/
  scripts/   mk-thumbs, mk-4k, aether-fix, aether-doctor, aether-tune-vault, test-iso, sign-iso,
             sync-payloads, payload-manifest, generate-release-key, make-release-metadata
  tests/     vault, update-signature, apt-policy, AV, mail (+extras), backup, gamemode,
             clipboard, release-metadata, gtk-readiness, payload-sync, hardening, iso (235 tests)
  assets/    wallpapers, logo, emblem, manifest (1080p + 4K)
  docs/      APPS, BROWSER, MAIL, UPDATES, RECOVERY, ENCRYPTION, ANIMATIONS, AV, BACKUP,
             BEGINNERS, TESTING, HARDENING, SUPPORT_MATRIX, INSTALL, PAYLOADS, RELEASE, GTK-AUDIT
```

Preinstalled: Aether Browser (Chromium + managed policy + MV3 filter), Mail
(IMAP/SMTP/PGP, attachments, IDLE push), Vault (keyfile + 30s clipboard auto-clear),
Updater (signed, authenticated APT policy), Antivirus (signed definitions,
fail-closed), Backup (verified non-destructive restore), App Center, Security Center,
Animations, Gaming Hub (PID-scoped GameMode), Doctor, Fix, plus the GNOME/gaming/media
stack. Everything launches without a download first.

Verification status: 235 tests pass (20 environment-gated skips); 68/68 payload
mirrors byte-identical. ISO boot, live GTK rendering and live IMAP/SMTP remain
owed on a Linux runner — see `docs/SUPPORT_MATRIX.md` and `docs/GTK-AUDIT.md`.

## Docs & install

See `docs/APPS.md` for the full preinstalled app list and the one-command repair (`aether-fix`). `docs/BEGINNERS.md` is the plain-language help table; `aether-doctor` prints what's wrong and the exact command to fix it. `docs/INSTALL.md`, `docs/SUPPORT_MATRIX.md`, `docs/TESTING.md` cover flashing + verification.

## Design

Deep Obsidian `#0F131A`, Deep Void `#08090C`, Aether Blue `#00A3FF`, Indigo `#2B56FF`. Premium, minimal.

See `ARCHITECTURE.md` for the phase plan.
