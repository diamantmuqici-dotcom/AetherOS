# Support Matrix

| Component | Status | Notes |
|-----------|--------|-------|
| AetherOS 1.0 (amd64) | ✅ | Reproducible container build; Aether-only branding and boot splash |
| Preinstalled app suite | ✅ | Every desktop entry verified at build; `aether-fix` repairs at runtime |
| Aether Browser / Mail | ✅ | Chromium / Thunderbird engines bundled with privacy defaults |
| Browser policy + filter | ✅ | Managed policy (DoH, WebRTC, no sync), MV3 DNR filter, profile isolation |
| Aether Mail core | ✅ | IMAP/SMTP TLS, OpenPGP, Mail Lock, HTML sanitizer (19 tests); live server untested |
| Mail attachments + IDLE | ✅ | Bounded 10/20 MiB caps, extension+magic agreement, executable blocklist; IMAP IDLE push (23 tests) |
| Signed updates | ✅ | Ed25519 manifest verification before apply; 13 tests; public key staged at build |
| Authenticated APT policy | ✅ | Signature-pinned packages only; `--check`/`--apply-plan` emit argv, execute nothing (23 tests) |
| Aether Antivirus | ✅ | Ed25519-signed definitions, fail-closed, copy-before-delete quarantine; 23 tests |
| Vault keyfile + recovery | ✅ | Argon2id benchmark, 24-word checksum phrase, LUKS2 installer helper (16 tests) |
| Vault clipboard auto-clear | ✅ | 30s timer, fingerprint-only state, no plaintext at rest (12 tests) |
| Animations pass two | ✅ | Window/workspace/lock motion, 5 gschema keys, settings panel |
| Aether Doctor | ✅ | Read-only diagnostics with one-command fixes; `--json` |
| Service + AppArmor hardening | ✅ | 5 services sandboxed, 2 enforce profiles; 9 tests |
| GameMode | ✅ | PID-scoped + `/proc` verified, `trap` guaranteed restore, presets (16 tests) |
| Aether Backup | ✅ | sha256 manifest, no `--delete`, dry-run default, verified non-destructive restore (16 tests) |
| Payload single source | ✅ | 68 source→chroot pairs in `payload-manifest.txt`, strict `sync-payloads.sh check` |
| Release metadata | ✅ | Offline Ed25519 keygen + canonical signed JSON/SHA256SUMS (12 tests); key held outside repo |
| ISO boot test / CI | CONFIG | `test-iso.sh --self-test` (12 assertions) + `ci.yml` skip-fails; full QEMU boot not run on a Linux runner here |
| GTK UI runtime | CONFIG | Static audit + `gtk-smoke.sh --all` headless check; per-window/button render owed on a live desktop (`GTK-AUDIT.md`) |
| GNOME Wayland | ✅ | Aether shell extensions (original code) |
| Installer | 🔜 Calamares (Phase 6) | Live-boot + first-boot wizard works today |
| 4K display | ✅ | Wallpapers have 4K cover variants (upscaled 1080p→4K) |
| Gaming | ✅ Game Mode | PID-scoped GameMode + ESG overlay shipped; Steam/Proton-GE install at setup |
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
| System Logs | ✅ | `org.aether.Logs` / journalctl |
| Codec pack (opt-in) | ✅ | `codec-pack.sh` — multimedia opt-in, ISO stays open-only |
| ESG gaming overlay | ✅ | `org.aether.Overlay` + MangoHud/GameMode |
| Accessibility suite | ✅ | `org.aether.Accessibility` / Orca+Magnifier |

Hardware tested: Ryzen 7 5700X (builder host, not target). Further physical testing via your USB boot — report back CPU/GPU/RAM + what broke.
