#!/usr/bin/env python3
"""Aether Backup — Deja Dup wrapper + rsync snapshots to ~/Backups."""
import subprocess, pathlib
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk, Adw
class App(Adw.Application):
    def __init__(self): super().__init__(application_id="org.aether.Backup")
    def do_activate(self):
        win=Adw.ApplicationWindow(application=self,title="Aether Backup"); win.set_default_size(680,480)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        box.set_margin_top(20);box.set_margin_start(24);box.set_margin_end(24);box.set_margin_bottom(20)
        box.append(Adw.HeaderBar(title="Aether Backup"))
        box.append(Gtk.Label(label="Deja Dup (duplicity) preferred; rsync fallback to ~/Backups/YYYY-MM-DD"))
        b1=Gtk.Button(label="Backup now (rsync)"); b1.connect("clicked", lambda w: self.do()); box.append(b1)
        b2=Gtk.Button(label="Restore list"); b2.connect("clicked", lambda w: self.open("/usr/bin/deja-dup")); box.append(b2)
        win.set_content(box); win.present()
    def do(self):
        dest = pathlib.Path.home()/ "Backups" / __import__("datetime").date.today().isoformat()
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["rsync","-a","--delete",str(pathlib.Path.home())+"/",str(dest)+"/"])
    def open(self, p):
        try: subprocess.Popen([p])
        except Exception: pass
if __name__ == "__main__":
    import sys; sys.exit(App().run(sys.argv))
