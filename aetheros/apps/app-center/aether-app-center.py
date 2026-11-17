#!/usr/bin/env python3
"""Aether App Center — Flatpak inventory, system packages, permission visibility."""
from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys

MAX_LINES = 2000
MAX_FIELD = 512
LIST_TIMEOUT = 15
ACTION_TIMEOUT = 180
FLATPAK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,254}$")
RELEVANT_PACKAGES = (
    "aether",
    "chromium",
    "flatpak",
    "apparmor",
    "ufw",
    "nftables",
    "plymouth",
    "pipewire",
    "wireplumber",
    "gstreamer",
    "mesa",
    "steam",
    "proton",
    "gamemode",
)


def run(command: list[str], timeout: int = LIST_TIMEOUT) -> dict[str, object]:
    rendered = shlex.join(command)
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": rendered,
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": rendered,
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
            "returncode": None,
        }


def list_flatpak_apps() -> dict[str, object]:
    available = shutil.which("flatpak") is not None
    result: dict[str, object] = {
        "available": available,
        "command": "",
        "apps": [],
        "error": "",
    }
    if not available:
        result["error"] = "flatpak binary not found"
        return result

    proc = run(["flatpak", "list", "--columns=application,version,origin,name"])
    result["command"] = proc["command"]
    if not proc["ok"]:
        result["error"] = str(proc["stderr"]).strip() or "flatpak list failed"
        return result

    apps: list[dict[str, str]] = []
    for line in str(proc["stdout"]).splitlines()[:MAX_LINES]:
        fields = line.split("\t")
        if len(fields) < 4:
            continue
        app_id, version, origin, name = (field.strip()[:MAX_FIELD] for field in fields[:4])
        if not FLATPAK_ID_RE.fullmatch(app_id):
            continue
        apps.append({"id": app_id, "name": name, "version": version, "origin": origin})
    result["apps"] = apps
    return result


def list_system_packages() -> dict[str, object]:
    fmt = r"${Package}\t${Version}\t${Status}\n"
    proc = run(["dpkg-query", "-W", "-f=" + fmt])
    result: dict[str, object] = {
        "command": proc["command"],
        "packages": [],
        "error": "",
    }
    if not proc["ok"]:
        result["error"] = str(proc["stderr"]).strip() or "dpkg-query failed"
        return result

    packages: list[dict[str, str]] = []
    for line in str(proc["stdout"]).splitlines()[:MAX_LINES]:
        fields = line.split("\t")
        if len(fields) < 3:
            continue
        name, version, status = (field.strip()[:MAX_FIELD] for field in fields[:3])
        if "installed" not in status:
            continue
        if not any(token in name.lower() for token in RELEVANT_PACKAGES):
            continue
        packages.append({"name": name, "version": version, "status": status})
    result["packages"] = packages
    return result


def flatpak_permissions(app_id: str) -> dict[str, object]:
    if not FLATPAK_ID_RE.fullmatch(app_id):
        return {"command": "", "ok": False, "lines": [], "error": "invalid application id"}
    proc = run(["flatpak", "info", "--show-permissions", app_id])
    lines = [
        line.strip()[:MAX_FIELD]
        for line in str(proc["stdout"]).splitlines()[:MAX_LINES]
        if line.strip()
    ]
    return {
        "command": proc["command"],
        "ok": proc["ok"],
        "lines": lines,
        "error": str(proc["stderr"]).strip(),
    }


def install_app(app_id: str, remote: str) -> dict[str, object]:
    if not FLATPAK_ID_RE.fullmatch(app_id):
        return {"command": "", "ok": False, "stderr": "invalid application id"}
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", remote):
        return {"command": "", "ok": False, "stderr": "invalid remote name"}
    return run(
        ["flatpak", "install", "--noninteractive", remote, app_id],
        timeout=ACTION_TIMEOUT,
    )


def remove_app(app_id: str) -> dict[str, object]:
    if not FLATPAK_ID_RE.fullmatch(app_id):
        return {"command": "", "ok": False, "stderr": "invalid application id"}
    return run(["flatpak", "uninstall", "--noninteractive", app_id], timeout=ACTION_TIMEOUT)


def snapshot() -> dict[str, object]:
    flatpak = list_flatpak_apps()
    packages = list_system_packages()
    return {
        "flatpak_available": flatpak["available"],
        "flatpak_command": flatpak["command"],
        "flatpak_apps": flatpak["apps"],
        "flatpak_error": flatpak["error"],
        "system_packages_command": packages["command"],
        "system_packages": packages["packages"],
        "system_packages_error": packages["error"],
    }


