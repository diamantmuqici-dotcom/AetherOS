# AetherOS Architecture

## 1. Base decision

**Debian 13 'Trixie' stable, amd64 (arm64 later).** Rationale:

- Stable, reproducible, 5-year support, no telemetry by default.
- Self-contained `live-build` + Calamares path; every Phase 1 component is a Debian package.
- Gaming: Steam official deb + Proton-GE (runtime) + Mesa/Vulkan backports pinned by version. Arch is faster-chasing but worse for a non-technical installer; Fedora is shorter-lived.

## 2. Component map

| Layer | Choice | Why |
|-------|--------|-----|
| Kernel/Graphics | Debian kernel + `mesa-vulkan-drivers`, `firmware-linux-nonfree` (opt-in) | Best open Vulkan support; NVIDIA 550+ documented |
| Window server | GNOME Shell (Wayland), XWayland for legacy | Stable Wayland, accessibility, HDR/VVR via Mutter |
| Shell | `aether-shell` extensions: Dock, Launcher, TopBar, notifications | Feels premium in Phase 2 without re-inventing a compositor |
| Setup | `aether-setup` (GTK4 + libadwaita + Python) | Native gsettings/D-Bus, offline-first |
| Settings | `aether-settings` (GTK4) | 14 panels, real backends |
| Files | Nautilus (themed) + `aether-bin` (Trash UI) | Proven GVFS, drag/drop, mounts |
| Terminal | GNOME Terminal + profiles | Tabs/splits; zsh/fish/pwsh detection |
| Gaming | Steam deb, Proton-GE, `gamemode`, evdev | Honest compatibility, no fake promises |
| Browser | Zen Browser deb/tar (MPL) | Official distribution, not rebranded |
| Installer | Calamares (branded) | Partitioning, users, locale/keyboard |

## 3. Data flow — first boot

```
live boot → gdm (Aether theme) → first login → marker ~/.config/aether/firstboot
  → aether-setup (steps) → gsettings apply + /usr/share/backgrounds/aether/*.jpg
  → privacy.json + gaming status → remove marker → desktop session (no reboot)
```

- Wallpaper payload: `/usr/share/backgrounds/aether/*.jpg` + `wallpaper-manifest.json`
- GSettings: `/usr/share/glib-2.0/schemas/90_aether.gschema.override` → `glib-compile-schemas`
- Privacy: `~/.config/aether/privacy.json` (all false by default)
- Adaptive perf: `scripts/adaptive-perf.sh` (VRAM/RAM → blur/transparency/animation)

## 4. Packages (ISO)

Core: `gnome-session`, `gnome-shell`, `gdm3`, `nautilus`, `gnome-terminal`,
`network-manager`, `pipewire`, `wireplumber`, `bluez`, `upower`,
`power-profiles-daemon`, `gamemode`, `python3-gi`, `gir1.2-adw-1`, `calamares`,
`xwayland`, `evince`, `eog`, `totem`, `gnome-text-editor`.

Firmware/graphics: `firmware-linux`, `mesa-va-drivers`, `mesa-vdpau-drivers`,
`libgl1-mesa-dri`, `vulkan-tools` (test).

See `iso/config/package-lists/aether.list.chroot` for the pinned list.

## 5. Phases

1. Foundation (this commit): Docker env, Makefile, live-build ISO, branding, wallpaper payload, QEMU test.
2. Desktop: Dock/Launcher/TopBar extensions, GDM theme, adaptive perf.
3. First Boot: `aether-setup` full wizard.
4. Core Apps: Settings panels, Files/Bin, Terminal profiles.
5. Gaming: Steam/Proton-GE/Game Hub/Game Mode.
6. Installer/Updates: Calamares config, unattended-upgrades.
7. Optimization: boot/memory profiling, weak-hardware tuning, test matrix.

## 6. What is preserved from the old Aether (Windows) repo

- 10 wallpapers (`cosmos-*`, `prism-*`, 1920x1080 JPG q88)
- Identity: `aether-logo.svg`, `aether_emblem.png`, palette
- Concepts: cover-fit gallery logic, hardware-aware game list (re-implemented for Linux)

Windows C# optimizer code is **not** shipped in the ISO.
