#!/usr/bin/env python3
"""Aether System Logs — journalctl viewer (read-only)."""
import subprocess
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk, Adw
class App(Adw.Application):
    def __init__(self): super().__init__(application_id="org.aether.Logs")
    def do_activate(self):
        win=Adw.ApplicationWindow(application=self,title="System Logs"); win.set_default_size(900,600)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        box.set_margin_top(12);box.set_margin_start(16);box.set_margin_end(16);box.set_margin_bottom(12)
        box.append(Adw.HeaderBar(title="System Logs (journalctl)"))
        try: out=subprocess.run(["journalctl","-n","500","--no-pager"],capture_output=True,text=True,timeout=5).stdout
        except Exception: out="journalctl unavailable"
        lab=Gtk.Label(label=out[-20000:], selectable=True); lab.set_wrap(True); lab.set_xalign(0)
        sc=Gtk.ScrolledWindow(child=lab, hexpand=True, vexpand=True)
        box.append(sc); win.set_content(box); win.present()
if __name__ == "__main__":
    import sys; sys.exit(App().run(sys.argv))
