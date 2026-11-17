# Gaming

- Steam: official `steam-installer` deb via Gaming Hub (installed/optional/experimental). Download processes get priority boost (nice -5) while downloading, reset on Steam exit.
- Compatibility: Proton-GE (fetched), Vulkan (Mesa). **No universal compatibility promise.** Game configs graphics-only, input never touched.
- Game Mode: `gamemode` D-Bus + `powerprofilesctl` + notification suppress + **scoped game-PID priority** (nice -5). `gamemode-hook.sh` targets only verified PIDs and restores prior settings on exit. Never kills critical services.
- Controllers: evdev test (button/stick/trigger).
- Zen Browser: official deb (MPL), launcher integration, not rebranded.
- FPS/quality: safe profiles only (Balanced/Performance/Gaming/Battery Saver).
- ESG overlay: `org.aether.Overlay` (FPS/frame/RAM/GameMode) + MangoHud (`mangohud`) — Steam launch: `gamemoderun mangohud %command%`.

## GameMode hook — PID scoping and restore
`gamemode-hook.sh` (also `/usr/local/bin/gamemode-hook`):
- Commands: `start [preset]`, `stop`, `status`. Presets: `performance` (power profile + nice -5 + banners off, default), `balanced` (nice -5 only), `quiet` (banners off only).
- PID sources in order: explicit `--pids 123,456` → gamemode runtime dir (`$XDG_RUNTIME_DIR/gamemode`, `/run/user/$UID/gamemode`) → conservative `pgrep -x` fallback. Capped at 64 PIDs.
- Every candidate is validated as an integer, checked against `/proc/<pid>/comm`/`exe` and a critical-service deny list before any `renice`. No substring `pgrep -f`, no process termination.
- `start` snapshots prior profile/banner values into `$HOME/.config/aether/gamemode/state` (schema marker + timestamp) before changing anything; invalid snapshot aborts with no changes. An `EXIT/INT/TERM` trap restores and removes the snapshot, so a crash or signal cannot leave settings changed. `start` is idempotent; `stop` restores explicitly.
- `sudo -n` is used only for negative `renice` on verified PIDs; otherwise `renice -n 0`. All external calls are argv-only and time-bounded.

## Optimizations (safe only)
`optimize-all.sh`: zram (if present), powerprofiles `balanced`, mouse accel off + flat profile, keyboard delay 250ms/interval 30ms. No undocumented kernel tweaks.
