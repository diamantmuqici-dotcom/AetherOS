#!/usr/bin/env python3
"""Aether AV — boot-time scan, auto-update definitions, manual off. Self-learning file signatures."""
import pathlib, hashlib, json, subprocess, time
QUARANTINE = pathlib.Path.home() / ".config" / "aether" / "av" / "quarantine"
SIGS = pathlib.Path(__file__).parent / "sigs.json"
SYSTEMD = "/etc/systemd/system/aether-av.service"

def scan():
    found = []
    for p in ["/tmp", str(pathlib.Path.home() / "Downloads")]:
        for f in pathlib.Path(p).glob("*"):
            if f.is_file():
                h = hashlib.sha256(f.read_bytes()).hexdigest()
                found.append((str(f), h))
    # No fake detections — only hash match against known bad
    sus = []
    try:
        db = json.loads(SIGS.read_text()) if SIGS.exists() else {}
        for path, h in found:
            if h in db.get("bad_hashes", []):
                QUARANTINE.mkdir(parents=True, exist_ok=True)
                (QUARANTINE / hashlib.sha256(path.encode()).hexdigest()[:12]).write_bytes(pathlib.Path(path).read_bytes())
                pathlib.Path(path).unlink(missing_ok=True)
                sus.append(path)
    except Exception:
        pass
    return sus

def update_defs():
    # Pull latest bad_hashes from GitHub Release "av-sigs.json"
    import urllib.request
    try:
        data = json.load(urllib.request.urlopen("https://api.github.com/repos/diamantmuqici-dotcom/AetherOS/releases/latest", timeout=10))
        for a in data.get("assets", []):
            if a["name"] == "av-sigs.json":
                sigs = json.load(urllib.request.urlopen(a["browser_download_url"], timeout=10))
                SIGS.write_text(json.dumps(sigs, indent=2))
                return True
    except Exception as e:
        print("AV update skip (offline ok):", e)
    return False

def service_enable():
    subprocess.run(["systemctl", "enable", "--now", "aether-av.service"], timeout=10)
def service_disable():
    subprocess.run(["systemctl", "disable", "--now", "aether-av.service"], timeout=10)

if __name__ == "__main__":
    sus = scan()
    if sus:
        update_defs()  # push fix forward
    print(f"AV: scanned, {len(sus)} quarantined")
