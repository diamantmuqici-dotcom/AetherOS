"""Tests for the encryption upgrades: keyfiles, recovery, Argon2 tuning, LUKS2 helper.

Run with:  python -m unittest discover -s aetheros/tests -p 'test_vault_extras.py' -v
"""

from __future__ import annotations

import os
import pathlib
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core.vault import benchmark as bench  # noqa: E402
from core.vault import keyfile as kf  # noqa: E402
from core.vault import recovery as rec  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]


class KeyfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_generate_and_load(self) -> None:
        path = self.dir / "vault.key"
        kf.generate_keyfile(path)
        raw = path.read_bytes()
        self.assertEqual(len(raw), 32)
        loaded = kf.load_keyfile(path)
        self.assertEqual(loaded.key, raw)
        self.assertIsInstance(loaded.perms_ok, bool)
        if os.name != "nt":
            self.assertTrue(loaded.perms_ok)

    def test_permission_check_is_strict(self) -> None:
        self.assertTrue(kf._permissions_ok(stat.S_IFREG | 0o600))
        self.assertFalse(kf._permissions_ok(stat.S_IFREG | 0o644))
        self.assertFalse(kf._permissions_ok(stat.S_IFREG | 0o666))

    def test_overwrite_refusal_and_force(self) -> None:
        path = self.dir / "vault.key"
        kf.generate_keyfile(path)
        first = path.read_bytes()
        with self.assertRaises(FileExistsError):
            kf.generate_keyfile(path)
        self.assertEqual(path.read_bytes(), first)
        kf.generate_keyfile(path, force=True)
        self.assertNotEqual(path.read_bytes(), first)

    def test_load_rejects_bad_length_and_oversize(self) -> None:
        path = self.dir / "bad.key"
        path.write_bytes(b"x" * 17)
        with self.assertRaises(kf.KeyfileError):
            kf.load_keyfile(path)
        path.write_bytes(b"x" * 32)
        with self.assertRaises(kf.KeyfileError):
            kf.load_keyfile(path, max_bytes=31)
        self.assertEqual(kf.load_keyfile(path, max_bytes=32).key, b"x" * 32)

    def test_combine_determinism_and_domain_separation(self) -> None:
        passphrase = b"correct horse battery staple"
        material = bytes(range(32))
        a = kf.combine_passphrase_keyfile(passphrase, material)
        self.assertEqual(len(a), 32)
        self.assertEqual(a, kf.combine_passphrase_keyfile(passphrase, material))
        self.assertNotEqual(a, kf.combine_passphrase_keyfile(passphrase + b"x", material))
        self.assertNotEqual(a, kf.combine_passphrase_keyfile(passphrase, bytes(31) + b"\x01"))
        self.assertNotEqual(
            kf._hkdf(passphrase, material, b"domain-A", kf._INFO),
            kf._hkdf(passphrase, material, b"domain-B", kf._INFO),
        )
        with self.assertRaises(ValueError):
            kf.combine_passphrase_keyfile(b"", material)


class RecoveryTests(unittest.TestCase):
    def test_wordlist_shape(self) -> None:
        self.assertEqual(len(rec.WORDLIST), 256)
        self.assertEqual(len(set(rec.WORDLIST)), 256)
        self.assertEqual(rec.WORD_COUNT, 24)

    def test_phrase_roundtrip_and_key(self) -> None:
        phrase = rec.generate_recovery_phrase()
        self.assertEqual(len(phrase.split()), 24)
        entropy = rec.decode_phrase(phrase)
        self.assertEqual(len(entropy), rec.ENTROPY_BYTES)
        self.assertEqual(rec.encode_entropy(entropy), phrase)
        salt = os.urandom(16)
        key = rec.mnemonic_to_key(phrase, salt)
        self.assertEqual(len(key), 32)
        self.assertEqual(key, rec.mnemonic_to_key(phrase, salt))
        self.assertNotEqual(key, rec.mnemonic_to_key(phrase, os.urandom(16)))

    def test_wrong_word_count(self) -> None:
        with self.assertRaises(rec.RecoveryError):
            rec.decode_phrase(" ".join(rec.generate_recovery_phrase().split()[:23]))

    def test_unknown_word(self) -> None:
        words = rec.generate_recovery_phrase().split()
        words[0] = "notaword"
        with self.assertRaises(rec.RecoveryError):
            rec.decode_phrase(" ".join(words))

    def test_tampered_checksum_word(self) -> None:
        words = rec.generate_recovery_phrase().split()
        index = rec._WORD_INDEX[words[-1]]
        words[-1] = rec.WORDLIST[(index + 1) % len(rec.WORDLIST)]
        with self.assertRaises(rec.RecoveryError):
            rec.decode_phrase(" ".join(words))

    def test_bad_checksum_from_raw_bits(self) -> None:
        entropy = os.urandom(rec.ENTROPY_BYTES)
        checksum = rec._checksum(entropy) ^ 0x01
        value = (int.from_bytes(entropy, "big") << 8) | checksum
        words = [
            rec.WORDLIST[(value >> (8 * (rec.WORD_COUNT - 1 - i))) & 0xFF]
            for i in range(rec.WORD_COUNT)
        ]
        with self.assertRaises(rec.RecoveryError):
            rec.decode_phrase(" ".join(words))

    def test_invalid_salt_length(self) -> None:
        phrase = rec.generate_recovery_phrase()
        with self.assertRaises(rec.RecoveryError):
            rec.mnemonic_to_key(phrase, b"short")


class BenchmarkTests(unittest.TestCase):
    def test_bounded_parameters(self) -> None:
        params = bench.benchmark_argon2(target_ms=100, max_mem_mib=32)
        self.assertLessEqual(params["mem_mib"], 32)
        self.assertEqual(params["memory_cost_kib"], params["mem_mib"] * 1024)
        self.assertIn(params["iterations"], bench.LADDER_ITERS)
        self.assertLessEqual(params["attempts"], bench.MAX_ATTEMPTS)
        self.assertGreaterEqual(params["measured_ms"], 0)
        self.assertIn("Argon2id", bench.format_recommendation(params))

    def test_invalid_bounds(self) -> None:
        with self.assertRaises(ValueError):
            bench.benchmark_argon2(target_ms=0)
        with self.assertRaises(ValueError):
            bench.benchmark_argon2(max_mem_mib=8)


class ScriptSourceTests(unittest.TestCase):
    def test_luks_helper_requires_confirmation_and_block_device(self) -> None:
        source = (
            REPO
            / "iso/config/includes.chroot/usr/share/aether/scripts/luks2-setup.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("AETHER_CONFIRM", source)
        self.assertIn('"LUKS"', source)
        self.assertIn("[ ! -b", source)
        self.assertIn("cryptsetup luksFormat", source)
        self.assertIn("--pbkdf argon2id", source)
        self.assertIn("--iter-time", source)

    def test_tune_wrapper_uses_bounded_timeout(self) -> None:
        source = (REPO / "scripts/aether-tune-vault.sh").read_text(encoding="utf-8")
        self.assertIn("timeout 30", source)
        self.assertIn("chmod 600", source)
        self.assertIn("--json", source)


if __name__ == "__main__":
    unittest.main()
