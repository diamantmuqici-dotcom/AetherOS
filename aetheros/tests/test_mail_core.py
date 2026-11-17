"""Unit tests for the Aether Mail core.

Run with: python -m unittest discover -s aetheros/tests -p 'test_mail_core.py' -v
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from email.message import EmailMessage
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core.mail.account import Account, AccountError, AccountStore  # noqa: E402
from core.mail.credentials import CredentialStore, LockedError  # noqa: E402
from core.mail.html_sanitize import sanitize  # noqa: E402
from core.mail import pgp  # noqa: E402
from core.mail.lock import LockError, LockedError as MailLockedError, MailLock, should_lock  # noqa: E402
from core.mail.smtp_send import MailSendError, send_message  # noqa: E402
from core.vault.secure_vault import Argon2Params, WrongPasswordError  # noqa: E402

TEST_PARAMS = Argon2Params(memory_cost_kib=1024, iterations=1, parallelism=1, salt_len=16)


def make_account(**overrides):
    values = {
        "id": "personal",
        "email": "user@example.org",
        "imap_host": "imap.example.org",
        "imap_port": 993,
        "imap_tls": "ssl",
        "smtp_host": "smtp.example.org",
        "smtp_port": 465,
        "smtp_security": "ssl",
        "username": "user",
        "auth_method": "password",
    }
    values.update(overrides)
    return Account(**values)


class AccountTests(unittest.TestCase):
    def test_valid_tls_modes_validate(self) -> None:
        make_account().validate()
        make_account(imap_tls="starttls", smtp_security="starttls", imap_port=143, smtp_port=587).validate()

    def test_cleartext_transport_rejected(self) -> None:
        with self.assertRaises(AccountError):
            make_account(imap_tls="none").validate()
        with self.assertRaises(AccountError):
            make_account(smtp_security="plain").validate()
        with self.assertRaises(AccountError):
            make_account(imap_tls="", smtp_security="").validate()

    def test_bad_host_port_and_id_rejected(self) -> None:
        for change in ({"imap_port": 0}, {"smtp_port": 70000}, {"imap_host": "bad host"}, {"id": "bad id"}):
            with self.subTest(change=change), self.assertRaises(AccountError):
                make_account(**change).validate()

    def test_store_roundtrip_and_no_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "accounts.json"
            store = AccountStore(path)
            account = make_account()
            store.add(account)
            raw = path.read_text(encoding="utf-8")
            keys = set(json.loads(raw)["accounts"][0])
            self.assertNotIn("secret", keys)
            self.assertNotIn("password_field", keys)
            self.assertEqual(store.load(), [account])
            self.assertTrue(store.remove(account.id))
            self.assertEqual(store.load(), [])
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class SanitizerTests(unittest.TestCase):
    def test_script_style_and_iframe_removed(self) -> None:
        html = "<p>ok</p><script>alert(1)</script><style>x{}</style><iframe src='x'></iframe>"
        out = sanitize(html, False)
        self.assertIn("<p>ok</p>", out)
        for token in ("script", "alert", "style", "iframe"):
            self.assertNotIn(token, out)

    def test_event_handlers_and_js_urls_removed(self) -> None:
        html = '<a href="javascript:alert(1)" onclick="bad()">link</a>'
        out = sanitize(html, False)
        self.assertNotIn("javascript", out)
        self.assertNotIn("onclick", out)
        self.assertIn("link", out)

    def test_remote_image_placeholder(self) -> None:
        html = '<img src="https://tracker.example/pixel.gif" alt="pix">'
        blocked = sanitize(html, False)
        self.assertNotIn("tracker.example", blocked)
        self.assertIn("remote image", blocked)
        self.assertIn("tracker.example", sanitize(html, True))

    def test_data_url_removed(self) -> None:
        out = sanitize('<a href="data:text/html;base64,AAAA">x</a>', True)
        self.assertNotIn("data:", out)


class LockTests(unittest.TestCase):
    def test_should_lock_pure_function(self) -> None:
        self.assertFalse(should_lock(100.0, 104.0, 5.0))
        self.assertTrue(should_lock(100.0, 105.0, 5.0))
        self.assertTrue(should_lock(None, 10.0, 5.0))
        self.assertFalse(should_lock(100.0, 90.0, 5.0))
        self.assertTrue(should_lock(100.0, 100.0, 0.0))

    def test_lock_gate(self) -> None:
        lock = MailLock("correct horse", params=TEST_PARAMS, timeout_s=300.0)
        self.assertTrue(lock.locked)
        with self.assertRaises(MailLockedError):
            lock.passphrase()
        with self.assertRaises(LockError):
            lock.unlock("wrong")
        lock.unlock("correct horse")
        self.assertFalse(lock.locked)
        self.assertEqual(lock.passphrase(), "correct horse")
        lock.lock()
        self.assertTrue(lock.locked)

    def test_auto_lock(self) -> None:
        lock = MailLock("pw", params=TEST_PARAMS, timeout_s=5.0, now_fn=lambda: 0.0)
        lock.unlock("pw")
        self.assertFalse(lock.check_auto_lock(now=4.0))
        self.assertTrue(lock.check_auto_lock(now=6.0))
        self.assertTrue(lock.locked)


class CredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "credentials.enc"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_roundtrip_and_no_plaintext(self) -> None:
        store = CredentialStore(
            self.path, "passphrase", prefer_secret_service=False, params=TEST_PARAMS
        )
        store.store("personal", "s3cret-token")
        self.assertEqual(store.get("personal"), "s3cret-token")
        raw = self.path.read_bytes()
        self.assertNotIn(b"s3cret-token", raw)
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(store.delete("personal"))
        self.assertIsNone(store.get("personal"))

    def test_locked_refuses_access(self) -> None:
        store = CredentialStore(
            self.path, "passphrase", prefer_secret_service=False, params=TEST_PARAMS
        )
        store.store("personal", "value")
        store.lock()
        with self.assertRaises(LockedError):
            store.get("personal")
        with self.assertRaises(LockedError):
            store.store("personal", "new")

    def test_wrong_passphrase_fails_closed(self) -> None:
        CredentialStore(
            self.path, "passphrase", prefer_secret_service=False, params=TEST_PARAMS
        ).store("personal", "value")
        with self.assertRaises(WrongPasswordError):
            CredentialStore(
                self.path, "wrong", prefer_secret_service=False, params=TEST_PARAMS
            )


class PGPTests(unittest.TestCase):
    def test_missing_gpg_fails_closed(self) -> None:
        with mock.patch.object(pgp.shutil, "which", return_value=None):
            with self.assertRaises(pgp.GPGUnavailableError):
                pgp.encrypt("plaintext", "A" * 40)

    def test_argv_and_stdin(self) -> None:
        fake = subprocess.CompletedProcess([], 0, stdout=b"-----BEGIN PGP MESSAGE-----\nx\n", stderr=b"")
        with mock.patch.object(pgp.shutil, "which", return_value="/usr/bin/gpg"), \
             mock.patch.object(pgp.subprocess, "run", return_value=fake) as run:
            result = pgp.encrypt("secret body", "A" * 40)
        self.assertIn("BEGIN PGP MESSAGE", result)
        args, kwargs = run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "/usr/bin/gpg")
        self.assertIn("--batch", cmd)
        self.assertIn("A" * 40, cmd)
        self.assertNotIn("secret body", cmd)
        self.assertEqual(kwargs["input"], b"secret body")
        self.assertIs(kwargs["shell"], False)
        self.assertIs(kwargs["capture_output"], True)

    def test_invalid_fingerprint_rejected(self) -> None:
        with self.assertRaises(pgp.PGPError):
            pgp.encrypt("text", "not a fingerprint; rm -rf /")


class SMTPTests(unittest.TestCase):
    def test_cleartext_rejected_before_connect(self) -> None:
        account = make_account(smtp_security="none")
        with mock.patch("core.mail.smtp_send.smtplib.SMTP") as smtp:
            with self.assertRaises(MailSendError):
                send_message(account, "pw", object())
        smtp.assert_not_called()

    def test_implicit_tls_path(self) -> None:
        account = make_account()
        client = mock.MagicMock()
        with mock.patch("core.mail.smtp_send.smtplib.SMTP_SSL", return_value=client) as factory:
            send_message(account, "pw", EmailMessage())
        factory.assert_called_once()
        client.login.assert_called_once_with("user", "pw")
        client.send_message.assert_called_once()
