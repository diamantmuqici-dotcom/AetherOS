#!/usr/bin/env python3
"""Aether Optimize All — one-click safe optimizations (ram/gpu/cpu/input)."""
import subprocess, pathlib

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return (r.stdout + r.stderr).strip()[-2000:]
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    print(run("bash /usr/share/aether/scripts/optimize-all.sh"))
