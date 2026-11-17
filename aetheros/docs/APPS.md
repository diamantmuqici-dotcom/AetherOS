# Preinstalled apps

Every Aether app ships in the ISO with a launcher in `/usr/local/bin` and a
desktop entry in `/usr/share/applications`. No app requires a download before
first use.

| App | Launcher | Engine |
|-----|----------|--------|
| Aether Browser | `aether-browser` | Chromium (privacy flags, incognito, encrypted DNS), Firefox fallback |
| Aether Mail | `aether-mail` | Thunderbird, Geary fallback |
| Aether Vault | `aether-vault` | Argon2id + ChaCha20-Poly1305 core |
| Aether Gaming Hub | `aether-gaming-hub` | Steam / Proton-GE / Zen links |
| Aether Settings | `aether-settings` | GTK4 settings app |
| Aether Setup | `aether-setup` | GTK4 first-boot wizard |
| Aether Updater | `aether-updater` | Update Center |
| Aether Animations | `aether-animations full\|reduced\|off` | GNOME Shell extension |
| Aether Fix | `aether-fix` | App and subsystem repair |
| Quick Look, Overlay, Logs, Fonts, Focus, Backup, Accessibility | matching `aether-*` launcher | bundled GTK4 apps |
| Network tune, printer, Bluetooth, wallpaper slideshow, codecs, displays | matching launcher | bundled scripts |

## Beginner repair

If an app will not open, a shortcut is missing, or the boot splash looks wrong:

```
aether-fix
```

It restores launcher permissions, recreates any missing launcher, recompiles
settings schemas, re-enables Aether services, reapplies the Aether boot theme,
then verifies every Aether desktop entry. It reports any unresolved target.

Run it from the Aether Fix desktop entry if you prefer clicking.

## Boot and login branding

The boot splash, login screen, MOTD and desktop use Aether branding only.
`aether-fix` reapplies the boot theme if it was changed.
