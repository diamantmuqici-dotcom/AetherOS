# Aether Browser

`aether-browser` is a launcher over a preinstalled browser engine. Privacy
settings come from a Chromium managed policy file, not from command-line
switches. Extensions are declarative and bundled with the image.

## Engines

Discovery order, first match wins:

| Kind | Candidates |
|---|---|
| Chromium | `chromium`, `chromium-browser`, `google-chrome-stable`, `google-chrome` |
| Firefox | `firefox-esr`, `firefox` |

If no engine is on `PATH`, the launcher exits 1 with a repair hint. The engine
is launched directly via an argv list; no shell is involved.

## Managed policy

Path: `/etc/chromium/policies/managed/aether.json` (chroot source:
`iso/config/includes.chroot/etc/chromium/policies/managed/aether.json`).
Chromium reads this file natively. The launcher does not restate any policy key
in argv — no `--disable-sync`, no `--host-resolver-rules`, no
`--webrtc-ip-handling-policy`.

| Key | Value |
|---|---|
| `DefaultSearchProviderEnabled` | `true` |
| `DefaultSearchProviderName` | `Aether Search` |
| `DefaultSearchProviderSearchURL` | `https://search.aetheros.org/search?q={searchTerms}` |
| `DefaultSearchProviderSuggestURL` | `https://search.aetheros.org/suggest?q={searchTerms}` |
| `HomepageLocation` | `https://search.aetheros.org/` |
| `HomepageIsNewTabPage` | `false` |
| `SyncDisabled` | `true` |
| `SigninAllowed` | `false` |
| `DnsOverHttpsMode` | `secure` |
| `DnsOverHttpsTemplates` | Cloudflare and Google DoH templates with `{?dns}` |
| `WebRtcIPHandling` | `disable_non_proxied_udp` |
| `ExtensionInstallSources` | `file:///usr/share/aether/browser/extensions/*` |
| `DefaultNotificationsSetting` | `2` (block) |
| `MetricsReportingEnabled` | `false` |
| `SafeBrowsingProtectionLevel` | `1` (standard) |

The only engine flags in argv are session/lifecycle flags (`--no-first-run`,
`--no-default-browser-check`, `--disable-component-update`,
`--disable-background-networking`, `--force-dark-mode`), the valid feature
disable list `--disable-features=Translate,MediaRouter,OptimizationHints`, the
profile directory, and the bundled extension path when present.

## Bundled extension

Path: `/usr/share/aether/browser/extensions/aether-filter`.

Manifest V3, `declarativeNetRequest` only. `rules.json` contains 26 static
`block` rules keyed to known ad and telemetry hosts (doubleclick,
google-analytics, googletagmanager, facebook connect, scorecardresearch,
quantserve, adnxs, rubiconproject, pubmatic, taboola, outbrain, bing, tiktok,
hotjar, mixpanel, segment, newrelic, crashlytics, amplitude, appsflyer, and
others). Rule IDs are unique positive integers, priority `1`, with resource
types limited to scripts, images, subframes, XHR, and pings.

The launcher adds `--load-extension=<path>` only when `manifest.json` is
present. Removal of the extension directory disables loading without changing
the policy file.

## Profiles

Profiles are isolated per name under `~/.config/aether/browser/<name>`:

```sh
aether-browser                    # uses profile "default"
aether-browser --profile work https://example.org
aether-browser --profile=research
```

Chromium receives `--user-data-dir=<dir>`; Firefox receives
`-profile <dir> -no-remote`. Profile names match
`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`, which prevents path traversal. Engine
arguments are capped at 64 entries of 4096 characters each; no shell is used.

## Diagnose

```sh
aether-browser --diagnose
aether-browser --diagnose --profile work
```

Prints a JSON report with `sort_keys=True`:

- `engine`, `engine_kind` — resolved executable and family, or `null`
- `policy_file`, `policy_present`, `policy_valid_json`
- `extension_path`, `extension_manifest_present`
- `profile_root`, `profiles` — names, paths, and whether each exists

`--diagnose` never imports GTK and never launches an engine.
