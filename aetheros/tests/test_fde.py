"""Tests for the LUKS2 full-disk-encryption status helpers and scripts.

Run with:  python -m unittest discover -s aetheros/tests -p 'test_fde.py' -v
"""

from __future__ import annotations

import filecmp
import json
import pathlib
import re
import sys
import unittest

AETHER_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AETHER_ROOT))

from core.fde import status as fde  # noqa: E402

SAMPLE_DUMP = """LUKS header information for /dev/nvme0n1p3

Version:       	2
Epoch:         	3
Metadata area: 	16384 [bytes]
UUID:          	2f6f0c2a-9b1d-4c3e-8f7a-1d2e3f4a5b6c
Label:         	(no label)
Flags:       	(no flags)

Data segments:
  0: crypt
	offset: 16777216 [bytes]
	length: (whole device)
	cipher: aes-xts-plain64
	sector: 512

Keyslots:
  0: luks2
	Key:        	512 bits
	Cipher:     	aes-xts-plain64
	PBKDF:      	argon2id
	Iteration:  	4
	Memory:     	1048576
  1: luks2
	Key:        	512 bits
	PBKDF:      	argon2id
	Iteration:  	4
"""

MIRROR_PAIRS = (
    (
        "scripts/luks2-setup.sh",
        "iso/config/includes.chroot/usr/share/aether/scripts/luks2-setup.sh",
    ),
    (
        "scripts/fde-verify.sh",
        "iso/config/includes.chroot/usr/share/aether/scripts/fde-verify.sh",
    ),
    (
        "scripts/fde-verify.sh",
        "iso/config/includes.chroot/usr/local/bin/aether-fde-verify",
    ),
    (
        "core/fde/__init__.py",
        "iso/config/includes.chroot/usr/share/aether/core/fde/__init__.py",
    ),
    (
        "core/fde/status.py",
        "iso/config/includes.chroot/usr/share/aether/core/fde/status.py",
    ),
)


class ParseLuksDumpTests(unittest.TestCase):
    def test_valid_dump_fields(self) -> None:
        parsed = fde.parse_luks_dump(SAMPLE_DUMP)
        self.assertEqual(parsed["version"], 2)
        self.assertEqual(parsed["cipher"], "aes-xts-plain64")
        self.assertEqual(parsed["pbkdf"], "argon2id")
        self.assertEqual(parsed["iterations"], 4)
        self.assertEqual(parsed["keyslots_enabled"], 2)
        self.assertEqual(parsed["uuid"], "2f6f0c2a-9b1d-4c3e-8f7a-1d2e3f4a5b6c")
        self.assertEqual(parsed["missing"], [])

    def test_formatting_tolerance(self) -> None:
        messy = "VERSION :\t2\nuuid:   AA-BB-CC-DD\ncipher:\tchacha20\nPBKDF : argon2id\nTime cost:\t7\n3: LUKS2\n"
        parsed = fde.parse_luks_dump(messy)
        self.assertEqual(parsed["version"], 2)
        self.assertEqual(parsed["cipher"], "chacha20")
        self.assertEqual(parsed["pbkdf"], "argon2id")
        self.assertEqual(parsed["iterations"], 7)
        self.assertEqual(parsed["keyslots_enabled"], 1)

    def test_malformed_dump_fails_closed(self) -> None:
        parsed = fde.parse_luks_dump("not a luks dump\nrandom noise: 1\n")
        self.assertIsNone(parsed["version"])
        self.assertIsNone(parsed["cipher"])
        self.assertIsNone(parsed["pbkdf"])
        self.assertIsNone(parsed["iterations"])
        self.assertIsNone(parsed["uuid"])
        self.assertEqual(parsed["keyslots_enabled"], 0)
        self.assertEqual(
            parsed["missing"],
            ["version", "cipher", "pbkdf", "iterations", "uuid"],
        )

    def test_non_string_rejected(self) -> None:
        for bad in (None, b"bytes", 123, []):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                fde.parse_luks_dump(bad)


