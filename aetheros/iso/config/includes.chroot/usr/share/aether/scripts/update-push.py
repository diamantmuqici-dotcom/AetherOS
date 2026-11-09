#!/usr/bin/env python3
"""Aether Update Push — check GitHub for a newer AetherOS release.

Compares the latest non-prerelease release tag against the installed
version in /usr/share/aether/VERSION. If newer and not snoozed/declined,
opens the Aether Updater dialog (Accept / Don't Accept / Later).
Runs at desktop login via /etc/xdg/autostart/aether-update-check.desktop.
"""
import json
import pathlib
import re
import subprocess
import time
import urllib.request

API = "https://api.github.com/repos/diamantmuqici-dotcom/AetherOS/releases/latest"
VERSION_FILE = pathlib.Path("/usr/share/aether/VERSION")
STATE_DIR = pathlib.Path.home() / ".config" / "aether"
LATER = STATE_DIR / "update-later"
DECLINED = STATE_DIR / "update-declined"

SNOOZE_SECONDS = 24 * 60 * 60
DECLINE_SECONDS = 7 * 24 * 60 * 60


def version_tuple(s: str):
    """Extract (numbers, suffix) for comparison, e.g. 'os-v1.2.3' -> ((1,2,3), '')"""
    s = s.strip()
    s = re.sub(r"^(os-)?v", "", s)
    nums = tuple(int(x) for x in re.findall(r"\d+", s))
    suffix = re.sub(r"^[\d.]+" , "", s).lstrip("-_")
    return nums, suffix


def is_newer(latest: str, current: str) -> bool:
    ln, ls = version_tuple(latest)
    cn, cs = version_tuple(current)
    if ln != cn:
        return ln > cn
    # Same numbers: a suffix like '-proof' means a prerelease build;
    # an empty suffix (plain release) counts as newer than any suffix.
    return ls != cs and (cs != "" and ls == "")


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Snoozed by "Later" until midnight?
    if LATER.exists():
        try:
            if float(LATER.read_text().strip()) > time.time():
                return 0
            LATER.unlink()
        except ValueError:
            LATER.unlink()
        except OSError:
            pass

    # Declined recently? Don't nag for a week.
    if DECLINED.exists():
        try:
            if time.time() - float(DECLINED.read_text().strip()) < DECLINE_SECONDS:
                return 0
        except ValueError:
            pass
        except OSError:
            pass

    try:
        with urllib.request.urlopen(API, timeout=10) as resp:
            data = json.load(resp)
        latest = data.get("tag_name", "").strip()
    except Exception:
        return 0

    if not latest:
        return 0

    try:
        current = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else ""
    except OSError:
        current = ""

    if current and not is_newer(latest, current):
        return 0

    subprocess.run(["aether-updater", "--latest", latest], timeout=60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
