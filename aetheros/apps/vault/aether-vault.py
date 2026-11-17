#!/usr/bin/env python3
"""Aether Vault application.

Uses the audited core in aetheros/core/vault/secure_vault.py. No cryptography is
implemented in this file. Supports a non-GTK CLI mode for automated testing.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

APP_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_ROOT))
# The ISO installs this app into /usr/share/aether with core/ beside it.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core.vault.secure_vault import (  # noqa: E402
    Argon2Params,
    SecureVault,
    VaultError,
    migrate_legacy_vault,
)

DEFAULT_PATH = pathlib.Path.home() / ".config" / "aether" / "vault.enc"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aether-vault", description="Aether Vault")
    parser.add_argument("--vault", type=pathlib.Path, default=DEFAULT_PATH)
    parser.add_argument("--gui", action="store_true", help="launch the GTK interface")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("create")
    sub.add_parser("unlock")
    p_add = sub.add_parser("add")
    p_add.add_argument("--site", required=True)
    p_add.add_argument("--user", default="")
    p_add.add_argument("--secret", required=True)
    sub.add_parser("list")
    sub.add_parser("save")
    sub.add_parser("change-password")
    p_mig = sub.add_parser("migrate")
    p_mig.add_argument("--from-file", type=pathlib.Path, required=True)
    return parser


def cli_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or ("gui" if args.gui else "unlock")

    if command == "migrate":
        master = input("Current master password: ")
        report = migrate_legacy_vault(master, args.from_file, args.vault)
        print(f"Migrated {report['records']} records to {report['target']}")
        print(f"Legacy copy retained at {report['legacy_backup']}")
        return 0

    if command == "create":
        master = input("New master password: ")
        confirm = input("Confirm master password: ")
        if master != confirm or not master:
            print("Passwords did not match or were empty.", file=sys.stderr)
            return 2
        SecureVault(args.vault, master).create()
        print(f"Created {args.vault}")
        return 0

    master = input("Master password: ")
    vault = SecureVault(args.vault, master)
    try:
        if command == "unlock":
            payload = vault.unlock()
            print(f"Unlocked: {len(payload.get('records', []))} records")
        elif command == "add":
            vault.unlock()
            vault.add({"site": args.site, "user": args.user, "secret": args.secret})
            vault.save()
            print("Record added and saved.")
        elif command == "list":
            for index, record in enumerate(vault.unlock().get("records", [])):
                print(f"{index}: {record.get('site', '')} / {record.get('user', '')}")
        elif command == "save":
            vault.unlock()
            vault.save()
            print("Saved.")
        elif command == "change-password":
            vault.unlock()
            new = input("New master password: ")
            vault.change_password(new)
            print("Master password changed; backup retained.")
        else:
            print(f"Unknown command: {command}", file=sys.stderr)
            return 2
    except VaultError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def gui_main() -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    class VaultApp(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aether.Vault")
            self.vault: SecureVault | None = None

        def do_activate(self) -> None:
            window = Adw.ApplicationWindow(application=self, title="Aether Vault")
            window.set_default_size(760, 560)
            stacked = Adw.ViewStack()
            unlock_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            unlock_page.set_margin_top(24)
            unlock_page.set_margin_start(32)
            unlock_page.set_margin_end(32)
            password = Gtk.PasswordEntry(show_peek_icon=True)
            password.set_placeholder_text("Master password")
            status = Gtk.Label(label="Locked")
            unlock_button = Gtk.Button(label="Unlock")
            unlock_button.add_css_class("suggested-action")

            def on_unlock(_button: Gtk.Button) -> None:
                try:
                    candidate = SecureVault(DEFAULT_PATH, password.get_text())
                    payload = candidate.unlock()
                except VaultError as exc:
                    status.set_label(str(exc))
                    return
                self.vault = candidate
                status.set_label(f"Unlocked — {len(payload.get('records', []))} records")
                render_records()

            def render_records() -> None:
                if self.vault is None:
                    return
                for child in list(page.get_children()):
                    page.remove(child)
                for record in self.vault.payload.get("records", []):
                    row = Adw.ActionRow(title=record.get("site", ""), subtitle=record.get("user", ""))
                    page.add(row)
                page.add(Gtk.Label(label=status.get_label()))

            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            unlock_button.connect("clicked", on_unlock)
            unlock_page.append(password)
            unlock_page.append(unlock_button)
            unlock_page.append(status)
            stacked.add_titled(unlock_page, "unlock", "Unlock")
            stacked.add_titled(page, "records", "Records")
            switcher = Adw.ViewSwitcher(stack=stacked)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            outer.append(switcher)
            outer.append(stacked)
            window.set_content(outer)
            window.present()

    return VaultApp().run(sys.argv)


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    sys.exit(cli_main() if parsed.command else gui_main())
