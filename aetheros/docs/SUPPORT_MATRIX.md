# Support matrix (honest)

| Area | Status | Notes |
|------|--------|-------|
| Intel iGPU (Mesa) | ✅ Supported | Wayland, Vulkan |
| AMD (Mesa) | ✅ Supported | Vulkan + HDR/VRR where Mutter exposes |
| NVIDIA (proprietary) | ⚠️ Supported via docs | 550+ driver; Wayland OK; settings show "check driver" if missing |
| Wi-Fi | ✅ NetworkManager | Requires updated firmware-linux-nonfree for Intel/Realtek |
| Bluetooth | ✅ BlueZ | Headsets/mice/kb/controllers |
| Controllers | ✅ evdev | Xbox, DualSense, 8BitDo — test in Controllers panel |
| Steam / Proton-GE | ✅ Optional | Installed from Gaming Hub; Proton-GE fetched at runtime |
| Game Mode | ⚠️ Experimental | `gamemode` + powerprofiles; restores on exit |
| HDR | ✅ If hardware exposes | Mutter 46+; Settings hides unsupported |
| Multi-monitor | ✅ Mirror/extend, scale 100/200% | Per-monitor scale via Settings |
| ARM64 | 🔜 Phase 7 | ISO is amd64 for Phase 1 |
