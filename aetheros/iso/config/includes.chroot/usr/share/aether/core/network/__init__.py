"""AetherOS whole-stack network encryption CLI (argv-only, offline, fail closed)."""

from __future__ import annotations

import json
import os
import pathlib
import sys

from .policy import (
    HARDENED,
    PARTIAL,
    network_status,
    parse_nm_conf,
    parse_resolved_conf,
    parse_sysctl,
    render_nm_conf,
    render_resolved_conf,
    render_sysctl,
)

__all__ = [
    "main",
    "check",
    "apply",
    "self_test",
    "network_status",
]

VERSION = "network-encrypt 1.0"
MAX_CONFIG_BYTES = 1 << 20

RESOLVED_REL = "etc/systemd/resolved.conf.d/aether-dns.conf"
NM_REL = "etc/NetworkManager/conf.d/aether-wifi.conf"
SYSCTL_REL = "etc/sysctl.d/99-aether-network.conf"
CHROMIUM_REL = "etc/chromium/policies/managed/aether.json"

TARGETS = (
    (RESOLVED_REL, render_resolved_conf),
    (NM_REL, render_nm_conf),
    (SYSCTL_REL, render_sysctl),
)

_AETHEROS = pathlib.Path(__file__).resolve().parents[2]


def _default_root() -> pathlib.Path:
    """Resolve the chroot root without ever defaulting to the live host /etc."""
    override = os.environ.get("AETHER_NETWORK_ROOT")
    if override:
        return pathlib.Path(override)
    chroot = _AETHEROS / "iso" / "config" / "includes.chroot"
    in_repo = (
        (_AETHEROS / "core" / "network" / "policy.py").is_file()
        and chroot.is_dir()
    )
    if in_repo:
        return chroot
    if _AETHEROS == pathlib.Path("/usr/share/aether"):
        return pathlib.Path("/")
    return chroot  # fail closed: absent chroot means no host writes


def _read_text(path: pathlib.Path) -> str | None:
    """Read a bounded UTF-8 file; any failure is indistinguishable from absent."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > MAX_CONFIG_BYTES:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _chromium_doh(root: pathlib.Path) -> bool:
    """Read Chromium's managed DoH mode; absent/invalid policy fails closed."""
    text = _read_text(root / CHROMIUM_REL)
    if text is None:
        return False
    try:
        policy = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        return False
    if not isinstance(policy, dict):
        return False
    return str(policy.get("DnsOverHttpsMode", "")).strip().lower() == "secure"


def check(root: pathlib.Path) -> dict:
    """Build the offline status report; never fabricate unread policy state."""
    resolved_text = _read_text(root / RESOLVED_REL)
    nm_text = _read_text(root / NM_REL)
    sysctl_text = _read_text(root / SYSCTL_REL)
    resolved = parse_resolved_conf(resolved_text) if resolved_text is not None else None
    nm = parse_nm_conf(nm_text) if nm_text is not None else None
    sysctl = parse_sysctl(sysctl_text) if sysctl_text is not None else None
    return network_status(resolved, nm, sysctl, _chromium_doh(root))


def apply(root: pathlib.Path, force: bool = False) -> tuple[dict, int]:
    """Write the three rendered drop-ins under root with mode 0644."""
    targets = [(root / rel, render()) for rel, render in TARGETS]
    existing = [str(path) for path, _ in targets if path.exists()]
    if existing and not force:
        return {
            "version": VERSION,
            "status": "refused",
            "root": str(root),
            "written": [],
            "existing": existing,
            "error": "existing config; use --force",
        }, 1
    written: list[str] = []
    try:
        for path, text in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
            path.chmod(0o644)
            written.append(str(path))
    except OSError as exc:
        return {
            "version": VERSION,
            "status": "error",
            "root": str(root),
            "written": written,
            "existing": [],
            "error": type(exc).__name__,
        }, 1
    return {
        "version": VERSION,
        "status": "ok",
        "root": str(root),
        "written": written,
        "existing": [],
        "error": None,
    }, 0


def self_test() -> tuple[dict, int]:
    """Run pure policy assertions without touching the filesystem."""
    checks = 0
    try:
        resolved_text = render_resolved_conf()
        nm_text = render_nm_conf()
        sysctl_text = render_sysctl()
        assert "DNSOverTLS=yes" in resolved_text
        assert "1.1.1.1#cloudflare-dns.com" in resolved_text
        assert "wifi.cloned-mac-address=random" in nm_text
        assert "net.ipv4.conf.all.rp_filter=2" in sysctl_text

        good = network_status(
            parse_resolved_conf(resolved_text),
            parse_nm_conf(nm_text),
            parse_sysctl(sysctl_text),
            True,
        )
        assert good["overall"] == HARDENED and good["gaps"] == []
        bad = network_status(None, None, None, False)
        assert bad["overall"] == PARTIAL and bad["gaps"]
        checks = 7
    except AssertionError:
        return {"version": VERSION, "self-test": "fail", "checks": checks}, 1
    return {"version": VERSION, "self-test": "ok", "checks": checks}, 0


def _emit(report: dict) -> None:
    print(json.dumps(report, sort_keys=True))


def _usage() -> int:
    print(
        "usage: network-encrypt.sh --check [--root DIR] | "
        "--apply [--dest DIR] [--force] | --self-test | --version",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    """Argv-only entry point; no shell strings, no network access."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--version"]:
        print(VERSION)
        return 0
    if args == ["--self-test"]:
        report, code = self_test()
        _emit(report)
        return code
    if args and args[0] == "--check":
        root = _default_root()
        index = 1
        while index < len(args):
            if args[index] == "--root" and index + 1 < len(args):
                root = pathlib.Path(args[index + 1])
                index += 2
            else:
                return _usage()
        _emit(check(root))
        return 0
    if args and args[0] == "--apply":
        root = _default_root()
        force = False
        index = 1
        while index < len(args):
            if args[index] in ("--dest", "--root") and index + 1 < len(args):
                root = pathlib.Path(args[index + 1])
                index += 2
            elif args[index] == "--force":
                force = True
                index += 1
            else:
                return _usage()
        report, code = apply(root, force)
        _emit(report)
        return code
    return _usage()
