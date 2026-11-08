# Gaming

- Steam: official `steam-installer` deb via Gaming Hub (installed/optional/experimental). Download processes get priority boost (nice -5) while downloading, reset on Steam exit.
- Compatibility: Proton-GE (fetched), Vulkan (Mesa). **No universal compatibility promise.** Game configs graphics-only, input never touched.
- Game Mode: `gamemode` D-Bus + `powerprofilesctl` + notification suppress + **game PID priority/affinity** (nice -5). Most-played game gets High priority on launch, restored on exit. Never kills critical services.
- Controllers: evdev test (button/stick/trigger).
- Zen Browser: official deb (MPL), launcher integration, not rebranded.
- FPS/quality: safe profiles only (Balanced/Performance/Gaming/Battery Saver).

## Optimizations (safe only)
`optimize-all.sh`: zram (if present), powerprofiles `balanced`, mouse accel off + flat profile, keyboard delay 250ms/interval 30ms. No undocumented kernel tweaks.
