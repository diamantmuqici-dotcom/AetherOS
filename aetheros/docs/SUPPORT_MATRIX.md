# Support Matrix

| Component | Status | Notes |
|-----------|--------|-------|
| Debian Bookworm (amd64) | ✅ | Built in `debian:bookworm-slim` container |
| GNOME Wayland | ✅ | Aether shell extensions (original code) |
| Installer | 🔜 Calamares (Phase 6) | Live-boot + first-boot wizard works today |
| 4K display | ✅ | Wallpapers have 4K cover variants (upscaled 1080p→4K) |
| Gaming | 🔜 Steam/Proton-GE/Game Mode (Phase 5) | Hub + scripts staged; install at setup |
| Zen Browser | 🔜 Official deb integration (Phase 5) | Installer script staged |
| QEMU test | ✅ | `make test-qemu` (4096MB, 2 cores, KVM) |

Hardware tested: Ryzen 7 5700X (builder host, not target). Further physical testing via your USB boot — report back CPU/GPU/RAM + what broke.
