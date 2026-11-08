#!/usr/bin/env python3
"""Aether Update Push — 3 choices: Accept / Decline / Later (12AM or shutdown)."""
import json, urllib.request, subprocess, pathlib, time

STATE_DIR = pathlib.Path.home() / ".config" / "aether"
STATE = STATE_DIR / "update-push"
LATER = STATE_DIR / "update-later"

def check():
    try:
        data = json.load(urllib.request.urlopen("https://api.github.com/repos/diamantmuqici-dotcom/AetherOS/releases/latest", timeout=10))
        latest = data.get("tag_name", "")
    except Exception:
        return
    if not latest: return
    # If snoozed until midnight, skip until midnight
    if LATER.exists():
        try:
            when = float(LATER.read_text().strip())
            if when > time.time():
                print(f"snoozed until {when}")
                return
            else:
                LATER.unlink()
        except Exception:
            pass
    # Notify with countdown? Use Gtk dialog via aether-updater (has 3 buttons)
    subprocess.run(["aether-updater", "--latest", latest], timeout=10)

if __name__ == "__main__":
    check()
