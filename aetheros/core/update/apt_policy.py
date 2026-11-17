"""APT state inspection and signed-manifest-driven policy (argv-only, fail closed).

Existing inspection helpers are unchanged. The policy layer below converts an
already-verified release manifest into an allow-list of exact version pins; any
package or version not pinned is denied. No shell is ever used.
"""

from __future__ import annotations

import re
import subprocess

from .release import ReleaseError, load_release, select_channel

__all__ = [
    "parse_apt_policy",
    "parse_simulated_upgrade",
    "run_apt_policy",
    "run_simulated_upgrade",
    "PolicyError",
    "POLICY",
    "build_policy_from_manifest",
    "evaluate_package_policy",
    "intersect_upgrades_with_policy",
    "validate_plan",
    "build_apt_argv",
]

_TIMEOUT_MAX = 30
_INST_RE = re.compile(
    r"^Inst\s+(?P<pkg>\S+)\s+\[(?P<current>[^\]]+)\]\s+\((?P<rest>[^)]*)\)"
)


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
    # check=False keeps stderr/stdout available for fail-closed parsing.
    return subprocess.run(
        argv, check=False, timeout=max(1, min(int(timeout), _TIMEOUT_MAX)),
        text=True, capture_output=True,
    )


def parse_simulated_upgrade(text: str) -> tuple[list[dict], str]:
    """Parse `apt-get -s upgrade` output into (upgrades, status)."""
    if not isinstance(text, str) or not text.strip():
        return [], "unrecognized-output"
    upgrades: list[dict] = []
    recognized = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Inst "):
            recognized = True
            match = _INST_RE.match(line)
            if match is None:
                continue  # unknown Inst shape: omit that package entirely
            fields = match.group("rest").split()
            if len(fields) < 2:
                continue
            upgrades.append({
                "package": match.group("pkg"),
                "current": match.group("current"),
                "candidate": fields[0],
                "origin": fields[1],
            })
        elif (line.startswith(("Conf ", "Remv ", "The following"))
              or "upgraded," in line):
            recognized = True
    if not recognized:
        return [], "unrecognized-output"
    return upgrades, ("ok" if upgrades else "no-upgrades")