class FdeStatusTests(unittest.TestCase):
    def test_all_good_is_strong(self) -> None:
        report = fde.fde_status(SAMPLE_DUMP, True, True, True)
        self.assertEqual(report["overall"], "FDE_STRONG")
        self.assertTrue(report["luks2"])
        self.assertTrue(report["argon2id"])
        self.assertTrue(report["keyslots_ok"])
        self.assertEqual(report["gaps"], [])

    def test_missing_bootloader_or_swap_is_partial(self) -> None:
        report = fde.fde_status(SAMPLE_DUMP, False, False, True)
        self.assertEqual(report["overall"], "FDE_PARTIAL")
        joined = " ".join(report["gaps"])
        self.assertIn("bootloader", joined)
        self.assertIn("swap", joined)

    def test_no_luks_is_not_encrypted(self) -> None:
        report = fde.fde_status("", False, False, False)
        self.assertEqual(report["overall"], "NOT_ENCRYPTED")
        self.assertFalse(report["luks2"])
        self.assertFalse(report["keyslots_ok"])

    def test_external_key_false_is_gap(self) -> None:
        report = fde.fde_status(SAMPLE_DUMP, True, True, False)
        self.assertFalse(report["key_external"])
        self.assertEqual(report["overall"], "FDE_PARTIAL")
        self.assertTrue(any("key" in gap for gap in report["gaps"]))

    def test_keyfile_in_image_is_gap(self) -> None:
        # keyfile_external=False models a boot keyfile baked into the image.
        report = fde.fde_status(SAMPLE_DUMP, True, True, False)
        self.assertTrue(
            any("stored in image" in gap for gap in report["gaps"]),
            msg="keyfile-in-image must appear as a gap",
        )

    def test_weak_kdf_is_partial(self) -> None:
        pbkdf2_dump = SAMPLE_DUMP.replace("PBKDF:      	argon2id", "PBKDF:      	pbkdf2")
        report = fde.fde_status(pbkdf2_dump, True, True, True)
        self.assertFalse(report["argon2id"])
        self.assertEqual(report["overall"], "FDE_PARTIAL")

    def test_no_keyslots_is_not_encrypted(self) -> None:
        no_slots = re.sub(r"^\s*\d+: luks2.*$", "", SAMPLE_DUMP, flags=re.MULTILINE)
        report = fde.fde_status(no_slots, True, True, True)
        self.assertEqual(report["keyslots"], 0)
        self.assertEqual(report["overall"], "NOT_ENCRYPTED")


class RenderReportTests(unittest.TestCase):
    def test_deterministic_canonical_json(self) -> None:
        report = fde.fde_status(SAMPLE_DUMP, False, True, True)
        first = fde.render_report(report)
        second = fde.render_report(report)
        self.assertEqual(first, second)
        self.assertEqual(first, json.dumps(report, sort_keys=True, separators=(",", ":")))
        self.assertEqual(json.loads(first), report)


class ScriptContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.setup_script = (AETHER_ROOT / "scripts" / "luks2-setup.sh").read_text(
            encoding="utf-8"
        )
        cls.verify_script = (AETHER_ROOT / "scripts" / "fde-verify.sh").read_text(
            encoding="utf-8"
        )

    def test_setup_retains_confirm_gate(self) -> None:
        self.assertIn('AETHER_CONFIRM:-}', self.setup_script)
        self.assertIn('!= "LUKS"', self.setup_script)
        self.assertIn("[ ! -b \"$device\" ]", self.setup_script)

    def test_setup_has_check_mode_and_swap(self) -> None:
        self.assertIn("--check", self.setup_script)
        self.assertIn("AETHER_SWAP_DEVICE", self.setup_script)
        self.assertIn("/crypto_keyfile.bin", self.setup_script)
        self.assertIn("chmod 600", self.setup_script)
        self.assertIn("luksAddKey", self.setup_script)

    def test_verify_uses_real_argv_no_eval(self) -> None:
        low = self.verify_script.lower()
        self.assertNotIn("shell=true", low)
        self.assertNotRegex(self.verify_script, r"\beval\b")
        self.assertIn("luksdump", low)
        self.assertIn("render_report", self.verify_script)
        self.assertIn("--self-test", self.verify_script)

    def test_verify_never_prints_key_material(self) -> None:
        low = self.verify_script.lower()
        for token in ("xxd", "hexdump", "od -", "cat /crypto_keyfile", "print(key"):
            with self.subTest(token=token):
                self.assertNotIn(token, low)

    def test_mirrors_are_byte_identical(self) -> None:
        for source, dest in MIRROR_PAIRS:
            with self.subTest(pair=f"{source} -> {dest}"):
                src_path = AETHER_ROOT / source
                dst_path = AETHER_ROOT / dest
                self.assertTrue(src_path.is_file(), msg=f"missing {source}")
                self.assertTrue(dst_path.is_file(), msg=f"missing {dest}")
                self.assertTrue(
                    filecmp.cmp(src_path, dst_path, shallow=False),
                    msg=f"not byte-identical: {source} != {dest}",
                )


if __name__ == "__main__":
    unittest.main()
