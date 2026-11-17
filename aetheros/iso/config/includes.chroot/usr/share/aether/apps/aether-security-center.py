#!/usr/bin/env python3
"""Aether Security Center — read-only checks against live system state."""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shlex
import shutil
import subprocess
import sys

MAX_FIELD = 512
MAX_LINES = 2000
UNIT_LIMIT = 32
VAULT_PATH = pathlib.Path.home() / ".config" / "aether" / "vault.enc"


def run(command: list[str], timeout: int = 15) -> dict[str, object]:
    rendered = shlex.join(command)
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": rendered,
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": rendered,
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
            "returncode": None,
        }


def make_check(
    check_id: str,
    title: str,
    proc: dict[str, object],
    ok: bool,
    detail: str,
    expected: str,
) -> dict[str, object]:
    return {
        "command": proc["command"],
        "detail": detail[:MAX_FIELD],
        "expected": expected,
        "exit_code": proc["returncode"],
        "id": check_id,
        "ok": bool(ok),
        "title": title,
    }


def check_apparmor() -> dict[str, object]:
    proc = run(["aa-status"])
    loaded = 0
    enforce = 0
    for line in str(proc["stdout"]).splitlines()[:MAX_LINES]:
        match = re.search(r"(\d+)\s+profiles? are loaded", line)
        if match:
            loaded = int(match.group(1))
        match = re.search(r"(\d+)\s+profiles? are in enforce mode", line)
        if match:
            enforce = int(match.group(1))
    detail = f"{loaded} profiles loaded, {enforce} enforcing"
    return make_check(
        "apparmor", "AppArmor", proc, proc["ok"] and loaded > 0,
        detail, "aa-status reports at least one loaded profile",
    )


def check_firewall() -> dict[str, object]:
    if shutil.which("ufw"):
        proc = run(["ufw", "status"])
        state = next(
            (line.strip() for line in str(proc["stdout"]).splitlines() if "Status:" in line),
            "status unavailable",
        )
        return make_check(
            "firewall", "Firewall", proc, proc["ok"] and "Status: active" in state,
            state, "ufw status: active",
        )
    proc = run(["nft", "list", "ruleset"])
    tables = sum(1 for line in str(proc["stdout"]).splitlines() if line.strip().startswith("table "))
    return make_check(
        "firewall", "Firewall", proc, proc["ok"] and tables > 0,
        f"{tables} nftables tables", "nft list ruleset reports at least one table",
    )


def check_animations() -> dict[str, object]:
    proc = run(["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"])
    value = str(proc["stdout"]).strip()
    return make_check(
        "animations", "Desktop animations", proc, proc["ok"] and value == "true",
        f"enable-animations = {value or 'unreadable'}", "true",
    )


def check_services() -> dict[str, object]:
    listing = run([
        "systemctl", "list-unit-files", "aether-*",
        "--no-legend", "--plain", "--no-pager",
    ])
    units: list[str] = []
    for line in str(listing["stdout"]).splitlines()[:MAX_LINES]:
        fields = line.split()
        if len(fields) >= 2 and fields[0].startswith("aether-"):
            units.append(fields[0])
        if len(units) >= UNIT_LIMIT:
            break

    details: list[dict[str, str]] = []
    enabled = 0
    for unit in units:
        proc = run(["systemctl", "is-enabled", unit])
        state = str(proc["stdout"]).strip()
        if not state:
            stderr_lines = str(proc["stderr"]).strip().splitlines()
            state = stderr_lines[0] if stderr_lines else "unknown"
        enabled += int(state == "enabled")
        details.append({"command": str(proc["command"]), "state": state[:64], "unit": unit})

    check = make_check(
        "aether_services", "Aether services", listing,
        bool(units) and enabled > 0,
        f"{enabled}/{len(units)} units enabled",
        "at least one aether-* unit enabled",
    )
    check["units"] = details
    return check


