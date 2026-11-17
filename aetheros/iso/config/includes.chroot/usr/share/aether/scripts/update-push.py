#!/usr/bin/env python3
"""Authenticated APT policy CLI for AetherOS updates (argv-only, offline, fail closed).

Replaces the old unverified GitHub release check. --check emits a JSON status
report; --apply-plan validates a plan against the verified release manifest and
prints the resulting APT argument vectors without executing them.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys

VERSION = "update-push 1.0"
DEFAULT_MANIFEST = "/usr/share/aether/updates/release-manifest.json"
DEFAULT_SIGNATURE = DEFAULT_MANIFEST + ".sig"
DEFAULT_PUBLIC_KEY = "/usr/share/aether/updates/aether-release.pub.pem"
_PLAN_MAX_BYTES = 1024 * 1024


def _ensure_core_importable() -> None:
    """Locate core/update beside scripts/ (repo) or under /usr/share/aether (chroot)."""
    here = pathlib.Path(__file__).resolve().parent
    roots = (
        here.parent,
        pathlib.Path("/usr/share/aether"),
        pathlib.Path("/usr/lib/aether"),
    )
    for root in roots:
        if (root / "core" / "update" / "signature.py").is_file():
            text = str(root)
            if text not in sys.path:
                sys.path.insert(0, text)
            return


_ensure_core_importable()
from core.update.apt_policy import (  # noqa: E402
    POLICY,
    PolicyError,
    build_apt_argv,
    build_policy_from_manifest,
    intersect_upgrades_with_policy,
    run_simulated_upgrade,
    validate_plan,
)
from core.update.signature import (  # noqa: E402
    MAX_MANIFEST_BYTES,
    SignatureError,
    verify_release,
)


def _paths() -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    return (
        pathlib.Path(os.environ.get("AETHER_RELEASE_MANIFEST", DEFAULT_MANIFEST)),
        pathlib.Path(os.environ.get("AETHER_RELEASE_SIGNATURE", DEFAULT_SIGNATURE)),
        pathlib.Path(os.environ.get("AETHER_RELEASE_PUBLIC_KEY", DEFAULT_PUBLIC_KEY)),
    )


def _signature_status() -> tuple[str, dict | None]:
    """Return (VALID|INVALID|MISSING, verified payload)."""
    manifest, signature, public_key = _paths()
    if not (manifest.is_file() and signature.is_file() and public_key.is_file()):
        return "MISSING", None
    try:
        raw = manifest.read_bytes()
        if len(raw) > MAX_MANIFEST_BYTES:
            raise SignatureError("manifest exceeds 1 MiB")
        payload = verify_release(raw, signature, public_key)
    except (SignatureError, OSError):
        return "INVALID", None
    return "VALID", payload


def _channel() -> str:
    return os.environ.get("AETHER_UPDATE_CHANNEL", "stable")


def _emit(report: dict) -> None:
    print(json.dumps(report, sort_keys=True))


def check() -> dict:
    """Build the offline status report; never fabricate APT state."""
    channel = _channel()
    report = {
        "version": VERSION,
        "policy_source": None,
        "signature": "INVALID",
        "channel": channel,
        "allowed_packages": [],
        "pending_upgrades": [],
        "apt_status": "not-run",
        "expires": None,
        "min_os_version": None,
        "error": None,
    }
    state, payload = _signature_status()
    report["signature"] = state
    if state != "VALID" or payload is None:
        report["error"] = f"signature {state.lower()}"
        return report
    try:
        policy = build_policy_from_manifest(payload, channel)
    except PolicyError as exc:
        report["error"] = f"invalid policy: {exc}"
        return report
    report["policy_source"] = policy["source"]
    report["allowed_packages"] = policy["allowed"]
    report["expires"] = policy["expires"]
    report["min_os_version"] = policy["min_os_version"]

    missing = [
        name for name in ("apt-get", "apt-cache") if shutil.which(name) is None
    ]
    if missing:
        report["apt_status"] = "apt-unavailable"
        report["error"] = "apt binaries absent: " + ", ".join(missing)
        return report
    upgrades, status = run_simulated_upgrade()
    report["apt_status"] = status
    report["pending_upgrades"] = intersect_upgrades_with_policy(policy, upgrades)
    return report


def _read_plan(path: str) -> tuple[list[dict], str]:
    """Read a bounded plan file and return (entries, status)."""
    try:
        p = pathlib.Path(path)
        data = p.read_bytes()
    except OSError as exc:
        return [], f"cannot read plan: {type(exc).__name__}"
    if len(data) > _PLAN_MAX_BYTES:
        return [], "plan exceeds 1 MiB"
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return [], "plan is not valid JSON"
    if isinstance(parsed, list):
        return parsed, "ok"
    if isinstance(parsed, dict):
        for key in ("entries", "actions", "upgrades"):
            if isinstance(parsed.get(key), list):
                return parsed[key], "ok"
        return [], "plan has no entry list"
    return [], "plan root must be a list or object"


def apply_plan(path: str) -> tuple[dict, int]:
    """Validate each entry against the signed manifest; emit argv, never execute."""
    base = {
        "version": VERSION,
        "policy_source": None,
        "signature": "INVALID",
        "status": "denied",
        "argv": [],
        "error": None,
    }
    state, payload = _signature_status()
    base["signature"] = state
    if state != "VALID" or payload is None:
        base["error"] = f"signature {state.lower()}"
        return base, 1
    try:
        policy = build_policy_from_manifest(payload, _channel())
    except PolicyError as exc:
        base["error"] = f"invalid policy: {exc}"
        return base, 1
    base["policy_source"] = policy["source"]

    entries, status = _read_plan(path)
    if status != "ok":
        base["error"] = status
        return base, 1
    normalized, status = validate_plan(policy, entries)
    if status != "ok":
        base["error"] = status
        return base, 1
    base["status"] = "ok"
    base["argv"] = build_apt_argv(normalized)
    return base, 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--version"]:
        print(VERSION)
        return 0
    if args == ["--check"]:
        _emit(check())
        return 0
    if len(args) == 2 and args[0] == "--apply-plan":
        report, code = apply_plan(args[1])
        _emit(report)
        return code
    print(
        "usage: update-push.py --check | --apply-plan <plan.json> | --version",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
