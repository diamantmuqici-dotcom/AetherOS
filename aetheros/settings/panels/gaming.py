"""Aether Gaming Hub panel — Steam / Proton-GE / GameMode (real detection)."""
import shutil
import pathlib
import subprocess

def steam_installed():
    return shutil.which("steam") is not None or pathlib.Path.home().joinpath(".steam").exists()

def proton_ge_installed():
    # Proton-GE lives under Steam compatibilitytools.d
    base = pathlib.Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common"
    return any(base.glob("Proton-*-GE*")) if base.exists() else False

def gamemode_active():
    try:
        r = subprocess.run(["busctl", "--user", "get-property", "org.freedesktop.GameMode", "/", "org.freedesktop.GameMode"],
                           capture_output=True, text=True, timeout=5)
        return "active" in r.stdout.lower()
    except Exception:
        return False
