"""Automated cryptographic and data-integrity tests for Aether Vault.

Run with:  python -m unittest discover -s aetheros/tests -p 'test_*.py' -v
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core.vault.secure_vault import (  # noqa: E402
    Argon2Params,
    IntegrityError,
    MigrationError,
    SecureVault,
    UnsupportedFormatError,
    VaultError,
    WrongPasswordError,
    _legacy_derive,
    decrypt_payload,
    encrypt_payload,
    migrate_legacy_vault,
)

# Small parameters keep the suite fast; the container records the parameters
# used, so this does not weaken the format or the production defaults.
TEST_PARAMS = Argon2Params(memory_cost_kib=1024, iterations=2, parallelism=1, salt_len=16)
PASSWORD = "correct horse battery staple"


class VaultCryptoTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        payload = {"records": [{"site": "example.org", "user": "a", "pw": "s3cret"}]}
        blob = encrypt_payload(PASSWORD, payload, TEST_PARAMS)
        self.assertEqual(decrypt_payload(PASSWORD, blob), payload)

    def test_unique_nonces_and_ciphertexts(self) -> None:
        payload = {"records": []}
        a = encrypt_payload(PASSWORD, payload, TEST_PARAMS)
        b = encrypt_payload(PASSWORD, payload, TEST_PARAMS)
        self.assertNotEqual(a[54:66], b[54:66], "nonces must be unique per write")
        self.assertNotEqual(a, b, "ciphertexts must differ for identical plaintext")

    def test_wrong_password_fails_closed(self) -> None:
        blob = encrypt_payload(PASSWORD, {"records": []}, TEST_PARAMS)
        with self.assertRaises(WrongPasswordError):
            decrypt_payload("wrong password", blob)

    def test_corrupted_ciphertext_is_rejected(self) -> None:
        blob = bytearray(encrypt_payload(PASSWORD, {"records": []}, TEST_PARAMS))
        blob[-1] ^= 0x01
        with self.assertRaises(WrongPasswordError):
            decrypt_payload(PASSWORD, bytes(blob))

    def test_tampered_kdf_parameters_are_rejected(self) -> None:
        blob = bytearray(encrypt_payload(PASSWORD, {"records": []}, TEST_PARAMS))
        blob[16] = 0x02  # iterations field
        with self.assertRaises(WrongPasswordError):
            decrypt_payload(PASSWORD, bytes(blob))

    def test_truncated_container_is_rejected(self) -> None:
        blob = encrypt_payload(PASSWORD, {"records": []}, TEST_PARAMS)
        with self.assertRaises(IntegrityError):
            decrypt_payload(PASSWORD, blob[:-4])

    def test_unknown_version_is_rejected(self) -> None:
        blob = bytearray(encrypt_payload(PASSWORD, {"records": []}, TEST_PARAMS))
        blob[12] = 99
        with self.assertRaises(UnsupportedFormatError):
            decrypt_payload(PASSWORD, bytes(blob))


class VaultFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.path = self.dir / "vault.enc"
        self.vault = SecureVault(self.path, PASSWORD, TEST_PARAMS)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_unlock_add_save_reopen(self) -> None:
        self.vault.create()
        self.vault.unlock()
        self.vault.add({"site": "a.example", "user": "u", "pw": "p"})
        self.vault.save()
        self.vault.lock()
        reopened = SecureVault(self.path, PASSWORD, TEST_PARAMS).unlock()
        self.assertEqual(reopened["records"][0]["site"], "a.example")

    def test_backup_holds_previous_version(self) -> None:
        self.vault.create()
        self.vault.unlock()
        self.vault.add({"site": "one"})
        self.vault.save()
        before = self.path.read_bytes()
        self.vault.add({"site": "two"})
        self.vault.save()
        self.assertEqual(decrypt_payload(PASSWORD, self.vault.backup_path.read_bytes()),
                         {"format": "aether-vault-records", "version": 1,
                          "records": [{"site": "one"}]})
        self.assertNotEqual(before, self.path.read_bytes())

    def test_failed_replace_leaves_original_intact(self) -> None:
        self.vault.create()
        self.vault.unlock()
        self.vault.add({"site": "original"})
        self.vault.save()
        original = self.path.read_bytes()
        self.vault.add({"site": "pending"})
        with mock.patch("core.vault.secure_vault.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.vault.save()
        self.assertEqual(self.path.read_bytes(), original)

    def test_change_password_keeps_records(self) -> None:
        self.vault.create()
        self.vault.unlock()
        self.vault.add({"site": "keep.me"})
        self.vault.save()
        self.vault.change_password("a new master password")
        reopened = SecureVault(self.path, "a new master password", TEST_PARAMS).unlock()
        self.assertEqual(reopened["records"][0]["site"], "keep.me")
        with self.assertRaises(WrongPasswordError):
            SecureVault(self.path, PASSWORD, TEST_PARAMS).unlock()

    def test_locked_vault_refuses_mutation(self) -> None:
        with self.assertRaises(VaultError):
            self.vault.add({"site": "x"})

    def test_restore_backup(self) -> None:
        self.vault.create()
        self.vault.unlock()
        self.vault.add({"site": "first"})
        self.vault.save()
        self.vault.add({"site": "second"})
        self.vault.save()
        self.vault.restore_backup()
        self.assertEqual([r["site"] for r in self.vault.payload["records"]], ["first"])


class LegacyMigrationTests(unittest.TestCase):
    def _make_legacy(self, directory: pathlib.Path, master: str) -> pathlib.Path:
        salt = os.urandom(16)
        key = _legacy_derive(master, salt)
        data = {
            "passwords": [{"site": "legacy.example", "user": "old", "pw": "kept"}],
            "history": [{"url": "https://legacy.example", "title": "Old"}],
        }
        ct = ChaCha20Poly1305(key).encrypt(b"\x00" * 12, json.dumps(data).encode(), salt)
        path = directory / "vault.enc"
        path.write_bytes(salt + ct)
        return path

    def test_migration_preserves_all_records(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            directory = pathlib.Path(td)
            legacy = self._make_legacy(directory, PASSWORD)
            original = legacy.read_bytes()
            target = directory / "vault-v2.enc"
            report = migrate_legacy_vault(PASSWORD, legacy, target, TEST_PARAMS)
            self.assertEqual(report["records"], 1)
            self.assertEqual(pathlib.Path(report["legacy_backup"]).read_bytes(), original)
            payload = decrypt_payload(PASSWORD, target.read_bytes())
            self.assertEqual(payload["records"][0]["site"], "legacy.example")
            self.assertEqual(payload["history"][0]["title"], "Old")
            self.assertEqual(payload["migrated_from"], "v1")

    def test_migration_wrong_password_leaves_files_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            directory = pathlib.Path(td)
            legacy = self._make_legacy(directory, PASSWORD)
            original = legacy.read_bytes()
            target = directory / "vault-v2.enc"
            with self.assertRaises(MigrationError):
                migrate_legacy_vault("wrong", legacy, target, TEST_PARAMS)
            self.assertEqual(legacy.read_bytes(), original)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
