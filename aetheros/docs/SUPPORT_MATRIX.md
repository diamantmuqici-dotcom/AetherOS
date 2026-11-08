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

| Quick Look (Space peek) | ✅ | `org.aether.QuickLook` / eog+evince |
| Wallpaper slideshow | ✅ | `wallpaper-slideshow.sh` (INTERVAL seconds) |
| Fonts app | ✅ | `org.aether.Fonts` / fc-list + ~/.local fonts |
| Displays HDR/VRR | ✅ | `displays-hdr.py` + gcc display panel |
| Sound spatial (HRTF) | ✅ | `sound-spatial.py` / PipeWire |
| Focus modes | ✅ | `org.aether.Focus` / DND+grayscale |
| Launcher everything search | ✅ | `launcher-search.sh` + shell search |
| Pointer gestures | ✅ | `pointer-gestures.sh` / libinput |
| Bluetooth quick pair | ✅ | `bluetooth-quickpair.sh` / BlueZ |
| Printer IPP | ✅ | `printer-ipp.sh` / system-config-printer |
| Aether Backup | ✅ | `org.aether.Backup` / Deja Dup + rsync |
| System Logs | ✅ | `org.aether.Logs` / journalctl |
| Codec pack (opt-in) | ✅ | `codec-pack.sh` — Debian multimedia opt-in, ISO stays open-only |
| ESG gaming overlay | ✅ | `org.aether.Overlay` + MangoHud/GameMode |
| Accessibility suite | ✅ | `org.aether.Accessibility` / Orca+Magnifier |

Hardware tested: Ryzen 7 5700X (builder host, not target). Further physical testing via your USB boot — report back CPU/GPU/RAM + what broke.
