"""Aether Settings Power panel — real powerprofilesctl / UPower integration."""
import subprocess

def get_profile():
    try:
        return subprocess.check_output(["powerprofilesctl", "get"], text=True, timeout=5).strip()
    except Exception:
        return "balanced"

def set_profile(name):
    try:
        subprocess.run(["powerprofilesctl", "set", name], check=True, timeout=10)
        return True
    except Exception:
        return False

def battery_status():
    try:
        return subprocess.check_output(["upower", "-i", "/org/freedesktop/UPower/devices/DisplayDevice"], text=True, timeout=5)
    except Exception:
        return "No battery (desktop)"
