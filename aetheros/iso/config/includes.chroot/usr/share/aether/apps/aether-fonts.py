#!/usr/bin/env python3
"""Aether Fonts — list, preview, install to ~/.local/share/fonts."""
import subprocess, pathlib, shutil
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk, Adw
class App(Adw.Application):
    def __init__(self): super().__init__(application_id="org.aether.Fonts")
    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title="Aether Fonts"); win.set_default_size(780,540)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(16);box.set_margin_start(20);box.set_margin_end(20);box.set_margin_bottom(16)
        box.append(Adw.HeaderBar(title="Fonts"))
        try:
            out = subprocess.run(["fc-list",":family"],capture_output=True,text=True,timeout=5).stdout
            fams = sorted(set(x for x in out.splitlines() if x))[:200]
        except Exception: fams=["(fc-list unavailable)"]
        lb = Gtk.ListBox()
        for f in fams:
            lb.append(Gtk.ListItem(child=Gtk.Label(label=f, xalign=0)))
        sc = Gtk.ScrolledWindow(child=lb, hexpand=True, vexpand=True)
        box.append(sc); win.set_content(box); win.present()
if __name__ == "__main__": import sys; sys.exit(App().run(sys.argv))
