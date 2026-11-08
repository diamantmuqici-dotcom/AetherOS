#!/usr/bin/env python3
"""Aether Accessibility suite — Orca, magnifier, high-contrast, captions."""
import subprocess
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk, Adw
def gset(s,k,v):
    try: subprocess.run(["gsettings","set",s,k,str(v)])
    except Exception: pass
class App(Adw.Application):
    def __init__(self): super().__init__(application_id="org.aether.Accessibility")
    def do_activate(self):
        win=Adw.ApplicationWindow(application=self,title="Accessibility"); win.set_default_size(640,520)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        box.set_margin_top(16);box.set_margin_start(20);box.set_margin_end(20);box.set_margin_bottom(16)
        box.append(Adw.HeaderBar(title="Accessibility"))
        items=[
          ("Screen reader (Orca)", "org.gnome.desktop.a11y.applications","screen-reader"),
          ("Magnifier", "org.gnome.desktop.a11y.magnifier","magnifier"),
          ("High contrast", "org.gnome.desktop.interface","color-scheme"),
          ("Text scaling 1.25x", "org.gnome.desktop.interface","text-scaling-factor"),
          ("Large cursor", "org.gnome.desktop.interface","cursor-size"),
        ]
        for label,s,k in items:
            b=Gtk.CheckButton(label=label)
            b.connect("toggled", lambda c,ss=s,kk=k: gset(ss,kk, "true" if c.get_active() else "false"))
            box.append(b)
        box.append(Gtk.Label(label="Orca: Super+Alt+S. Magnifier: Super+scroll. Captions via Settings > Accessibility > Captions."))
        win.set_content(box); win.present()
if __name__ == "__main__":
    import sys; sys.exit(App().run(sys.argv))
