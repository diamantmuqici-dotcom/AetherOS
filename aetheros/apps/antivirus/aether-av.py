#!/usr/bin/env python3
"""Aether Antivirus — signature-gated definitions and bounded local scans.

Headless modes (--check/--scan/--update/--verify-file) never import GTK. The
GTK4/libadwaita interface is imported only inside gui_main(). Definition bytes
are acted on only after Ed25519 verification, schema and expiry checks pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def _ensure_core_importable() -> None:
    here = pathlib.Path(__file__).resolve().parent
    roots = [
        here.parent,
        here.parents[1] if len(here.parents) > 1 else here,
        pathlib.Path("/usr/share/aether"),
        pathlib.Path("/usr/lib/aether"),
    ]
    # Repo layout keeps core/ above apps/; chroot layout stages it beside apps/.
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
    canonical_signing_input,
)
from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: E402

VERSION = "1.0.0"
SCHEMA = "aether-av-sigs/1"
DEFS_URL = (
    "https://github.com/diamantmuqici-dotcom/AetherOS/releases/latest/download/"
    "aether-av-sigs.json"
)
SIG_URL = DEFS_URL + ".sig"
DEFAULT_PUBLIC_KEY = "/usr/share/aether/updates/aether-av.pub.pem"

MAX_DEFS_BYTES = MAX_MANIFEST_BYTES
MAX_SIG_BYTES = 4096
MAX_KEY_BYTES = 64 * 1024
MAX_STATE_BYTES = 256 * 1024
MAX_HASHES = 20000
MAX_NAME = 512
MAX_SCAN_FILES = 20000
MAX_SCAN_DIRS = 4096
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_REPORT_ENTRIES = 200
CHUNK = 1024 * 1024
NETWORK_TIMEOUT = 10
_ED25519_SIG_LEN = 64


def paths() -> dict[str, pathlib.Path]:
    base = pathlib.Path.home() / ".config" / "aether" / "av"
    return {
        "definitions": pathlib.Path(os.environ.get("AETHER_AV_DEFS", base / "definitions.json")),
        "signature": pathlib.Path(os.environ.get("AETHER_AV_SIGNATURE", base / "definitions.sig")),
        "public_key": pathlib.Path(os.environ.get("AETHER_AV_PUBLIC_KEY", DEFAULT_PUBLIC_KEY)),
        "state": pathlib.Path(os.environ.get("AETHER_AV_STATE", base / "state.json")),
        "quarantine": pathlib.Path(os.environ.get("AETHER_AV_QUARANTINE", base / "quarantine")),
    }


def _bounded_read(path, limit: int) -> bytes:
    target = pathlib.Path(path)
    with target.open("rb") as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise SignatureError(f"input exceeds {limit} bytes: {target}")
    return data


def _parse_iso_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SignatureError(f"missing {field}")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SignatureError(f"malformed {field}") from exc
    if moment.tzinfo is None:
        raise SignatureError(f"{field} must carry a UTC offset")
    return moment.astimezone(timezone.utc)


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def parse_definitions(payload: object) -> dict:
    """Normalize a definition payload after its signature has been verified."""
    if not isinstance(payload, dict):
        raise SignatureError("definitions root must be an object")
    if payload.get("schema") != SCHEMA:
        raise SignatureError(f"unsupported schema: {payload.get('schema')!r}")
    generated = _parse_iso_utc(payload.get("generated_utc"), "generated_utc")
    expires = _parse_iso_utc(payload.get("expires_utc"), "expires_utc")
    if expires <= datetime.now(timezone.utc):
        raise SignatureError("definition set has expired")
    entries = payload.get("hashes")
    if not isinstance(entries, list) or len(entries) > MAX_HASHES:
        raise SignatureError("invalid hash list")
    hashes: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, dict):
            raise SignatureError("hash entry must be an object")
        digest = item.get("sha256")
        name = item.get("name")
        if not _valid_sha256(digest) or not isinstance(name, str) or not name:
            raise SignatureError("invalid hash entry")
        hashes.setdefault(digest, name[:MAX_NAME])
    return {
        "schema": SCHEMA,
        "generated_utc": generated.isoformat().replace("+00:00", "Z"),
        "expires_utc": expires.isoformat().replace("+00:00", "Z"),
        "hashes": hashes,
        "hash_count": len(hashes),
    }


def verify_definitions(defs_bytes: bytes, signature_bytes: bytes, public_key_path) -> dict:
    """Verify Ed25519 signature, then schema and expiry; return trusted hashes."""
    if not isinstance(defs_bytes, (bytes, bytearray)) or len(defs_bytes) > MAX_DEFS_BYTES:
        raise SignatureError("definition payload exceeds 1 MiB")
    if not isinstance(signature_bytes, (bytes, bytearray)):
        raise SignatureError("signature must be bytes")
    if len(signature_bytes) != _ED25519_SIG_LEN:
        raise SignatureError("signature length is invalid")
    try:
        payload = json.loads(bytes(defs_bytes).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SignatureError("definitions are not valid JSON") from exc
    if not isinstance(payload, dict):
        raise SignatureError("definitions root must be an object")
    key_bytes = _bounded_read(public_key_path, MAX_KEY_BYTES)
    try:
        public_key = serialization.load_pem_public_key(key_bytes)
    except Exception as exc:  # backend raises several distinct PEM errors
        raise SignatureError("public key is not valid PEM") from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise SignatureError("public key is not Ed25519")
    # Same canonical input core.update.signature.sign_release signs.
    try:
        public_key.verify(bytes(signature_bytes), canonical_signing_input(payload))
    except InvalidSignature as exc:
        raise SignatureError("signature does not match definitions") from exc
    return parse_definitions(payload)


def signature_status() -> tuple[str, dict | None, str | None]:
    """Return (VALID|SIGNATURE_INVALID|SIGNATURE_MISSING, record, error)."""
    resolved = paths()
    for label in ("definitions", "signature", "public_key"):
        if not resolved[label].is_file():
            return "SIGNATURE_MISSING", None, f"missing {label}"
    try:
        raw = _bounded_read(resolved["definitions"], MAX_DEFS_BYTES)
        sig = _bounded_read(resolved["signature"], MAX_SIG_BYTES)
        record = verify_definitions(raw, sig, resolved["public_key"])
    except FileNotFoundError:
        return "SIGNATURE_MISSING", None, "definition input disappeared"
    except (SignatureError, OSError) as exc:
        return "SIGNATURE_INVALID", None, str(exc)
    return "VALID", record, None


def _open_url(url: str, timeout: int = NETWORK_TIMEOUT):
    return urllib.request.urlopen(url, timeout=timeout)


def download_bounded(url: str) -> bytes:
    if urllib.parse.urlparse(url).scheme != "https":
        raise SignatureError("definition URL must be HTTPS")
    with _open_url(url, NETWORK_TIMEOUT) as response:
        headers = getattr(response, "headers", None)
        declared = headers.get("Content-Length") if headers is not None else None
        if declared and declared.isdigit() and int(declared) > MAX_DEFS_BYTES:
            raise SignatureError("download exceeds 1 MiB")
        data = response.read(MAX_DEFS_BYTES + 1)
    if len(data) > MAX_DEFS_BYTES:
        raise SignatureError("download exceeds 1 MiB")
    return data


def _atomic_write(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    with tmp.open("xb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def update_definitions() -> dict:
    resolved = paths()
    result = {"ok": False, "signature": "SIGNATURE_INVALID", "hash_count": 0, "error": None}
    if not resolved["public_key"].is_file():
        result.update(signature="SIGNATURE_MISSING", error="missing public_key")
        return result
    try:
        raw = download_bounded(os.environ.get("AETHER_AV_DEFS_URL", DEFS_URL))
        sig = download_bounded(os.environ.get("AETHER_AV_SIGNATURE_URL", SIG_URL))
        record = verify_definitions(raw, sig, resolved["public_key"])
    except (SignatureError, OSError, ValueError) as exc:
        result.update(signature="SIGNATURE_INVALID", error=str(exc))
        return result
    _atomic_write(resolved["definitions"], raw)
    _atomic_write(resolved["signature"], sig)
    result.update(ok=True, signature="VALID", hash_count=record["hash_count"])
    return result


def _sha256_file(path: pathlib.Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _walk_files(roots, skip_dirs, skip_files):
    stack = [pathlib.Path(root) for root in roots]
    seen_dirs = 0
    seen_files = 0
    while stack and seen_dirs < MAX_SCAN_DIRS and seen_files < MAX_SCAN_FILES:
        base = stack.pop()
        if base.is_symlink() or base.resolve() in skip_dirs:
            continue
        seen_dirs += 1
        try:
            with os.scandir(base) as entries:
                for entry in entries:
                    if seen_files >= MAX_SCAN_FILES:
                        break
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(pathlib.Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            candidate = pathlib.Path(entry.path)
                            if candidate.resolve() in skip_files:
                                continue
                            seen_files += 1
                            yield candidate
                    except OSError:
                        continue
        except OSError:
            continue


def _quarantine_file(path: pathlib.Path, digest: str, qdir: pathlib.Path) -> bool:
    qdir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", path.name)[:120] or "file"
    stem = f"{digest[:16]}_{safe}"
    for attempt in range(100):
        name = stem if attempt == 0 else f"{stem}.{attempt}"
        dest = qdir / name
        try:
            output = dest.open("xb")
        except FileExistsError:
            # POSIX reports EEXIST when dest is a directory; that is a hard block, not a retryable name clash.
            if dest.is_dir():
                return False
            continue
        except OSError:
            return False
        copied = 0
        digest_copy = hashlib.sha256()
        try:
            with output:
                with path.open("rb") as source:
                    while copied <= MAX_FILE_BYTES:
                        chunk = source.read(CHUNK)
                        if not chunk:
                            break
                        output.write(chunk)
                        digest_copy.update(chunk)
                        copied += len(chunk)
            if copied > MAX_FILE_BYTES or digest_copy.hexdigest() != digest:
                dest.unlink(missing_ok=True)
                return False
            # Original is removed only after the copy verifies by sha256.
            path.unlink()
            return True
        except OSError:
            dest.unlink(missing_ok=True)
            return False
    return False


def _write_state(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def _read_state(path: pathlib.Path) -> dict:
    try:
        data = json.loads(_bounded_read(path, MAX_STATE_BYTES).decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, SignatureError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return {}


def scan(paths_arg=None) -> dict:
    resolved = paths()
    state, record, error = signature_status()
    roots = [str(item) for item in paths_arg] if paths_arg else [
        "/tmp", str(pathlib.Path.home() / "Downloads")
    ]
    summary = {
        "signature": state,
        "scanned": 0,
        "matched": 0,
        "skipped": 0,
        "quarantined": [],
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hash_count": record["hash_count"] if record else 0,
        "error": error,
    }
    if state == "VALID" and record is not None:
        skip_files = {
            resolved["definitions"].resolve(),
            resolved["signature"].resolve(),
            resolved["state"].resolve(),
        }
        skip_dirs = {resolved["quarantine"].resolve()}
        matched = 0
        for candidate in _walk_files(roots, skip_dirs, skip_files):
            summary["scanned"] += 1
            digest = _sha256_file(candidate)
            if digest is None:
                summary["skipped"] += 1
                continue
            if digest in record["hashes"]:
                matched += 1
                if matched <= MAX_REPORT_ENTRIES and _quarantine_file(
                    candidate, digest, resolved["quarantine"]
                ):
                    summary["quarantined"].append(str(candidate))
        summary["matched"] = matched
    _write_state(resolved["state"], summary)
    return summary


def _gpg_verify(path: pathlib.Path, asc: pathlib.Path) -> bool:
    try:
        proc = subprocess.run(
            ["gpg", "--batch", "--verify", str(asc), str(path)],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def verify_file(path) -> dict:
    target = pathlib.Path(path)
    state, record, error = signature_status()
    result = {
        "path": str(target),
        "sha256": None,
        "signature": state,
        "in_definitions": False,
        "name": None,
        "gpg": "not-run",
        "error": error,
    }
    digest = _sha256_file(target)
    result["sha256"] = digest
    if digest is None:
        result["error"] = error or "file is missing or too large"
        return result
    if state == "VALID" and record is not None:
        result["in_definitions"] = digest in record["hashes"]
        result["name"] = record["hashes"].get(digest)
    if os.environ.get("AETHER_AV_GPG") == "1":
        asc = target.with_name(target.name + ".asc")
        if asc.is_file():
            result["gpg"] = "valid" if _gpg_verify(target, asc) else "invalid"
    return result


def check() -> dict:
    resolved = paths()
    state, record, error = signature_status()
    report = {
        "version": VERSION,
        "signature": state,
        "generated_utc": None,
        "expires_utc": None,
        "age_seconds": None,
        "hash_count": 0,
        "definitions_path": str(resolved["definitions"]),
        "public_key_path": str(resolved["public_key"]),
        "quarantine_dir": str(resolved["quarantine"]),
        "last_scan": _read_state(resolved["state"]),
        "error": error,
    }
    if state == "VALID" and record is not None:
        generated = _parse_iso_utc(record["generated_utc"], "generated_utc")
        report["generated_utc"] = record["generated_utc"]
        report["expires_utc"] = record["expires_utc"]
        report["age_seconds"] = max(0, int((datetime.now(timezone.utc) - generated).total_seconds()))
        report["hash_count"] = record["hash_count"]
    return report


def gui_main(report: dict) -> int:
    import gi  # deferred: headless modes must work without the GTK stack

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, GLib, Gtk

    class Antivirus(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aether.Antivirus")

        def do_activate(self) -> None:
            win = Adw.ApplicationWindow(application=self, title="Aether Antivirus")
            win.set_default_size(640, 480)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(20)
            box.set_margin_bottom(20)
            box.set_margin_start(24)
            box.set_margin_end(24)
            box.append(Adw.HeaderBar())

            badge = Gtk.Label(label=f"Signatures: {report['signature']}")
            badge.add_css_class("success" if report["signature"] == "VALID" else "error")
            box.append(badge)
            box.append(Gtk.Label(
                label=f"Definitions: {report['hash_count']} hashes — "
                      f"Quarantine: {report['quarantine_dir']}",
                wrap=True,
            ))

            view = Gtk.TextView()
            view.set_editable(False)
            view.set_wrap_mode(Gtk.WrapMode.WORD)
            buffer = view.get_buffer()
            box.append(view)

            def log(text: str) -> None:
                buffer.insert_at_cursor(text[-4000:])

            def refresh() -> None:
                current = check()
                badge.set_label(f"Signatures: {current['signature']}")
                log(json.dumps(current, sort_keys=True)[-4000:] + "\n")

            def do_update(_button) -> None:
                log(json.dumps(update_definitions(), sort_keys=True) + "\n")
                refresh()

            def do_scan(_button) -> None:
                def work() -> None:
                    result = scan()
                    GLib.idle_add(lambda: (log(json.dumps(result, sort_keys=True)[-4000:] + "\n"), False)[1])

                log("scanning...\n")
                threading.Thread(target=work, daemon=True).start()

            controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            update_button = Gtk.Button(label="Update definitions")
            scan_button = Gtk.Button(label="Scan")
            refresh_button = Gtk.Button(label="Refresh")
            for button in (update_button, scan_button, refresh_button):
                controls.append(button)
            box.append(controls)

            update_button.connect("clicked", do_update)
            scan_button.connect("clicked", do_scan)
            refresh_button.connect("clicked", lambda _button: refresh())
            win.set_content(box)
            win.present()

    Antivirus().run(None)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aether-av")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="emit headless JSON status")
    group.add_argument("--scan", nargs="*", default=None, metavar="PATH", help="bounded scan of PATH(s)")
    group.add_argument("--update", action="store_true", help="fetch and verify definitions")
    group.add_argument("--verify-file", metavar="PATH", help="check one file against verified hashes")
    group.add_argument("--version", action="store_true", help="print version")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.check:
        print(json.dumps(check(), sort_keys=True))
    elif args.scan is not None:
        print(json.dumps(scan(args.scan), sort_keys=True))
    elif args.update:
        print(json.dumps(update_definitions(), sort_keys=True))
    elif args.verify_file:
        print(json.dumps(verify_file(args.verify_file), sort_keys=True))
    elif args.version:
        print(VERSION)
    else:
        try:
            return gui_main(check())
        except ImportError as exc:
            print(f"GTK4/libadwaita unavailable: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
