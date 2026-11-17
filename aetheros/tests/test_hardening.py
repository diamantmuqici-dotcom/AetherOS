"""Static hardening assertions for AetherOS phase 1.

Run with:  python -m unittest discover -s aetheros/tests -p 'test_hardening.py' -v
"""
from __future__ import annotations

import pathlib
import unittest

AETHEROS = pathlib.Path(__file__).resolve().parents[1]
CHROOT = AETHEROS / "iso" / "config" / "includes.chroot"
SYSTEMD_DIRS = (
    CHROOT / "lib" / "systemd" / "system",
    CHROOT / "etc" / "systemd" / "system",
)
APPARMOR_DIR = CHROOT / "etc" / "apparmor.d"
FACTORY_RESET = (
    AETHEROS / "apps" / "factory-reset" / "aether-factory-reset.py",
    CHROOT / "usr" / "share" / "aether" / "apps" / "aether-factory-reset.py",
)
SERVICE_DIRECTIVES = (
    "NoNewPrivileges=true",
    "PrivateTmp=true",
    "ProtectSystem=strict",
    "ProtectHome=read-only",
    "RestrictSUIDSGID=true",
    "LockPersonality=true",
    "MemoryDenyWriteExecute=true",
)
PROFILES = (
    "usr.local.bin.aether-browser",
    "usr.local.bin.aether-mail",
)


def _services() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for directory in SYSTEMD_DIRS:
        if directory.is_dir():
            found.extend(sorted(directory.glob("aether-*.service")))
    return found


class FactoryResetTests(unittest.TestCase):
    def test_sources_exist(self) -> None:
        for path in FACTORY_RESET:
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"missing factory-reset copy: {path}")

    def test_no_shell_true(self) -> None:
        for path in FACTORY_RESET:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("shell=True", text)

    def test_allowlist_and_deny_list(self) -> None:
        for path in FACTORY_RESET:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("ALLOWED_ROOTS", text)
                self.assertIn("DENY_PATHS", text)
                for denied in ("/etc", "/usr", "/var", "/boot", "/proc", "/sys", "/dev"):
                    self.assertIn(f'"{denied}"', text)

    def test_confirmation_and_argv_subprocess(self) -> None:
        for path in FACTORY_RESET:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn('strip() != "RESET"', text)
                self.assertIn("subprocess.run(", text)
                self.assertIn("check=False", text)
                self.assertIn("timeout=", text)
                self.assertIn('"rm", "-rf", "--"', text)


class SystemdUnitTests(unittest.TestCase):
    def test_services_present(self) -> None:
        self.assertTrue(_services(), "expected at least one aether-*.service unit")

    def test_services_harden_service_section(self) -> None:
        for path in _services():
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("[Service]", text)
                for directive in SERVICE_DIRECTIVES:
                    self.assertIn(directive, text)

    def test_execstart_and_install_preserved(self) -> None:
        for path in _services():
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("ExecStart=", text)
                self.assertIn("[Install]", text)
                self.assertIn("WantedBy=", text)


class AppArmorTests(unittest.TestCase):
    def test_profiles_exist_and_parse(self) -> None:
        for name in PROFILES:
            path = APPARMOR_DIR / name
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"missing AppArmor profile: {path}")
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count("{"), text.count("}"), "unbalanced braces")
                self.assertRegex(text, r"(?m)^/usr/local/bin/aether-[\w-]+ \{$")
                self.assertIn("#include <tunables/global>", text)
                self.assertIn("#include <abstractions/base>", text)
                self.assertIn("network inet stream,", text)
                self.assertIn("network inet6 stream,", text)
                self.assertIn("network unix,", text)
                self.assertIn("deny /etc/** w,", text)
                self.assertIn("audit deny", text)
                self.assertNotIn("flags=(complain)", text)


class DocsTests(unittest.TestCase):
    def test_hardening_doc_exists(self) -> None:
        doc = AETHEROS / "docs" / "HARDENING.md"
        self.assertTrue(doc.is_file(), f"missing hardening doc: {doc}")


if __name__ == "__main__":
    unittest.main()
