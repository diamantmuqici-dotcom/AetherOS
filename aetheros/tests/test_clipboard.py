"""Tests for headless clipboard auto-clear logic.

Run with:  python -m unittest discover -s aetheros/tests -p 'test_clipboard.py' -v
"""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core.vault import clipboard as clip  # noqa: E402


class TimeoutValidationTests(unittest.TestCase):
    def test_default_and_bounds(self) -> None:
        self.assertEqual(clip.DEFAULT_TIMEOUT_S, 30)
        self.assertEqual(clip.ClipboardTimer().timeout_s, 30)
        self.assertEqual(clip.ClipboardTimer(1).timeout_s, 1)
        self.assertEqual(clip.ClipboardTimer(300).timeout_s, 300)

    def test_invalid_timeout_rejected(self) -> None:
        for bad in (0, -1, 301, 1.5, "abc", None, ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                clip.validate_timeout(bad)
        with self.assertRaises(ValueError):
            clip.ClipboardTimer(0)
        with self.assertRaises(ValueError):
            clip.ClipboardTimer(301)

    def test_env_validation(self) -> None:
        self.assertEqual(clip.timeout_from_env({}), 30)
        self.assertEqual(clip.timeout_from_env({clip.TIMEOUT_ENV: "45"}), 45)
        self.assertEqual(clip.timeout_from_env({clip.TIMEOUT_ENV: "nope"}), 30)
        self.assertEqual(clip.timeout_from_env({clip.TIMEOUT_ENV: "900"}), 30)


class ExpiryTests(unittest.TestCase):
    def test_before_at_after_deadline(self) -> None:
        timer = clip.ClipboardTimer(10)
        token = timer.arm(100.0, "fingerprint")
        self.assertTrue(timer.clear_armed)
        self.assertEqual(timer.expiry_at, 110.0)
        self.assertEqual(timer.expires_at, 110.0)
        self.assertFalse(timer.should_clear(109.999, token))
        self.assertFalse(timer.is_expired(109.999))
        self.assertTrue(timer.is_expired(110.0))
        self.assertTrue(timer.should_clear(110.0, token))
        self.assertTrue(timer.should_clear(500.0, token))

    def test_wrong_token_never_clears(self) -> None:
        timer = clip.ClipboardTimer(5)
        timer.arm(0.0, "fp")
        self.assertFalse(timer.should_clear(100.0, 999))

    def test_plan_clear_has_no_plaintext(self) -> None:
        timer = clip.ClipboardTimer(20)
        token = timer.arm(1.0, "abc123")
        state = timer.plan_clear("abc123", 20)
        self.assertEqual(state["next_owner"], token + 1)
        self.assertEqual(state["fingerprint"], "abc123")
        self.assertEqual(state["timeout_s"], 20)
        self.assertTrue(state["armed"])
        with self.assertRaises(ValueError):
            timer.plan_clear("abc123", 0)


class RedactionTests(unittest.TestCase):
    def test_fingerprint_shape_and_stability(self) -> None:
        raw = b"correct horse battery staple"
        fp = clip.redact_fingerprint(raw)
        self.assertEqual(len(fp), clip.FINGERPRINT_BYTES * 2)
        self.assertEqual(fp, clip.redact_fingerprint(raw))
        self.assertEqual(fp, clip.redact_fingerprint(raw.decode()))
        self.assertNotEqual(fp, clip.redact_fingerprint(raw + b"x"))

    def test_redact_never_contains_secret(self) -> None:
        secret = "Tr0ub4dor&3-PASSPHRASE-xyzzy"
        fp = clip.redact_fingerprint(secret)
        self.assertNotIn(secret, fp)
        self.assertNotIn(secret[:8], fp)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))


class BackendTests(unittest.TestCase):
    def test_null_backend_roundtrip(self) -> None:
        backend = clip.NullBackend()
        self.assertIsNone(backend.get_text())
        backend.set_text("secret")
        self.assertEqual(backend.get_text(), "secret")
        backend.claim(7)
        self.assertEqual(backend.owner_token(), 7)
        backend.clear()
        self.assertIsNone(backend.get_text())
        self.assertIsNone(backend.owner_token())

    def test_clear_called_exactly_once(self) -> None:
        backend = clip.NullBackend()
        timer = clip.ClipboardTimer(10)
        token = clip.arm_secret(backend, "secret", timer, 0.0)
        self.assertTrue(clip.schedule_clear(backend, timer, token, 5.0))
        self.assertEqual(backend.clear_calls, 0)
        self.assertFalse(clip.schedule_clear(backend, timer, token, 10.0))
        self.assertEqual(backend.clear_calls, 1)
        self.assertFalse(clip.schedule_clear(backend, timer, token, 20.0))
        self.assertEqual(backend.clear_calls, 1)

    def test_rearm_cancels_prior_owner(self) -> None:
        backend = clip.NullBackend()
        timer = clip.ClipboardTimer(10)
        old = clip.arm_secret(backend, "first", timer, 0.0)
        new = clip.arm_secret(backend, "second", timer, 1.0)
        self.assertNotEqual(old, new)
        self.assertEqual(backend.owner_token(), new)
        self.assertFalse(clip.schedule_clear(backend, timer, old, 100.0))
        self.assertEqual(backend.clear_calls, 0)
        self.assertEqual(backend.get_text(), "second")
        self.assertFalse(clip.schedule_clear(backend, timer, new, 100.0))
        self.assertEqual(backend.clear_calls, 1)

    def test_arm_secret_does_not_persist_plaintext(self) -> None:
        secret = "never-write-me-plaintext-9999"
        backend = clip.NullBackend()
        timer = clip.ClipboardTimer(15)
        with mock.patch("builtins.open", side_effect=AssertionError("file write")), mock.patch.object(
            pathlib.Path, "write_bytes", side_effect=AssertionError("write_bytes")
        ), mock.patch.object(
            pathlib.Path, "write_text", side_effect=AssertionError("write_text")
        ):
            token = clip.arm_secret(backend, secret, timer, 0.0)
        self.assertEqual(backend.get_text(), secret)
        self.assertNotIn(secret, timer.fingerprint)
        self.assertNotIn(secret, repr(timer.plan_clear(timer.fingerprint, 15)))
        self.assertEqual(backend.owner_token(), token)


if __name__ == "__main__":
    unittest.main()
