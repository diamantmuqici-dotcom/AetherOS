#!/usr/bin/env python3
"""Aether Browser — private Chromium-based (de-googled flags), zero tracking."""
flags = [
    "--no-first-run", "--no-default-browser-check",
    "--disable-component-update", "--disable-background-networking",
    "--disable-sync", "--disable-translate",
    "--force-dark-mode", "--enable-features=EncryptedDns",
    "--dns-over-https-templates=https://cloudflare-dns.com/dns-query",
    "--dns-over-https-mode=secure",
    "--incognito", "--private-window",
    "--disable-hang-monitor", "--webrtc-ip-handling-policy=disable_non_proxied_udp",
]
print("Aether Browser will launch Chromium with:", flags)
