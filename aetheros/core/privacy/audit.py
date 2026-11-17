"""Bounded, deterministic static source audit for telemetry patterns.

No file writes, no imports of gi/network libraries, no subprocesses. Findings
carry a severity, a repo-relative path and one bounded evidence line.
"""
from __future__ import annotations

import os
import pathlib
import re
from typing import Iterable
from urllib.parse import urlsplit

from .policy import audit_finding, classify_url, is_loopback_host

MAX_FILES = 20_000
MAX_FILE_BYTES = 8 * 1024 * 1024
SOURCE_SUFFIXES = frozenset({".py", ".js", ".sh"})
IGNORE_MARKER = "privacy-scan-ignore"  # privacy-scan-ignore

# HIGH: harvesting APIs and third-party collectors. MEDIUM: generic network
# primitives that become INFO when their URL is on the explicit allowlist.
_HIGH = (
    (r"navigator\.geolocation", "geolocation-api"),  # privacy-scan-ignore
    (r"\bgeolocation\b", "geolocation"),  # privacy-scan-ignore
    (r"\bgetMac\b", "mac-collection"),  # privacy-scan-ignore
    (r"/sys/class/net/[^\s'\"`]*/address", "mac-address-path"),  # privacy-scan-ignore
    (r"\bsendBeacon\s*\(", "beacon-api"),  # privacy-scan-ignore
    (r"\bgtag\s*\(", "gtag"),  # privacy-scan-ignore
    (r"googletagmanager", "google-tag-manager"),  # privacy-scan-ignore
    (r"\bsentry\b", "sentry"),  # privacy-scan-ignore
    (r"\bmixpanel\b", "mixpanel"),  # privacy-scan-ignore
)
_MEDIUM = (
    (r"\bcurl\s+", "curl"),  # privacy-scan-ignore
    (r"\bwget\s+", "wget"),  # privacy-scan-ignore
    (r"urllib\.request\.urlopen", "urlopen"),  # privacy-scan-ignore
    (r"requests\.", "requests"),  # privacy-scan-ignore
    (r"XMLHttpRequest", "xhr"),  # privacy-scan-ignore
    (r"http://", "insecure-http"),  # privacy-scan-ignore
)
PATTERNS = tuple(
    (re.compile(rx), sev, kind)
    for sev, group in (("HIGH", _HIGH), ("MEDIUM", _MEDIUM))
    for rx, kind in group
)

_URL_RE = re.compile(r"https?://[^\s'\"<>)\]}]+")  # privacy-scan-ignore


def _urls(text: str) -> list[str]:
    """Extract absolute URLs, trimming trailing sentence punctuation."""
    return [u for match in _URL_RE.findall(text) if (u := match.rstrip(".,;:!?"))]


def _classify_urls(urls: Iterable[str]) -> tuple[str, str]:
    """Return (severity, reason) using the worst classification in the set."""
    allowed: list[tuple[str, str]] = []
    denied: list[str] = []
    for url in urls:
        ok, purpose, reason = classify_url(url)
        if ok:
            allowed.append((purpose, url))
        else:
            denied.append(reason)
    if denied:
        return "MEDIUM", denied[0]
    if allowed:
        return "INFO", "allowlisted:" + (urlsplit(allowed[0][1]).hostname or "")
    return "MEDIUM", "no-url"


def _scan_text(text: str, rel: str) -> list[dict]:
    """Scan one source text; emit at most one finding per matching line."""
    file_urls = _urls(text)
    file_severity, file_reason = _classify_urls(file_urls)
    findings: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if IGNORE_MARKER in line:
            continue
        line_urls = _urls(line)
        # Localhost probes are offline fixtures, not outbound telemetry.
        if line_urls and all(is_loopback_host(urlsplit(u).hostname or "") for u in line_urls):
            continue
        for regex, severity, kind in PATTERNS:
            if not regex.search(line):
                continue
            if severity == "HIGH":
                final_severity, reason = "HIGH", kind
            elif line_urls:
                final_severity, reason = _classify_urls(line_urls)
            else:
                final_severity = "INFO" if file_severity == "INFO" else "MEDIUM"
                reason = file_reason if file_urls else "unclassified-network-call"
            evidence = f"{lineno}: {line.strip()[:240]} [{kind}:{final_severity}:{reason}]"
            findings.append(audit_finding(final_severity, rel, evidence))
            break
    return findings


def _sort_key(finding: dict) -> tuple:
    head = finding["evidence"].split(":", 1)[0]
    try:
        lineno = int(head)
    except ValueError:
        lineno = 0
    return (finding["path"], lineno, finding["severity"], finding["evidence"])


def _candidates(root: pathlib.Path, skip: set[str]) -> list[pathlib.Path]:
    """Collect bounded file paths; symlinks and skipped dirs are pruned."""
    if root.is_file():
        return [root] if not root.is_symlink() else []
    found: list[pathlib.Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in skip and not (pathlib.Path(dirpath) / d).is_symlink()
        )
        for name in sorted(filenames):
            found.append(pathlib.Path(dirpath) / name)
            if len(found) >= MAX_FILES:
                return found
    return found


def scan_sources(
    root: pathlib.Path, skip_dirs: tuple[str, ...] = ("tests",)
) -> list[dict]:
    """Walk .py/.js/.sh sources and return deterministic bounded findings."""
    root = pathlib.Path(root)
    skip = set(skip_dirs)
    if not (root.is_dir() or root.is_file()):
        return []
    findings: list[dict] = []
    files_seen = 0
    for path in _candidates(root, skip):
        if files_seen >= MAX_FILES:
            break
        if path.suffix not in SOURCE_SUFFIXES or path.is_symlink():
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files_seen += 1
        rel = path.relative_to(root).as_posix() if root.is_dir() else path.name
        findings.extend(_scan_text(text, rel))
    findings.sort(key=_sort_key)
    return findings
