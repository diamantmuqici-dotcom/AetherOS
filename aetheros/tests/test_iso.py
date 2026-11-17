"""ISO boot test helpers and serial-log parsing tests.

Run: python -m unittest discover -s aetheros/tests -p 'test_iso.py' -v

The parsing/result helpers are pure and always run. The QEMU integration
tests skip unless a qemu binary and an AETHER_ISO path are present.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ISO_SCRIPT = REPO_ROOT / "aetheros" / "scripts" / "test-iso.sh"

BANNER_RE = re.compile(r"AetherOS", re.I)
LOGIN_RE = re.compile(r"login:|\b[Gg][Dd][Mm]\b|Debian GNU/Linux", re.I)
CMDLINE_RE = re.compile(r"Command line:\s*(.*)", re.I)
QUIET_SPLASH_RE = re.compile(r"quiet\s+splash", re.I)


def parse_qemu_serial(text: str) -> dict:
    """Extract boot milestones from a captured QEMU serial log."""
    cmdline = ""
    for line in text.splitlines():
        match = CMDLINE_RE.search(line)
        if match:
            cmdline = match.group(1).strip()
            break
    banner = bool(BANNER_RE.search(text))
    login = bool(LOGIN_RE.search(text))
    return {
        "aether_banner": banner,
        "login_prompt": login,
        "quiet_splash": bool(QUIET_SPLASH_RE.search(text)),
        "kernel_cmdline": cmdline,
        "reached_prompt": banner or login,
    }


def parse_result_json(raw: str | bytes | dict) -> dict:
    """Normalize the JSON written by test-iso.sh for assertions."""
    data = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else dict(raw)
    checks = data.get("checks") or {}
    notes = data.get("notes") or []
    return {
        "status": str(data.get("status", "")),
        "exit_code": int(data.get("exit_code", -1)),
        "prompt_seen": bool(data.get("prompt_seen", False)),
        "checks": checks if isinstance(checks, dict) else {},
        "notes": list(notes) if isinstance(notes, list) else [],
        "all_pass": bool(checks) and all(v == "pass" for v in checks.values()),
    }


class SerialParsingTests(unittest.TestCase):
    """Pure helper tests: no QEMU required."""

    def test_recognizes_aether_banner(self) -> None:
        parsed = parse_qemu_serial("Welcome to AetherOS 1.0\n")
        self.assertTrue(parsed["aether_banner"])
        self.assertTrue(parsed["reached_prompt"])

    def test_recognizes_login_prompt(self) -> None:
        parsed = parse_qemu_serial("aetheros-live login: _\n")
        self.assertTrue(parsed["login_prompt"])

    def test_recognizes_quiet_splash_in_cmdline(self) -> None:
        log = "[    0.000000] Kernel command line: BOOT_IMAGE=/vmlinuz quiet splash hostname=aetheros-live\n"
        parsed = parse_qemu_serial(log)
        self.assertTrue(parsed["quiet_splash"])
        self.assertIn("quiet splash", parsed["kernel_cmdline"])
        self.assertIn("BOOT_IMAGE=/vmlinuz", parsed["kernel_cmdline"])

    def test_empty_log_has_no_milestones(self) -> None:
        parsed = parse_qemu_serial("")
        self.assertFalse(parsed["aether_banner"])
        self.assertFalse(parsed["login_prompt"])
        self.assertFalse(parsed["quiet_splash"])
        self.assertFalse(parsed["reached_prompt"])
        self.assertEqual(parsed["kernel_cmdline"], "")

    def test_cmdline_without_quiet_splash(self) -> None:
        parsed = parse_qemu_serial("Kernel command line: root=/dev/sda1 single\n")
        self.assertEqual(parsed["kernel_cmdline"], "root=/dev/sda1 single")
        self.assertFalse(parsed["quiet_splash"])


class ResultParsingTests(unittest.TestCase):
    """Simulated result JSON parsing: no QEMU required."""

    def test_all_pass_result(self) -> None:
        raw = json.dumps({
            "status": "pass",
            "exit_code": 0,
            "prompt_seen": 1,
            "checks": {"boot_prompt": "pass", "iso_payload": "pass"},
            "notes": [],
        })
        parsed = parse_result_json(raw)
        self.assertEqual(parsed["status"], "pass")
        self.assertEqual(parsed["exit_code"], 0)
        self.assertTrue(parsed["prompt_seen"])
        self.assertTrue(parsed["all_pass"])

    def test_skip_result_with_notes(self) -> None:
        raw = json.dumps({
            "status": "skip",
            "exit_code": 77,
            "checks": {},
            "notes": ["plymouth_theme: lsinitrd unavailable"],
        })
        parsed = parse_result_json(raw)
        self.assertEqual(parsed["status"], "skip")
        self.assertEqual(parsed["exit_code"], 77)
        self.assertFalse(parsed["all_pass"])
        self.assertEqual(parsed["notes"], ["plymouth_theme: lsinitrd unavailable"])

    def test_malformed_json_raises(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            parse_result_json("{not json")


@unittest.skipUnless(
    shutil.which("qemu-system-x86_64") and os.environ.get("AETHER_ISO"),
    "qemu/ISO not present",
)
class IsoBootIntegrationTests(unittest.TestCase):
    """Integration checks that need QEMU and a built ISO."""

    def test_iso_exists_and_nonempty(self) -> None:
        iso = pathlib.Path(os.environ["AETHER_ISO"])
        self.assertTrue(iso.is_file(), f"ISO not found: {iso}")
        self.assertGreater(iso.stat().st_size, 0, "ISO is empty")

    def test_script_present(self) -> None:
        self.assertTrue(ISO_SCRIPT.is_file(), f"missing: {ISO_SCRIPT}")
        self.assertTrue(
            os.access(ISO_SCRIPT, os.X_OK) or os.access(ISO_SCRIPT, os.R_OK),
            "test-iso.sh is neither executable nor readable",
        )

    def test_script_run_writes_valid_result(self) -> None:
        """Bounded argv-only run; accept pass/fail/skip, require valid JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            result = out / "result.json"
            env = dict(os.environ)
            env["AETHER_TEST_RESULT"] = str(result)
            env["AETHER_TEST_LOG"] = str(out / "serial.log")
            env["AETHER_TEST_SCREENSHOT"] = str(out / "shot.ppm")
            env["AETHER_TEST_TIMEOUT"] = "20"
            proc = subprocess.run(
                ["bash", str(ISO_SCRIPT), os.environ["AETHER_ISO"]],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertIn(proc.returncode, (0, 1, 77), proc.stderr)
            parsed = parse_result_json(result.read_text(encoding="utf-8"))
            self.assertIn(parsed["status"], {"pass", "fail", "skip"})
            self.assertEqual(parsed["exit_code"], proc.returncode)


if __name__ == "__main__":
    unittest.main()
