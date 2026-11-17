"""Tests for signed release verification and manifest-pinned upgrade planning.

Run with: python -m unittest discover -s aetheros/tests -p 'test_update_signature.py' -v
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core.update.apt_policy import parse_simulated_upgrade  # noqa: E402
from core.update.release import (  # noqa: E402
    ReleaseError,
    load_release,
    plan_upgrade,
    select_channel,
)
from core.update.signature import (  # noqa: E402
    MAX_MANIFEST_BYTES,
    SignatureError,
    sign_release,
    verify_release,
)


class UpdateSignatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.private = ed25519.Ed25519PrivateKey.generate()
        self.private_path = self.dir / "private.pem"
        self.public_path = self.dir / "public.pem"
        self.signature_path = self.dir / "release.sig"
        self.private_path.write_bytes(self.private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        self.public_path.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _payload(self, **overrides) -> dict:
        expires = (datetime.now(timezone.utc) + timedelta(days=1))
        expires = expires.isoformat().replace("+00:00", "Z")
        payload = {
            "schema": "aether-release/1",
            "channel": "stable",
            "expires": expires,
            "min_os_version": "1.0",
            "packages": {"foo": "2.0", "bar": "3.0"},
        }
        payload.update(overrides)
        return payload

    def _sign(self, payload: dict) -> bytes:
        signature = sign_release(payload, self.private_path)
        self.signature_path.write_bytes(signature)
        return signature

    def test_valid_signature_verifies(self) -> None:
        payload = self._payload()
        self._sign(payload)
        raw = json.dumps(payload).encode("utf-8")  # non-canonical spacing on purpose
        self.assertEqual(verify_release(raw, self.signature_path, self.public_path), payload)

    def test_tampered_payload_is_rejected(self) -> None:
        payload = self._payload()
        self._sign(payload)
        tampered = self._payload(packages={"foo": "9.9"})
        raw = json.dumps(tampered, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with self.assertRaises(SignatureError):
            verify_release(raw, self.signature_path, self.public_path)

    def test_tampered_signature_is_rejected(self) -> None:
        payload = self._payload()
        signature = bytearray(self._sign(payload))
        signature[0] ^= 0x01
        self.signature_path.write_bytes(bytes(signature))
        raw = json.dumps(payload).encode("utf-8")
        with self.assertRaises(SignatureError):
            verify_release(raw, self.signature_path, self.public_path)

    def test_expired_manifest_is_rejected(self) -> None:
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        payload = self._payload(expires=past)
        self._sign(payload)
        raw = json.dumps(payload).encode("utf-8")
        with self.assertRaises(SignatureError):
            verify_release(raw, self.signature_path, self.public_path)

    def test_oversized_manifest_is_rejected(self) -> None:
        with self.assertRaises(SignatureError):
            verify_release(b"x" * (MAX_MANIFEST_BYTES + 1),
                           self.signature_path, self.public_path)

    def test_unknown_schema_is_rejected(self) -> None:
        payload = self._payload(schema="aether-release/2")
        self._sign(payload)
        raw = json.dumps(payload).encode("utf-8")
        with self.assertRaises(SignatureError):
            verify_release(raw, self.signature_path, self.public_path)

    def test_missing_inputs_fail_closed(self) -> None:
        with self.assertRaises(SignatureError):
            verify_release(b"{}", self.dir / "absent.sig", self.public_path)

    def test_invalid_json_fails_closed(self) -> None:
        with self.assertRaises(SignatureError):
            verify_release(b"not json", self.signature_path, self.public_path)

    def test_signature_is_canonical_and_deterministic(self) -> None:
        payload = self._payload()
        reordered = dict(reversed(list(payload.items())))
        self.assertEqual(sign_release(payload, self.private_path),
                         sign_release(reordered, self.private_path))

    def test_plan_upgrade_keeps_only_pinned_versions(self) -> None:
        upgrades = [
            {"package": "foo", "current": "1.0", "candidate": "2.0", "origin": "Debian:13/stable"},
            {"package": "bar", "current": "2.9", "candidate": "3.1", "origin": "Debian:13/stable"},
            {"package": "evil", "current": "0.1", "candidate": "9.9", "origin": "unknown"},
        ]
        plan = plan_upgrade(self._payload(), upgrades)
        self.assertEqual([entry["package"] for entry in plan], ["foo"])
        self.assertEqual(plan[0]["version"], "2.0")
        self.assertEqual(plan[0]["current"], "1.0")


class ReleasePolicyTests(unittest.TestCase):
    def test_load_release_requires_packages(self) -> None:
        payload = {
            "schema": "aether-release/1", "channel": "stable",
            "expires": "2026-12-01T00:00:00Z", "min_os_version": "1.0",
        }
        with self.assertRaises(ReleaseError):
            load_release(payload)

    def test_channel_override_applies(self) -> None:
        payload = {
            "schema": "aether-release/1", "channel": "stable",
            "expires": "2026-12-01T00:00:00Z", "min_os_version": "1.0",
            "packages": {"foo": "2.0"},
            "channels": {"beta": {"packages": {"foo": "2.1~beta-1"}}},
        }
        view = select_channel(load_release(payload), "beta")
        self.assertEqual(view["packages"], {"foo": "2.1~beta-1"})
        with self.assertRaises(ReleaseError):
            select_channel(load_release(payload), "development")

    def test_parse_simulated_upgrade(self) -> None:
        text = (
            "Reading package lists...\n"
            "The following packages will be upgraded:\n  foo bar\n"
            "Inst foo [1.0] (2.0 Debian:13/stable [amd64])\n"
            "Inst bar [3.0] (3.1 Debian:13/stable [amd64])\n"
            "Conf foo (2.0)\n"
            "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"
        )
        upgrades, status = parse_simulated_upgrade(text)
        self.assertEqual(status, "ok")
        self.assertEqual([item["package"] for item in upgrades], ["foo", "bar"])
        self.assertEqual(upgrades[0]["current"], "1.0")
        self.assertEqual(upgrades[0]["candidate"], "2.0")
        self.assertEqual(upgrades[0]["origin"], "Debian:13/stable")
        self.assertEqual(parse_simulated_upgrade("garbage output"), ([], "unrecognized-output"))


if __name__ == "__main__":
    unittest.main()
