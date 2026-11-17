#!/usr/bin/env python3
"""Aether Mail — GTK4/libadwaita client with a headless status check."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

VERSION = "1.0.0"
_FPR_RE = re.compile(r"^[0-9A-Fa-f]{16,40}$")


def _bootstrap() -> None:
    here = pathlib.Path(__file__).resolve()
    candidates = [here.parent]
    candidates.extend(here.parents[:8])
    for candidate in candidates:
        if (candidate / "core" / "mail" / "account.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return


_bootstrap()

from core.mail import pgp  # noqa: E402
from core.mail.account import Account, AccountError, AccountStore  # noqa: E402
from core.mail.credentials import CredentialStore, secret_service_available  # noqa: E402
from core.mail.html_sanitize import sanitize  # noqa: E402
from core.mail.imap_sync import IMAPMail, MailSyncError  # noqa: E402
from core.mail.lock import MailLock, install_dbus_hooks  # noqa: E402
from core.mail.smtp_send import MailSendError, build_message, send_message  # noqa: E402


def check_status() -> dict:
    store = AccountStore()
    try:
        accounts = store.load()
    except AccountError:
        accounts = []
    return {
        "version": VERSION,
        "accounts": [{"id": account.id, "email": account.email} for account in accounts],
        "account_count": len(accounts),
        "locked": True,
        "credential_backend": "secret-service" if secret_service_available() else "encrypted-file",
        "pgp_available": pgp.is_available(),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="aether-mail")
    parser.add_argument("--check", action="store_true", help="print account/lock status JSON")
    parser.add_argument("--version", action="store_true", help="print the version")
    args = parser.parse_args(argv[1:])
    if args.version:
        print(VERSION)
        return 0
    if args.check:
        print(json.dumps(check_status(), sort_keys=True))
        return 0
    return run_gui()


def run_gui() -> int:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, GLib, Gtk

    class AetherMail(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aetheros.Mail")
            self.accounts = AccountStore()
            self.creds = CredentialStore()
            self.mail_lock: MailLock | None = None
            self.current: Account | None = None
            self.folder = "INBOX"
            self.allow_remote_images = False
            self.rows: dict[object, int] = {}
            self.folder_rows: dict[object, str] = {}

        def do_activate(self) -> None:
            win = Adw.ApplicationWindow(
                application=self, title="Aether Mail", default_width=1100, default_height=760
            )
            self.win = win
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            win.set_content(root)

            header = Adw.HeaderBar()
            header.set_title_widget(Adw.WindowTitle(title="Aether Mail", subtitle="local-first"))
            self.add_button = Gtk.Button(label="Add account")
            self.sync_button = Gtk.Button(label="Sync")
            self.compose_button = Gtk.Button(label="Compose")
            self.lock_button = Gtk.Button(label="Lock / Unlock")
            self.image_switch = Gtk.CheckButton(label="Remote images")
            header.pack_start(self.add_button)
            header.pack_start(self.sync_button)
            header.pack_start(self.compose_button)
            header.pack_end(self.image_switch)
            header.pack_end(self.lock_button)
            root.append(header)

            self.status = Gtk.Label(
                label="Locked — set a passphrase with Lock / Unlock",
                halign=Gtk.Align.START,
                margin_start=12,
                margin_top=6,
            )
            root.append(self.status)

            paned = Gtk.Paned(
                orientation=Gtk.Orientation.HORIZONTAL,
                shrink_start_child=False,
                shrink_end_child=False,
            )
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self.folders = Gtk.ListBox()
            self.messages = Gtk.ListBox()
            left.append(Gtk.Label(label="Folders", halign=Gtk.Align.START, margin_start=6))
            left.append(self.folders)
            left.append(Gtk.Label(label="Messages", halign=Gtk.Align.START, margin_start=6))
            left.append(self.messages)
            right = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
            self.body_view = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD)
            right.set_child(self.body_view)
            paned.set_start_child(left)
            paned.set_end_child(right)
            paned.set_position(380)
            root.append(paned)

            self.add_button.connect("clicked", self.on_add_account)
            self.sync_button.connect("clicked", self.on_sync)
            self.compose_button.connect("clicked", self.on_compose)
            self.lock_button.connect("clicked", self.on_lock_toggle)
            self.image_switch.connect("toggled", self.on_image_toggled)
            self.folders.connect("row-activated", self.on_folder_activated)
            self.messages.connect("row-activated", self.on_message_activated)
            GLib.timeout_add_seconds(15, self.on_tick)
            win.present()

        def _set_status(self, text: str) -> None:
            self.status.set_label(text[:300])

        def _text(self, entry) -> str:
            value = entry.get_text()
            return value if isinstance(value, str) else ""

        def _dialog(self, title: str, fields: list[tuple[str, str, str, bool]]):
            dialog = Gtk.Dialog(title=title, transient_for=self.win, modal=True)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.add_button("OK", Gtk.ResponseType.OK)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
            dialog.get_content_area().append(box)
            entries: dict[str, object] = {}
            for key, label, default, secret in fields:
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                line.append(Gtk.Label(label=label, width_chars=18, xalign=0))
                entry = Gtk.PasswordEntry() if secret else Gtk.Entry()
                if not secret and default:
                    entry.set_text(default)
                line.append(entry)
                box.append(line)
                entries[key] = entry
            return dialog, entries

        def _clear_list(self, listbox) -> None:
            while True:
                row = listbox.get_row_at_index(0)
                if row is None:
                    break
                listbox.remove(row)

        def _row(self, text: str):
            label = Gtk.Label(label=text[:200], xalign=0, margin=6)
            row = Gtk.ListBoxRow()
            row.set_child(label)
            return row

        def _ensure_unlocked(self) -> bool:
            if self.mail_lock is None or self.mail_lock.locked or not self.creds.unlocked:
                self._set_status("Locked — unlock before using mail")
                return False
            return True

        def _selected_account(self):
            if self.current is not None:
                return self.current
            loaded = self.accounts.load()
            if loaded:
                self.current = loaded[0]
            return self.current

        def on_lock_toggle(self, button) -> None:
            if self.mail_lock is None:
                dialog, entries = self._dialog("Set mail passphrase", [
                    ("pass", "Passphrase", "", True),
                    ("confirm", "Confirm", "", True),
                ])
                response = dialog.run()
                values = {key: self._text(entry) for key, entry in entries.items()}
                dialog.destroy()
                if response != Gtk.ResponseType.OK:
                    return
                if not values["pass"] or values["pass"] != values["confirm"]:
                    self._set_status("Passphrases did not match")
                    return
                try:
                    self.mail_lock = MailLock(values["pass"])
                    self.creds.unlock(values["pass"])
                    install_dbus_hooks(self.mail_lock)
                    self._set_status(f"Unlocked — credential backend: {self.creds.backend_name}")
                except Exception as exc:
                    self.mail_lock = None
                    self._set_status(f"Unlock failed: {exc}")
                return

            if self.mail_lock.locked:
                dialog, entries = self._dialog("Unlock mail", [("pass", "Passphrase", "", True)])
                response = dialog.run()
                value = self._text(entries["pass"])
                dialog.destroy()
                if response != Gtk.ResponseType.OK:
                    return
                try:
                    self.mail_lock.unlock(value)
                    self.creds.unlock(value)
                    self._set_status("Unlocked")
                except Exception as exc:
                    self._set_status(f"Unlock failed: {exc}")
                return

            self.creds.lock()
            self.mail_lock.lock()
            self._set_status("Locked")

        def on_image_toggled(self, button) -> None:
            self.allow_remote_images = button.get_active()

        def on_tick(self) -> bool:
            if self.mail_lock is not None and not self.mail_lock.locked:
                if self.mail_lock.check_auto_lock():
                    self.creds.lock()
                    self._set_status("Locked after inactivity")
            return True

        def on_add_account(self, button) -> None:
            if not self._ensure_unlocked():
                return
            dialog, entries = self._dialog("Add mail account", [
                ("id", "Account ID", "", False),
                ("email", "Email", "", False),
                ("username", "Username", "", False),
                ("imap_host", "IMAP host", "", False),
                ("imap_port", "IMAP port", "993", False),
                ("imap_tls", "IMAP TLS (ssl/starttls)", "ssl", False),
                ("smtp_host", "SMTP host", "", False),
                ("smtp_port", "SMTP port", "465", False),
                ("smtp_security", "SMTP TLS (ssl/starttls)", "ssl", False),
                ("auth_method", "Auth (password/oauth2)", "password", False),
                ("password", "Password / token", "", True),
            ])
            response = dialog.run()
            values = {key: self._text(entry).strip() for key, entry in entries.items()}
            dialog.destroy()
            if response != Gtk.ResponseType.OK:
                return
            try:
                account = Account(
                    id=values["id"],
                    email=values["email"],
                    imap_host=values["imap_host"],
                    imap_port=int(values["imap_port"]),
                    imap_tls=values["imap_tls"],
                    smtp_host=values["smtp_host"],
                    smtp_port=int(values["smtp_port"]),
                    smtp_security=values["smtp_security"],
                    username=values["username"],
                    auth_method=values["auth_method"],
                ).validate()
                self.accounts.add(account)
                self.creds.store(account.id, values["password"])
                self.current = account
                self._set_status(f"Account {account.id} added")
            except Exception as exc:
                self._set_status(f"Could not add account: {exc}")

        def on_folder_activated(self, listbox, row) -> None:
            folder = self.folder_rows.get(row)
            if folder:
                self.folder = folder
                self.on_sync(None)

        def on_sync(self, button) -> None:
            if not self._ensure_unlocked():
                return
            account = self._selected_account()
            if account is None:
                self._set_status("Add an account first")
                return
            password = self.creds.get(account.id)
            if not password:
                self._set_status(f"No stored credential for {account.id}")
                return
            try:
                with IMAPMail(account, password) as mail:
                    folders = mail.list_folders()
                    headers = mail.fetch_headers(200, self.folder)
            except Exception as exc:
                self._set_status(f"Sync failed: {exc}")
                return
            self._clear_list(self.folders)
            self.folder_rows = {}
            for entry in folders[:200]:
                row = self._row(entry["name"])
                self.folder_rows[row] = entry["name"]
                self.folders.append(row)
            self._clear_list(self.messages)
            self.rows = {}
            for header in headers:
                row = self._row(f"{header['subject'] or '(no subject)'} — {header['from']}")
                self.rows[row] = header["uid"]
                self.messages.append(row)
            self._set_status(f"Synced {len(headers)} messages from {self.folder}")

        def on_message_activated(self, listbox, row) -> None:
            if not self._ensure_unlocked():
                return
            uid = self.rows.get(row)
            account = self._selected_account()
            if uid is None or account is None:
                return
            password = self.creds.get(account.id)
            if not password:
                self._set_status("No stored credential")
                return
            try:
                with IMAPMail(account, password) as mail:
                    message = mail.fetch_body(uid, self.folder)
            except Exception as exc:
                self._set_status(f"Read failed: {exc}")
                return
            rendered = sanitize(message["body"], self.allow_remote_images)
            self.body_view.get_buffer().set_text(rendered[:2 * 1024 * 1024], -1)
            suffix = " (truncated)" if message["truncated"] else ""
            self._set_status(f"Message {uid}{suffix}")

        def on_compose(self, button) -> None:
            if not self._ensure_unlocked():
                return
            account = self._selected_account()
            if account is None:
                self._set_status("Add an account first")
                return
            password = self.creds.get(account.id)
            if not password:
                self._set_status("No stored credential")
                return

            def pgp_status(mode: str, fingerprint: str) -> str:
                normalized = fingerprint.replace(" ", "").replace("\t", "")
                if mode == "none":
                    return "PGP: off — message will be sent in plaintext"
                if not pgp.is_available():
                    return f"PGP: gpg unavailable — cannot {mode}"
                if not _FPR_RE.fullmatch(normalized):
                    return f"PGP: invalid fingerprint — cannot {mode}"
                return f"PGP: {mode} with {normalized} — ready"

            dialog = Gtk.Dialog(title="Compose", transient_for=self.win, modal=True)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.add_button("Review", Gtk.ResponseType.OK)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
            dialog.get_content_area().append(box)

            to_entry = Gtk.Entry()
            subject_entry = Gtk.Entry()
            fpr_entry = Gtk.Entry()
            mode = Gtk.ComboBoxText()
            for item in ("none", "sign", "encrypt"):
                mode.append_text(item)
            mode.set_active(0)
            body_view = Gtk.TextView(editable=True, wrap_mode=Gtk.WrapMode.WORD)
            body_scroll = Gtk.ScrolledWindow(height_request=180)
            body_scroll.set_child(body_view)
            pgp_label = Gtk.Label(label="", halign=Gtk.Align.START, wrap=True)

            for label, widget in (
                ("To", to_entry),
                ("Subject", subject_entry),
                ("PGP mode", mode),
                ("Fingerprint", fpr_entry),
            ):
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                line.append(Gtk.Label(label=label, width_chars=14, xalign=0))
                line.append(widget)
                box.append(line)
            box.append(body_scroll)
            box.append(pgp_label)

            def refresh(*_) -> None:
                pgp_label.set_label(pgp_status(mode.get_active_text() or "none", fpr_entry.get_text()))

            mode.connect("changed", refresh)
            fpr_entry.connect("changed", refresh)
            refresh()

            response = dialog.run()
            values = {
                "to": to_entry.get_text().strip(),
                "subject": subject_entry.get_text().strip(),
                "mode": mode.get_active_text() or "none",
                "fpr": fpr_entry.get_text(),
            }
            buffer = body_view.get_buffer()
            body_text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
            dialog.destroy()
            if response != Gtk.ResponseType.OK:
                return

            status_text = pgp_status(values["mode"], values["fpr"])
            confirm = Gtk.Dialog(title="Review before sending", transient_for=self.win, modal=True)
            confirm.add_button("Cancel", Gtk.ResponseType.CANCEL)
            confirm.add_button("Send", Gtk.ResponseType.OK)
            summary = Gtk.Label(
                label=f"To: {values['to']}\nSubject: {values['subject']}\n{status_text}\n\nSend now?",
                wrap=True,
                margin=12,
            )
            confirm.get_content_area().append(summary)
            confirmed = confirm.run()
            confirm.destroy()
            if confirmed != Gtk.ResponseType.OK:
                return
            if values["mode"] != "none" and ("unavailable" in status_text or "invalid" in status_text):
                self._set_status(status_text)
                return

            outgoing = body_text
            tag = None
            try:
                if values["mode"] == "encrypt":
                    outgoing = pgp.encrypt(body_text, values["fpr"])
                    tag = "encrypted"
                elif values["mode"] == "sign":
                    outgoing = pgp.sign(body_text, values["fpr"])
                    tag = "signed"
                message = build_message(account.email, [values["to"]], values["subject"], outgoing, pgp_status=tag)
                send_message(account, password, message)
            except Exception as exc:
                self._set_status(f"Send failed: {exc}")
                return
            self._set_status(f"Sent — {status_text}")

    app = AetherMail()
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
