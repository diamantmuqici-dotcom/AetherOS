#!/usr/bin/env python3
"""Aether Privacy Banner — shown on browser first launch + first OS boot."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

TEXT = (
    "We do not share your data. No serial numbers. 5 layers of encryption.\n"
    "We are not some lame guys who share your data — and we will never share your data.\n"
    "Even if they offer ridiculous money, we will not. We can't — by design.\n\n"
    "Our apps (Aether Browser, Aether Mail, Aether OS shell) are ours, encrypted, and open.\n"
    "You choose what we do with your data. We do nothing."
)
def show():
    app = Adw.Application(application_id="org.aether.PrivacyBanner")
    def activate(a):
        win = Adw.ApplicationWindow(application=a, title="Aether — No Data Sharing")
        win.set_default_size(640, 360)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(24); box.set_margin_end(24)
        lbl = Gtk.Label(label=TEXT, wrap=True)
        lbl.add_css_class("aether-big")
        box.append(lbl)
        box.append(Gtk.Label(label="You can re-read this in Settings → Privacy & Security."))
        b = Gtk.Button(label="I understand — Continue")
        b.add_css_class("suggested")
        b.connect("clicked", lambda btn: win.close())
        box.append(b)
        win.set_content(box)
        win.present()
    app.connect("activate", activate)
    return app

if __name__ == "__main__":
    show().run([])
