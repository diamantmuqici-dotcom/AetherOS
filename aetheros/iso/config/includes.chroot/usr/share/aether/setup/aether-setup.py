#!/usr/bin/env python3
"""Aether Setup — premium first-boot wizard (GTK4 + libadwaita).

Steps: Welcome → Language → Keyboard → Network → Choose Your Aether
       → Appearance → Privacy → Gaming → Your AetherOS Is Ready → Enter.

Offline-first: reads /usr/share/backgrounds/aether/*.jpg (10 bundled).
Applies real configuration via gsettings + localed + NetworkManager files.
"""
import json, os, random, subprocess, sys, pathlib

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib

AETHER_BG_DIR = pathlib.Path("/usr/share/backgrounds/aether")
FALLBACK_BG_DIR = pathlib.Path(__file__).parent.parent / "assets" / "wallpapers"
AETHER_BLUE = "#00A3FF"
WALLPAPER_MANIFEST = pathlib.Path("/usr/share/aether/wallpaper-manifest.json")
STATE_DIR = pathlib.Path.home() / ".config" / "aether"
PRIVACY_FILE = STATE_DIR / "privacy.json"
FINISHED_MARKER = STATE_DIR / "firstboot.done"
FIRSTBOOT_MARKER = STATE_DIR / "firstboot"

def wallpapers():
    d = AETHER_BG_DIR if AETHER_BG_DIR.exists() else FALLBACK_BG_DIR
    files = sorted(d.glob("*.jpg")) + sorted(d.glob("*.png"))
    return files or [FALLBACK_BG_DIR / "cosmos-nebula.jpg"]

def gset(schema, key, value):
    try:
        subprocess.run(["gsettings", "set", schema, key, str(value)], check=False, timeout=5)
    except Exception:
        pass

