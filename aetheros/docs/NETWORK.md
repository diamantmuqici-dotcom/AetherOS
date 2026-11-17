# AetherOS network encryption

Whole-OS network hardening shipped as static config drop-ins plus a headless,
fail-closed report tool. No live network state is read on this bench; the tool
reports what the shipped configuration declares, and fails closed when a file
is missing or malformed.

## What is encrypted

- **DNS queries** — systemd-resolved uses DNS-over-TLS (`DNSOverTLS=yes`) to
  Cloudflare (`1.1.1.1` / `1.0.0.1`, TLS name `cloudflare-dns.com`), with Quad9
  (`9.9.9.9#dns.quad9.net`) as fallback. The `server#tls-name` form gives
  resolved the certificate name to authenticate; inline `#` is data here, not
  a comment.
- **Browser DNS** — Chromium managed policy sets DoH mode and WebRTC hardening;
  the homepage defaults to DuckDuckGo.
- **App traffic** — the Aether updater and AV definition fetch are HTTPS and
  Ed25519-signed; the signature is verified before any field is read.
- **On-wire identity** — WiFi scan and cloned MAC addresses are randomized
  (`wifi.scan-rand-mac-address=yes`, `wifi.cloned-mac-address=random`,
  `ethernet.cloned-mac-address=random`), so the real hardware MAC is not sent
  on probes or associations.

## What is NOT encrypted

- IP source/destination headers and packet sizes are visible on the wire.
- SNI is plaintext unless ECH is negotiated by the client and server.
- Traffic from user-installed third-party apps is outside Aether's policy.
- WireGuard/VPN is user-configurable but not forced.
- No live DoT/MAC/sysctl verification ran on this bench — that is owed on a
  Linux host with a real interface.

## Config files (exact render outputs)

| File | Renderer | Effect |
|---|---|---|
| `iso/config/includes.chroot/etc/systemd/resolved.conf.d/aether-dns.conf` | `render_resolved_conf()` | DNS-over-TLS + fallback |
| `iso/config/includes.chroot/etc/NetworkManager/conf.d/aether-wifi.conf` | `render_nm_conf()` | WiFi/eth MAC randomization |
| `iso/config/includes.chroot/etc/sysctl.d/99-aether-network.conf` | `render_sysctl()` | rp_filter=2, reject redirects, IPv6 temp addresses |

Each shipped file is byte-identical to its renderer output; the test suite
asserts this. Kernel sysctls cover reverse-path filtering (`rp_filter=2` on
all/default interfaces), ignoring and not sending ICMP redirects, and IPv6
privacy extensions (`use_tempaddr=2`).

## Core module

`core/network/policy.py` is pure — no `gi`, sockets, or filesystem at import.
It exposes the three renderers, matching parsers, and `network_status(...)`,
which builds a canonical report with fields `dns_over_tls`, `mac_randomization`,
`antispoof`, `browser_doh`, `overall`, and `gaps`. Overall is `NETWORK_HARDENED`
only when every control is present; any missing or malformed fragment becomes
a gap, so a failed read can never be reported as hardened.

## CLI

`aether-network-encrypt` (mirrored at
`iso/config/includes.chroot/usr/local/bin/aether-network-encrypt`):

- `--check [--root PATH]` — emit canonical JSON status read from the shipped
  config files under `--root` (default the chroot path), plus the Chromium DoH
  policy setting when present. No side effects; fails closed when files are
  absent.
- `--apply --dest ROOT [--force]` — write the three config files (mode 0644)
  to a destination root. Refuses to overwrite without `--force`. Never touches
  live `/etc` unless explicitly rooted there.
- `--self-test` — run pure policy assertions without any files.
- `--version` — print the tool version.

No `shell=True`, `eval`, or network calls. All operations are argv-only.

## Verification

```
python -m unittest discover -s aetheros/tests -p 'test_network_encryption.py' -v
```
