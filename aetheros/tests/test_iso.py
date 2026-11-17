"""ISO boot test helpers, boot-check invariants and serial-log parsing tests.

Run: python -m unittest discover -s aetheros/tests -p 'test_iso.py' -v

The parsing/result helpers and the script self-test are pure (no QEMU). The
QEMU integration tests skip unless a qemu binary and an AETHER_ISO path exist.
Tests that shell out to the script additionally skip unless bash is on PATH.
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

# Mirrors CHECK_KEYS in test-iso.sh: every result JSON must carry all of these.
EXPECTED_CHECK_KEYS = frozenset({
    "boot_prompt", "kernel_cmdline", "plymouth_theme",
    "iso_payload", "os_release", "screenshot",
})
TIMEOUT_DEFAULT = 180
TIMEOUT_MIN = 30
TIMEOUT_MAX = 900


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


def missing_check_keys(raw: str | bytes | dict) -> set:
    """Check keys absent from a result JSON; empty set means a complete map."""
    return EXPECTED_CHECK_KEYS - set(parse_result_json(raw)["checks"])


def normalize_timeout(value) -> int:
    """Mirror the script: decimal integers clamp to 30..900, else use 180."""
    text = str(value)
    if not re.fullmatch(r"[0-9]+", text):
        return TIMEOUT_DEFAULT
    return max(TIMEOUT_MIN, min(int(text, 10), TIMEOUT_MAX))


def parse_os_release(text: str) -> dict:
    """Parse shell-style KEY=VALUE os-release content into a dict."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def os_release_has_aether_identity(text: str) -> bool:
    """True when NAME=AetherOS and VERSION_CODENAME=trixie are both present."""
    parsed = parse_os_release(text)
    return (
        parsed.get("NAME") == "AetherOS"
        and parsed.get("VERSION_CODENAME") == "trixie"
    )


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


class ResultCompletenessTests(unittest.TestCase):
    """The checks map must list every key, even on early exit or skip."""

    def test_complete_result_has_no_missing_keys(self) -> None:
        raw = json.dumps({
            "status": "pass", "exit_code": 0,
            "checks": {key: "pass" for key in EXPECTED_CHECK_KEYS},
        })
        self.assertEqual(missing_check_keys(raw), set())

    def test_early_exit_result_lists_every_key_as_skip(self) -> None:
        raw = json.dumps({
            "status": "fail", "exit_code": 1,
            "checks": {key: "skip" for key in EXPECTED_CHECK_KEYS},
            "notes": ["input: ISO missing"],
        })
        self.assertEqual(missing_check_keys(raw), set())
        parsed = parse_result_json(raw)
        self.assertTrue(all(v == "skip" for v in parsed["checks"].values()))

    def test_missing_keys_are_named(self) -> None:
        raw = json.dumps({
            "status": "fail", "exit_code": 1,
            "checks": {"boot_prompt": "fail", "screenshot": "skip"},
        })
        self.assertIn("os_release", missing_check_keys(raw))
        self.assertIn("kernel_cmdline", missing_check_keys(raw))
        self.assertNotIn("boot_prompt", missing_check_keys(raw))

    def test_non_dict_checks_are_all_missing(self) -> None:
        raw = json.dumps({"status": "fail", "exit_code": 1, "checks": []})
        self.assertEqual(missing_check_keys(raw), set(EXPECTED_CHECK_KEYS))


class TimeoutValidationTests(unittest.TestCase):
    """Mirrors normalize_timeout in test-iso.sh."""

    def test_bounds_and_default(self) -> None:
        self.assertEqual(normalize_timeout(""), TIMEOUT_DEFAULT)
        self.assertEqual(normalize_timeout("180"), 180)
        self.assertEqual(normalize_timeout("5"), TIMEOUT_MIN)
        self.assertEqual(normalize_timeout("29"), TIMEOUT_MIN)
        self.assertEqual(normalize_timeout("30"), 30)
        self.assertEqual(normalize_timeout("900"), 900)
        self.assertEqual(normalize_timeout("901"), TIMEOUT_MAX)
        self.assertEqual(normalize_timeout("5000"), TIMEOUT_MAX)

    def test_malformed_values_fall_back_to_default(self) -> None:
        for value in ("abc", "-5", "3.5", " 45 ", None):
            with self.subTest(value=value):
                self.assertEqual(normalize_timeout(value), TIMEOUT_DEFAULT)

    def test_leading_zeroes_are_decimal(self) -> None:
        self.assertEqual(normalize_timeout("045"), 45)


