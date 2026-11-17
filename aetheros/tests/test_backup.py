"""Tests for backup manifests, non-destructive restore and the headless CLI.

Run with: python -m unittest discover -s aetheros/tests -p 'test_backup.py' -v
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

AETHEROS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AETHEROS))

from core.backup.manifest import (  # noqa: E402
    MANIFEST_NAME,
    ManifestError,
    build_manifest,
    load_manifest,
    normalize_rel,
    save_manifest,
    sha256_file,
    verify_manifest,
)
from core.backup.restore import RestoreError, execute_plan, plan_restore  # noqa: E402

APP_PATH = AETHEROS / "apps" / "backup" / "aether-backup.py"


def _load_app_module():
    spec = importlib.util.spec_from_file_location("aether_backup_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.src = self.dir / "source"
        self.base = self.dir / "Backups"
        (self.src / "sub").mkdir(parents=True)
        (self.base).mkdir()
        self.files = {
            "a.txt": b"alpha\n",
            "b.bin": bytes(range(256)) * 4,
            "sub/c.txt": b"gamma\n",
        }
        for rel, payload in self.files.items():
            target = self.src / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

        self.private = ed25519.Ed25519PrivateKey.generate()
        self.private_path = self.dir / "signing.pem"
        self.public_path = self.dir / "public.pem"
        self.private_path.write_bytes(self.private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        self.public_path.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        self.app = _load_app_module()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _rels(self, root=None):
        root = root or self.src
        return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]

    def _manifest(self):
        return build_manifest(self.src, self._rels())

    # --- manifest ---------------------------------------------------------

    def test_manifest_roundtrip(self) -> None:
        manifest = self._manifest()
        path = self.dir / MANIFEST_NAME
        saved = save_manifest(path, manifest, private_key_path=self.private_path)
        self.assertEqual(saved["schema"], "aether-backup/1")
        self.assertEqual(saved["count"], 3)
        self.assertIsInstance(saved["signature"], dict)
        loaded = load_manifest(path, public_key_path=self.public_path)
        self.assertEqual(loaded["entries"], manifest["entries"])
        self.assertEqual(loaded["total_bytes"], manifest["total_bytes"])

    def test_tampered_file_detected(self) -> None:
        manifest = self._manifest()
        (self.src / "a.txt").write_bytes(b"ALPHA\n")
        ok, problems = verify_manifest(self.src, manifest)
        self.assertFalse(ok)
        self.assertTrue(any("sha256 mismatch: a.txt" in item for item in problems))

    def test_tampered_manifest_detected(self) -> None:
        manifest = self._manifest()
        path = self.dir / MANIFEST_NAME
        saved = save_manifest(path, manifest, private_key_path=self.private_path)
        self.assertTrue(load_manifest(path, public_key_path=self.public_path)["entries"])

        tampered = dict(saved)
        tampered["entries"] = [dict(entry) for entry in saved["entries"]]
        tampered["entries"][0]["sha256"] = "0" * 64
        ok, problems = verify_manifest(self.src, tampered)
        self.assertFalse(ok)
        self.assertTrue(any("digest mismatch" in item for item in problems))

        forged_path = self.dir / "forged.json"
        save_manifest(forged_path, tampered)
        with self.assertRaises(ManifestError):
            load_manifest(forged_path, public_key_path=self.public_path)

    def test_missing_and_extra_file_detected(self) -> None:
        manifest = self._manifest()
        (self.src / "b.bin").unlink()
        (self.src / "extra.txt").write_bytes(b"surprise")
        ok, problems = verify_manifest(self.src, manifest)
        self.assertFalse(ok)
        self.assertTrue(any("missing file: b.bin" in item for item in problems))
        self.assertTrue(any("extra file: extra.txt" in item for item in problems))

    def test_traversal_normalization_rejected(self) -> None:
        for value in ("../evil", "/etc/passwd", "sub/../../x", "a\\b", ""):
            with self.subTest(value=value), self.assertRaises(ManifestError):
                normalize_rel(value)

    def test_chunked_hash_matches_reference(self) -> None:
        import hashlib
        expected = hashlib.sha256(self.files["b.bin"]).hexdigest()
        self.assertEqual(sha256_file(self.src / "b.bin"), expected)

    # --- restore ----------------------------------------------------------

    def test_restore_plan_is_argv_list(self) -> None:
        target = self.dir / "restore"
        manifest = self._manifest()
        plan = plan_restore(self.src, target, manifest)
        self.assertIsInstance(plan, list)
        self.assertEqual(len(plan), 3)
        for operation in plan:
            self.assertIsInstance(operation, list)
            self.assertEqual(len(operation), 4)
            self.assertTrue(all(isinstance(part, str) for part in operation))
            self.assertEqual(operation[0], "copy2")
        joined = " ".join(part for operation in plan for part in operation)
        self.assertNotIn(";", joined)
        self.assertNotIn("shell", joined)

    def test_path_traversal_rejected_in_manifest(self) -> None:
        manifest = self._manifest()
        manifest["entries"].append({
            "path": "../escape.txt", "size": 1, "sha256": "0" * 64,
            "mtime": 0, "type": "file",
        })
        with self.assertRaises(ManifestError):
            plan_restore(self.src, self.dir / "restore", manifest)

    def test_containment_enforced_at_execution(self) -> None:
        target = self.dir / "restore"
        plan = plan_restore(self.src, target, self._manifest())
        plan[0][2] = str(self.dir / "outside" / "escape.txt")
        with self.assertRaises(RestoreError):
            execute_plan(plan, self.src, target, dry_run=False)

    def test_copy_verified_and_dryrun_default(self) -> None:
        target = self.dir / "restore"
        manifest = self._manifest()
        plan = plan_restore(self.src, target, manifest)
        report = execute_plan(plan, self.src, target)
        self.assertTrue(report["dry_run"])
        self.assertFalse((target / "a.txt").exists())

        report = execute_plan(plan, self.src, target, dry_run=False)
        self.assertEqual(report["verified"], 3)
        self.assertEqual((target / "a.txt").read_bytes(), self.files["a.txt"])
        self.assertEqual((target / "sub" / "c.txt").read_bytes(), self.files["sub/c.txt"])

    def test_source_hash_mismatch_rejected(self) -> None:
        target = self.dir / "restore"
        plan = plan_restore(self.src, target, self._manifest())
        plan[0][3] = "f" * 64
        with self.assertRaises(RestoreError):
            execute_plan(plan, self.src, target, dry_run=False)

    def test_overwrite_requires_explicit_flag(self) -> None:
        target = self.dir / "restore"
        target.mkdir()
        (target / "a.txt").write_bytes(b"old")
        manifest = self._manifest()
        with self.assertRaises(RestoreError):
            plan_restore(self.src, target, manifest)
        plan = plan_restore(self.src, target, manifest, overwrite=True)
        report = execute_plan(plan, self.src, target, dry_run=False, overwrite=True)
        self.assertEqual(report["verified"], 3)
        self.assertEqual((target / "a.txt").read_bytes(), self.files["a.txt"])

    # --- headless CLI -----------------------------------------------------

    def test_check_json_shape(self) -> None:
        env = {
            "AETHER_BACKUP_SOURCE": str(self.src),
            "AETHER_BACKUP_ROOT": str(self.base),
            "AETHER_BACKUP_SIGNING_KEY": str(self.private_path),
            "AETHER_BACKUP_PUBLIC_KEY": str(self.public_path),
        }
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(buffer):
            code = self.app.main(["--check"])
        self.assertEqual(code, 0)
        report = json.loads(buffer.getvalue())
        for key in ("rsync", "source", "backup_root", "signing_key", "public_key",
                    "last_snapshot", "manifest", "entries", "discrepancies", "error"):
            self.assertIn(key, report)
        self.assertIn(report["rsync"], ("available", "missing"))
        self.assertTrue(report["signing_key"])
        self.assertTrue(report["public_key"])

    def test_snapshot_dry_run_emits_json(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = self.app.main([
                "--snapshot", str(self.base), "--source", str(self.src), "--dry-run",
            ])
        self.assertEqual(code, 0)
        report = json.loads(buffer.getvalue())
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["files"], 3)
        self.assertIsNone(report["snapshot"])

    def test_snapshot_verify_plan_end_to_end(self) -> None:
        with mock.patch.object(self.app.subprocess, "run", side_effect=FileNotFoundError("no rsync")):
            report = self.app.create_snapshot(self.src, self.base, sign_key=self.private_path)
        self.assertEqual(report["copy"], "python-copy2")
        self.assertEqual(report["signature"], "signed")
        snapshot = pathlib.Path(report["snapshot"])

        result = self.app.verify_snapshot(snapshot, public_key=self.public_path)
        self.assertTrue(result["ok"], result["discrepancies"])

        target = self.dir / "restored"
        plan = self.app.plan_snapshot_restore(snapshot, target, public_key=self.public_path)
        self.assertFalse(plan["shell"])
        self.assertEqual(plan["count"], 3)
        execution = execute_plan(plan["operations"], snapshot, target, dry_run=False)
        self.assertEqual(execution["verified"], 3)
        self.assertEqual((target / "a.txt").read_bytes(), self.files["a.txt"])

    def test_no_delete_and_no_shell_true(self) -> None:
        paths = [APP_PATH] + sorted((AETHEROS / "core" / "backup").glob("*.py"))
        for path in paths:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn('"--delete"', text)
                self.assertNotIn("shell=True", text)


if __name__ == "__main__":
    unittest.main()
