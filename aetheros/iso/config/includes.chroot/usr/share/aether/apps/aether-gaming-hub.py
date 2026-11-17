#!/usr/bin/env python3
"""Aether Gaming Hub — Steam / Proton-GE / Zen Browser launcher (official URLs)."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio
import sys

class Hub(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.aether.GamingHub")
    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title="Aether Gaming Hub")
        win.set_default_size(760, 520)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(24); box.set_margin_end(24)
        box.append(Adw.HeaderBar(title="Aether Gaming Hub"))
        box.append(Gtk.Label(label="Steam — install from steam-installer deb (Valve). Proton-GE — fetched at runtime (not bundled). Zen Browser — official deb (MPL), launcher integrated."))
        for title, url in [
            ("Install Steam", "https://store.steampowered.com"),
            ("Zen Browser", "https://zen-browser.app"),
            ("Proton-GE releases", "https://github.com/GloriousEggroll/proton-ge-custom"),
        ]:
            btn = Gtk.Button(label=title)
            btn.connect("clicked", lambda b, u=url: Gio.AppInfo.launch_default_for_type("text/html", u))
            box.append(btn)
        win.set_content(box)
        win.present()

if __name__ == "__main__":
    sys.exit(Hub().run(sys.argv))
