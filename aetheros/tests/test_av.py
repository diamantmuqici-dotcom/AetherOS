"""Tests for the signature-gated Aether Antivirus front-ends.

Run with: python -m unittest discover -s aetheros/tests -p 'test_av.py' -v
Network downloads are mocked; no live requests are made.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.update.signature import SignatureError, sign_release  # noqa: E402

APP = REPO / "apps" / "antivirus" / "aether-av.py"
LIGHT = REPO / "apps" / "antivirus" / "aether-av-light.py"
MIRROR = (
    REPO / "iso" / "config" / "includes.chroot" / "usr" / "share"
    / "aether" / "apps" / "aether-av.py"
)
LAUNCHER = (
    REPO / "iso" / "config" / "includes.chroot" / "usr" / "local"
    / "bin" / "aether-av"
)
DESKTOP = (
    REPO / "iso" / "config" / "includes.chroot" / "usr" / "share"
    / "applications" / "org.aether.Antivirus.desktop"
)


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


av = _load(APP, "aether_av_test")
light = _load(LIGHT, "aether_av_light_test")


class AvVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.private = ed25519.Ed25519PrivateKey.generate()
        self.private_path = self.dir / "private.pem"
        self.public_path = self.dir / "public.pem"
        self.defs_path = self.dir / "definitions.json"
        self.sig_path = self.dir / "definitions.sig"
        self.state_path = self.dir / "state.json"
        self.qdir = self.dir / "quarantine"
        self.private_path.write_bytes(self.private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        self.public_path.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        self.env = patch.dict(os.environ, {
            "AETHER_AV_PUBLIC_KEY": str(self.public_path),
            "AETHER_AV_DEFS": str(self.defs_path),
            "AETHER_AV_SIGNATURE": str(self.sig_path),
            "AETHER_AV_STATE": str(self.state_path),
            "AETHER_AV_QUARANTINE": str(self.qdir),
        })
        self.env.start()
        self._write_defs(self._payload())

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def _payload(self, **overrides) -> dict:
        generated = (datetime.now(timezone.utc) - timedelta(hours=1))
        expires = (datetime.now(timezone.utc) + timedelta(days=7))
        payload = {
            "schema": av.SCHEMA,
            "generated_utc": generated.isoformat().replace("+00:00", "Z"),
            "expires_utc": expires.isoformat().replace("+00:00", "Z"),
            "hashes": [
                {"sha256": "a" * 64, "name": "known-a"},
                {"sha256": "b" * 64, "name": "known-b"},
            ],
        }
        payload.update(overrides)
        return payload

    def _write_defs(self, payload: dict) -> None:
        signature = sign_release(payload, self.private_path)
        self.defs_path.write_bytes(json.dumps(payload).encode("utf-8"))
        self.sig_path.write_bytes(signature)

    def test_valid_definitions_verify(self) -> None:
        state, record, error = av.signature_status()
        self.assertEqual("VALID", state)
        self.assertIsNone(error)
        self.assertEqual(2, record["hash_count"])
        self.assertIn("b" * 64, record["hashes"])

    def test_tampered_definitions_rejected_and_not_acted_on(self) -> None:
        payload = self._payload()
        self._write_defs(payload)
        payload["hashes"][0]["sha256"] = "c" * 64
        self.defs_path.write_bytes(json.dumps(payload).encode("utf-8"))
        state, record, _error = av.signature_status()
        self.assertEqual("SIGNATURE_INVALID", state)
        self.assertIsNone(record)
        target = self.dir / "victim.bin"
        target.write_bytes(b"keep me")
        summary = av.scan([str(self.dir)])
        self.assertEqual("SIGNATURE_INVALID", summary["signature"])
        self.assertEqual([], summary["quarantined"])
        self.assertTrue(target.exists())

    def test_expired_definitions_rejected(self) -> None:
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self._write_defs(self._payload(expires_utc=past))
        state, _record, _error = av.signature_status()
        self.assertEqual("SIGNATURE_INVALID", state)

    def test_unknown_schema_rejected(self) -> None:
        self._write_defs(self._payload(schema="aether-av-sigs/2"))
        state, _record, _error = av.signature_status()
        self.assertEqual("SIGNATURE_INVALID", state)

    def test_tampered_signature_rejected(self) -> None:
        self._write_defs(self._payload())
        sig = bytearray(self.sig_path.read_bytes())
        sig[0] ^= 0x01
        self.sig_path.write_bytes(bytes(sig))
        state, _record, _error = av.signature_status()
        self.assertEqual("SIGNATURE_INVALID", state)

    def test_missing_key_fails_closed(self) -> None:
        os.environ["AETHER_AV_PUBLIC_KEY"] = str(self.dir / "absent.pem")
        state, record, error = av.signature_status()
        self.assertEqual("SIGNATURE_MISSING", state)
        self.assertIsNone(record)
        self.assertIn("public_key", error)
        target = self.dir / "victim.bin"
        target.write_bytes(b"keep me")
        summary = av.scan([str(self.dir)])
        self.assertEqual("SIGNATURE_MISSING", summary["signature"])
        self.assertTrue(target.exists())
        self.assertEqual([], summary["quarantined"])
        with patch.object(av, "_open_url") as mocked:
            update = av.update_definitions()
            mocked.assert_not_called()
        self.assertEqual("SIGNATURE_MISSING", update["signature"])
        self.assertFalse(update["ok"])

    def test_missing_definition_inputs_fail_closed(self) -> None:
        self.defs_path.unlink()
        state, _record, _error = av.signature_status()
        self.assertEqual("SIGNATURE_MISSING", state)
        with patch.object(av, "_open_url", side_effect=OSError("offline")) as mocked:
            result = av.update_definitions()
            mocked.assert_called()
        self.assertEqual("SIGNATURE_INVALID", result["signature"])
        self.assertFalse(result["ok"])
        self.assertFalse(self.defs_path.exists())

    def test_invalid_public_key_rejected(self) -> None:
        self.public_path.write_bytes(b"not a pem file")
        state, _record, _error = av.signature_status()
        self.assertEqual("SIGNATURE_INVALID", state)

    def test_oversized_definition_bytes_rejected(self) -> None:
        with self.assertRaises(SignatureError):
            av.verify_definitions(
                b"x" * (av.MAX_DEFS_BYTES + 1), b"\x00" * 64, self.public_path
            )

    def test_pure_parse_helpers(self) -> None:
        self.assertTrue(av._valid_sha256("a" * 64))
        self.assertFalse(av._valid_sha256("A" * 64))
        self.assertFalse(av._valid_sha256("z" * 64))
        self.assertFalse(av._valid_sha256("a" * 63))
        moment = av._parse_iso_utc("2026-11-17T00:00:00Z", "expires_utc")
        self.assertEqual(timezone.utc, moment.tzinfo)
        with self.assertRaises(SignatureError):
            av._parse_iso_utc("2026-11-17T00:00:00", "expires_utc")
        payload = self._payload(hashes=[
            {"sha256": "a" * 64, "name": "first"},
            {"sha256": "a" * 64, "name": "second"},
        ])
        record = av.parse_definitions(payload)
        self.assertEqual(1, record["hash_count"])
        self.assertEqual("first", record["hashes"]["a" * 64])


class AvScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.private = ed25519.Ed25519PrivateKey.generate()
        self.private_path = self.dir / "private.pem"
        self.public_path = self.dir / "public.pem"
        self.defs_path = self.dir / "definitions.json"
        self.sig_path = self.dir / "definitions.sig"
        self.state_path = self.dir / "state.json"
        self.qdir = self.dir / "quarantine"
        self.private_path.write_bytes(self.private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        self.public_path.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        self.env = patch.dict(os.environ, {
            "AETHER_AV_PUBLIC_KEY": str(self.public_path),
            "AETHER_AV_DEFS": str(self.defs_path),
            "AETHER_AV_SIGNATURE": str(self.sig_path),
            "AETHER_AV_STATE": str(self.state_path),
            "AETHER_AV_QUARANTINE": str(self.qdir),
        })
        self.env.start()
        self.content = b"quarantine this test payload" * 4
        self.digest = hashlib.sha256(self.content).hexdigest()
        self._write_defs([{"sha256": self.digest, "name": "test-bad"}])
        self.target = self.dir / "bad.bin"
        self.target.write_bytes(self.content)

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def _write_defs(self, hashes: list[dict], **overrides) -> None:
        generated = (datetime.now(timezone.utc) - timedelta(hours=1))
        expires = (datetime.now(timezone.utc) + timedelta(days=7))
        payload = {
            "schema": av.SCHEMA,
            "generated_utc": generated.isoformat().replace("+00:00", "Z"),
            "expires_utc": expires.isoformat().replace("+00:00", "Z"),
            "hashes": hashes,
        }
        payload.update(overrides)
        signature = sign_release(payload, self.private_path)
        self.defs_path.write_bytes(json.dumps(payload).encode("utf-8"))
        self.sig_path.write_bytes(signature)

    def test_quarantine_copies_before_deleting_original(self) -> None:
        summary = av.scan([str(self.dir)])
        self.assertEqual("VALID", summary["signature"])
        self.assertEqual(1, summary["matched"])
        self.assertIn(str(self.target), summary["quarantined"])
        self.assertFalse(self.target.exists())
        copies = list(self.qdir.iterdir())
        self.assertEqual(1, len(copies))
        self.assertEqual(self.digest, hashlib.sha256(copies[0].read_bytes()).hexdigest())

    def test_failed_copy_leaves_original_in_place(self) -> None:
        blocked = self.qdir / f"{self.digest[:16]}_bad.bin"
        blocked.mkdir(parents=True, exist_ok=True)
        summary = av.scan([str(self.dir)])
        self.assertNotIn(str(self.target), summary["quarantined"])
        self.assertTrue(self.target.exists())

    def test_symlinks_not_followed_or_quarantined(self) -> None:
        link = self.dir / "link.bin"
        try:
            link.symlink_to(self.target)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        summary = av.scan([str(self.dir)])
        self.assertTrue(link.is_symlink())
        self.assertNotIn(str(link), summary["quarantined"])
        self.assertFalse(self.target.exists())

    def test_state_file_records_last_scan(self) -> None:
        av.scan([str(self.dir)])
        report = av.check()
        self.assertEqual("VALID", report["signature"])
        self.assertEqual("VALID", report["last_scan"]["signature"])
        self.assertEqual(1, report["last_scan"]["matched"])


class AvNetworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.private = ed25519.Ed25519PrivateKey.generate()
        self.private_path = self.dir / "private.pem"
        self.public_path = self.dir / "public.pem"
        self.defs_path = self.dir / "definitions.json"
        self.sig_path = self.dir / "definitions.sig"
        self.state_path = self.dir / "state.json"
        self.qdir = self.dir / "quarantine"
        self.private_path.write_bytes(self.private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        self.public_path.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        self.env = patch.dict(os.environ, {
            "AETHER_AV_PUBLIC_KEY": str(self.public_path),
            "AETHER_AV_DEFS": str(self.defs_path),
            "AETHER_AV_SIGNATURE": str(self.sig_path),
            "AETHER_AV_STATE": str(self.state_path),
            "AETHER_AV_QUARANTINE": str(self.qdir),
        })
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def _payload(self) -> dict:
        return {
            "schema": av.SCHEMA,
            "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "expires_utc": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "hashes": [{"sha256": "a" * 64, "name": "network-bad"}],
        }

    def test_update_writes_only_after_verification(self) -> None:
        payload = self._payload()
        raw = json.dumps(payload).encode("utf-8")
        sig = sign_release(payload, self.private_path)

        def fake_open(url, timeout):
            self.assertEqual(10, timeout)
            return io.BytesIO(raw if url == av.DEFS_URL else sig)

        with patch.object(av, "_open_url", side_effect=fake_open):
            result = av.update_definitions()
        self.assertTrue(result["ok"])
        self.assertEqual("VALID", result["signature"])
        self.assertEqual(1, result["hash_count"])
        self.assertEqual(raw, self.defs_path.read_bytes())
        self.assertEqual(sig, self.sig_path.read_bytes())

    def test_unsigned_download_never_replaces_definitions(self) -> None:
        raw = json.dumps(self._payload()).encode("utf-8")
        self.defs_path.write_bytes(b"previous-good-definitions")
        self.sig_path.write_bytes(b"x" * 64)

        def fake_open(url, timeout):
            return io.BytesIO(raw if url == av.DEFS_URL else b"")

        with patch.object(av, "_open_url", side_effect=fake_open):
            result = av.update_definitions()
        self.assertFalse(result["ok"])
        self.assertEqual("SIGNATURE_INVALID", result["signature"])
        self.assertEqual(b"previous-good-definitions", self.defs_path.read_bytes())

    def test_oversized_download_guard(self) -> None:
        def fake_open(url, timeout):
            return io.BytesIO(b"x" * (av.MAX_DEFS_BYTES + 1))

        with patch.object(av, "_open_url", side_effect=fake_open):
            with self.assertRaises(SignatureError):
                av.download_bounded(av.DEFS_URL)
        with patch.object(av, "_open_url", side_effect=fake_open):
            result = av.update_definitions()
        self.assertFalse(result["ok"])
        self.assertEqual("SIGNATURE_INVALID", result["signature"])
        self.assertFalse(self.defs_path.exists())

    def test_non_https_download_rejected_before_open(self) -> None:
        with patch.object(av, "_open_url") as mocked:
            with self.assertRaises(SignatureError):
                av.download_bounded("http://example.test/aether-av-sigs.json")
            mocked.assert_not_called()

    def test_content_length_cap_rejects_early(self) -> None:
        class Response(io.BytesIO):
            headers = {"Content-Length": str(av.MAX_DEFS_BYTES + 1)}

        with patch.object(av, "_open_url", return_value=Response(b"short")):
            with self.assertRaises(SignatureError):
                av.download_bounded(av.DEFS_URL)


class AvInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.private = ed25519.Ed25519PrivateKey.generate()
        self.private_path = self.dir / "private.pem"
        self.public_path = self.dir / "public.pem"
        self.defs_path = self.dir / "definitions.json"
        self.sig_path = self.dir / "definitions.sig"
        self.state_path = self.dir / "state.json"
        self.qdir = self.dir / "quarantine"
        self.private_path.write_bytes(self.private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        self.public_path.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        self.env = patch.dict(os.environ, {
            "AETHER_AV_PUBLIC_KEY": str(self.public_path),
            "AETHER_AV_DEFS": str(self.defs_path),
            "AETHER_AV_SIGNATURE": str(self.sig_path),
            "AETHER_AV_STATE": str(self.state_path),
            "AETHER_AV_QUARANTINE": str(self.qdir),
        })
        self.env.start()
        payload = {
            "schema": av.SCHEMA,
            "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "expires_utc": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "hashes": [],
        }
        signature = sign_release(payload, self.private_path)
        self.defs_path.write_bytes(json.dumps(payload).encode("utf-8"))
        self.sig_path.write_bytes(signature)

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_check_json_shape_and_sorted_keys(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = av.main(["--check"])
        text = output.getvalue()
        report = json.loads(text)
        self.assertEqual(0, code)
        self.assertEqual(json.dumps(report, sort_keys=True) + "\n", text)
        for key in (
            "version", "signature", "generated_utc", "expires_utc",
            "age_seconds", "hash_count", "definitions_path", "public_key_path",
            "quarantine_dir", "last_scan", "error",
        ):
            self.assertIn(key, report)
        self.assertEqual("VALID", report["signature"])
        self.assertEqual(str(self.qdir), report["quarantine_dir"])

    def test_version_mode_headless(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = av.main(["--version"])
        self.assertEqual(0, code)
        self.assertEqual(av.VERSION, output.getvalue().strip())

    def test_light_cli_verify_file(self) -> None:
        self.assertNotIn("import gi", LIGHT.read_text(encoding="utf-8"))
        target = self.dir / "sample.bin"
        target.write_bytes(b"sample")
        digest = hashlib.sha256(b"sample").hexdigest()
        payload = {
            "schema": av.SCHEMA,
            "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "expires_utc": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "hashes": [{"sha256": digest, "name": "sample-bad"}],
        }
        signature = sign_release(payload, self.private_path)
        self.defs_path.write_bytes(json.dumps(payload).encode("utf-8"))
        self.sig_path.write_bytes(signature)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = light.main(["--verify-file", str(target)])
        result = json.loads(output.getvalue())
        self.assertEqual(0, code)
        self.assertEqual("VALID", result["signature"])
        self.assertTrue(result["in_definitions"])
        self.assertEqual("sample-bad", result["name"])

    def test_mirror_and_install_assets(self) -> None:
        self.assertEqual(APP.read_bytes(), MIRROR.read_bytes())
        launcher = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('exec python3 /usr/share/aether/apps/aether-av.py "$@"', launcher)
        desktop = DESKTOP.read_text(encoding="utf-8")
        for expected in (
            "[Desktop Entry]", "Name=Aether Antivirus", "Exec=aether-av",
            "Terminal=false", "Categories=System;Security;",
        ):
            self.assertIn(expected, desktop)


if __name__ == "__main__":
    unittest.main()
