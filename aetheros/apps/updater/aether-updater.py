#!/usr/bin/env python3
"""Aether Updater — one-click safe system updates (GTK4)."""
import gi, subprocess, sys
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

class Updater(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.aether.Updater")
    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title="Aether Updater")
        win.set_default_size(640, 420)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(24); box.set_margin_end(24)
        box.append(Adw.HeaderBar(title="Aether Updater"))
        box.append(Gtk.Label(label="Updates your PC automatically (safe upgrades only).\nNo destructive distro switches. Reboot if the kernel changes."))
        log = Gtk.TextView()
        log.set_editable(False)
        log.set_wrap_mode(True)
        box.append(log)
        btn = Gtk.Button(label="Check & Install Updates")
        btn.add_css_class("suggested")
        def run(_):
            btn.set_sensitive(False)
            buf = log.get_buffer()
            buf.insert_at_cursor("Checking…\n")
            def do():
                r = subprocess.run(["bash", "/usr/share/aether/scripts/auto-update.sh"],
                                   capture_output=True, text=True, timeout=1800)
                GLib.idle_add(lambda: (buf.insert_at_cursor(r.stdout[-4000:] + r.stderr[-2000:] + f"\nDone (rc={r.returncode})\n"), btn.set_sensitive(True), False)[-1])
            GLib.thread_pool_push(lambda: None, do)
        btn.connect("clicked", run)
        box.append(btn)
        win.set_content(box)
        win.present()

if __name__ == "__main__":
    sys.exit(Updater().run(sys.argv))
