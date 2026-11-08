# Gaming

- Steam: official `steam-installer` deb via Gaming Hub (installed/optional/experimental labels).
- Compatibility: Proton-GE (fetched), Vulkan (Mesa). **No universal compatibility promise.**
- Game Mode: `gamemode` D-Bus + `powerprofilesctl` + notification suppress; restores on exit. Never kills critical services.
- Controllers: evdev test (button/stick/trigger) in Aether Settings → Controllers.
- Zen Browser: official deb/tar per MPL; launcher integration + default browser picker; not rebranded as Aether software.
- FPS/quality: safe profiles only (Balanced/Performance/Gaming/Battery Saver via `power-profiles-daemon`).
