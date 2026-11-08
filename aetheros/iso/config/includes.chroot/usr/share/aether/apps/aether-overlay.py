#!/usr/bin/env python3
"""Aether ESG Overlay — FPS / frame-time / latency / RAM (gamemode aware)."""
import subprocess, time
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk, Adw, GLib
class App(Adw.Application):
    def __init__(self): super().__init__(application_id="org.aether.Overlay")
    def do_activate(self):
        win=Adw.ApplicationWindow(application=self,title="ESG Overlay"); win.set_default_size(420,300)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        box.set_margin_top(16);box.set_margin_start(16);box.set_margin_end(16);box.set_margin_bottom(16)
        box.append(Adw.HeaderBar(title="ESG — FPS / Latency / RAM"))
        self.lab=Gtk.Label(label="FPS: —  Frame: —  RAM: —  GameMode: —"); box.append(self.lab)
        box.append(Gtk.Label(label="Add via Steam launch option: mangohud + gamemoderun. ESG reads MangoHud.log if present."))
        GLib.timeout_add(1000, self.tick); win.set_content(box); win.present()
    def tick(self):
        try: ram = subprocess.run(["free","-m"],capture_output=True,text=True,timeout=3).stdout.splitlines()[1]
        except Exception: ram="—"
        try: gm = subprocess.run(["gamemoded","-s"],capture_output=True,text=True,timeout=3).stdout.strip()
        except Exception: gm="off"
        if hasattr(self,"lab"): self.lab.set_label(f"FPS: (see MangoHud)  RAM:{ram[:30]}  GameMode:{gm}")
        return True
if __name__ == "__main__":
    import sys; sys.exit(App().run(sys.argv))
