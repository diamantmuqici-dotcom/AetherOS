"""Tests for reproducible release metadata and the release key scaffolding.

Run with: python -m unittest discover -s aetheros/tests -p 'test_release_metadata.py' -v
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.update.signature import canonical_signing_input  # noqa: E402

_SCRIPT = ROOT / "scripts" / "signing" / "make-release-metadata.py"
_SPEC = importlib.util.spec_from_file_location("aether_release_metadata", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
metadata_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(metadata_mod)


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.iso = self.dir / "aetheros-live.iso"
        self.iso.write_bytes(b"aether-iso-bytes" * 4096)
        self.key = Ed25519PrivateKey.generate()
        self.private = self.dir / "private.pem"
        self.public = self.dir / "public.pem"
        self.private.write_bytes(self.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        self.public.write_bytes(self.key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        self.timestamp = "2026-01-02T03:04:05Z"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build(self, key=None, timestamp=None) -> dict:
        return metadata_mod.build_metadata(
            self.iso,
            timestamp=timestamp or self.timestamp,
            key=key,
        )

    def test_canonical_determinism(self) -> None:
        first = self._build()
        second = self._build()
        self.assertEqual(canonical_signing_input(first), canonical_signing_input(second))
        reordered = dict(reversed(list(first.items())))
        self.assertEqual(canonical_signing_input(first), canonical_signing_input(reordered))
        out_a, _ = metadata_mod.write_outputs(self.dir / "out-a", first)
        out_b, _ = metadata_mod.write_outputs(self.dir / "out-b", second)
        self.assertEqual(out_a.read_bytes(), out_b.read_bytes())

    def test_timestamp_from_source_date_epoch(self) -> None:
        previous = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = "1767323045"
        try:
            self.assertEqual(metadata_mod.resolve_timestamp(None), "2026-01-02T03:04:05Z")
        finally:
            if previous is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = previous

    def test_signature_valid_and_tampered_detection(self) -> None:
        payload = self._build(key=self.private)
        self.assertEqual(payload["status"], "signed")
        self.assertTrue(metadata_mod.verify_metadata(payload, self.public))
        tampered = json.loads(json.dumps(payload))
        tampered["iso"]["sha256"] = "0" * 64
        self.assertFalse(metadata_mod.verify_metadata(tampered, self.public))
        bad_sig = json.loads(json.dumps(payload))
        raw = bytearray(base64.b64decode(bad_sig["signature"]))
        raw[0] ^= 0x01
        bad_sig["signature"] = base64.b64encode(bytes(raw)).decode("ascii")
        self.assertFalse(metadata_mod.verify_metadata(bad_sig, self.public))

    def test_unsigned_status_fails_closed(self) -> None:
        payload = self._build()
        self.assertEqual(payload["status"], "unsigned")
        self.assertIsNone(payload["signature"])
        self.assertFalse(metadata_mod.verify_metadata(payload, self.public))
        forged = dict(payload, signature=base64.b64encode(b"\x00" * 64).decode("ascii"))
        self.assertFalse(metadata_mod.verify_metadata(forged, self.public))

    def test_checksums_correct(self) -> None:
        meta_path, sums_path = metadata_mod.write_outputs(self.dir / "out", self._build())
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        digest, name = sums_path.read_text(encoding="utf-8").strip().split("  ", 1)
        expected = hashlib.sha256(self.iso.read_bytes()).hexdigest()
        self.assertEqual(name, self.iso.name)
        self.assertEqual(digest, expected)
        self.assertEqual(meta["iso"]["sha256"], expected)
        self.assertEqual(meta["iso"]["size"], self.iso.stat().st_size)

    def test_cli_help_and_no_args(self) -> None:
        help_out = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(help_out):
            metadata_mod.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("--iso", help_out.getvalue())

        err_out = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(err_out):
            metadata_mod.main([])
        self.assertNotEqual(ctx.exception.code, 0)
        self.assertIn("usage", err_out.getvalue().lower())

    def test_cli_unsigned_and_signed_runs(self) -> None:
        unsigned_dir = self.dir / "cli-unsigned"
        with redirect_stdout(io.StringIO()):
            rc = metadata_mod.main(["--iso", str(self.iso), "--out", str(unsigned_dir)])
        self.assertEqual(rc, 0)
        unsigned = json.loads((unsigned_dir / "release-metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(unsigned["status"], "unsigned")
        self.assertTrue((unsigned_dir / "SHA256SUMS").is_file())

        signed_dir = self.dir / "cli-signed"
        args = ["--iso", str(self.iso), "--out", str(signed_dir),
                "--key", str(self.private), "--timestamp", self.timestamp]
        with redirect_stdout(io.StringIO()):
            rc = metadata_mod.main(args)
        self.assertEqual(rc, 0)
        signed = json.loads((signed_dir / "release-metadata.json").read_text(encoding="utf-8"))
        self.assertTrue(metadata_mod.verify_metadata(signed, self.public))


class KeygenScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        script = ROOT / "scripts" / "signing" / "generate-release-key.sh"
        cls.text = script.read_text(encoding="utf-8")

    def test_private_key_mode_0600_and_public_0644(self) -> None:
        self.assertIn("chmod 600", self.text)
        self.assertIn("chmod 644", self.text)

    def test_no_overwrite_without_force(self) -> None:
        self.assertIn("--force", self.text)
        self.assertIn("refusing to overwrite", self.text)

    def test_no_key_bytes_printed(self) -> None:
        for forbidden in ('cat "$PRIV"', 'cat "$TMP_PRIV"', "-text", "openssl rand", "printenv"):
            self.assertNotIn(forbidden, self.text)
        self.assertIn("printf 'SHA256:%s\\n'", self.text)

    def test_default_dir_outside_repo(self) -> None:
        self.assertIn("AETHER_KEY_DIR", self.text)
        self.assertIn("$HOME/.config/aether/release-keys", self.text)
        self.assertIn("refusing to write inside the repository", self.text)

    def test_bounded_no_shell_scripts(self) -> None:
        self.assertNotIn("eval", self.text)
        self.assertIn("genpkey -algorithm ED25519", self.text)
        self.assertIn("cmp -s", self.text)
        self.assertIn("command -v openssl", self.text)


if __name__ == "__main__":
    unittest.main()
