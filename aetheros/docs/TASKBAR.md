# Aether Dock (Taskbar)

`dock@aether` is a GNOME Shell 45+ bottom taskbar. It is a single ES-module
extension built only on local Shell/Gio APIs — no network access, no telemetry,
no `eval`, and no subprocesses.

## What it does

- **Bottom panel** — a rounded `#0F131A` bar with a `#00A3FF` accent, centered
  along the bottom edge of the screen.
- **App grid / Show Applications** — the leftmost button opens the GNOME
  overview. This is the Start / Launchpad equivalent.
- **App icon strip** — favorites first, then running apps not already pinned.
  Icons come from `Shell.AppSystem` and `AppFavorites`; clicking an icon focuses
  an open window or launches the app if none is open.
- **Active-window indicators** — a small dot under each icon lights up when
  that app owns the focused window, tracked through the Shell window tracker
  and workspace manager signals.
- **Clock/day label** — a short `Day HH:MM` label on the right, refreshed by a
  single GLib timeout every 30 seconds.

The icon list is capped at 40 entries. Icons are rebuilt only when favorites,
installed apps, or the window set actually change — there is no per-frame
allocation loop.

## Enabling

The extension ships in two places: the source at `shell/dock/` and a byte-
identical chroot mirror at
`iso/config/includes.chroot/usr/share/gnome-shell/extensions/dock@aether/`.

```sh
gnome-extensions enable dock@aether
```

Reload the shell if it was installed while the session was running (Alt+F2,
`r` on X11; log out and back in on Wayland). The stylesheet `stylesheet.css`
is loaded automatically by GNOME Shell from the extension directory.

## Windows / macOS familiarity

| Familiar concept | Where it lives here |
|---|---|
| Windows taskbar / macOS Dock | Bottom panel with app icons. |
| Start menu / Launchpad | Show Applications button at the left of the bar. |
| Pinned apps | Favorites from the GNOME app grid, shown first. |
| Running-app button | Any running app appears in the strip even if not pinned. |
| Taskbar window indicator | Active dot under the icon whose window has focus. |
| System tray clock | Clock/day label at the right of the bar. |

## Clean teardown

`disable()` is explicit and ordered so a reload or logout leaves no residue:

1. Removes the clock GLib source and clears the timer list.
2. Disconnects every long-lived and per-icon signal handler.
3. Removes all panel children and destroys the actors.
4. Removes the chrome actor from the layout manager and nulls all references.

Every signal handler and timer created in `enable()` is registered in a list
and reversed in `disable()`; nothing relies on garbage collection.

## Verification status

The static contract is covered by `tests/test_taskbar.py`: real Shell API
usage, clean signal/timer teardown, bounded icon cap, no network/eval/subprocess,
valid JSON manifest, palette CSS with balanced braces, byte-identical source and
chroot mirrors, and a JavaScript syntax check (`node --check`) when Node is
present. All 13 checks pass on this bench.

**Not rendered live.** There is no GNOME Shell desktop in this build
environment, so the taskbar was never displayed on a real session. Runtime
look, feel, icon theming, panel placement and signal behavior still need
verification on a Linux runner with GNOME Shell 45+ (Trixie). That verification
is owed; the static suite does not substitute for it.
