"""APT state inspection through bounded, argument-vector subprocesses.

No shell is used. Simulation output is parsed into pinned upgrade records and
anything that does not match the expected apt format is rejected, never guessed.
"""

from __future__ import annotations

import re
import subprocess

__all__ = [
    "parse_apt_policy",
    "parse_simulated_upgrade",
    "run_apt_policy",
    "run_simulated_upgrade",
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
