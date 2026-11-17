"""AetherOS privacy policy: endpoint allowlist, dconf lockdown, finding schema.

Pure module: no gi, no network, no filesystem writes. Every answer is a
function of its arguments so the audit and the CLI stay unit-testable offline.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

VERSION = "privacy-policy/1"

# Explicit outbound allowlist. Anything outside this set is telemetry by
# definition; subdomains of a listed host inherit that host's purpose.
ALLOWED_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("github.com", "signed AV definitions + release metadata + display links"),
    ("duckduckgo.com", "browser homepage (display only)"),
    ("store.steampowered.com", "gaming hub display-only link"),
    ("zen-browser.app", "gaming hub display-only link"),
)

# System lockdown defaults. Values are GVariant booleans; paths map 1:1 to
# GNOME schemas so dconf reads them without any gsettings process.
PRIVACY_KEYS: tuple[tuple[str, str, str], ...] = (
    ("org.gnome.system.location", "enabled", "false"),
    ("org.gnome.desktop.privacy", "send-software-usage-stats", "false"),
    ("org.gnome.desktop.privacy", "report-technical-problems", "false"),
    ("org.gnome.desktop.privacy", "recent-files-enabled", "false"),
    ("org.gnome.desktop.privacy", "remove-old-temp-files", "true"),
    ("org.gnome.desktop.privacy", "remove-old-trash-files", "true"),
)

_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def is_loopback_host(host: str) -> bool:
    """True for local-only hosts used by offline services and test fixtures."""
    return host.lower() in _LOOPBACK


def _normalize_host(host: str) -> str:
    host = host.strip().lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host


def _allowed_purpose(host: str) -> str:
    for allowed_host, purpose in ALLOWED_ENDPOINTS:
        if host == allowed_host or host.endswith("." + allowed_host):
            return purpose
    return ""


def classify_url(url: str) -> tuple[bool, str, str]:
    """Return (allowed, purpose, reason) for one absolute URL.

    Stable reasons: empty-url, malformed-url, scheme-not-https,
    userinfo-forbidden, malformed-port, nonstandard-port, empty-host,
    ip-literal-host, host-not-allowlisted, ok.
    """
    if not isinstance(url, str) or not url:
        return False, "", "empty-url"
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False, "", "malformed-url"
    if parts.scheme.lower() != "https":
        return False, "", "scheme-not-https"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return False, "", "userinfo-forbidden"
    try:
        port = parts.port
    except ValueError:
        return False, "", "malformed-port"
    if port is not None and port != 443:
        return False, "", "nonstandard-port"
    host = _normalize_host(parts.hostname or "")
    if not host:
        return False, "", "empty-host"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return False, "", "ip-literal-host"
    purpose = _allowed_purpose(host)
    if not purpose:
        return False, "", "host-not-allowlisted"
    return True, purpose, "ok"


def render_dconf_keyfile() -> str:
    """Render the dconf keyfile: slash paths, GVariant booleans, stable order."""
    sections: dict[str, list[str]] = {}
    for schema, key, value in PRIVACY_KEYS:
        path = schema.replace(".", "/")
        sections.setdefault(path, []).append(f"{key}={value}")
    lines = ["# AetherOS privacy lockdown: location off, no telemetry or reporting."]
    for path in sorted(sections):
        lines.append("")
        lines.append(f"[{path}]")
        lines.extend(sections[path])
    return "\n".join(lines) + "\n"


def audit_finding(severity: str, path: str, evidence: str) -> dict[str, str]:
    """Canonical JSON-ready finding; one shape across audit, CLI and tests."""
    return {"severity": severity, "path": path, "evidence": evidence}
