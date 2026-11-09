# Releasing

AetherOS and its apps release independently, each from its own tag prefix.
Pushing a matching tag triggers that component's workflow in
`.github/workflows/`.

| Component    | Tag pattern       | Workflow                                   | Ships |
|--------------|--------------------|---------------------------------------------|-------|
| AetherOS     | `os-v1.0.0`        | `build-iso.yml`                             | The ISO (`sha256sum`-verifiable) |
| Aether Browser | `browser-v1.0.0` | `release-browser.yml`                       | Standalone Linux/GTK4 bundle |
| Aether Mail  | `mail-v1.0.0`      | `release-mail.yml`                          | Standalone Linux/GTK4 bundle |
| Aether Vault | `vault-v1.0.0`     | `release-vault.yml`                         | Standalone Linux/GTK4 bundle |
| Aether Updater | `updater-v1.0.0` | `release-updater.yml`                       | Standalone Linux/GTK4 bundle |
| Aether Gaming Hub | `gaming-hub-v1.0.0` | `release-gaming-hub.yml`              | Standalone Linux/GTK4 bundle |

Every push to `main` also republishes the rolling `latest` prerelease (OS ISO
only) via `build-iso.yml`, so there's always a current build to test without
cutting a tag.

## Cutting a release

```sh
# AetherOS 1.2.0
git tag os-v1.2.0
git push origin os-v1.2.0

# Aether Browser 1.1.0, independently of the OS version
git tag browser-v1.1.0
git push origin browser-v1.1.0
```

Each component keeps its own version number — the OS and its apps don't have
to move in lockstep. A tag only builds and releases the one component named
in its prefix; it never triggers the others.

## Why apps release separately from the OS

Aether Browser, Mail, Vault, Updater, and Gaming Hub are useful (and
updatable) on their own, and most of them change far more often than the
base OS. Splitting releases means:

- a browser bugfix doesn't force a full ISO rebuild and a new OS version
  number, and
- someone who only wants Aether Mail on their existing GNOME/GTK4 desktop
  can grab just that, without a 1+ GB ISO.

## What the app bundles are (and aren't)

The app release workflows call `aetheros/scripts/package-app.sh`, which zips
the app's source, a `run.sh` launcher, its `.desktop` file (if any), and a
README into one `Aether<App>-linux-x86_64.zip`, plus a `SHA256SUMS` file.

These apps are native AetherOS components built on Python 3 + PyGObject
(GTK4 + libadwaita). The bundles are for other GNOME/GTK4 Linux desktops —
there is no Windows, macOS, or Android build, and the workflows don't
pretend otherwise. Install AetherOS itself to get all of them preinstalled.
