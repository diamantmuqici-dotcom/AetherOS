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
  shell/     GNOME extensions: dock/ launcher/ notifications/ (original)
  setup/     Aether Setup — GTK4 wizard (10 wallpapers, 4K)
  settings/  Aether Settings — sidebar + icons + Power/Gaming panels
  apps/gaming-hub/  Steam/Proton/Zen launcher
  scripts/   mk-thumbs, mk-4k, adaptive-perf, gamemode, firstboot, sign-iso
  assets/    wallpapers, logo, emblem, manifest (1080p + 4K)
  docs/      SUPPORT_MATRIX, PRIVACY, GAMING, INSTALL
```

## Docs & install

See `docs/APPS.md` for the full preinstalled app list and the one-command repair (`aether-fix`). `docs/INSTALL.md` and `docs/SUPPORT_MATRIX.md` cover flashing + test checklist.

## Design

Deep Obsidian `#0F131A`, Deep Void `#08090C`, Aether Blue `#00A3FF`, Indigo `#2B56FF`. Premium, minimal.

See `ARCHITECTURE.md` for the phase plan.
