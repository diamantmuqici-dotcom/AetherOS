"""Unit tests for Aether Mail attachments and IMAP IDLE.

Run: python -m unittest discover -s aetheros/tests -p 'test_mail_extras.py' -v
"""

from __future__ import annotations

import base64
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.mail import attachment, imap_idle  # noqa: E402
from core.mail.smtp_send import build_message  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"x" * 48
JPEG = b"\xff\xd8\xff\xe0JFIF" + b"y" * 48
TEXT = b"plain report content\n"


def write(path: pathlib.Path, data: bytes) -> pathlib.Path:
    path.write_bytes(data)
    return path


class FakeIdleConnection:
    """Minimal IdleSession connection protocol implementation."""

    def __init__(self, lines=None, *, fail_idle: bool = False):
        self.lines = list(lines or [])
        self.fail_idle = fail_idle
        self.selects: list[str] = []
        self.idle_count = 0
        self.done_count = 0
        self.closed = False
        self.on_read: object = None

    def select(self, mailbox: str) -> tuple[str, list]:
        self.selects.append(mailbox)
        return "OK", [b"1"]

    def issue_idle(self) -> bytes:
        self.idle_count += 1
        if self.fail_idle:
            raise imap_idle.IdleConnectionError("fake disconnect")
        return b"A001"

    def read_idle_line(self, timeout_s: float) -> bytes | None:
        if self.on_read is not None:
            callback, self.on_read = self.on_read, None
            callback()
        return self.lines.pop(0) if self.lines else None

    def finish_idle(self, token: bytes) -> None:
        self.done_count += 1

    def close(self) -> None:
        self.closed = True


class AttachmentPolicyTests(unittest.TestCase):
    def test_sanitize_filename_strips_paths_and_controls(self) -> None:
        self.assertEqual(attachment.sanitize_filename("../../etc/passwd"), "passwd")
        self.assertEqual(
            attachment.sanitize_filename("..\\..\\windows\\system32\\cmd.exe"), "cmd.exe"
        )
        self.assertEqual(attachment.sanitize_filename("C:\\temp\\report.txt"), "report.txt")
        self.assertEqual(attachment.sanitize_filename("bad\x00name\x01.txt"), "badname.txt")
        self.assertEqual(attachment.sanitize_filename("../"), "attachment")
        self.assertEqual(attachment.sanitize_filename("..."), "attachment")
        self.assertEqual(len(attachment.sanitize_filename("a" * 300)), 120)
        self.assertNotIn("/", attachment.sanitize_filename("a/b/c.txt"))
        self.assertNotIn("\\", attachment.sanitize_filename("a\\b\\c.txt"))

    def test_allowed_files_are_prepared_with_sniffed_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            prepared = attachment.prepare_attachments([
                write(root / "photo.png", PNG),
                write(root / "note.txt", TEXT),
                write(root / "archive.zip", b"PK\x03\x04" + b"z" * 32),
            ])
        self.assertEqual([item.filename for item in prepared], ["photo.png", "note.txt", "archive.zip"])
        self.assertEqual(
            [item.content_type for item in prepared],
            ["image/png", "text/plain", "application/zip"],
        )
        self.assertEqual([item.size for item in prepared], [len(PNG), len(TEXT), 36])
        self.assertEqual(prepared[0].data, PNG)

    def test_per_file_and_total_size_caps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            big = write(root / "big.txt", b"a" * 65)
            with self.assertRaises(attachment.AttachmentError):
                attachment.prepare_attachments([big], max_each=64)
            first = write(root / "one.txt", b"a" * 60)
            second = write(root / "two.txt", b"b" * 60)
            with self.assertRaises(attachment.AttachmentError):
                attachment.prepare_attachments([first, second], max_total=100, max_each=64)

    def test_executable_extensions_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for name, data in (
                ("payload.exe", b"MZ" + b"x" * 32),
                ("script.sh", TEXT),
                ("module.py", TEXT),
                ("loader.bin", TEXT),
            ):
                with self.subTest(name=name), self.assertRaises(attachment.AttachmentError):
                    attachment.prepare_attachments([write(root / name, data)])

    def test_magic_mismatch_and_unknown_extensions_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            disguised = write(root / "fake.png", TEXT)
            unknown = write(root / "mystery.unknownext", TEXT)
            for path in (disguised, unknown):
                with self.subTest(path=path), self.assertRaises(attachment.AttachmentError):
                    attachment.prepare_attachments([path])

    def test_allowlist_can_be_narrowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(pathlib.Path(tmp) / "photo.png", PNG)
            with self.assertRaises(attachment.AttachmentError):
                attachment.prepare_attachments([path], allowed_types={"text/plain"})
            self.assertEqual(
                len(attachment.prepare_attachments([path], allowed_types={"image/png"})), 1
            )

    def test_non_regular_and_missing_files_failed_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with self.assertRaises(attachment.AttachmentError):
                attachment.prepare_attachments([root])
            with self.assertRaises(attachment.AttachmentError):
                attachment.prepare_attachments([root / "missing.txt"])


