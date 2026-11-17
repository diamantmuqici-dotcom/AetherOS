# Aether Animations

AetherOS motion is driven by `org.aether.animations` and applied by the
`animations@aether` GNOME Shell extension. The stylesheet defines the curves;
the extension toggles CSS classes on the shell UI group and writes the global
compositor animation flag.

## Presets

| Preset | Behaviour |
|---|---|
| `full` | Spring curves at baseline durations (1.0x). |
| `reduced` | Short transitions (~110ms) and a softened spring. |
| `off` | All styled transitions collapse to 1ms and compositor animations are disabled. |

`profile` accepts only `full`, `reduced`, `off`.

## Keys

| Key | Type | Default | Meaning |
|---|---|---|---|
| `profile` | `s` | `full` | Preset selector; choices `full`/`reduced`/`off`. |
| `intensity` | `d` | `1.0` | Duration multiplier, `0.0`–`2.0`. `0.0` collapses transitions. |
| `window-animations` | `b` | `true` | Window map/unmap/close clone transitions. |
| `workspace-swipe` | `b` | `true` | Workspace switcher and overview workspace transitions. |
| `lock-fade` | `b` | `true` | Shield, lock dialog group, login dialog and modal dialog fades. |

`intensity` bands: `0.0` → off (1ms), below `0.75` → soft (~110ms),
`0.75`–`1.25` → baseline, above `1.25` → bold (~320ms).

## CLI

`aether-animations` writes GSettings via argv; no gi or Python bindings needed.

```sh
aether-animations full
aether-animations reduced
aether-animations off
aether-animations set profile reduced
aether-animations set intensity 0.5
aether-animations set intensity 1.75
aether-animations set window off
aether-animations set workspace off
aether-animations set lock off
aether-animations status
```

`status` prints JSON with `profile`, `intensity`, `window-animations`,
`workspace-swipe`, `lock-fade` and `enable-animations`. Invalid presets,
non-numeric or out-of-range intensity, and values other than `on`/`off` return
exit code 2.

The settings app exposes the preset combo, intensity scale and three feature
toggles; every control calls this CLI.

## Selectors

| Selector | Animated property |
|---|---|
| `.window-picker .window-clone` | Opacity and transform for window map/unmap/close clones. |
| `.workspace-switcher` | Opacity, transform and background on workspace switching. |
| `.shell-overview`, `.shell-overview .workspace` | Overview and workspace transition state. |
| `#lockDialogGroup`, `.screen-shield` | Lock-screen opacity and shield background fade. |
| `.login-dialog`, `.modal-dialog` | Login and modal dialog fade with Aether blue border. |
| `.aether-dock`, `.overview`, `.notification` | Existing dock, overview and notification motion. |

`.shell-overview` is attached to the real overview actor by the extension, so
the selector always has a matching widget. The root UI group receives the
`aether-no-window-motion`, `aether-no-workspace-motion`, `aether-no-lock-motion`
and `aether-motion-*` classes from the current settings.

Curves use the palette already in the stylesheet: `cubic-bezier(0.22, 0.85,
0.3, 1.15)` for window/panel motion and `cubic-bezier(0.16, 1, 0.3, 1)` for
shield and notification fades. Accents are `rgba(0, 163, 255, ...)`.

## Reduced motion

`@media (prefers-reduced-motion: reduce)` forces every transition in the sheet
to `1ms` and removes hover transforms, independently of the preset. The `off`
preset and `intensity 0.0` produce the same collapse through the
`.aether-motion-off` class and also set
`org.gnome.desktop.interface enable-animations` to `false`.

Mutter 45–48 has no animation key. The extension checks `list_keys()` before
writing any Mutter or St setting, so unsupported keys are skipped instead of
throwing.
