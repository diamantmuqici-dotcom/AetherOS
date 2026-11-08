# AetherOS

A real operating system built on **Debian 13 'Trixie'** + **GNOME on Wayland**, with an original Aether shell, first-boot setup, wallpaper gallery, and gaming stack. No Windows/macOS code or assets.

## Quick start (reproducible)

```bash
# on any machine with Docker
make iso
# or inside a Debian 13 VM:
sudo apt install live-build
cd iso && sudo lb config && sudo lb build
# -> live-build produces aether-live-*.iso in current dir
```

Test with KVM (recommended):

```bash
make test-qemu        # needs qemu-system-x86_64
```

## Layout

```
aetheros/
  iso/       live-build config + payload (gsettings, wallpapers, hooks)
  shell/     GNOME extensions (Dock, Launcher, TopBar)
  setup/     Aether Setup — first-boot wizard (GTK4 + libadwaita)
  settings/  Aether Settings — sidebar + 14 panels
  scripts/   build, adaptive-perf, gamemode, firstboot
  assets/    wallpapers (migrated), logo, emblem
  docs/      SUPPORT_MATRIX, PRIVACY, GAMING, INSTALL
```

## First-boot flow

Welcome → Language → Keyboard → Network → **Choose Your Aether** (cover-fit gallery + live desktop preview, Fill by default) → Appearance → Privacy → Gaming → Your AetherOS Is Ready → Enter AetherOS (no reboot).

## Design

Deep Obsidian `#0F131A`, Deep Void `#08090C`, Aether Blue `#00A3FF`, Indigo `#2B56FF`. Premium, minimal — no neon excess.

See `ARCHITECTURE.md` for the full phase plan.
