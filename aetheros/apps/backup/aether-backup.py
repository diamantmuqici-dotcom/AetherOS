#!/usr/bin/env python3
"""Aether Backup: verified snapshots and non-destructive restore.

Backups are copied into a dated snapshot directory (never with rsync --delete)
and indexed by a canonical, optionally signed manifest. Restore planning and
execution are dry-run by default and verify every byte they touch.

`--check`, `--verify` and `--plan-restore` emit JSON with no GTK dependency.
The GTK4/libadwaita interface is imported only when the UI is launched.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys

_RSYNC_TIMEOUT = 3600


def _ensure_core_importable() -> None:
    here = pathlib.Path(__file__).resolve().parent
    roots = [
        here.parent,
        here.parents[1] if len(here.parents) > 1 else here,
        pathlib.Path("/usr/share/aether"),
        pathlib.Path("/usr/lib/aether"),
    ]
    # Repo layout keeps core/ above apps/; the chroot layout keeps it beside apps/.
    for root in roots:
        if (root / "core" / "backup" / "manifest.py").is_file():
            text = str(root)
            if text not in sys.path:
                sys.path.insert(0, text)
            return


_ensure_core_importable()
from core.backup.manifest import (  # noqa: E402
    MANIFEST_NAME,
    MAX_FILE_BYTES,
    ManifestError,
    build_manifest,
    iter_snapshot_files,
    load_manifest,
    save_manifest,
    sha256_file,
    verify_manifest,
)
from core.backup.restore import RestoreError, execute_plan, plan_restore  # noqa: E402


class BackupError(Exception):
    """Raised when a backup operation cannot complete safely."""


def _source_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("AETHER_BACKUP_SOURCE", str(pathlib.Path.home()))).resolve()


def _backup_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("AETHER_BACKUP_ROOT", str(pathlib.Path.home() / "Backups"))).resolve()


def _signing_key() -> pathlib.Path:
    return pathlib.Path(os.environ.get(
        "AETHER_BACKUP_SIGNING_KEY", "/usr/share/aether/backup/aether-backup-signing.pem"))


def _public_key() -> pathlib.Path:
    return pathlib.Path(os.environ.get(
        "AETHER_BACKUP_PUBLIC_KEY", "/usr/share/aether/backup/aether-backup.pub.pem"))


def _snapshot_files(root: pathlib.Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in iter_snapshot_files(root)]


def _copy_fallback(source: pathlib.Path, snapshot: pathlib.Path, rels: list[str]) -> None:
    for rel in rels:
        src = source / rel
        dst = snapshot / rel
        if src.stat().st_size > MAX_FILE_BYTES:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        expected = sha256_file(src)
        shutil.copy2(src, dst)
        if sha256_file(dst) != expected:
            raise BackupError(f"copy verification failed: {rel}")


def _new_snapshot_dir(base: pathlib.Path) -> pathlib.Path:
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    snapshot = base / stamp
    suffix = 1
    while snapshot.exists():
        snapshot = base / f"{stamp}-{suffix}"
        suffix += 1
    return snapshot


def create_snapshot(source, base, *, dry_run: bool = False, sign_key=None) -> dict:
    """Copy a source tree into a dated snapshot and write a verified manifest."""
    source_root = pathlib.Path(source).resolve()
    base_root = pathlib.Path(base).resolve()
    if not source_root.is_dir():
        raise BackupError(f"source is not a directory: {source_root}")
    rels = _snapshot_files(source_root)
    total = sum((source_root / rel).stat().st_size for rel in rels)

    if dry_run:
        return {
            "dry_run": True,
            "source": str(source_root),
            "backup_root": str(base_root),
            "files": len(rels),
            "total_bytes": total,
            "snapshot": None,
            "manifest": None,
        }

    snapshot = _new_snapshot_dir(base_root)
    snapshot.mkdir(parents=True, exist_ok=False)
    method = "rsync"
    argv = ["rsync", "-a", str(source_root) + os.sep, str(snapshot) + os.sep]
    try:
        result = subprocess.run(argv, check=False, timeout=_RSYNC_TIMEOUT,
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise OSError((result.stderr or "rsync failed").strip()[-500:])
    except (OSError, subprocess.SubprocessError):
        method = "python-copy2"
        _copy_fallback(source_root, snapshot, rels)

    snap_rels = _snapshot_files(snapshot)
    manifest = build_manifest(snapshot, snap_rels)
    manifest_path = snapshot / MANIFEST_NAME
    manifest = save_manifest(manifest_path, manifest, private_key_path=sign_key)
    ok, problems = verify_manifest(snapshot, manifest)
    if not ok:
        raise BackupError("post-snapshot verification failed: " + "; ".join(problems[:8]))

    return {
        "dry_run": False,
        "source": str(source_root),
        "backup_root": str(base_root),
        "snapshot": str(snapshot),
        "manifest": str(manifest_path),
        "files": len(snap_rels),
        "total_bytes": total,
        "copy": method,
        "signature": "signed" if manifest.get("signature") else "none",
    }


def verify_snapshot(snapshot, *, public_key=None) -> dict:
    """Load the snapshot manifest and verify every tracked file on disk."""
    snap = pathlib.Path(snapshot).resolve()
    manifest_path = snap / MANIFEST_NAME
    if not manifest_path.is_file():
        return {
            "snapshot": str(snap), "ok": False, "entries": 0,
            "signature": "missing", "discrepancies": ["manifest missing"],
        }
    try:
        manifest = load_manifest(manifest_path, public_key_path=public_key)
    except ManifestError as exc:
        return {
            "snapshot": str(snap), "ok": False, "entries": 0,
            "signature": "invalid", "discrepancies": [str(exc)],
        }
    ok, problems = verify_manifest(snap, manifest, public_key_path=public_key)
    return {
        "snapshot": str(snap),
        "ok": ok,
        "entries": manifest.get("count", len(manifest.get("entries", []))),
        "signature": "signed" if manifest.get("signature") else "none",
        "discrepancies": problems,
    }


def plan_snapshot_restore(snapshot, target, *, overwrite: bool = False,
                          public_key=None) -> dict:
    """Build a non-shell restore plan from a verified snapshot manifest."""
    snap = pathlib.Path(snapshot).resolve()
    manifest = load_manifest(snap / MANIFEST_NAME, public_key_path=public_key)
    ok, problems = verify_manifest(snap, manifest, public_key_path=public_key)
    if not ok:
        raise RestoreError("snapshot failed verification: " + "; ".join(problems[:8]))
    operations = plan_restore(snap, target, manifest, overwrite=overwrite)
    return {
        "snapshot": str(snap),
        "target": str(pathlib.Path(target).resolve()),
        "count": len(operations),
        "shell": False,
        "operations": operations,
    }


def _latest_snapshot(base: pathlib.Path):
    if not base.is_dir():
        return None
    candidates = [
        directory for directory in base.iterdir()
        if directory.is_dir() and (directory / MANIFEST_NAME).is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def check() -> dict:
    """Headless status report; never import GTK or touch the network."""
    source = _source_root()
    base = _backup_root()
    signing = _signing_key()
    public = _public_key()
    report: dict = {
        "rsync": "available" if shutil.which("rsync") else "missing",
        "source": str(source),
        "backup_root": str(base),
        "signing_key": signing.is_file(),
        "public_key": public.is_file(),
        "last_snapshot": None,
        "manifest": "missing",
        "entries": 0,
        "discrepancies": [],
        "error": None,
    }
    try:
        latest = _latest_snapshot(base)
        if latest is None:
            return report
        report["last_snapshot"] = str(latest)
        result = verify_snapshot(latest, public_key=public if public.is_file() else None)
        report["manifest"] = "valid" if result["ok"] else "invalid"
        report["entries"] = result.get("entries", 0)
        report["discrepancies"] = result.get("discrepancies", [])
    except OSError as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    return report


def gui_main(args: argparse.Namespace) -> int:
    """GTK4/libadwaita interface; imported only when the UI is requested."""
    import gi  # deferred: headless flags must work without the GTK stack

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    class BackupApp(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aether.Backup")

        def do_activate(self) -> None:
            window = Adw.ApplicationWindow(application=self, title="Aether Backup")
            window.set_default_size(680, 520)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(20)
            box.set_margin_bottom(20)
            box.set_margin_start(24)
            box.set_margin_end(24)
            box.append(Adw.HeaderBar(title="Aether Backup"))

            latest = _latest_snapshot(_backup_root())
            snapshot_entry = Gtk.Entry()
            snapshot_entry.set_text(str(latest) if latest else "")
            snapshot_entry.set_placeholder_text("Snapshot directory")
            target_entry = Gtk.Entry()
            target_entry.set_placeholder_text("Restore target directory")
            box.append(Gtk.Label(label="Snapshot", xalign=0))
            box.append(snapshot_entry)
            box.append(Gtk.Label(label="Restore target", xalign=0))
            box.append(target_entry)

            status = Gtk.TextView()
            status.set_editable(False)
            status.set_wrap_mode(Gtk.WrapMode.WORD)
            box.append(status)
            buffer = status.get_buffer()

            def show(payload: dict) -> None:
                buffer.set_text(json.dumps(payload, sort_keys=True, indent=2))

            def do_backup(_button) -> None:
                try:
                    show(create_snapshot(_source_root(), _backup_root(),
                                         sign_key=_signing_key() if _signing_key().is_file() else None))
                except (BackupError, ManifestError, OSError) as exc:
                    show({"ok": False, "error": str(exc)})

            def snapshot_from_entry() -> pathlib.Path:
                text = snapshot_entry.get_text().strip()
                return pathlib.Path(text) if text else (
                    latest or pathlib.Path.home() / "Backups" / "none")

            def do_verify(_button) -> None:
                show(verify_snapshot(snapshot_from_entry(),
                                     public_key=_public_key() if _public_key().is_file() else None))

            def do_plan(_button) -> None:
                target = pathlib.Path(target_entry.get_text().strip())
                if not target_entry.get_text().strip():
                    show({"ok": False, "error": "restore target is empty"})
                    return
                try:
                    show(plan_snapshot_restore(snapshot_from_entry(), target,
                                               public_key=_public_key() if _public_key().is_file() else None))
                except (ManifestError, RestoreError, OSError) as exc:
                    show({"ok": False, "error": str(exc)})

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            for label, handler in (
                ("Backup now", do_backup),
                ("Verify snapshot", do_verify),
                ("Plan restore", do_plan),
            ):
                button = Gtk.Button(label=label)
                button.connect("clicked", handler)
                row.append(button)
            box.append(row)

            window.set_content(box)
            window.present()

    BackupApp().run(None)
    return 0


def _emit(payload: dict, code: int = 0) -> int:
    print(json.dumps(payload, sort_keys=True))
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aether Backup: verified, non-destructive snapshots")
    parser.add_argument("--snapshot", metavar="DIR", help="backup root; create a dated snapshot in DIR")
    parser.add_argument("--source", metavar="DIR", help="source tree (default: home or AETHER_BACKUP_SOURCE)")
    parser.add_argument("--dry-run", action="store_true", help="with --snapshot, report without writing")
    parser.add_argument("--verify", metavar="SNAPSHOT", help="verify a snapshot manifest and files")
    parser.add_argument("--plan-restore", metavar="SNAPSHOT", help="print a non-shell restore plan")
    parser.add_argument("--target", metavar="DIR", help="restore destination for --plan-restore")
    parser.add_argument("--overwrite", action="store_true", help="allow replacement of existing target files")
    parser.add_argument("--check", action="store_true", help="emit JSON status with no GTK dependency")
    parser.add_argument("--sign-key", metavar="FILE", help="Ed25519 PEM private key for signing")
    parser.add_argument("--public-key", metavar="FILE", help="Ed25519 PEM public key for verification")
    opts = parser.parse_args(argv)

    try:
        if opts.check:
            return _emit(check())
        if opts.snapshot:
            source = opts.source or str(_source_root())
            key = opts.sign_key or (str(_signing_key()) if _signing_key().is_file() else None)
            return _emit(create_snapshot(source, opts.snapshot, dry_run=opts.dry_run, sign_key=key))
        if opts.verify:
            result = verify_snapshot(opts.verify, public_key=opts.public_key)
            return _emit(result, 0 if result["ok"] else 1)
        if opts.plan_restore:
            if not opts.target:
                parser.error("--plan-restore requires --target")
            result = plan_snapshot_restore(opts.plan_restore, opts.target,
                                           overwrite=opts.overwrite, public_key=opts.public_key)
            return _emit(result)
    except (BackupError, ManifestError, RestoreError, OSError) as exc:
        return _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 1)
    return gui_main(opts)


if __name__ == "__main__":
    sys.exit(main())
