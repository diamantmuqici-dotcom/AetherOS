#!/usr/bin/env python3
"""Aether Quick Look — Space peek (image/text/PDF via eog/evince)."""
import sys, pathlib
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk, Adw
class App(Adw.Application):
    def __init__(self): super().__init__(application_id="org.aether.QuickLook")
    def do_activate(self):
        f = sys.argv[1] if len(sys.argv)>1 else ""
        win = Adw.ApplicationWindow(application=self, title=f"Quick Look — {pathlib.Path(f).name}")
        win.set_default_size(800,600)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20);box.set_margin_bottom(20);box.set_margin_start(24);box.set_margin_end(24)
        box.append(Adw.HeaderBar(title="Quick Look"))
        if f and pathlib.Path(f).suffix.lower() in (".jpg",".jpeg",".png",".webp"):
            box.append(Gtk.Image.new_from_file(f))
        elif f and pathlib.Path(f).suffix.lower() in (".txt",".md",".sh",".py"):
            lab = Gtk.Label(label=pathlib.Path(f).read_text(errors="ignore")[:20000], selectable=True)
            lab.set_wrap(True); box.append(lab)
        else:
            box.append(Gtk.Label(label="Press Space in Nautilus for peek. Open files here for preview."))
        win.set_content(box); win.present()
if __name__ == "__main__": sys.exit(App().run(sys.argv))
