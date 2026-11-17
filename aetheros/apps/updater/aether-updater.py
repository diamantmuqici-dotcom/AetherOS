#!/usr/bin/env python3
"""Aether Updater: signature-gated, manifest-pinned APT upgrades.

`--check` emits a JSON status report with no GTK dependency for tests and CI.
The GTK4/libadwaita interface is imported only when the UI is launched.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading
import time

DEFAULT_MANIFEST = "/usr/share/aether/updates/release-manifest.json"
DEFAULT_SIGNATURE = DEFAULT_MANIFEST + ".sig"
DEFAULT_PUBLIC_KEY = "/usr/share/aether/updates/aether-release.pub.pem"
_APPLY_TIMEOUT = 1800
_STATE_PATH = pathlib.Path.home() / ".config" / "aether" / "updater.json"


def _ensure_core_importable() -> None:
    here = pathlib.Path(__file__).resolve().parent
    roots = [
        here.parent,
        here.parents[1] if len(here.parents) > 1 else here,
        pathlib.Path("/usr/share/aether"),
        pathlib.Path("/usr/lib/aether"),
    ]
    # The repo layout keeps core/ one level above apps/; the chroot layout keeps it beside updater/.
    for root in roots:
        if (root / "core" / "update" / "signature.py").is_file():
            text = str(root)
            if text not in sys.path:
                sys.path.insert(0, text)
            return


_ensure_core_importable()
from core.update.signature import (  # noqa: E402
    MAX_MANIFEST_BYTES,
    SignatureError,
    verify_release,
)
from core.update.apt_policy import run_simulated_upgrade  # noqa: E402
from core.update.release import (  # noqa: E402
    CHANNELS,
    ReleaseError,
    load_release,
    plan_upgrade,
    select_channel,
)


def _paths() -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    return (
        pathlib.Path(os.environ.get("AETHER_RELEASE_MANIFEST", DEFAULT_MANIFEST)),
        pathlib.Path(os.environ.get("AETHER_RELEASE_SIGNATURE", DEFAULT_SIGNATURE)),
        pathlib.Path(os.environ.get("AETHER_RELEASE_PUBLIC_KEY", DEFAULT_PUBLIC_KEY)),
    )


def signature_status() -> tuple[str, dict | None]:
    """Return (VALID|INVALID|MISSING, verified payload)."""
    manifest, signature, public_key = _paths()
    if not (manifest.is_file() and signature.is_file() and public_key.is_file()):
        return "MISSING", None
    try:
        raw = manifest.read_bytes()
        if len(raw) > MAX_MANIFEST_BYTES:
            raise SignatureError("manifest exceeds 1 MiB")
        payload = verify_release(raw, signature, public_key)
    except (SignatureError, OSError):
        return "INVALID", None
    return "VALID", payload


def check() -> dict:
    """Build the headless status report; never include untrusted upgrade plans."""
    channel = os.environ.get("AETHER_UPDATE_CHANNEL", "stable")
    report = {
        "signature": "INVALID",
        "channel": channel,
        "expires": None,
        "min_os_version": None,
        "apt_status": "not-run",
        "upgrades": [],
        "error": None,
    }
    state, payload = signature_status()
    report["signature"] = state
    if state != "VALID" or payload is None:
        report["error"] = f"signature {state.lower()}"
        return report
    if channel not in CHANNELS:
        report["error"] = f"unknown channel: {channel}"
        return report
    try:
        view = select_channel(load_release(payload), channel)
    except ReleaseError as exc:
        report["error"] = f"invalid release: {exc}"
        return report

    report["expires"] = view["expires"]
    report["min_os_version"] = view["min_os_version"]
    upgrades, status = run_simulated_upgrade()
    report["apt_status"] = status
    report["upgrades"] = plan_upgrade(view, upgrades)
    return report


def _write_state(data: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def _install_argv(upgrades: list[dict]) -> list[str]:
    argv = ["apt-get", "install", "-y", "--no-install-recommends"]
    argv.extend(f"{item['package']}={item['version']}" for item in upgrades)
    return argv


def _run_ui(report: dict) -> int:
    import gi  # deferred: --check must work without the GTK stack

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, GLib, Gtk

    class Updater(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aether.Updater")

        def do_activate(self) -> None:
            win = Adw.ApplicationWindow(application=self, title="Aether Update")
            win.set_default_size(640, 460)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(20)
            box.set_margin_bottom(20)
            box.set_margin_start(24)
            box.set_margin_end(24)
            box.append(Adw.HeaderBar())

            state = report["signature"]
            badge = Gtk.Label(label=f"Signature: {state}")
            badge.add_css_class("success" if state == "VALID" else "error")
            box.append(badge)

            detail = report.get("error") or f"Channel: {report['channel']}"
            box.append(Gtk.Label(label=detail, wrap=True))

            lines = [
                f"{item['package']}: {item['current']} -> {item['version']}"
                for item in report["upgrades"]
            ]
            body = Gtk.Label(
                label="\n".join(lines) if lines else "No pinned upgrades available.",
                wrap=True,
                selectable=True,
            )
            box.append(body)

            log = Gtk.TextView()
            log.set_editable(False)
            log.set_wrap_mode(Gtk.WrapMode.WORD)
            box.append(log)
            buffer = log.get_buffer()

            row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
            accept = Gtk.Button(label="Accept")
            decline = Gtk.Button(label="Decline")
            later = Gtk.Button(label="Later")
            row.append(accept)
            row.append(decline)
            row.append(later)
            box.append(row)

            if state != "VALID" or not report["upgrades"]:
                accept.set_sensitive(False)

            def append_log(text: str) -> None:
                buffer.insert_at_cursor(text)

            def do_accept(_button) -> None:
                # Re-check at apply time so a changed manifest cannot be installed.
                current, _payload = signature_status()
                if current != "VALID":
                    append_log("Refusing: signature is not VALID.\n")
                    return
                accept.set_sensitive(False)

                def work() -> None:
                    try:
                        result = subprocess.run(
                            _install_argv(report["upgrades"]), check=False,
                            timeout=_APPLY_TIMEOUT, text=True, capture_output=True,
                        )
                        text = (result.stdout or "")[-4000:] + (result.stderr or "")[-2000:]
                        code = result.returncode
                    except (OSError, subprocess.SubprocessError) as exc:
                        text, code = f"{type(exc).__name__}: {exc}\n", 1

                    def finish() -> bool:
                        append_log(text + f"\nInstaller rc={code}\n")
                        return False

                    GLib.idle_add(finish)

                threading.Thread(target=work, daemon=True).start()

            def do_decline(_button) -> None:
                _write_state({"declined_at": time.time()})
                win.close()

            def do_later(_button) -> None:
                _write_state({"snoozed_at": time.time()})
                win.close()

            accept.connect("clicked", do_accept)
            decline.connect("clicked", do_decline)
            later.connect("clicked", do_later)

            win.set_content(box)
            win.present()

    Updater().run(None)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--check" in args:
        print(json.dumps(check(), sort_keys=True))
        return 0
    try:
        return _run_ui(check())
    except ImportError as exc:
        print(f"GTK4/libadwaita unavailable: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