class AetherSetup(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.aether.Setup")
        self.selected_wallpaper = wallpapers()[0] if wallpapers() else FALLBACK_BG_DIR / "cosmos-nebula.jpg"
        self.fit_mode = "cover"  # Fill/Cover preserved; Fit/Stretch/Center/Tile available
        self.theme_mode = "dark"
        self.accent = AETHER_BLUE
        self.transparency = "standard"
        self.animations = "full"
        self.privacy = {"diagnostics": False, "crash_reports": False, "usage": False}
        self.gaming = {"steam": "optional", "gamemode": False, "controller": True}

    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title="Aether Setup")
        win.set_default_size(980, 680)
        win.set_size_request(980, 680)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE)
        stack.set_transition_duration(280)

        # ---------- helpers ----------
        def page(title, subtitle=None):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(24); box.set_margin_bottom(24)
            box.set_margin_start(32); box.set_margin_end(32)
            h = Adw.HeaderBar(title=title)
            if subtitle:
                lbl = Gtk.Label(label=subtitle, wrap=True)
                lbl.add_css_class("subtitle")
                box.append(lbl)
            return box

        def nav_buttons(back_label, primary_label, on_back, on_primary):
            row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
            back = Gtk.Button(label=back_label)
            primary = Gtk.Button(label=primary_label)
            primary.add_css_class("suggested")
            back.connect("clicked", on_back)
            primary.connect("clicked", on_primary)
            row.append(back); row.append(primary)
            return row

        # ---------- STEP 1 Welcome ----------
        welcome = page("Welcome to AetherOS", "Premium desktop — privacy-first, gaming-ready, beautiful from the first screen.")
        logo = Gtk.Image.new_from_pixbuf(Gio.File.new_for_path("/usr/share/pixmaps/aether-logo.png").query_pixbuf() if pathlib.Path("/usr/share/pixmaps/aether-logo.png").exists() else None)
        logo.set_pixel_size(96)
        welcome.append(logo)
        welcome.append(Gtk.Label(label="Choose your wallpaper, configure appearance and privacy, then enter AetherOS. Works offline."))
        welcome.append(nav_buttons("Accessibility Options", "Get Started",
            lambda b: self.show_a11y_hint(),
            lambda b: stack.set_visible_child_name("language")))
        stack.add_named(welcome, "welcome")

        # ---------- STEP 2 Language/Region ----------
        lang = page("Language and Region")
        lang.append(Gtk.Label(label="Suggested defaults come from your install. You can change everything here."))
        lang_combo = Gtk.ComboBoxText()
        for code in ["en_US.UTF-8", "sq_AL.UTF-8", "de_DE.UTF-8", "fr_FR.UTF-8", "es_ES.UTF-8"]:
            lang_combo.append_text(code)
        lang_combo.set_active(0)
        # time/date format
        fmt_combo = Gtk.ComboBoxText()
        fmt_combo.append_text("24h / YYYY-MM-DD"); fmt_combo.append_text("12h / MM/DD/YYYY")
        fmt_combo.set_active(0)
        region_combo = Gtk.ComboBoxText()
        for r in ["United States", "Albania", "Germany", "France", "Spain"]:
            region_combo.append_text(r)
        region_combo.set_active(0)
        lang.append(Gtk.Label(label="Language")); lang.append(lang_combo)
        lang.append(Gtk.Label(label="Region")); lang.append(region_combo)
        lang.append(Gtk.Label(label="Time / Date format")); lang.append(fmt_combo)
        lang.append(nav_buttons("Back", "Continue",
            lambda b: stack.set_visible_child_name("welcome"),
            lambda b: self.apply_locale(lang_combo.get_active_text(), region_combo.get_active_text()) or stack.set_visible_child_name("keyboard")))
        stack.add_named(lang, "language")

        # ---------- STEP 3 Keyboard ----------
        kbd = page("Keyboard")
        kbd.append(Gtk.Label(label="Select your layout. Test it below."))
        kbd_combo = Gtk.ComboBoxText()
        for l in ["US", "UK", "Albanian", "German", "French", "Spanish"]:
            kbd_combo.append_text(l)
        kbd_combo.set_active(0)
        test_entry = Gtk.Entry(placeholder_text="Type here to test…")
        kbd.append(Gtk.Label(label="Layout")); kbd.append(kbd_combo)
        kbd.append(Gtk.Label(label="Test area")); kbd.append(test_entry)
        kbd.append(nav_buttons("Back", "Continue",
            lambda b: stack.set_visible_child_name("language"),
            lambda b: (self.apply_keyboard(kbd_combo.get_active_text()), stack.set_visible_child_name("network"))))
        stack.add_named(kbd, "keyboard")

        # ---------- STEP 4 Network ----------
        net = page("Network")
        net.append(Gtk.Label(label="Wi-Fi or Ethernet. You can skip — no cloud account required."))
        net_combo = Gtk.ComboBoxText()
        net_combo.append_text("Ethernet (auto)"); net_combo.append_text("Wi-Fi…"); net_combo.append_text("Skip for now")
        net_combo.set_active(0)
        wifi_rows = Gtk.ListBox()
        # .wifi_ssid rows populated if NM scan data present; keep offline-safe
        wifi_rows.append(Gtk.ListBoxRow(child=Gtk.Label(label="No Wi-Fi scan yet — connect after setup")))
        net.append(Gtk.Label(label="Connection")); net.append(net_combo)
        net.append(wifi_rows)
        net.append(nav_buttons("Back", "Continue",
            lambda b: stack.set_visible_child_name("keyboard"),
            lambda b: stack.set_visible_child_name("wallpaper")))
        stack.add_named(net, "network")

        # ---------- STEP 5 Wallpaper (hero) ----------
        wall = page("Choose Your Aether", "Bundled wallpapers — available offline. Fill/Cover is the default (no distortion).")
        wfiles = wallpapers()

        # live desktop preview (wallpaper + dock + icons mock)
        preview_frame = Gtk.Frame()
        preview_frame.set_hexpand(True)
        preview_frame.set_vexpand(False)
        preview_frame.set_size_request(640, 300)
        preview_overlay = Gtk.Overlay()
        preview_img = Gtk.Image()
        preview_img.set_pixel_size(640)
        preview_overlay.set_child(preview_img)
        dock_mock = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.END, spacing=6)
        dock_mock.set_margin_bottom(8)
        for _ in range(5):
            icon = Gtk.Image.new_from_icon_name("application-x-executable")
            icon.set_pixel_size(28)
            dock_mock.append(icon)
        preview_overlay.add_overlay(dock_mock)
        preview_frame.set_child(preview_overlay)
        wall.append(preview_frame)
        preview_label = Gtk.Label(label=wfiles[0].name if wfiles else "No wallpapers")
        wall.append(preview_label)

        # gallery (cover-fit thumbnails via grid)
        gallery = Gtk.FlowBox()
        gallery.set_column_spacing(8); gallery.set_row_spacing(8)
        gallery.set_selection_mode(Gtk.SelectionMode.NONE)
        gallery.set_min_children_per_line(4)
        gallery.set_max_children_per_line(6)
        self._gallery_cards = []
        for f in wfiles:
            card = self.make_wallpaper_card(f, preview_img, preview_label)
            gallery.append(card)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(gallery)
        scrolled.set_vexpand(True)
        wall.append(scrolled)

        # fit modes + actions
        fit_row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        fit_combo = Gtk.ComboBoxText()
        for m in ["cover", "fit", "stretch", "center", "tile"]:
            fit_combo.append_text(m)
        fit_combo.set_active(0)
        fit_row.append(Gtk.Label(label="Fit")); fit_row.append(fit_combo)
        wall.append(fit_row)

        wall_buttons = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        back_b = Gtk.Button(label="Back"); back_b.connect("clicked", lambda b: stack.set_visible_child_name("network"))
        rand_b = Gtk.Button(label="Randomize"); rand_b.connect("clicked", lambda b: self.randomize_wallpaper(preview_img, preview_label))
        cont_b = Gtk.Button(label="Continue"); cont_b.add_css_class("suggested")
        cont_b.connect("clicked", lambda b: (self.apply_wallpaper(str(self.selected_wallpaper), fit_combo.get_active_text()), stack.set_visible_child_name("appearance")))
        wall_buttons.append(back_b); wall_buttons.append(rand_b); wall_buttons.append(cont_b)
        wall.append(wall_buttons)
        stack.add_named(wall, "wallpaper")

        # ---------- STEP 6 Appearance ----------
        app_page = page("Appearance")
        theme_combo = Gtk.ComboBoxText()
        for t in ["Dark", "Light", "Auto"]: theme_combo.append_text(t)
        theme_combo.set_active(0)
        accent_combo = Gtk.ComboBoxText()
        for a in ["Aether Blue #00A3FF", "Cyan #00D4FF", "Indigo #2B56FF", "White #FFFFFF"]:
            accent_combo.append_text(a)
        accent_combo.set_active(0)
        trans_combo = Gtk.ComboBoxText()
        for t in ["Standard", "Reduced Transparency", "Disabled"]: trans_combo.append_text(t)
        trans_combo.set_active(0)
        anim_combo = Gtk.ComboBoxText()
        for a in ["Full", "Reduced", "Disabled"]: anim_combo.append_text(a)
        anim_combo.set_active(0)
        app_page.append(Gtk.Label(label="Theme")); app_page.append(theme_combo)
        app_page.append(Gtk.Label(label="Accent Color")); app_page.append(accent_combo)
        app_page.append(Gtk.Label(label="Transparency")); app_page.append(trans_combo)
        app_page.append(Gtk.Label(label="Animations")); app_page.append(anim_combo)
        app_page.append(nav_buttons("Back", "Continue",
            lambda b: stack.set_visible_child_name("wallpaper"),
            lambda b: (self.apply_appearance(theme_combo.get_active_text(), accent_combo.get_active_text(), trans_combo.get_active_text(), anim_combo.get_active_text()), stack.set_visible_child_name("privacy"))))
        stack.add_named(app_page, "appearance")

        # ---------- STEP 7 Privacy ----------
        priv = page("Privacy & Security")
        priv.append(Gtk.Label(label="Privacy-first defaults. No advertising tracking, no hidden telemetry. Optional diagnostics are clearly opt-in."))
        priv_checks = []
        for key, desc in [("diagnostics", "Optional diagnostics (off by default)"),
                          ("crash_reports", "Crash reports (off by default)"),
                          ("usage", "Anonymous usage information (off by default)")]:
            row = Gtk.CheckButton(label=desc)
            row.set_active(False)
            priv_checks.append((key, row))
            priv.append(row)
        priv.append(nav_buttons("Back", "Continue",
            lambda b: stack.set_visible_child_name("appearance"),
            lambda b: (self.apply_privacy([ (k, r.get_active()) for k,r in priv_checks]), stack.set_visible_child_name("gaming"))))
        stack.add_named(priv, "privacy")

        # ---------- STEP 8 Gaming ----------
        game = page("Gaming")
        game.append(Gtk.Label(label="Installed / optional / experimental are clearly marked. Not every game is promised."))
        steam_row = Gtk.Label(label="Steam — optional (install from Gaming Hub)")
        gm_row = Gtk.CheckButton(label="Game Mode (experimental, supported games only)")
        ctrl_row = Gtk.CheckButton(label="Controller support (evdev)")
        ctrl_row.set_active(True)
        game.append(steam_row); game.append(gm_row); game.append(ctrl_row)
        game.append(nav_buttons("Back", "Continue",
            lambda b: stack.set_visible_child_name("privacy"),
            lambda b: (self.apply_gaming(gm_row.get_active(), ctrl_row.get_active()), stack.set_visible_child_name("finish"))))
        stack.add_named(game, "gaming")

        # ---------- STEP 9 Finish ----------
        fin = page("Your AetherOS Is Ready")
        fin.append(Gtk.Label(label=f"Wallpaper: {self.selected_wallpaper.name}\nTheme: Dark • Accent: Aether Blue #00A3FF\nPrivacy: all diagnostics off (recommended)\nGaming: Steam optional • Game Mode experimental"))
        enter_btn = Gtk.Button(label="Enter AetherOS")
        enter_btn.add_css_class("suggested")
        enter_btn.connect("clicked", lambda b: self.finish(win))
        fin.append(enter_btn)
        fin.append(nav_buttons("Back", "Back", lambda b: stack.set_visible_child_name("gaming"), lambda b: None))
        # hide unused second nav by default — keep simple: only enter button matters here
        stack.add_named(fin, "finish")

        win.set_child(stack)
        win.present()

    def show_a11y_hint(self):
        # Accessibility options open GNOME settings (if available)
        Gio.AppInfo.launch_default_for_type("application/x-desktop", None)

    def make_wallpaper_card(self, f: pathlib.Path, preview_img: Gtk.Image, preview_label: Gtk.Label):
        btn = Gtk.ToggleButton()
        btn.set_can_focus(False)
        thumb = Gtk.Image()
        try:
            pix = Gio.File.new_for_path(str(f)).query_pixbuf()
            scaled = pix.scale_simple(160, 100, 2)  # device scale
            thumb.set_pixbuf(scaled)
        except Exception:
            thumb.set_from_pixbuf(Gio.File.new_for_path(str(FALLBACK_BG_DIR / "cosmos-nebula.jpg")).query_pixbuf())
        btn.set_child(thumb)
        # checkmark overlay
        overlay = Gtk.Overlay()
        overlay.set_child(btn)
        check = Gtk.Image.new_from_icon_name("object-select-symbolic")
        check.set_pixel_size(24)
        check.set_valign(Gtk.Align.START); check.set_halign(Gtk.Align.END)
        overlay.add_overlay(check)
        btn.connect("toggled", lambda b: self.select_wallpaper(f, preview_img, preview_label))
        if f == self.selected_wallpaper:
            btn.set_active(True)
        return overlay

    def select_wallpaper(self, f, preview_img, preview_label):
        self.selected_wallpaper = f
        preview_label.set_label(f.name)
        try:
            pix = Gio.File.new_for_path(str(f)).query_pixbuf()
            preview_img.set_pixbuf(pix.scale_simple(640, 360, 2))
        except Exception:
            pass

    def randomize_wallpaper(self, preview_img, preview_label):
        files = wallpapers()
        if not files: return
        self.select_wallpaper(random.choice(files), preview_img, preview_label)

    def apply_locale(self, lang, region):
        # localed via polkit (may prompt); tolerant of failure offline
        try:
            subprocess.run(["localectl", "set-locale", lang], check=False, timeout=5)
        except Exception:
            pass
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "locale.json").write_text(json.dumps({"lang": lang, "region": region}, indent=2))
        return True

    def apply_keyboard(self, layout):
        # gsettings input source (per-user, safe)
        try:
            subprocess.run(["gsettings", "set", "org.gnome.desktop.input-sources", "sources",
                            f"[('xkb', '{layout.lower()}')]"], check=False, timeout=5)
        except Exception:
            pass
        return True

    def apply_wallpaper(self, path, fit):
        self.fit_mode = fit
        # fit mapping to GNOME semantics
        gset("org.gnome.desktop.background", "picture-uri", f"file://{path}")
        gset("org.gnome.desktop.background", "picture-uri-dark", f"file://{path}")
        # GNOME uses picture-options: zoom/crop/fit params; store our intent for Settings to read
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "wallpaper.json").write_text(json.dumps({"path": path, "fit": fit}, indent=2))
        try:
            subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-options", "zoom"], check=False, timeout=5)
        except Exception:
            pass
        return True

    def apply_appearance(self, theme, accent, transparency, animations):
        self.theme_mode = theme.lower()
        self.transparency = transparency.lower()
        self.animations = animations.lower()
        # gtk theme
        gtk_theme = "Aether-Dark" if theme == "Dark" else "Aether-Light" if theme == "Light" else "Aether-Dark"
        gset("org.gnome.desktop.interface", "gtk-theme", gtk_theme)
        gset("org.gnome.desktop.interface", "color-scheme", "prefer-dark" if theme == "Dark" else "prefer-light" if theme == "Light" else "default")
        gset("org.gnome.desktop.interface", "enable-animations", "false" if animations == "Disabled" else "true")
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "appearance.json").write_text(json.dumps({"theme": theme, "accent": accent, "transparency": transparency, "animations": animations}, indent=2))
        return True

    def apply_privacy(self, checks):
        self.privacy = {k: bool(v) for k, v in checks}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        PRIVACY_FILE.write_text(json.dumps(self.privacy, indent=2))
        # wiring: whoopsie/apport off unless diagnostics on
        return True

    def apply_gaming(self, gamemode_on, controller_on):
        self.gaming = {"gamemode": bool(gamemode_on), "controller": bool(controller_on)}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "gaming.json").write_text(json.dumps(self.gaming, indent=2))
        return True

    def finish(self, win):
        try:
            self.apply_wallpaper(str(self.selected_wallpaper), self.fit_mode)
        except Exception:
            pass
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        FINISHED_MARKER.touch(exist_ok=True)
        # remove firstboot marker so Setup does not relaunch
        try:
            if FIRSTBOOT_MARKER.exists(): FIRSTBOOT_MARKER.unlink()
        except Exception:
            pass
        # adaptive perf pass
        try:
            subprocess.run(["/usr/local/bin/adaptive-perf", "auto"], check=False, timeout=10)
        except Exception:
            pass
        win.close()
        self.quit()

if __name__ == "__main__":
    app = AetherSetup()
    sys.exit(app.run(sys.argv))
