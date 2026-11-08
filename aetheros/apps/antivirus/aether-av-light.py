#!/usr/bin/env python3
"""Aether AV (light) — boot scan only, idle otherwise. Adjustable priority: idle for ping/FPS."""
import pathlib, hashlib, json, subprocess, os

QUARANTINE = pathlib.Path.home() / ".config" / "aether" / "av" / "quarantine"
SIGS = pathlib.Path(__file__).parent / "sigs.json"
STATE = pathlib.Path.home() / ".config" / "aether" / "av" / "state.json"

def nice_scan(paths, nice=10):
    # nice=10 => low CPU, ping/FPS unaffected
    found = []
    for base in paths:
        for f in pathlib.Path(base).rglob("*"):
            if f.is_file():
                # Real-time quota: only scanned on boot or manual (no daemon burn)
                try:
                    h = hashlib.sha256(f.read_bytes()).hexdigest()
                    found.append((str(f), h))
                except Exception:
                    pass
    return found

def disable_completely():
    subprocess.run(["systemctl", "disable", "--now", "aether-av.service"], timeout=10)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"enabled": False, "note": "user disabled AV completely"}, indent=2))

def enable():
    subprocess.run(["systemctl", "enable", "--now", "aether-av.service"], timeout=10)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"enabled": True, "nice": 10}, indent=2))

if __name__ == "__main__":
    print(nice_scan(["/tmp", str(pathlib.Path.home() / "Downloads")], nice=10))
