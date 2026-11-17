"""Tests for whole-OS network encryption policy, configs, CLI and mirrors.

Run with: python -m unittest discover -s aetheros/tests -p 'test_network_encryption.py' -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import py_compile
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.network import apply, check, main, self_test  # noqa: E402
from core.network.policy import (  # noqa: E402
    HARDENED,
    PARTIAL,
    network_status,
    parse_nm_conf,
    parse_resolved_conf,
    parse_sysctl,
    render_nm_conf,
    render_resolved_conf,
    render_sysctl,
)

CHROOT = ROOT / "iso" / "config" / "includes.chroot"
SCRIPT = ROOT / "scripts" / "network-encrypt.sh"
SCRIPT_MIRROR = CHROOT / "usr" / "share" / "aether" / "scripts" / "network-encrypt.sh"
CORE_MIRROR = CHROOT / "usr" / "share" / "aether" / "core" / "network"
LAUNCHER = CHROOT / "usr" / "local" / "bin" / "aether-network-encrypt"
CONFIGS = (
    (CHROOT / "etc" / "systemd" / "resolved.conf.d" / "aether-dns.conf", render_resolved_conf),
    (CHROOT / "etc" / "NetworkManager" / "conf.d" / "aether-wifi.conf", render_nm_conf),
    (CHROOT / "etc" / "sysctl.d" / "99-aether-network.conf", render_sysctl),
)
REPORT_KEYS = {"dns_over_tls", "mac_randomization", "antispoof", "browser_doh", "overall", "gaps"}


def _good_fragments() -> tuple[dict, dict, dict]:
    return (
        parse_resolved_conf(render_resolved_conf()),
        parse_nm_conf(render_nm_conf()),
        parse_sysctl(render_sysctl()),
    )


def _run_main(args: list[str]) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(args)
    return code, json.loads(out.getvalue())


def _bash() -> str | None:
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


def _write_hardened_root(root: pathlib.Path) -> None:
    for rel, render in (
        ("etc/systemd/resolved.conf.d/aether-dns.conf", render_resolved_conf),
        ("etc/NetworkManager/conf.d/aether-wifi.conf", render_nm_conf),
        ("etc/sysctl.d/99-aether-network.conf", render_sysctl),
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(render().encode("utf-8"))
    chromium = root / "etc/chromium/policies/managed/aether.json"
    chromium.parent.mkdir(parents=True, exist_ok=True)
    chromium.write_text(json.dumps({"DnsOverHttpsMode": "secure"}), encoding="utf-8")


class RenderTests(unittest.TestCase):
    def test_render_resolved_conf_required_directives(self) -> None:
        text = render_resolved_conf()
        self.assertIn("[Resolve]\n", text)
        self.assertIn("DNS=1.1.1.1#cloudflare-dns.com 1.0.0.1#cloudflare-dns.com", text)
        self.assertIn("DNSOverTLS=yes", text)
        self.assertIn("FallbackDNS=9.9.9.9#dns.quad9.net", text)
        self.assertIn("Domains=~", text)
        self.assertIn("Cache=yes", text)
        self.assertTrue(text.endswith("\n"))

    def test_render_nm_conf_required_directives(self) -> None:
        text = render_nm_conf()
        self.assertIn("[device]", text)
        self.assertIn("wifi.scan-rand-mac-address=yes", text)
        self.assertIn("[connection]", text)
        self.assertIn("wifi.cloned-mac-address=random", text)
        self.assertIn("ethernet.cloned-mac-address=random", text)

    def test_render_sysctl_required_directives(self) -> None:
        text = render_sysctl()
        for directive in (
            "net.ipv4.conf.all.rp_filter=2",
            "net.ipv4.conf.default.rp_filter=2",
            "net.ipv4.conf.all.accept_redirects=0",
            "net.ipv4.conf.all.send_redirects=0",
            "net.ipv6.conf.all.accept_redirects=0",
            "net.ipv6.conf.default.use_tempaddr=2",
        ):
            self.assertIn(directive, text)


class ParserTests(unittest.TestCase):
    def test_parse_round_trips(self) -> None:
        resolved = parse_resolved_conf(render_resolved_conf())
        nm = parse_nm_conf(render_nm_conf())
        sysctl = parse_sysctl(render_sysctl())
        self.assertEqual(resolved["DNSOverTLS"], "yes")
        self.assertEqual(resolved["DNS"], "1.1.1.1#cloudflare-dns.com 1.0.0.1#cloudflare-dns.com")
        self.assertEqual(nm["wifi.cloned-mac-address"], "random")
        self.assertEqual(nm["ethernet.cloned-mac-address"], "random")
        self.assertEqual(sysctl["net.ipv6.conf.default.use_tempaddr"], "2")

    def test_parse_ignores_comment_lines_but_keeps_inline_hash(self) -> None:
        text = "# a comment\n; another\n[Resolve]\nDNS=1.1.1.1#cloudflare-dns.com\n\n"
        parsed = parse_resolved_conf(text)
        self.assertEqual(parsed, {"DNS": "1.1.1.1#cloudflare-dns.com"})

    def test_parse_non_string_fails_closed(self) -> None:
        for parse in (parse_resolved_conf, parse_nm_conf, parse_sysctl):
            with self.subTest(parse=parse.__name__):
                self.assertEqual(parse(None), {})
                self.assertEqual(parse(123), {})


class StatusTests(unittest.TestCase):
    def test_all_good_is_hardened(self) -> None:
        report = network_status(*_good_fragments(), True)
        self.assertEqual(report["overall"], HARDENED)
        self.assertEqual(report["gaps"], [])
        self.assertTrue(report["dns_over_tls"])
        self.assertTrue(report["mac_randomization"])
        self.assertTrue(report["antispoof"])
        self.assertTrue(report["browser_doh"])

    def test_missing_dns_over_tls_creates_gap(self) -> None:
        resolved, nm, sysctl = _good_fragments()
        del resolved["DNSOverTLS"]
        report = network_status(resolved, nm, sysctl, True)
        self.assertFalse(report["dns_over_tls"])
        self.assertEqual(report["overall"], PARTIAL)
        self.assertIn("dns-over-tls-disabled", report["gaps"])

    def test_mac_randomization_off_creates_gap(self) -> None:
        resolved, nm, sysctl = _good_fragments()
        nm["wifi.cloned-mac-address"] = "no"
        report = network_status(resolved, nm, sysctl, True)
        self.assertFalse(report["mac_randomization"])
        self.assertIn("wifi-cloned-mac-randomization-off", report["gaps"])

    def test_antispoof_missing_creates_gap(self) -> None:
        resolved, nm, sysctl = _good_fragments()
        del sysctl["net.ipv4.conf.all.rp_filter"]
        report = network_status(resolved, nm, sysctl, True)
        self.assertFalse(report["antispoof"])
        self.assertIn("sysctl-net.ipv4.conf.all.rp_filter-mismatch", report["gaps"])

    def test_browser_doh_false_creates_gap(self) -> None:
        report = network_status(*_good_fragments(), False)
        self.assertFalse(report["browser_doh"])
        self.assertIn("browser-doh-disabled", report["gaps"])

    def test_missing_fragments_fail_closed(self) -> None:
        report = network_status(None, None, None, False)
        self.assertEqual(report["overall"], PARTIAL)
        self.assertFalse(report["dns_over_tls"])
        self.assertFalse(report["mac_randomization"])
        self.assertFalse(report["antispoof"])
        self.assertFalse(report["browser_doh"])
        self.assertTrue(report["gaps"])

    def test_non_dict_fragments_fail_closed(self) -> None:
        report = network_status("resolved", [], 42, 1)
        self.assertEqual(report["overall"], PARTIAL)
        self.assertFalse(any((report["dns_over_tls"], report["mac_randomization"],
                              report["antispoof"], report["browser_doh"])))


class ConsistencyTests(unittest.TestCase):
    def test_config_files_byte_match_render_outputs(self) -> None:
        for path, render in CONFIGS:
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"missing config: {path}")
                self.assertEqual(path.read_bytes(), render().encode("utf-8"))

    def test_mirrors_byte_identical(self) -> None:
        self.assertEqual(SCRIPT.read_bytes(), SCRIPT_MIRROR.read_bytes())
        for name in ("__init__.py", "policy.py"):
            source = ROOT / "core" / "network" / name
            mirror = CORE_MIRROR / name
            with self.subTest(name=name):
                self.assertTrue(mirror.is_file(), f"missing mirror: {mirror}")
                self.assertEqual(source.read_bytes(), mirror.read_bytes())

    def test_launcher_present_and_delegating(self) -> None:
        self.assertTrue(LAUNCHER.is_file(), f"missing launcher: {LAUNCHER}")
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("#!/usr/bin/env bash", text)
        self.assertIn("/usr/share/aether/scripts/network-encrypt.sh", text)
        self.assertIn('"$@"', text)

    def test_sources_py_compile_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp)
            for source in (ROOT / "core" / "network" / "__init__.py",
                           ROOT / "core" / "network" / "policy.py"):
                with self.subTest(source=source.name):
                    py_compile.compile(
                        str(source), cfile=str(target / (source.name + "c")), doraise=True,
                    )


class CliTests(unittest.TestCase):
    def test_script_has_no_shell_eval_or_network_calls(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for token in ("shell=True", "eval(", "urllib", "urlopen", "requests", "curl ", "wget "):
            with self.subTest(token=token):
                self.assertNotIn(token, text)
        self.assertIn('"$@"', text)

    def test_version_flag(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("network-encrypt", out.getvalue())

    def test_self_test_flag(self) -> None:
        code, report = _run_main(["--self-test"])
        self.assertEqual(code, 0)
        self.assertEqual(report["self-test"], "ok")
        self.assertGreater(report["checks"], 0)

    def test_check_json_shape_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, report = _run_main(["--check", "--root", tmp])
        self.assertEqual(code, 0)
        self.assertEqual(set(report), REPORT_KEYS)
        self.assertEqual(report["overall"], PARTIAL)
        self.assertFalse(report["dns_over_tls"])
        self.assertFalse(report["browser_doh"])
        self.assertTrue(report["gaps"])
        self.assertIsInstance(report["gaps"], list)

    def test_check_hardened_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write_hardened_root(root)
            code, report = _run_main(["--check", "--root", tmp])
        self.assertEqual(code, 0)
        self.assertEqual(report["overall"], HARDENED)
        self.assertEqual(report["gaps"], [])

    def test_apply_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, first = _run_main(["--apply", "--dest", tmp])
            self.assertEqual(code, 0)
            self.assertEqual(first["status"], "ok")
            self.assertEqual(len(first["written"]), 3)
            code, second = _run_main(["--apply", "--dest", tmp])
            self.assertNotEqual(code, 0)
            self.assertEqual(second["status"], "refused")
            self.assertEqual(second["written"], [])
            self.assertTrue(second["existing"])
            code, forced = _run_main(["--apply", "--dest", tmp, "--force"])
            self.assertEqual(code, 0)
            self.assertEqual(forced["status"], "ok")

    def test_apply_writes_byte_exact_configs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            code, report = _run_main(["--apply", "--dest", tmp])
            self.assertEqual(code, 0)
            for rel, render in (
                ("etc/systemd/resolved.conf.d/aether-dns.conf", render_resolved_conf),
                ("etc/NetworkManager/conf.d/aether-wifi.conf", render_nm_conf),
                ("etc/sysctl.d/99-aether-network.conf", render_sysctl),
            ):
                path = root / rel
                with self.subTest(path=rel):
                    self.assertTrue(path.is_file())
                    self.assertEqual(path.read_bytes(), render().encode("utf-8"))
                    if os.name == "posix":
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_bash_wrapper_end_to_end(self) -> None:
        bash = _bash()
        if bash is None:
            self.skipTest("bash not available")
        env = dict(os.environ)
        env["AETHER_NETWORK_PYTHON"] = sys.executable.replace("\\", "/")
        env["AETHER_NETWORK_SCRIPT_DIR"] = str(ROOT / "scripts").replace("\\", "/")
        env["AETHER_NETWORK_CORE_PARENT"] = str(ROOT).replace("\\", "/")
        env["MSYS2_ARG_CONV_EXCL"] = "*"
        env["MSYS_NO_PATHCONV"] = "1"
        result = subprocess.run(
            [bash, str(SCRIPT).replace("\\", "/"), "--check"],
            env=env, capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), REPORT_KEYS)


if __name__ == "__main__":
    unittest.main()
