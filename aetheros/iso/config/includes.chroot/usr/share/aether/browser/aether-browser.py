#!/usr/bin/env python3
"""Aether Browser — privacy-first launcher over the preinstalled browser engine."""
from __future__ import annotations

import shutil
import subprocess
import sys

CHROMIUM_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-component-update",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-translate",
    "--disable-hang-monitor",
    "--force-dark-mode",
    "--enable-features=EncryptedDns",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--incognito",
]

FIREFOX_FLAGS = [
    "--private-window",
]

CHROMIUM_ENGINES = (
    "chromium",
    "chromium-browser",
    "google-chrome-stable",
    "google-chrome",
)
FIREFOX_ENGINES = ("firefox-esr", "firefox")


def find_engine() -> tuple[str, list[str]] | None:
    for name in CHROMIUM_ENGINES:
        path = shutil.which(name)
        if path:
            return path, list(CHROMIUM_FLAGS)
    for name in FIREFOX_ENGINES:
        path = shutil.which(name)
        if path:
            return path, list(FIREFOX_FLAGS)
    return None


def main(argv: list[str]) -> int:
    engine = find_engine()
    if engine is None:
        print(
            "Aether Browser engine is not installed. Run 'aether-fix' to repair it.",
            file=sys.stderr,
        )
        return 1

    executable, flags = engine
    try:
        return subprocess.call([executable, *flags, *argv[1:]])
    except OSError as exc:
        print(f"Aether Browser failed to start: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
