#!/usr/bin/env python3
"""Aether Factory Reset — destructive. Double-confirm required."""
from __future__ import annotations

import pathlib
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

# A destructive target must sit under one of these roots.
ALLOWED_ROOTS = (pathlib.Path.home(),)
# Never hand these, or anything beneath them, to rm/rsync.
DENY_PATHS = frozenset(
    str(pathlib.Path(p)) for p in ("/", "/etc", "/usr", "/var", "/boot", "/proc", "/sys", "/dev")
)
PROFILE_DIRS = ("Desktop", "Documents", "Downloads")
CONFIG_DIR = pathlib.Path.home() / ".config" / "aether"
TIMEOUT_SECONDS = 15
RM_BATCH = 100


def _forbidden(path: pathlib.Path) -> bool:
    return any(path == pathlib.Path(d) or pathlib.Path(d) in path.parents for d in DENY_PATHS)


def _validate_target(path: pathlib.Path) -> bool:
    """Absolute, existing, allowlisted, and outside every denied root."""
    if not path.is_absolute() or _forbidden(path) or not path.exists():
        return False
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if _forbidden(resolved):
        return False
    return any(path.is_relative_to(root) or resolved.is_relative_to(root) for root in ALLOWED_ROOTS)


def _run(argv: list[str]) -> bool:
    try:
        return subprocess.run(argv, check=False, timeout=TIMEOUT_SECONDS).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _clear_directory(directory: pathlib.Path) -> bool:
    """Remove a validated directory's children in bounded argv batches."""
    if not _validate_target(directory) or not directory.is_dir():
        return False
    children = [str(child) for child in sorted(directory.iterdir())]
    for start in range(0, len(children), RM_BATCH):
        batch = children[start:start + RM_BATCH]
        if not _run(["rm", "-rf", "--", *batch]):
            return False
    return True


class Reset(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.aether.FactoryReset")

    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title="Aether Factory Reset")
        win.set_default_size(620, 380)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(24); box.set_margin_end(24)
        box.append(Adw.HeaderBar(title="Factory Reset"))
        box.append(Gtk.Label(label="This erases personal files and user settings.\nType RESET to confirm. You cannot undo this.", wrap=True))
        entry = Gtk.Entry(placeholder_text="RESET")
        box.append(entry)
        btn = Gtk.Button(label="Erase Everything")
        btn.add_css_class("destructive-action")

        def do(_):
            if entry.get_text().strip() != "RESET":
                return
            targets = [pathlib.Path.home() / name for name in PROFILE_DIRS]
            if not all(_validate_target(t) for t in targets) or not _validate_target(CONFIG_DIR):
                box.append(Gtk.Label(label="Reset aborted: invalid target path."))
                return
            _run(["systemd-tmpfiles", "--create"])
            for target in targets:
                _clear_directory(target)
            _run(["mkdir", "-p", "--", str(CONFIG_DIR)])
            _run(["touch", "--", str(CONFIG_DIR / "firstboot")])
            done = CONFIG_DIR / "firstboot.done"
            if done.exists() and _validate_target(done):
                _run(["rm", "-f", "--", str(done)])
            box.append(Gtk.Label(label="Reset prepared. Reboot to run Setup again."))

        btn.connect("clicked", do)
        box.append(btn)
        win.set_content(box)
        win.present()


if __name__ == "__main__":
    sys.exit(Reset().run(sys.argv))