def parse_apt_policy(text: str) -> dict:
    """Parse `apt-cache policy <pkg>` output into a small state record."""
    if not isinstance(text, str) or not text.strip():
        return {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    package = lines[0].rstrip(":") if lines else ""
    installed = candidate = None
    for line in lines:
        if line.startswith("Installed:"):
            installed = line.split(":", 1)[1].strip()
        elif line.startswith("Candidate:"):
            candidate = line.split(":", 1)[1].strip()
    if not candidate or candidate == "(none)":
        return {}
    return {"package": package, "installed": installed or "", "candidate": candidate}


def run_simulated_upgrade(timeout: int = _TIMEOUT_MAX) -> tuple[list[dict], str]:
    """Return (upgrades, status) from a simulated APT upgrade, fail closed on errors."""
    try:
        result = _run(["apt-get", "-s", "upgrade"], timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"apt-simulation-error:{type(exc).__name__}"
    if result.returncode != 0:
        return [], f"apt-simulation-failed:rc={result.returncode}"
    return parse_simulated_upgrade(result.stdout)


def run_apt_policy(package: str, timeout: int = _TIMEOUT_MAX) -> tuple[dict, str]:
    """Return (policy, status) for one package, fail closed on errors."""
    if not isinstance(package, str) or not package:
        return {}, "invalid-package"
    try:
        result = _run(["apt-cache", "policy", package], timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {}, f"apt-policy-error:{type(exc).__name__}"
    if result.returncode != 0:
        return {}, f"apt-policy-failed:rc={result.returncode}"
    policy = parse_apt_policy(result.stdout)
    return (policy, "ok") if policy else ({}, "unrecognized-output")


# --- authenticated APT policy -------------------------------------------------

class PolicyError(ValueError):
    """Raised when a manifest cannot yield a usable policy (fail closed)."""


class POLICY:
    """Decision states and the only APT actions a signed policy may emit."""

    ALLOWED = "allowed"
    DISALLOWED = "disallowed"
    PINNED = "pinned"
    ACTIONS = ("install", "upgrade", "hold")
    SOURCE = "signed-manifest"


def build_policy_from_manifest(manifest: dict, channel: str = "stable") -> dict:
    """Build a fail-closed policy from an already-verified manifest payload.

    Verification happens upstream in signature.verify_release; this function only
    validates structure and converts the signed pins into the allow-list.
    """
    if not isinstance(manifest, dict):
        raise PolicyError("manifest must be a dict")
    if not isinstance(channel, str) or not channel:
        raise PolicyError("invalid channel")
    try:
        view = select_channel(load_release(manifest), channel)
    except ReleaseError as exc:
        raise PolicyError(f"invalid manifest: {exc}") from exc
    pins = view["packages"]
    if not isinstance(pins, dict):
        raise PolicyError("package pins must be an object")
    for name, version in pins.items():
        if not isinstance(name, str) or not name:
            raise PolicyError("invalid package name in pins")
        if not isinstance(version, str) or not version:
            raise PolicyError(f"invalid pin for {name}")
    return {
        "source": POLICY.SOURCE,
        "signature": "VALID",
        "channel": channel,
        "expires": view["expires"],
        "min_os_version": view["min_os_version"],
        "pinned": dict(pins),
        "allowed": sorted(pins),
        "action": POLICY.PINNED,
    }


def evaluate_package_policy(
    policy: dict,
    package: str,
    candidate: str | None = None,
    action: str = "upgrade",
) -> dict:
    """Decide whether one package action is permitted by the signed policy."""
    record = {
        "package": package if isinstance(package, str) else "",
        "candidate": candidate if isinstance(candidate, str) else None,
        "action": action if isinstance(action, str) else "",
        "decision": POLICY.DISALLOWED,
        "state": POLICY.DISALLOWED,
        "pinned_version": None,
        "reason": "",
    }
    pins = policy.get("pinned") if isinstance(policy, dict) else None
    if not isinstance(pins, dict):
        record["reason"] = "no-policy"
        return record
    if not isinstance(package, str) or not package:
        record["reason"] = "invalid-package"
        return record
    if package not in pins:
        record["reason"] = "not-pinned"
        return record
    if not isinstance(action, str) or action not in POLICY.ACTIONS:
        record["reason"] = "invalid-action"
        return record
    pinned = pins[package]
    if candidate is not None and candidate != pinned:
        record["reason"] = "version-mismatch"
        record["pinned_version"] = pinned
        return record
    record["decision"] = POLICY.ALLOWED
    record["state"] = POLICY.PINNED
    record["pinned_version"] = pinned
    record["version"] = pinned
    record["reason"] = "pinned"
    return record


def intersect_upgrades_with_policy(
    policy: dict,
    upgrades: list[dict],
    action: str = "upgrade",
) -> list[dict]:
    """Return only the observed upgrades the signed policy allows; no fabrication."""
    if not isinstance(upgrades, list):
        return []
    result: list[dict] = []
    for entry in upgrades:
        if not isinstance(entry, dict):
            continue
        decision = evaluate_package_policy(
            policy, entry.get("package"), entry.get("candidate"), action,
        )
        if decision["decision"] != POLICY.ALLOWED:
            continue
        decision["current"] = entry.get("current", "")
        decision["origin"] = entry.get("origin", "")
        result.append(decision)
    return result


def validate_plan(policy: dict, entries: list[dict]) -> tuple[list[dict], str]:
    """Validate every entry against signed pins; fail closed on any violation."""
    if not isinstance(entries, list):
        return [], "invalid-plan"
    normalized: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return [], "invalid-entry"
        package = entry.get("package")
        version = entry.get("version", entry.get("candidate"))
        action = entry.get("action", "upgrade")
        decision = evaluate_package_policy(policy, package, version, action)
        if decision["decision"] != POLICY.ALLOWED:
            return [], f"denied:{decision['reason']}"
        normalized.append({
            "package": package,
            "version": decision["pinned_version"],
            "action": action,
        })
    return normalized, "ok"


def build_apt_argv(entries: list[dict], action: str = "install") -> list[list[str]]:
    """Return a list of argv lists (never shell strings) for the allowed entries."""
    if not isinstance(entries, list):
        return []
    plans: list[list[str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        package = entry.get("package")
        version = entry.get("version", entry.get("candidate"))
        act = entry.get("action", action)
        if not isinstance(package, str) or not package:
            continue
        if act not in POLICY.ACTIONS:
            continue
        if act == "hold":
            plans.append(["apt-mark", "hold", package])
            continue
        if not isinstance(version, str) or not version:
            continue
        pin = f"{package}={version}"
        if act == "upgrade":
            plans.append(["apt-get", "install", "--only-upgrade", "-y", pin])
        else:
            plans.append([
                "apt-get", "install", "-y", "--no-install-recommends", pin,
            ])
    return plans
