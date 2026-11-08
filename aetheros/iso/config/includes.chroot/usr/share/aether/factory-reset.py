#!/usr/bin/env python3
"""Aether Factory Reset — destructive. Double-confirm required."""
import gi, subprocess, sys
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

class Reset(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.aether.FactoryReset")
    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title="Aether Factory Reset")
        win.set_default_size(620, 380)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(24); box.set_margin_end(24)
        box.append(Adw.HeaderBar(title="Factory Reset"))
        box.append(Gtk.Label(label="This erases personal files and user settings.\nType RESET to confirm. You cannot undo this.", wrap=True))
        entry = Gtk.Entry(placeholder_text="RESET")
        box.append(entry)
        btn = Gtk.Button(label="Erase Everything")
        btn.add_css_class("destructive-action")
        def do(_):
            if entry.get_text().strip() != "RESET":
                return
            subprocess.run(["systemd-tmpfiles", "--create"], timeout=10)
            # Safe reset: fresh user profile dirs (never wipe /)
            for d in ["Desktop", "Documents", "Downloads"]:
                subprocess.run(f"rm -rf ~/{d}/* 2>/dev/null; mkdir -p ~/{d}", shell=True)
            # Factory reset marker for next login = first-boot setup again
            subprocess.run("touch ~/.config/aether/firstboot && rm -f ~/.config/aether/firstboot.done", shell=True)
            box.append(Gtk.Label(label="Reset prepared. Reboot to run Setup again."))
        btn.connect("clicked", do)
        box.append(btn)
        win.set_content(box)
        win.present()

if __name__ == "__main__":
    sys.exit(Reset().run(sys.argv))