def gui_main(argv: list[str]) -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    class AppCenter(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aether.AppCenter")
            self.data: dict[str, object] = {}
            self.status = Gtk.Label(label="", wrap=True)
            self.flatpak_list = Gtk.ListBox()
            self.system_list = Gtk.ListBox()
            self.permission_list = Gtk.ListBox()

        def do_activate(self) -> None:
            window = Adw.ApplicationWindow(application=self, title="Aether App Center")
            window.set_default_size(860, 640)
            stack = Adw.ViewStack()

            self.flatpak_list.set_selection_mode(Gtk.SelectionMode.NONE)
            self.system_list.set_selection_mode(Gtk.SelectionMode.NONE)
            self.permission_list.set_selection_mode(Gtk.SelectionMode.NONE)

            flatpak_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            flatpak_page.set_margin_top(16)
            flatpak_page.set_margin_bottom(16)
            flatpak_page.set_margin_start(16)
            flatpak_page.set_margin_end(16)
            flatpak_page.append(Gtk.ScrolledWindow(child=self.flatpak_list))

            system_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            system_page.set_margin_top(16)
            system_page.set_margin_bottom(16)
            system_page.set_margin_start(16)
            system_page.set_margin_end(16)
            system_page.append(Gtk.ScrolledWindow(child=self.system_list))

            permission_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            permission_page.set_margin_top(16)
            permission_page.set_margin_bottom(16)
            permission_page.set_margin_start(16)
            permission_page.set_margin_end(16)
            permission_page.append(Gtk.ScrolledWindow(child=self.permission_list))

            for page, name, title in (
                (flatpak_page, "flatpak", "Flatpak"),
                (system_page, "system", "System"),
                (permission_page, "permissions", "Permissions"),
            ):
                stack.add_titled(page, name, title)

            header = Adw.HeaderBar()
            refresh_button = Gtk.Button(label="Refresh")
            refresh_button.connect("clicked", lambda _b: self.refresh())
            install_button = Gtk.Button(label="Install…")
            install_button.add_css_class("suggested-action")
            install_button.connect("clicked", lambda _b: self.show_install(window))
            header.pack_start(refresh_button)
            header.pack_end(install_button)

            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            outer.append(header)
            outer.append(Adw.ViewSwitcher(stack=stack))
            outer.append(stack)
            outer.append(self.status)
            window.set_content(outer)
            self.refresh()
            window.present()

        def refresh(self) -> None:
            self.data = snapshot()
            self.flatpak_list.remove_all()
            self.system_list.remove_all()
            self.status.set_label("Reading system state…")

            apps = list(self.data["flatpak_apps"])
            if not self.data["flatpak_available"]:
                self.flatpak_list.append(
                    Adw.ActionRow(title="Flatpak unavailable", subtitle=str(self.data["flatpak_error"]))
                )
            elif not apps:
                self.flatpak_list.append(Adw.ActionRow(title="No installed Flatpak applications"))
            for app in apps:
                row = Adw.ActionRow(
                    title=str(app["name"]) or str(app["id"]),
                    subtitle=f"{app['id']} · {app['version']} · {app['origin']}",
                )
                perms_button = Gtk.Button(label="Permissions")
                perms_button.connect("clicked", lambda _b, i=app["id"]: self.show_permissions(i))
                remove_button = Gtk.Button(label="Remove")
                remove_button.add_css_class("destructive-action")
                remove_button.connect("clicked", lambda _b, i=app["id"]: self.confirm_remove(i))
                row.add_suffix(perms_button)
                row.add_suffix(remove_button)
                self.flatpak_list.append(row)

            packages = list(self.data["system_packages"])
            for package in packages:
                self.system_list.append(
                    Adw.ActionRow(
                        title=package["name"],
                        subtitle=f"{package['version']} · {package['status']}",
                    )
                )
            if not packages:
                self.system_list.append(Adw.ActionRow(title="No matching system packages"))
            self.status.set_label(
                f"{len(apps)} Flatpak apps · {len(packages)} system packages · "
                f"{self.data['flatpak_command']}"
            )

        def show_permissions(self, app_id: str) -> None:
            info = flatpak_permissions(app_id)
            self.permission_list.remove_all()
            for line in info["lines"]:
                self.permission_list.append(Adw.ActionRow(title=line))
            if not info["lines"]:
                self.permission_list.append(
                    Adw.ActionRow(title="No permissions reported", subtitle=str(info["error"]))
                )
            self.status.set_label(f"{info['command']} → {'ok' if info['ok'] else 'failed'}")

        def show_install(self, window: Adw.ApplicationWindow) -> None:
            dialog = Adw.Window(transient_for=window, modal=True, title="Install Flatpak")
            dialog.set_default_size(440, 200)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(20)
            box.set_margin_bottom(20)
            box.set_margin_start(20)
            box.set_margin_end(20)
            app_entry = Gtk.Entry(placeholder_text="org.example.App")
            remote_entry = Gtk.Entry(text="flathub", placeholder_text="remote")
            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            actions.set_halign(Gtk.Align.END)
            cancel = Gtk.Button(label="Cancel")
            confirm = Gtk.Button(label="Install")
            confirm.add_css_class("suggested-action")
            actions.append(cancel)
            actions.append(confirm)
            box.append(app_entry)
            box.append(remote_entry)
            box.append(actions)
            dialog.set_content(box)

            def do_install(_button: Gtk.Button) -> None:
                app_id = app_entry.get_text().strip()
                remote = remote_entry.get_text().strip() or "flathub"
                result = install_app(app_id, remote)
                self.status.set_label(
                    f"{result['command']} → {'ok' if result['ok'] else str(result['stderr'])[:200]}"
                )
                dialog.destroy()
                self.refresh()

            cancel.connect("clicked", lambda _b: dialog.destroy())
            confirm.connect("clicked", do_install)
            dialog.present()

        def confirm_remove(self, app_id: str) -> None:
            window = self.get_active_window()
            dialog = Adw.MessageDialog(
                transient_for=window,
                heading=f"Remove {app_id}?",
                body="Installed application data will be deleted.",
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("remove", "Remove")
            dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")

            def on_response(_dialog: Adw.MessageDialog, response: str) -> None:
                if response != "remove":
                    return
                result = remove_app(app_id)
                self.status.set_label(
                    f"{result['command']} → {'ok' if result['ok'] else str(result['stderr'])[:200]}"
                )
                self.refresh()

            dialog.connect("response", on_response)
            dialog.present()

    return AppCenter().run(argv)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="aether-app-center", description="Aether App Center")
    parser.add_argument("--list", action="store_true", help="print inventory as JSON")
    args = parser.parse_args(argv[1:])
    if args.list:
        print(json.dumps(snapshot(), sort_keys=True, indent=2))
        return 0
    return gui_main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
