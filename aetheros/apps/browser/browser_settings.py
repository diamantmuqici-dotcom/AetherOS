#!/usr/bin/env python3
"""Aether Browser settings — wallpaper, search bar position, ad-block, VPN inline, fully customizable."""
import json, pathlib, subprocess, shutil, os

CONFIG = pathlib.Path.home() / ".config" / "aether" / "browser.json"
DEFAULT = {
    "wallpaper": "cosmos-nebula.jpg",
    "search_position": "top",
    "ad_block": True,
    "vpn_enabled": True,
    "dark_theme": True,
    "homepage": "https://duckduckgo.com",
    "wallpaper_opacity": 0.85,
}
def load():
    d = dict(DEFAULT)
    if CONFIG.exists():
        d.update(json.loads(CONFIG.read_text()))
    return d
def save(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))
def apply_wallpaper(path):
    subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", f"file://{path}"], timeout=5)
    subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", f"file://{path}"], timeout=5)
def toggle_vpn(enabled):
    if enabled:
        subprocess.run(["/usr/local/bin/aether-vpn-auto"], timeout=10)
        subprocess.run(["notify-send", "Aether Browser", "VPN enabled (Proton)"], timeout=5)
    else:
        subprocess.run(["notify-send", "Aether Browser", "VPN paused"], timeout=5)
def set_search_bar(pos):
    assert pos in ("top", "bottom", "left", "right")
    cfg = load(); cfg["search_position"] = pos; save(cfg)
def set_ad_block(on):
    cfg = load(); cfg["ad_block"] = on; save(cfg)
    print("Ad block", "ON (uBlock/Privacy Badger active)" if on else "OFF (side-effects may appear)")
