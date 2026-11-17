#!/usr/bin/env python3
"""Aether Browser — launcher over the preinstalled engine, governed by managed policy."""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

POLICY_PATH = pathlib.Path("/etc/chromium/policies/managed/aether.json")
EXTENSION_PATH = pathlib.Path("/usr/share/aether/browser/extensions/aether-filter")
PROFILE_ROOT = pathlib.Path.home() / ".config" / "aether" / "browser"
DEFAULT_PROFILE = "default"
PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_PASSTHROUGH = 64
MAX_ARG_LEN = 4096
MAX_POLICY_BYTES = 1024 * 1024

# Feature names here are valid Chromium base::Feature names and are not covered
# by the managed policy file, so argv never restates a policy key.
CHROMIUM_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-component-update",
    "--disable-background-networking",
    "--disable-features=Translate,MediaRouter,OptimizationHints",
    "--force-dark-mode",
]

FIREFOX_FLAGS = [
    "-no-remote",
]

CHROMIUM_ENGINES = (
    "chromium",
    "chromium-browser",
    "google-chrome-stable",
    "google-chrome",
)
FIREFOX_ENGINES = ("firefox-esr", "firefox")


def find_engine() -> tuple[str, str] | None:
    for name in CHROMIUM_ENGINES:
        path = shutil.which(name)
        if path:
            return path, "chromium"
    for name in FIREFOX_ENGINES:
        path = shutil.which(name)
        if path:
            return path, "firefox"
    return None


def profile_dir(name: str) -> pathlib.Path:
    if not PROFILE_RE.fullmatch(name) or name in (".", ".."):
        raise ValueError(f"invalid profile name: {name!r}")
    return PROFILE_ROOT / name


def parse_cli(argv: list[str]) -> tuple[str, bool, list[str]]:
    profile = DEFAULT_PROFILE
    diagnose = False
    passthrough: list[str] = []
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == "--profile":
            index += 1
            if index >= len(argv):
                raise ValueError("--profile requires a name")
            profile = argv[index]
        elif arg.startswith("--profile="):
            profile = arg.split("=", 1)[1]
        elif arg == "--diagnose":
            diagnose = True
        else:
            passthrough.append(arg)
        index += 1
    profile_dir(profile)
    if len(passthrough) > MAX_PASSTHROUGH:
        raise ValueError(f"too many engine arguments (limit {MAX_PASSTHROUGH})")
    for arg in passthrough:
        if len(arg) > MAX_ARG_LEN or "\x00" in arg:
            raise ValueError("engine argument exceeds length limit or contains NUL")
    return profile, diagnose, passthrough


def policy_is_valid() -> bool:
    try:
        if not POLICY_PATH.is_file() or POLICY_PATH.stat().st_size > MAX_POLICY_BYTES:
            return False
        json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    return True


def emit_diagnose(profile: str) -> int:
    engine = find_engine()
    profiles: list[dict[str, object]] = []
    try:
        existing = sorted(p for p in PROFILE_ROOT.iterdir() if p.is_dir())
    except OSError:
        existing = []
    for path in existing:
        profiles.append({"name": path.name, "path": str(path), "present": True})
    if not any(item["name"] == profile for item in profiles):
        profiles.append(
            {"name": profile, "path": str(profile_dir(profile)), "present": False}
        )
    report = {
        "engine": engine[0] if engine else None,
        "engine_kind": engine[1] if engine else None,
        "extension_manifest_present": (EXTENSION_PATH / "manifest.json").is_file(),
        "extension_path": str(EXTENSION_PATH),
        "policy_file": str(POLICY_PATH),
        "policy_present": POLICY_PATH.is_file(),
        "policy_valid_json": policy_is_valid(),
        "profile_root": str(PROFILE_ROOT),
        "profiles": profiles,
    }
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


def main(argv: list[str]) -> int:
    try:
        profile, diagnose, extra = parse_cli(argv)
    except ValueError as exc:
        print(f"aether-browser: {exc}", file=sys.stderr)
        return 2

    if diagnose:
        return emit_diagnose(profile)

    engine = find_engine()
    if engine is None:
        print(
            "Aether Browser engine is not installed. Run 'aether-fix' to repair it.",
            file=sys.stderr,
        )
        return 1

    executable, kind = engine
    target = profile_dir(profile)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Aether Browser cannot create profile: {exc}", file=sys.stderr)
        return 1

    if kind == "chromium":
        flags = list(CHROMIUM_FLAGS)
        flags.append(f"--user-data-dir={target}")
        if (EXTENSION_PATH / "manifest.json").is_file():
            flags.append(f"--load-extension={EXTENSION_PATH}")
    else:
        flags = list(FIREFOX_FLAGS)
        flags.extend(["-profile", str(target)])

    cmd = [executable, *flags, *extra]
    try:
        return subprocess.call(cmd)
    except OSError as exc:
        print(f"Aether Browser failed to start: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
