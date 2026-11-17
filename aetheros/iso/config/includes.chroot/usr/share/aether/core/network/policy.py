"""Pure whole-OS network encryption policy: renderers, parsers, status.

No gi, no sockets, no filesystem access at import time. All inputs are plain
text/dicts so the report can be unit-tested offline.
"""

from __future__ import annotations

__all__ = [
    "HARDENED",
    "PARTIAL",
    "render_resolved_conf",
    "render_nm_conf",
    "render_sysctl",
    "parse_resolved_conf",
    "parse_nm_conf",
    "parse_sysctl",
    "network_status",
]

HARDENED = "NETWORK_HARDENED"
PARTIAL = "NETWORK_PARTIAL"

# Server names after '#' give systemd-resolved the DoT TLS hostname; they are
# part of the value, not comments.
_DNS_SERVERS = "1.1.1.1#cloudflare-dns.com 1.0.0.1#cloudflare-dns.com"
_FALLBACK_DNS = "9.9.9.9#dns.quad9.net"

_NM_EXPECTATIONS = (
    ("wifi.scan-rand-mac-address", "yes", "wifi-scan-mac-randomization-off"),
    ("wifi.cloned-mac-address", "random", "wifi-cloned-mac-randomization-off"),
    ("ethernet.cloned-mac-address", "random", "ethernet-cloned-mac-randomization-off"),
)

_SYSCTL_EXPECTATIONS = (
    ("net.ipv4.conf.all.rp_filter", "2"),
    ("net.ipv4.conf.default.rp_filter", "2"),
    ("net.ipv4.conf.all.accept_redirects", "0"),
    ("net.ipv4.conf.all.send_redirects", "0"),
    ("net.ipv6.conf.all.accept_redirects", "0"),
    ("net.ipv6.conf.default.use_tempaddr", "2"),
)


def render_resolved_conf() -> str:
    """systemd-resolved drop-in enabling authenticated DNS-over-TLS."""
    return (
        "[Resolve]\n"
        f"DNS={_DNS_SERVERS}\n"
        "DNSOverTLS=yes\n"
        f"FallbackDNS={_FALLBACK_DNS}\n"
        "Domains=~\n"
        "Cache=yes\n"
    )


def render_nm_conf() -> str:
    """NetworkManager drop-in enabling scan and cloned MAC randomization."""
    return (
        "[device]\n"
        "wifi.scan-rand-mac-address=yes\n"
        "\n"
        "[connection]\n"
        "wifi.cloned-mac-address=random\n"
        "ethernet.cloned-mac-address=random\n"
    )


def render_sysctl() -> str:
    """Kernel reverse-path filtering, redirect rejection, IPv6 privacy."""
    return "".join(f"{key}={value}\n" for key, value in _SYSCTL_EXPECTATIONS)


def _parse_key_values(text: str) -> dict[str, str]:
    """Parse key=value lines; only whole-line '#'/';' are comments.

    Inline '#' is preserved because DoT server names use 'host#tls-name'.
    Last assignment wins, matching userspace override behaviour.
    """
    result: dict[str, str] = {}
    if not isinstance(text, str):
        return result
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            result[key] = value.strip()
    return result


def parse_resolved_conf(text: str) -> dict[str, str]:
    """Parse a resolved.conf drop-in into a flat key/value mapping."""
    return _parse_key_values(text)


def parse_nm_conf(text: str) -> dict[str, str]:
    """Parse a NetworkManager .conf file into a flat key/value mapping."""
    return _parse_key_values(text)


def parse_sysctl(text: str) -> dict[str, str]:
    """Parse a sysctl drop-in into a flat key/value mapping."""
    return _parse_key_values(text)


def network_status(resolved, nm, sysctl, chromium_doh: bool) -> dict:
    """Build the canonical fail-closed report from parsed policy fragments.

    Missing, malformed, or non-dict fragments are treated as empty, so a
    failed read can never be reported as a hardened state.
    """
    resolved = resolved if isinstance(resolved, dict) else {}
    nm = nm if isinstance(nm, dict) else {}
    sysctl = sysctl if isinstance(sysctl, dict) else {}
    browser_doh = chromium_doh is True

    gaps: list[str] = []

    if not resolved:
        gaps.append("resolved-config-missing")
    dotls = str(resolved.get("DNSOverTLS", "")).strip().lower()
    dns = str(resolved.get("DNS", "")).strip()
    if dotls != "yes":
        gaps.append("dns-over-tls-disabled")
    if not dns:
        gaps.append("dns-servers-missing")
    dns_over_tls = bool(resolved) and dotls == "yes" and bool(dns)

    if not nm:
        gaps.append("nm-config-missing")
    for key, expected, gap in _NM_EXPECTATIONS:
        if str(nm.get(key, "")).strip().lower() != expected:
            gaps.append(gap)
    mac_randomization = bool(nm) and all(
        str(nm.get(key, "")).strip().lower() == expected
        for key, expected, _ in _NM_EXPECTATIONS
    )

    if not sysctl:
        gaps.append("sysctl-config-missing")
    for key, expected in _SYSCTL_EXPECTATIONS:
        if str(sysctl.get(key, "")).strip().lower() != expected:
            gaps.append(f"sysctl-{key}-mismatch")
    antispoof = bool(sysctl) and all(
        str(sysctl.get(key, "")).strip().lower() == expected
        for key, expected in _SYSCTL_EXPECTATIONS
    )

    if not browser_doh:
        gaps.append("browser-doh-disabled")

    return {
        "dns_over_tls": dns_over_tls,
        "mac_randomization": mac_randomization,
        "antispoof": antispoof,
        "browser_doh": browser_doh,
        "overall": HARDENED if not gaps else PARTIAL,
        "gaps": gaps,
    }
