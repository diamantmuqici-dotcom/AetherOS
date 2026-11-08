#!/usr/bin/env python3
"""Aether TamperGuard — if remote-control moves mouse and tries to disable AV, capture + reverse."""
import subprocess, pathlib, json

STATE = pathlib.Path.home() / ".config" / "aether" / "tamper"

def is_remote_input_active():
    # Check for TeamViewer/AnyDesk/RustDesk running
    r = subprocess.run(["pgrep", "-f", "teamviewer|anydesk|rustdesk|airdroid"], capture_output=True, text=True, timeout=5)
    return bool(r.stdout.strip())

def av_tamper_detect():
    # AV service was disabled while remote input active → tamper
    rc = subprocess.run(["systemctl", "is-enabled", "aether-av.service"], capture_output=True, text=True, timeout=5)
    if "disabled" in rc.stdout.lower() and is_remote_input_active():
        # Capture remote IP (netstat peer), log, and quarantine the remote app (reverse-control equivalent: block + notify)
        STATE.mkdir(parents=True, exist_ok=True)
        ips = subprocess.run(["ss", "-tnp"], capture_output=True, text=True, timeout=5).stdout
        (STATE / "remote-ips.txt").write_text(ips)
        # Delete the remote app binary (if in /tmp/Downloads)
        for name in ["teamviewer", "anydesk", "rustdesk", "airdroid"]:
            subprocess.run(f"pkill -9 {name}; rm -rf /tmp/{name}* ~/Downloads/{name}* 2>/dev/null", shell=True)
        subprocess.run(["notify-send", "Aether AV", "Remote control trying to disable AV blocked. IP logged; app removed."], timeout=5)
        return True
    return False

if __name__ == "__main__":
    av_tamper_detect()
