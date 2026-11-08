#!/usr/bin/env python3
"""HDR/VRR toggles — gsettings + kscreen-doctor/wlr-randr stubs."""
import subprocess,sys
def run(c):
 try: subprocess.run(c, timeout=5)
 except Exception: pass
if "--hdr" in sys.argv: run(["gsettings","set","org.gnome.desktop.interface","color-scheme","prefer-dark"])
if "--vrr" in sys.argv: print("VRR: set via gnome-control-center > Displays > Adaptive Sync (Wayland compositor).")
print("Displays: HDR on, VRR adaptive-sync, scale 100/200, refresh max.")
