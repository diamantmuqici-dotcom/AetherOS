#!/usr/bin/env python3
"""Aether Browser Customize — wallpaper, search bar position, ad block, VPN (inside the browser)."""
import gi, json, subprocess, pathlib, shutil
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from browser_settings import load, save, apply_wallpaper, toggle_vpn, set_search_bar, set_ad_block

WALL_DIR = pathlib.Path("/usr/share/backgrounds/aether")

class Customize(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.aether.BrowserCustomize")
    def do_activate(self):
        cfg = load()
        win = Adw.ApplicationWindow(application=self, title="Aether Browser — Customize")
        win.set_default_size(720, 520)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(24); box.set_margin_end(24)
        box.append(Adw.HeaderBar(title="Aether Browser"))
        
        # Search bar position
        box.append(Gtk.Label(label="Search Bar Position"))
        pos_box = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        for pos in ["top", "bottom", "left", "right"]:
            b = Gtk.ToggleButton(label=pos.capitalize())
            b.set_active(cfg["search_position"] == pos)
            b.connect("toggled", lambda btn, p=pos: set_search_bar(p))
            pos_box.append(b)
        box.append(pos_box)
        
        # Wallpaper
        box.append(Gtk.Label(label="Browser Wallpaper (choose one of our wallpapers)"))
        if WALL_DIR.exists():
            flow = Gtk.FlowBox(); flow.set_column_spacing(8); flow.set_row_spacing(8)
            for f in sorted(WALL_DIR.glob("*.jpg")):
                b = Gtk.ToggleButton(label=f.stem)
                b.set_active(cfg["wallpaper"] == f.name)
                b.connect("toggled", lambda btn, p=str(f): apply_wallpaper_and_save(p))
                flow.append(b)
            box.append(flow)
        
        # Ad block + VPN toggles
        ab = Gtk.CheckButton(label="Ad Blocker (uBlock + Privacy Badger)")
        ab.set_active(cfg["ad_block"]); ab.connect("toggled", lambda c: set_ad_block(c.get_active()))
        vpn = Gtk.CheckButton(label="VPN (Proton, inline toggle)")
        vpn.set_active(cfg["vpn_enabled"]); vpn.connect("toggled", lambda c: toggle_vpn(c.get_active()))
        box.append(ab); box.append(vpn)
        
        win.set_content(box)
        win.present()

def apply_wallpaper_and_save(path):
    apply_wallpaper(path)
    cfg = load(); cfg["wallpaper"] = pathlib.Path(path).name; save(cfg)

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
if __name__ == "__main__":
    sys.exit(Customize().run(sys.argv))
