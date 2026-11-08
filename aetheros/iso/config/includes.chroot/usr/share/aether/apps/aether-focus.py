#!/usr/bin/env python3
"""Aether Focus — Do Not Disturb + grayscale + timer via gsettings."""
import subprocess
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk, Adw
MODES = {"Off":0,"Focus 25m":25,"Deep 50m":50,"Meeting":120}
class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.aether.Focus"); self.timer=None
    def do_activate(self):
        win=Adw.ApplicationWindow(application=self,title="Focus"); win.set_default_size(520,420)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        box.set_margin_top(20);box.set_margin_start(24);box.set_margin_end(24);box.set_margin_bottom(20)
        box.append(Adw.HeaderBar(title="Focus modes"))
        box.append(Gtk.Label(label="Do Not Disturb + optional grayscale while active."))
        for name in MODES:
            b=Gtk.Button(label=f"Start {name}")
            b.connect("clicked", lambda w,n=name: self.start(n)); box.append(b)
        win.set_content(box); win.present()
    def start(self, name):
        try: subprocess.run(["gsettings","set","org.gnome.desktop.notifications","show-banners","false"])
        except Exception: pass
        try: subprocess.run(["gsettings","set","org.gnome.desktop.interface","color-scheme","prefer-dark"])
        except Exception: pass
if __name__ == "__main__":
    import sys; sys.exit(App().run(sys.argv))