class OsReleaseHelperTests(unittest.TestCase):
    """os-release payload parsing: no QEMU required."""

    def test_parses_quoted_values(self) -> None:
        parsed = parse_os_release(
            'PRETTY_NAME="AetherOS 1.0"\nNAME="AetherOS"\nVERSION_CODENAME=trixie\n'
        )
        self.assertEqual(parsed["NAME"], "AetherOS")
        self.assertEqual(parsed["VERSION_CODENAME"], "trixie")
        self.assertEqual(parsed["PRETTY_NAME"], "AetherOS 1.0")

    def test_identity_helper_accepts_full_file(self) -> None:
        text = (
            'PRETTY_NAME="AetherOS 1.0"\nNAME="AetherOS"\nVERSION_ID="1.0"\n'
            'VERSION_CODENAME=trixie\nID=aetheros\nID_LIKE="debian"\n'
        )
        self.assertTrue(os_release_has_aether_identity(text))

    def test_identity_helper_rejects_wrong_codename(self) -> None:
        text = 'NAME="AetherOS"\nVERSION_CODENAME=bookworm\n'
        self.assertFalse(os_release_has_aether_identity(text))

    def test_identity_helper_rejects_missing_name(self) -> None:
        self.assertFalse(os_release_has_aether_identity("VERSION_CODENAME=trixie\n"))

    def test_comments_and_blank_lines_ignored(self) -> None:
        text = "# generated\n\nNAME=AetherOS\nVERSION_CODENAME=trixie\n"
        self.assertTrue(os_release_has_aether_identity(text))

    def test_single_quoted_values(self) -> None:
        text = "NAME='AetherOS'\nVERSION_CODENAME='trixie'\n"
        self.assertTrue(os_release_has_aether_identity(text))


@unittest.skipUnless(shutil.which("bash"), "bash not present")
class ScriptModeTests(unittest.TestCase):
    """Runs the script's own modes; needs bash but never QEMU or an ISO."""

    def test_self_test_exits_zero_and_reports_all_assertions(self) -> None:
        env = dict(os.environ)
        env.pop("AETHER_ISO", None)
        proc = subprocess.run(
            ["bash", str(ISO_SCRIPT), "--self-test"],
            env=env, capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("selftest PASS", proc.stdout)
        self.assertRegex(proc.stdout, r"selftest \d+ assertions, 0 failures")
        self.assertGreaterEqual(proc.stdout.count("selftest PASS "), 12)
        self.assertNotIn("booting:", proc.stdout)

    def test_self_test_survives_out_of_range_timeout(self) -> None:
        proc = subprocess.run(
            ["bash", str(ISO_SCRIPT), "--self-test", "--timeout", "5000"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 failures", proc.stdout)

    def test_missing_iso_result_is_complete_and_clamps_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            result = out / "result.json"
            env = dict(os.environ)
            env["AETHER_TEST_RESULT"] = str(result)
            env["AETHER_TEST_LOG"] = str(out / "serial.log")
            proc = subprocess.run(
                ["bash", str(ISO_SCRIPT), "--timeout", "5", str(out / "missing.iso")],
                env=env, capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stderr)
            data = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(data["timeout_seconds"], TIMEOUT_MIN)
            self.assertEqual(missing_check_keys(data), set())


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
            proc = subprocess.run(
                ["bash", str(ISO_SCRIPT), os.environ["AETHER_ISO"], "--timeout", "30"],
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            self.assertIn(proc.returncode, (0, 1, 77), proc.stderr)
            raw = result.read_text(encoding="utf-8")
            parsed = parse_result_json(raw)
            self.assertIn(parsed["status"], {"pass", "fail", "skip"})
            self.assertEqual(parsed["exit_code"], proc.returncode)
            self.assertEqual(missing_check_keys(raw), set())


if __name__ == "__main__":
    unittest.main()