class MimeMessageTests(unittest.TestCase):
    def test_build_mime_message_structure_and_base64(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            prepared = attachment.prepare_attachments([
                write(root / "photo.png", PNG),
                write(root / "note.txt", TEXT),
            ])
            message = attachment.build_mime_message("body text", prepared)
        self.assertTrue(message.is_multipart())
        parts = list(message.iter_attachments())
        self.assertEqual(len(parts), 2)
        for part, expected, name in zip(parts, (PNG, TEXT), ("photo.png", "note.txt")):
            self.assertEqual(part.get("Content-Transfer-Encoding"), "base64")
            self.assertTrue(part.get("Content-Disposition", "").startswith("attachment"))
            self.assertEqual(part.get_filename(), name)
            self.assertEqual(base64.b64decode(part.get_payload()), expected)

    def test_attach_to_message_preserves_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prepared = attachment.prepare_attachments([
                write(pathlib.Path(tmp) / "photo.png", PNG)
            ])
        message = build_message("a@example.org", ["b@example.org"], "subject", "body")
        attachment.attach_to_message(message, prepared)
        self.assertEqual(message["Subject"], "subject")
        self.assertEqual(len(list(message.iter_attachments())), 1)

    def test_plain_text_body_has_no_attachments(self) -> None:
        message = attachment.build_mime_message("body", [])
        self.assertFalse(message.is_multipart())
        self.assertEqual(message.get_content(), "body\n")


class IdleParsingTests(unittest.TestCase):
    def test_recognizes_unsolicited_events(self) -> None:
        events = imap_idle.parse_idle_unsolicited([
            b"* 5 EXISTS",
            b"* 2 RECENT\r\n",
            b"* 12 EXPUNGE",
            b"* OK still here",
            b"garbage",
            b"* 7 exists",
        ])
        self.assertEqual(events, [
            {"event": "EXISTS", "count": 5},
            {"event": "RECENT", "count": 2},
            {"event": "EXPUNGE", "seq": 12},
            {"event": "EXISTS", "count": 7},
        ])

    def test_accepts_strings_and_ignores_non_lines(self) -> None:
        self.assertEqual(
            imap_idle.parse_idle_unsolicited(["* 1 EXISTS", 42, None]),
            [{"event": "EXISTS", "count": 1}],
        )


class IdleSessionTests(unittest.TestCase):
    def test_select_idle_and_done(self) -> None:
        fake = FakeIdleConnection([b"* 3 EXISTS", b"* 1 RECENT"])
        session = imap_idle.IdleSession(fake, backoff_s=0)
        session.select("INBOX")
        events = session.idle(0.02)
        self.assertEqual(fake.selects, ["INBOX"])
        self.assertEqual(fake.idle_count, 1)
        self.assertEqual(fake.done_count, 1)
        self.assertEqual(events, [
            {"event": "EXISTS", "count": 3},
            {"event": "RECENT", "count": 1},
        ])

    def test_event_callback_receives_events(self) -> None:
        seen = []
        fake = FakeIdleConnection([b"* 9 EXISTS"])
        session = imap_idle.IdleSession(fake, backoff_s=0)
        session.select("INBOX")
        session.idle(0.02, on_event=seen.append)
        self.assertEqual(seen, [{"event": "EXISTS", "count": 9}])

    def test_cancel_stops_idle_early(self) -> None:
        fake = FakeIdleConnection()
        session = imap_idle.IdleSession(fake, backoff_s=0)
        fake.on_read = session.cancel
        session.select("INBOX")
        events = session.idle(5.0)
        self.assertEqual(events, [])
        self.assertTrue(session.cancelled)
        self.assertEqual(fake.done_count, 1)

    def test_idle_requires_select_and_bounds_timeout(self) -> None:
        session = imap_idle.IdleSession(FakeIdleConnection(), backoff_s=0)
        with self.assertRaises(imap_idle.IdleError):
            session.idle(0.01)
        session.select("INBOX")
        with self.assertRaises(imap_idle.IdleError):
            session.idle(0)
        with self.assertRaises(imap_idle.IdleError):
            session.idle(imap_idle.MAX_IDLE_SECONDS + 1)

    def test_reconnect_uses_backoff_and_bounded_attempts(self) -> None:
        sleeps: list[float] = []
        attempts: list[int] = []

        def factory():
            attempts.append(1)
            raise OSError("down")

        session = imap_idle.IdleSession(
            FakeIdleConnection(), connect_fn=factory, max_attempts=3,
            backoff_s=0.01, sleep_fn=sleeps.append,
        )
        with self.assertRaises(imap_idle.IdleError):
            session.reconnect()
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleeps, [0.01, 0.02])

    def test_idle_reconnects_then_succeeds(self) -> None:
        sleeps: list[float] = []
        attempts: list[int] = []
        good = FakeIdleConnection([b"* 4 EXISTS"])

        def factory():
            attempts.append(1)
            if len(attempts) < 3:
                raise OSError("not yet")
            return good

        session = imap_idle.IdleSession(
            FakeIdleConnection(fail_idle=True), connect_fn=factory,
            backoff_s=0, sleep_fn=sleeps.append,
        )
        session.select("INBOX")
        events = session.idle(0.02)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(events, [{"event": "EXISTS", "count": 4}])
        self.assertEqual(good.selects, ["INBOX"])

    def test_connection_error_without_factory_fails_closed(self) -> None:
        session = imap_idle.IdleSession(FakeIdleConnection(fail_idle=True), backoff_s=0)
        session.select("INBOX")
        with self.assertRaises(imap_idle.IdleError):
            session.idle(0.02)

    def test_close_terminates_and_closes(self) -> None:
        fake = FakeIdleConnection()
        session = imap_idle.IdleSession(fake, backoff_s=0)
        session.select("INBOX")
        session.idle(0.01)
        session.close()
        self.assertTrue(fake.closed)

    def test_connect_rejects_cleartext(self) -> None:
        account = type("A", (), {"imap_mode": "none"})()
        with self.assertRaises(imap_idle.IdleError):
            imap_idle.connect(account, "pw")


class StaticGuardsTests(unittest.TestCase):
    def test_new_modules_have_no_shell_or_plaintext_secrets(self) -> None:
        for name in ("attachment.py", "imap_idle.py"):
            text = (ROOT / "core" / "mail" / name).read_text(encoding="utf-8")
            with self.subTest(module=name):
                self.assertNotIn("shell=True", text)
                self.assertNotIn("os.system", text)
                self.assertNotIn("subprocess", text)

    def test_app_check_reports_policy_and_idle(self) -> None:
        script = ROOT / "apps" / "mail" / "aether-mail.py"
        result = subprocess.run(
            [sys.executable, str(script), "--check"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["idle_capable"])
        self.assertIn("allowed_types", payload["attachment_policy"])
        self.assertIn("blocked_executable_extensions", payload["attachment_policy"])
        self.assertEqual(payload["attachment_policy"]["max_each_bytes"], 10 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
