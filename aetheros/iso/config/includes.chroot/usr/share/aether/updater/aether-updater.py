#!/usr/bin/env python3
"""Aether Updater — 3 buttons: Accept / Don't Accept / Later (midnight/shutdown)."""
import gi, subprocess, sys, pathlib, time
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

STATE_DIR = pathlib.Path.home() / ".config" / "aether"
LATER = STATE_DIR / "update-later"
DECLINED = STATE_DIR / "update-declined"

class Updater(Adw.Application):
    def __init__(self, latest="latest"):
        super().__init__(application_id="org.aether.Updater")
        self.latest = latest
    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title="Aether Update Available")
        win.set_default_size(640, 420)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(24); box.set_margin_end(24)
        box.append(Adw.HeaderBar(title="Aether Update"))
        box.append(Gtk.Label(label=f"Aether {self.latest} is available.\nBluescreen-style fix included (if any) — safe upgrades only.\nDownload is optional.", wrap=True))
        row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        accept = Gtk.Button(label="Accept Update")
        accept.add_css_class("suggested")
        decline = Gtk.Button(label="Don't Accept Update")
        later = Gtk.Button(label="Later (12:00 AM / next restart)")
        def do_accept(_):
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            (STATE_DIR / "update-accepted").write_text(str(time.time()))
            log = Gtk.TextView(); log.set_editable(False); log.set_wrap_mode(True)
            box.append(log)
            buf = log.get_buffer(); buf.insert_at_cursor("Installing…\n")
            def run():
                r = subprocess.run(["bash", "/usr/share/aether/scripts/auto-update.sh"], capture_output=True, text=True, timeout=1800)
                GLib.idle_add(lambda: buf.insert_at_cursor(r.stdout[-4000:]+r.stderr[-2000:]+f"\nDone rc={r.returncode}\nReboot suggested when finished.\n") or False)
            GLib.thread_pool_push(None, run)
        def do_decline(_):
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            DECLINED.write_text(str(time.time()))
            win.close()
        def do_later(_):
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            # midnight next day
            now = time.localtime()
            midnight = time.mktime((now.tm_year, now.tm_mon, now.tm_mday+1, 0, 0, 0, 0, 0, -1))
            LATER.write_text(str(midnight))
            # Also schedule on shutdown via systemd? store flag read by firstboot? simple: notify at midnight
            win.close()
            subprocess.run(["notify-send", "Aether Updater", "Will ask again at 12:00 AM / next restart"], timeout=5)
        accept.connect("clicked", do_accept)
        decline.connect("clicked", do_decline)
        later.connect("clicked", do_later)
        row.append(accept); row.append(decline); row.append(later)
        box.append(row)
        win.set_content(box)
        win.present()

def parse_arg():
    if "--latest" in sys.argv:
        i = sys.argv.index("--latest")
        if i+1 < len(sys.argv): return sys.argv[i+1]
    return "latest"

if __name__ == "__main__":
    sys.exit(Updater(parse_arg()).run(sys.argv))
