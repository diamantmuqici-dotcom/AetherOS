"""Tests for signed-manifest APT policy and the offline update-push CLI.

Run with: python -m unittest discover -s aetheros/tests -p 'test_apt_policy.py' -v
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.update.apt_policy import (  # noqa: E402
    POLICY,
    PolicyError,
    build_apt_argv,
    build_policy_from_manifest,
    evaluate_package_policy,
    intersect_upgrades_with_policy,
    parse_apt_policy,
    parse_simulated_upgrade,
    validate_plan,
)

SCRIPT = ROOT / "scripts" / "update-push.py"


def _manifest(**overrides) -> dict:
    expires = (datetime.now(timezone.utc) + timedelta(days=1))
    expires = expires.isoformat().replace("+00:00", "Z")
    payload = {
        "schema": "aether-release/1",
        "channel": "stable",
        "expires": expires,
        "min_os_version": "1.0",
        "packages": {"aether-shell": "1.4-2", "aether-updater": "1.2-1"},
    }
    payload.update(overrides)
    return payload


class PolicyBuildTests(unittest.TestCase):
    def test_pins_and_allowed_set_come_from_manifest(self) -> None:
        policy = build_policy_from_manifest(_manifest())
        self.assertEqual(policy["source"], POLICY.SOURCE)
        self.assertEqual(policy["signature"], "VALID")
        self.assertEqual(policy["pinned"], {"aether-shell": "1.4-2", "aether-updater": "1.2-1"})
        self.assertEqual(policy["allowed"], ["aether-shell", "aether-updater"])

    def test_channel_override_applies(self) -> None:
        manifest = _manifest(channels={"beta": {"packages": {"aether-shell": "1.5~beta-1"}}})
        policy = build_policy_from_manifest(manifest, "beta")
        self.assertEqual(policy["pinned"], {"aether-shell": "1.5~beta-1"})

    def test_empty_pins_yield_empty_allow_list(self) -> None:
        policy = build_policy_from_manifest(_manifest(packages={}))
        self.assertEqual(policy["allowed"], [])

    def test_malformed_manifest_fails_closed(self) -> None:
        bad_manifests = [
            [],
            {},
            "not-a-dict",
            _manifest(packages="wrong"),
            _manifest(packages={"foo": 9}),
        ]
        for manifest in bad_manifests:
            with self.subTest(manifest=manifest), self.assertRaises(PolicyError):
                build_policy_from_manifest(manifest)

    def test_unknown_channel_fails_closed(self) -> None:
        with self.assertRaises(PolicyError):
            build_policy_from_manifest(_manifest(), "sideways")


class EvaluateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = build_policy_from_manifest(_manifest())

    def test_pinned_version_allowed(self) -> None:
        record = evaluate_package_policy(
            self.policy, "aether-shell", "1.4-2", "upgrade",
        )
        self.assertEqual(record["decision"], POLICY.ALLOWED)
        self.assertEqual(record["state"], POLICY.PINNED)
        self.assertEqual(record["pinned_version"], "1.4-2")

    def test_unpinned_package_denied(self) -> None:
        record = evaluate_package_policy(self.policy, "evil", "9.9", "install")
        self.assertEqual(record["decision"], POLICY.DISALLOWED)
        self.assertEqual(record["reason"], "not-pinned")

    def test_version_mismatch_denied(self) -> None:
        record = evaluate_package_policy(
            self.policy, "aether-shell", "9.9", "upgrade",
        )
        self.assertEqual(record["decision"], POLICY.DISALLOWED)
        self.assertEqual(record["reason"], "version-mismatch")
        self.assertEqual(record["pinned_version"], "1.4-2")

    def test_invalid_action_denied(self) -> None:
        record = evaluate_package_policy(self.policy, "aether-shell", "1.4-2", "exec")
        self.assertEqual(record["decision"], POLICY.DISALLOWED)
        self.assertEqual(record["reason"], "invalid-action")

    def test_hold_without_candidate_allowed(self) -> None:
        record = evaluate_package_policy(self.policy, "aether-shell", None, "hold")
        self.assertEqual(record["decision"], POLICY.ALLOWED)

    def test_no_policy_denies_everything(self) -> None:
        for policy in (None, {}, {"pinned": "bad"}):
            record = evaluate_package_policy(policy, "aether-shell", "1.4-2")
            self.assertEqual(record["decision"], POLICY.DISALLOWED)

    def test_intersection_keeps_only_pinned_matching_upgrades(self) -> None:
        upgrades = [
            {"package": "aether-shell", "current": "1.3-1", "candidate": "1.4-2", "origin": "Debian:13/stable"},
            {"package": "aether-updater", "current": "1.1-1", "candidate": "9.9", "origin": "Debian:13/stable"},
            {"package": "evil", "current": "0.1", "candidate": "9.9", "origin": "unknown"},
        ]
        result = intersect_upgrades_with_policy(self.policy, upgrades)
        self.assertEqual([item["package"] for item in result], ["aether-shell"])
        self.assertEqual(result[0]["version"], "1.4-2")
        self.assertEqual(result[0]["current"], "1.3-1")


class PlanArgvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = build_policy_from_manifest(_manifest())

    def test_valid_plan_is_normalized_to_pinned_versions(self) -> None:
        plan = [
            {"package": "aether-shell", "version": "1.4-2", "action": "upgrade"},
            {"package": "aether-updater", "version": "1.2-1", "action": "install"},
        ]
        normalized, status = validate_plan(self.policy, plan)
        self.assertEqual(status, "ok")
        self.assertEqual([item["version"] for item in normalized], ["1.4-2", "1.2-1"])

    def test_plan_denies_unpinned_and_mismatched_entries(self) -> None:
        for entry in (
            {"package": "evil", "version": "9.9", "action": "install"},
            {"package": "aether-shell", "version": "9.9", "action": "upgrade"},
            {"package": "aether-shell", "version": "1.4-2", "action": "exec"},
            "not-a-dict",
        ):
            with self.subTest(entry=entry):
                normalized, status = validate_plan(self.policy, [entry])
                self.assertEqual(normalized, [])
                self.assertTrue(status.startswith("denied:") or status == "invalid-entry")

    def test_argv_are_lists_of_strings_not_shell_strings(self) -> None:
        entries = [
            {"package": "aether-shell", "version": "1.4-2", "action": "upgrade"},
            {"package": "aether-updater", "version": "1.2-1", "action": "install"},
            {"package": "aether-shell", "version": "1.4-2", "action": "hold"},
        ]
        plans = build_apt_argv(entries)
        self.assertIsInstance(plans, list)
        for argv in plans:
            self.assertIsInstance(argv, list)
            self.assertTrue(all(isinstance(part, str) for part in argv))
            self.assertFalse(any(ch in ";&|`$" for part in argv for ch in part))
        self.assertEqual(plans[0][:2], ["apt-get", "install"])
        self.assertIn("aether-shell=1.4-2", plans[0])
        self.assertEqual(plans[2], ["apt-mark", "hold", "aether-shell"])

    def test_empty_plan_emits_no_argv(self) -> None:
        normalized, status = validate_plan(self.policy, [])
        self.assertEqual((normalized, status), ([], "ok"))
        self.assertEqual(build_apt_argv(normalized), [])


class ParserRegressionTests(unittest.TestCase):
    def test_parse_simulated_upgrade(self) -> None:
        text = (
            "Reading package lists...\n"
            "The following packages will be upgraded:\n  foo bar\n"
            "Inst foo [1.0] (2.0 Debian:13/stable [amd64])\n"
            "Conf foo (2.0)\n"
            "0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.\n"
        )
        upgrades, status = parse_simulated_upgrade(text)
        self.assertEqual(status, "ok")
        self.assertEqual(upgrades[0]["package"], "foo")
        self.assertEqual(upgrades[0]["candidate"], "2.0")
        self.assertEqual(parse_simulated_upgrade("garbage"), ([], "unrecognized-output"))

    def test_parse_apt_policy(self) -> None:
        text = (
            "foo:\n  Installed: 1.0\n  Candidate: 2.0\n"
            "  Version table:\n *** 2.0 500\n        500 /var/lib/apt/lists/Packages\n"
        )
        self.assertEqual(
            parse_apt_policy(text),
            {"package": "foo", "installed": "1.0", "candidate": "2.0"},
        )
        self.assertEqual(parse_apt_policy(""), {})


class _SignedEnv:
    """Create a signed manifest/signature/key trio and matching environment."""

    def __init__(self, directory: str, payload: dict) -> None:
        self.dir = pathlib.Path(directory)
        self.private = ed25519.Ed25519PrivateKey.generate()
        self.manifest = self.dir / "release-manifest.json"
        self.signature = self.dir / "release-manifest.json.sig"
        self.public_key = self.dir / "public.pem"
        self.public_key.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        self.manifest.write_bytes(json.dumps(payload).encode("utf-8"))
        signing_input = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.signature.write_bytes(self.private.sign(signing_input))

    def env(self) -> dict:
        env = dict(os.environ)
        env["AETHER_RELEASE_MANIFEST"] = str(self.manifest)
        env["AETHER_RELEASE_SIGNATURE"] = str(self.signature)
        env["AETHER_RELEASE_PUBLIC_KEY"] = str(self.public_key)
        env["AETHER_UPDATE_CHANNEL"] = "stable"
        return env


class CliTests(unittest.TestCase):
    def _run_cli(self, args: list[str], env: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env=env, capture_output=True, text=True, timeout=30, check=False,
        )

    def test_no_network_imports_in_script(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("urllib", text)
        self.assertNotIn("urlopen", text)
        self.assertNotIn("requests", text)
        self.assertNotIn("shell=True", text)
        self.assertNotIn("eval(", text)

    def test_version_flag(self) -> None:
        result = self._run_cli(["--version"], dict(os.environ))
        self.assertEqual(result.returncode, 0)
        self.assertIn("update-push", result.stdout)

    def test_check_offline_missing_manifest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            env = dict(os.environ)
            env["AETHER_RELEASE_MANIFEST"] = str(d / "absent.json")
            env["AETHER_RELEASE_SIGNATURE"] = str(d / "absent.sig")
            env["AETHER_RELEASE_PUBLIC_KEY"] = str(d / "absent.pem")
            result = self._run_cli(["--check"], env)
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["signature"], "MISSING")
        self.assertIsNone(report["policy_source"])
        self.assertEqual(report["allowed_packages"], [])
        self.assertEqual(report["pending_upgrades"], [])
        self.assertIn("missing", str(report["error"]).lower())

    def test_check_offline_signed_manifest_publishes_allowed_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _SignedEnv(tmp, _manifest()).env()
            result = self._run_cli(["--check"], env)
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["signature"], "VALID")
        self.assertEqual(report["policy_source"], POLICY.SOURCE)
        self.assertEqual(report["allowed_packages"], ["aether-shell", "aether-updater"])
        if shutil.which("apt-get") is None:
            self.assertEqual(report["apt_status"], "apt-unavailable")
            self.assertEqual(report["pending_upgrades"], [])
            self.assertIn("apt binaries absent", report["error"])
        else:
            self.assertIsInstance(report["pending_upgrades"], list)

    def test_apply_plan_validates_then_emits_argv_without_executing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            signed = _SignedEnv(tmp, _manifest())
            env = signed.env()
            good = signed.dir / "good-plan.json"
            bad = signed.dir / "bad-plan.json"
            good.write_text(json.dumps({"entries": [
                {"package": "aether-shell", "version": "1.4-2", "action": "upgrade"},
            ]}), encoding="utf-8")
            bad.write_text(json.dumps({"entries": [
                {"package": "aether-shell", "version": "1.4-2", "action": "upgrade"},
                {"package": "evil", "version": "9.9", "action": "install"},
            ]}), encoding="utf-8")

            denied = self._run_cli(["--apply-plan", str(bad)], env)
            self.assertNotEqual(denied.returncode, 0)
            denied_report = json.loads(denied.stdout)
            self.assertEqual(denied_report["status"], "denied")
            self.assertEqual(denied_report["argv"], [])
            self.assertIn("denied", denied_report["error"])

            allowed = self._run_cli(["--apply-plan", str(good)], env)
            self.assertEqual(allowed.returncode, 0)
            allowed_report = json.loads(allowed.stdout)
            self.assertEqual(allowed_report["status"], "ok")
            self.assertIsInstance(allowed_report["argv"], list)
            self.assertTrue(all(isinstance(argv, list) for argv in allowed_report["argv"]))
            self.assertIn("aether-shell=1.4-2", allowed_report["argv"][0])


if __name__ == "__main__":
    unittest.main()
