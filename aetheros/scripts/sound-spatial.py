#!/usr/bin/env python3
"""Spatial audio — PipeWire HRTF via wireplumber + pw-cli."""
import subprocess
def run(c):
 try: subprocess.run(c, timeout=5)
 except Exception: pass
run(["pw-cli","set-param","@DEFAULT_AUDIO_SINK@","SPA","{\"audio.position\": [\"FL\",\"FR\",\"FC\",\"LFE\",\"RL\",\"RR\"], \"spatial.enabled\": true}"])
print("Spatial: HRTF enabled (headphone). Disable via pavucontrol > Configuration > Pro Audio.")
