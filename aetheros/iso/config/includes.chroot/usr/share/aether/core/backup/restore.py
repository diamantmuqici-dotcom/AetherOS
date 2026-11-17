"""Non-destructive, verified restore planning and execution.

plan_restore emits a list of argv-style copy operations (never a shell string).
execute_plan is dry-run by default; a real write requires dry_run=False and
re-checks source/destination containment, source hashes, and post-copy hashes.
No operation deletes files, and existing targets are touched only with an
explicit overwrite=True plus full per-file verification.
"""

from __future__ import annotations

import os
import pathlib
import shutil

from .manifest import MAX_FILE_BYTES, normalize_rel, sha256_file

__all__ = [
    "MAX_PATH_CHARS",
    "RestoreError",
    "plan_restore",
    "execute_plan",
]

MAX_PATH_CHARS = 4096
_HASH_LEN = 64  # SHA-256 hex digest length


class RestoreError(ValueError):
    """Raised when a restore plan would be unsafe, incomplete, or unverified."""


def _resolve(path) -> pathlib.Path:
    p = pathlib.Path(path)
    text = str(p)
    if not text or "\x00" in text or len(text) > MAX_PATH_CHARS:
        raise RestoreError(f"invalid path: {text[:120]!r}")
    return p.resolve()


def _contained(base: pathlib.Path, candidate: pathlib.Path) -> bool:
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def plan_restore(source, target, manifest: dict, *, overwrite: bool = False) -> list[list[str]]:
    """Return verified argv copy operations confined to source and target roots."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        raise RestoreError("manifest entries missing")
    source_root = _resolve(source)
    target_root = _resolve(target)
    if not source_root.is_dir():
        raise RestoreError(f"source is not a directory: {source_root}")
    if target_root.exists() and not target_root.is_dir():
        raise RestoreError(f"target is not a directory: {target_root}")
    if target_root.exists() and any(target_root.iterdir()) and not overwrite:
        raise RestoreError("target is not empty; pass overwrite=True to replace files")

    operations: list[list[str]] = []
    seen: set[str] = set()
    for entry in sorted(manifest["entries"], key=lambda item: item.get("path", "")):
        if not isinstance(entry, dict):
            raise RestoreError("malformed manifest entry")
        rel = normalize_rel(entry.get("path"))
        expected = entry.get("sha256")
        size = entry.get("size")
        if not isinstance(expected, str) or len(expected) != _HASH_LEN:
            raise RestoreError(f"invalid digest for {rel}")
        if not isinstance(size, int) or size < 0 or size > MAX_FILE_BYTES:
            raise RestoreError(f"invalid size for {rel}")

        src = _resolve(source_root / rel)
        dst = _resolve(target_root / rel)
        if not _contained(source_root, src):
            raise RestoreError(f"source traversal rejected: {rel}")
        if not _contained(target_root, dst):
            raise RestoreError(f"target traversal rejected: {rel}")
        if str(dst) in seen:
            raise RestoreError(f"duplicate destination: {rel}")
        seen.add(str(dst))

        if src.is_symlink() or not src.is_file():
            raise RestoreError(f"source file missing or unsafe: {rel}")
        if dst.exists() and not overwrite:
            raise RestoreError(f"target file exists: {rel}; pass overwrite=True")

        operations.append(["copy2", str(src), str(dst), expected])
    return operations


def execute_plan(plan, source, target, *, dry_run: bool = True,
                 overwrite: bool = False) -> dict:
    """Execute a verbatim copy plan with containment and hash verification."""
    if not isinstance(plan, list):
        raise RestoreError("plan must be a list")
    source_root = _resolve(source)
    target_root = _resolve(target)

    report: dict = {
        "dry_run": bool(dry_run),
        "copy_command": "shutil.copy2",
        "planned": len(plan),
        "copied": [],
        "verified": 0,
    }

    for operation in plan:
        if (not isinstance(operation, list) or len(operation) != 4
                or any(not isinstance(item, str) for item in operation)
                or operation[0] != "copy2"):
            raise RestoreError("invalid copy operation in plan")
        _, src_text, dst_text, expected = operation
        if len(expected) != _HASH_LEN:
            raise RestoreError("invalid digest in plan")

        src = _resolve(src_text)
        dst = _resolve(dst_text)
        if not _contained(source_root, src):
            raise RestoreError(f"plan source escapes root: {src_text}")
        if not _contained(target_root, dst):
            raise RestoreError(f"plan target escapes root: {dst_text}")
        if src.is_symlink() or not src.is_file():
            raise RestoreError(f"source file missing or unsafe: {src_text}")
        if src.stat().st_size > MAX_FILE_BYTES:
            raise RestoreError(f"source file exceeds size cap: {src_text}")
        if sha256_file(src) != expected:
            raise RestoreError(f"source hash mismatch: {src_text}")
        if dst.exists() and not overwrite:
            raise RestoreError(f"target exists: {dst_text}; pass overwrite=True")

        rel = dst.relative_to(target_root).as_posix()
        if dry_run:
            report.setdefault("would_copy", []).append(rel)
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        temp = dst.with_name(dst.name + ".aether-restore.tmp")
        shutil.copy2(src, temp)
        try:
            if sha256_file(temp) != expected:
                raise RestoreError(f"copy verification failed: {rel}")
            os.replace(temp, dst)
        finally:
            if temp.exists():
                temp.unlink()
        report["copied"].append(rel)
        report["verified"] += 1

    return report
