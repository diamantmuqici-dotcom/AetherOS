#!/usr/bin/env python3
"""Aether Update Push — checks GitHub Releases for a newer tag, notifies."""
import json, urllib.request, subprocess, pathlib

STATE = pathlib.Path.home() / ".config" / "aether" / "update-push"
try:
    data = json.load(urllib.request.urlopen("https://api.github.com/repos/diamantmuqici-dotcom/AetherOS/releases/latest", timeout=10))
    latest = data.get("tag_name", "")
    if latest and latest != "v0.0.0":
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(latest)
        subprocess.run(["notify-send", "Aether Update", f"New release {latest} — open Aether Updater to install."], timeout=5)
    print("checked", latest)
except Exception as e:
    print("update check failed (offline ok):", e)
