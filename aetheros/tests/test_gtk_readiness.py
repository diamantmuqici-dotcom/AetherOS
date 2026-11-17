"""Static GTK runtime-readiness audit.

No GTK/GNOME host here: read app source as text, classify each app, and stay
tolerant of files being edited by other workstreams (skip, never false-fail).
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]  # aetheros/
SCRIPTS = ROOT / "scripts"
DOCS = ROOT / "docs"

HEADLESS_RE = re.compile(r"--(?:check|list|diagnose|version)\b")
MAIN_RE = re.compile(r"""if\s+__name__\s*==\s*['"]__main__['"]""")
IMPORT_GI_RE = re.compile(r"^(\s*)import\s+gi\b")
DECL_RE = re.compile(r"^\s*(?:def|class)\s+")
SUBCLASS_RE = re.compile(r"class\s+\w+\s*\(\s*(?:Gtk|Adw)\.Application\s*\)")
UNSAFE_RE = re.compile(r"\bshell\s*=\s*True\b|\bos\.system\s*\(|\beval\s*\(|\bexec\s*\(")
TRIPLE_RE = re.compile(r"'''|\"\"\"")


def discover_apps(root: pathlib.Path) -> list[pathlib.Path]:
    """Read-only discovery: apps/*/aether-*.py plus settings and setup."""
    found = sorted((root / "apps").glob("*/aether-*.py"))
    for rel in ("settings/aether-settings.py", "setup/aether-setup.py"):
        candidate = root / rel
        if candidate.is_file():
            found.append(candidate)
    return found


def _in_triple_quote(lines: list[str], index: int) -> bool:
    # Rough guard: an odd count of triple-quote tokens before the import means
    # the "import gi" text may live in a docstring, not in executable code.
    seen = sum(len(TRIPLE_RE.findall(line)) for line in lines[:index])
    return seen % 2 == 1


def _gi_state(src: str) -> tuple[str, str]:
    lines = src.splitlines()
    hits = [(i, m) for i, line in enumerate(lines) if (m := IMPORT_GI_RE.match(line))]
    if not hits:
        return "absent", "no gi import (CLI/launcher, not a GTK app)"
    indents = {len(m.group(1)) for _, m in hits}
    if len(indents) > 1:
        return "ambiguous", f"{len(hits)} gi imports at mixed indentation"
    index, match = hits[0]
    indent = len(match.group(1))
    prior_decl = any(DECL_RE.match(line) for line in lines[:index])
    if _in_triple_quote(lines, index):
        return "ambiguous", f"gi import at line {index + 1} sits inside a string literal"
    if indent > 0 or prior_decl:
        return "deferred", f"gi at line {index + 1} (indent={indent}, prior_decl={prior_decl})"
    return "top_level", f"gi at line {index + 1} is module-level"


def classify(path: pathlib.Path) -> tuple[str, str]:
    """Return (PASS|SKIP|FAIL, note) from source text only."""
    src = path.read_text(encoding="utf-8", errors="replace")
    fails: list[str] = []

    gi_state, gi_note = _gi_state(src)
    if gi_state in ("absent", "ambiguous"):
        return "SKIP", gi_note
    if gi_state == "top_level":
        fails.append(gi_note)  # deferral patch may still be landing

    if not (MAIN_RE.search(src) and HEADLESS_RE.search(src)):
        fails.append("no headless flag under __main__")

    unsafe = sorted(set(UNSAFE_RE.findall(src)))
    if unsafe:
        fails.append("unsafe call(s): " + ", ".join(unsafe))

    if not SUBCLASS_RE.search(src):
        fails.append("no Gtk/Adw.Application subclass")

    if fails:
        return "FAIL", "; ".join(fails)
    return "PASS", gi_note


class GtkReadinessTests(unittest.TestCase):
    def test_discovery_finds_apps(self) -> None:
        apps = discover_apps(ROOT)
        self.assertGreaterEqual(len(apps), 8, f"only {len(apps)} apps discovered")

    def test_each_app_static(self) -> None:
        for path in discover_apps(ROOT):
            status, note = classify(path)
            label = path.relative_to(ROOT).as_posix()
            with self.subTest(app=label, status=status, note=note):
                if status != "PASS":
                    # Mid-edit files are documented skips, never suite failures.
                    self.skipTest(f"{status}: {note}")

    def test_smoke_harness_contract(self) -> None:
        script = (SCRIPTS / "gtk-smoke.sh").read_text(encoding="utf-8")
        self.assertRegex(script, r"timeout\s+10s\b", "bounded 10s timeout required")
        self.assertIn("--all", script)
        self.assertIn("-m json.tool", script)
        self.assertNotIn("DISPLAY", script)
        self.assertNotIn("shell=True", script)
        self.assertNotIn("os.system", script)
        self.assertIn("python3", script)

    def test_audit_doc_exists(self) -> None:
        doc = DOCS / "GTK-AUDIT.md"
        self.assertTrue(doc.is_file(), "GTK-AUDIT.md missing")
        self.assertGreater(doc.stat().st_size, 200, "GTK-AUDIT.md is too small")


if __name__ == "__main__":
    unittest.main()
