# Install

1. **Live boot** the ISO (UEFI). You land on the Aether desktop with a wallpaper.
2. **First boot** auto-launches Aether Setup — choose wallpaper (offline, bundled), appearance, privacy.
3. **Install** via Calamares (Phase 6) — partitioner, users, locale/keyboard. Factory default: Debian `amd64`.
4. After install, first login re-runs Setup if marker present, then **Enter AetherOS** (no reboot).

Flashing: `dd if=aetheros-live-trixie-amd64.iso of=/dev/sdX bs=4M status=progress`