def check_updates() -> dict[str, object]:
    proc = run(["apt-get", "-s", "upgrade"], timeout=45)
    pending = sum(1 for line in str(proc["stdout"]).splitlines() if line.startswith("Inst "))
    return make_check(
        "updates", "Pending upgrades", proc, proc["ok"] and pending == 0,
        f"{pending} packages queued for upgrade", "0 packages queued for upgrade",
    )


def check_vault() -> dict[str, object]:
    proc = run(["stat", "-c", "%a", str(VAULT_PATH)])
    mode_text = str(proc["stdout"]).strip()
    private = False
    if proc["ok"] and mode_text:
        try:
            private = (int(mode_text, 8) & 0o077) == 0
        except ValueError:
            private = False
    state = "absent" if not mode_text else f"mode {mode_text}"
    return make_check(
        "vault", "Aether Vault file", proc, proc["ok"] and private,
        f"{VAULT_PATH}: {state}", "vault exists with no group/other permission bits",
    )


def check_plymouth() -> dict[str, object]:
    proc = run(["plymouth-set-default-theme", "-q"])
    lines = [line.strip() for line in str(proc["stdout"]).splitlines() if line.strip()]
    theme = lines[-1] if lines else ""
    return make_check(
        "plymouth", "Boot theme", proc, proc["ok"] and theme == "aether",
        f"default theme = {theme or 'unreadable'}", "aether",
    )


def run_checks() -> dict[str, object]:
    checks = [
        check_apparmor(),
        check_firewall(),
        check_animations(),
        check_services(),
        check_updates(),
        check_vault(),
        check_plymouth(),
    ]
    passed = sum(1 for check in checks if check["ok"])
    return {
        "checks": checks,
        "summary": {"failed": len(checks) - passed, "passed": passed, "total": len(checks)},
    }


def gui_main(argv: list[str]) -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    class SecurityCenter(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aether.SecurityCenter")
            self.report: dict[str, object] = {}
            self.status = Gtk.Label(label="", wrap=True)
            self.checks_list = Gtk.ListBox()

        def do_activate(self) -> None:
            window = Adw.ApplicationWindow(application=self, title="Aether Security Center")
            window.set_default_size(880, 640)
            self.checks_list.set_selection_mode(Gtk.SelectionMode.NONE)

            header = Adw.HeaderBar()
            refresh_button = Gtk.Button(label="Re-run checks")
            refresh_button.connect("clicked", lambda _b: self.refresh())
            header.pack_end(refresh_button)

            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            page.set_margin_top(16)
            page.set_margin_bottom(16)
            page.set_margin_start(16)
            page.set_margin_end(16)
            page.append(Gtk.ScrolledWindow(child=self.checks_list))

            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            outer.append(header)
            outer.append(page)
            outer.append(self.status)
            window.set_content(outer)
            self.refresh()
            window.present()

        def refresh(self) -> None:
            self.report = run_checks()
            self.checks_list.remove_all()
            for check in list(self.report["checks"]):
                row = Adw.ActionRow(
                    title=f"{'[PASS]' if check['ok'] else '[FAIL]'} {check['title']}",
                    subtitle=f"{check['command']} — {check['detail']} (expected: {check['expected']})",
                )
                badge = Gtk.Label(label="PASS" if check["ok"] else "FAIL")
                badge.add_css_class("success" if check["ok"] else "error")
                row.add_suffix(badge)
                for unit in check.get("units", []):
                    row.add_suffix(
                        Gtk.Label(label=f"{unit['unit']}: {unit['state']} ({unit['command']})")
                    )
                self.checks_list.append(row)

            summary = self.report["summary"]
            self.status.set_label(
                f"{summary['passed']}/{summary['total']} checks passing, "
                f"{summary['failed']} failing"
            )

    return SecurityCenter().run(argv)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="aether-security-center", description="Aether Security Center"
    )
    parser.add_argument("--check", action="store_true", help="print check results as JSON")
    args = parser.parse_args(argv[1:])
    if args.check:
        print(json.dumps(run_checks(), sort_keys=True, indent=2))
        return 0
    return gui_main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
