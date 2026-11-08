# AetherOS — Install & Test

## Quick install (live → installed)
1. Boot the ISO (UEFI) → live desktop with chosen wallpaper
2. First login auto-opens **Aether Setup** — Choose Your Aether → Appearance → Privacy → Gaming → Enter AetherOS
3. For permanent install use **Calamares** (Phase 6) — partitioning, user creation, locale/keyboard

## Flash
- Rufus → select `aetheros-live-*.iso` → **UEFI, GPT, DD mode** → USB ≥8GB → boot with F12/F8/Esc
- Or Ventoy: copy ISO to Ventoy USB, boot and select it

## Screenshots (expected)
| Stage | What you should see |
|-------|---------------------|
| Boot | Aether logo, obsidian gradient, Aether Blue accent |
| Live | Dock at bottom, selected wallpaper, Files/Terminal/Settings in launcher |
| Setup | Welcome → Language → Keyboard (test area) → Network (skip OK) → **Choose Your Aether** (10 wallpapers, cover-fit) → Appearance → Privacy → Gaming |
| Desktop | Wallpaper applied, dark theme, `Enter AetherOS` no reboot |

> Paste screenshots here after test — they go in README too.

## Test checklist
- [ ] Wallpaper gallery shows all 10 offline, Fill/Cover default, no stretch
- [ ] Live preview updates instantly
- [ ] Continue applies wallpaper, desktop shows it
- [ ] Settings sidebar shows all 13 categories with icons
- [ ] Files/Terminal/Settings launch
- [ ] No telemetry prompt, privacy defaults off in `privacy.json`

## Checksum
`sha256sum *.iso > *.iso.sha256` is emitted by the build. Verify with `sha256sum -c *.iso.sha256`.
