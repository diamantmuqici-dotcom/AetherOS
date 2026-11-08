# Privacy

- Default: **no telemetry, no advertising identifiers, no behavioral tracking**.
- Crash reports / diagnostics / usage: **off by default**, opt-in only in Aether Setup → Privacy. Stored at `~/.config/aether/privacy.json`.
- No hidden cloud sync. Network privacy: NetworkManager + optional DNS (e.g., 1.1.1.1, 9.9.9.9) clearly labeled.
- No dark patterns: toggles explain exactly what turns on.
- Verify: `grep -r telemetry /usr/share/aether` → no endpoints; `privacy.json` is the single source of truth.
