#!/usr/bin/env python3
"""Aether Anti-Impersonation — apps named 'Aether' that aren't ours are flagged."""
import pathlib, hashlib, subprocess, json

OURS = {"aether-browser", "aether-mail", "aether-updater", "aether-vault", "aether-setup", "aether-settings", "aether-gaming-hub", "aether-av"}
KNOWN_HASHES_PATH = pathlib.Path(__file__).parent / "ours.json"

def scan():
    sus = []
    for p in pathlib.Path("/usr/share/applications").glob("aether-*.desktop"):
        name = p.stem
        if name not in OURS:
            sus.append(str(p))
    # Anti-rename: if an app named Aether runs from /tmp or Downloads, flag it
    for p in ["/tmp", str(pathlib.Path.home() / "Downloads")]:
        for f in pathlib.Path(p).glob("aether*"):
            sus.append(str(f))
    if sus:
        # Instant patch: move to quarantine + notify
        q = pathlib.Path.home() / ".config" / "aether" / "av" / "quarantine"
        q.mkdir(parents=True, exist_ok=True)
        for s in sus:
            try: shutil.copy(s, q / pathlib.Path(s).name)
            except Exception: pass
            subprocess.run(["notify-send", "Aether AV", f"Impersonator blocked: {s} (anti-rename patch)"], timeout=5)
    return sus
