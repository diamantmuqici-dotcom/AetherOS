"""Static audit for the Aether Dock GNOME Shell taskbar.

No GNOME Shell on this bench: read the extension, manifest and stylesheet as
text and verify the build contract. Node, when present, does a syntax check on
a temporary .mjs copy; otherwise that check is skipped.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]  # aetheros/
SRC = ROOT / "shell" / "dock"
MIRROR = (
    ROOT
    / "iso" / "config" / "includes.chroot" / "usr" / "share"
    / "gnome-shell" / "extensions" / "dock@aether"
)

EXT_JS = SRC / "extension.js"
META_JSON = SRC / "metadata.json"
STYLE_CSS = SRC / "stylesheet.css"
MIRRORED = ("extension.js", "metadata.json", "stylesheet.css")

PAIRS = {")": "(", "}": "{", "]": "["}


def _balanced(src: str) -> bool:
    """Brace/paren/bracket balance, ignoring strings, templates and comments."""
    stack: list[str] = []
    state = "code"
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if state == "code":
            if c == "/" and nxt == "/":
                state = "line_comment"
                i += 2
                continue
            if c == "/" and nxt == "*":
                state = "block_comment"
                i += 2
                continue
            if c == "'":
                state = "single"
            elif c == '"':
                state = "double"
            elif c == "`":
                state = "template"
            elif c in "({[":
                stack.append(c)
            elif c in ")}]":
                if not stack or stack.pop() != PAIRS[c]:
                    return False
        elif state == "line_comment":
            if c == "\n":
                state = "code"
        elif state == "block_comment":
            if c == "*" and nxt == "/":
                state = "code"
                i += 2
                continue
        elif state in ("single", "double"):
            quote = "'" if state == "single" else '"'
            if c == "\\":
                i += 2
                continue
            if c == quote:
                state = "code"
        elif state == "template":
            if c == "\\":
                i += 2
                continue
            if c == "`":
                state = "code"
        i += 1
    return not stack


def _method_body(src: str, name: str) -> str:
    """Return the source of a no-arg method body, including its braces."""
    match = re.search(rf"\b{re.escape(name)}\s*\(\s*\)\s*\{{", src)
    if not match:
        return ""
    start = match.end() - 1
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    return ""


class TaskbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = EXT_JS.read_text(encoding="utf-8")
        cls.css = STYLE_CSS.read_text(encoding="utf-8")
        cls.meta = json.loads(META_JSON.read_text(encoding="utf-8"))

    def test_required_files_exist(self) -> None:
        for path in (EXT_JS, META_JSON, STYLE_CSS):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"missing {path}")
        self.assertTrue(MIRROR.is_dir(), "chroot extension mirror missing")

    def test_lifecycle_class_and_methods(self) -> None:
        self.assertIn("class AetherDockExtension", self.js)
        self.assertTrue(re.search(r"\benable\s*\(\s*\)\s*\{", self.js), "no enable()")
        self.assertTrue(re.search(r"\bdisable\s*\(\s*\)\s*\{", self.js), "no disable()")
        self.assertIn("export default AetherDockExtension", self.js)

    def test_gi_imports_not_bare_gi(self) -> None:
        for module in ("St", "Clutter", "Gio", "Meta", "Shell", "GLib"):
            with self.subTest(module=module):
                self.assertRegex(
                    self.js, rf"import\s+{module}\s+from\s+['\"]gi://{module}['\"]"
                )
        self.assertRegex(self.js, r"from\s+['\"]resource:///org/gnome/shell/")
        self.assertNotRegex(
            self.js, r"^\s*import\s+gi\b", "bare 'import gi' is not ES-module style"
        )

    def test_shell_app_and_window_apis(self) -> None:
        self.assertIn("Shell.AppSystem.get_default()", self.js)
        self.assertIn("AppFavorites.getAppFavorites()", self.js)
        self.assertIn("Shell.WindowTracker.get_default()", self.js)
        self.assertIn("window-added", self.js)
        self.assertIn("window-removed", self.js)
        self.assertIn("tracked-windows-changed", self.js)

    def test_clean_teardown(self) -> None:
        disable = _method_body(self.js, "disable")
        self.assertTrue(disable, "disable() body not found")
        self.assertIn("GLib.source_remove", disable, "clock timer not removed")
        self.assertIn("disconnect(id)", disable, "signals not disconnected")
        self.assertIn("remove_all_children()", disable, "panel children not removed")
        self.assertIn(".destroy()", disable, "panel actor not destroyed")
        self.assertIn("removeChrome", disable, "chrome not removed on disable")
        self.assertIn("_clearCellSignals()", disable, "cell handlers not cleared")

    def test_no_network_eval_subprocess(self) -> None:
        banned = [
            r"\beval\s*\(",
            r"\bexec\s*\(",
            r"\bfetch\s*\(",
            r"\bXMLHttpRequest\b",
            r"\bSoup\b",
            r"\bGio\.Subprocess\b",
            r"\bGLib\.spawn\w*\s*\(",
            r"\bspawn_sync\s*\(",
            r"https?://",
        ]
        for pattern in banned:
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.js, pattern)

    def test_bounded_icon_cap(self) -> None:
        cap = re.search(r"const\s+MAX_ICONS\s*=\s*(\d+)\s*;", self.js)
        self.assertIsNotNone(cap, "MAX_ICONS cap missing")
        assert cap is not None
        self.assertLessEqual(int(cap.group(1)), 40)
        self.assertIn("out.length >= MAX_ICONS", self.js, "cap not enforced")

    def test_clock_timer_is_bounded(self) -> None:
        self.assertIn("GLib.timeout_add", self.js)
        self.assertRegex(self.js, r"CLOCK_INTERVAL_MS\s*=\s*\d+")
        self.assertIn("GLib.SOURCE_CONTINUE", self.js)

    def test_metadata_manifest(self) -> None:
        self.assertEqual(self.meta.get("uuid"), "dock@aether")
        self.assertEqual(self.meta.get("name"), "Aether Dock")
        self.assertEqual(self.meta.get("version"), 1)
        self.assertIsInstance(self.meta.get("description"), str)
        self.assertTrue(self.meta.get("description", "").strip())
        self.assertTrue(str(self.meta.get("url", "")).startswith("https://"))
        versions = self.meta.get("shell-version")
        self.assertIsInstance(versions, list)
        for wanted in ("45", "46", "47"):
            with self.subTest(shell_version=wanted):
                self.assertIn(wanted, versions)

    def test_stylesheet_palette_and_balance(self) -> None:
        self.assertTrue(_balanced(self.css), "unbalanced CSS braces")
        for selector in (
            ".aether-dock",
            ".aether-dock-icon",
            ".aether-dock-indicator",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.css)
        self.assertIn("#0F131A", self.css)
        self.assertIn("#00A3FF", self.css)
        self.assertRegex(self.css, r"border-radius\s*:")
        self.assertRegex(self.css, r"box-shadow\s*:")
        self.assertGreaterEqual(
            len(re.findall(r"#[0-9A-Fa-f]{6}\b", self.css)), 2, "hex colors missing"
        )

    def test_js_braces_balanced(self) -> None:
        self.assertTrue(_balanced(self.js), "unbalanced JS braces/parens/brackets")

    def test_js_node_syntax_check(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available; balanced-brace check already ran")
        with tempfile.TemporaryDirectory() as tmp:
            check = pathlib.Path(tmp) / "extension.mjs"
            check.write_text(self.js, encoding="utf-8")
            result = subprocess.run(
                [node, "--check", str(check)],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mirrors_byte_identical(self) -> None:
        for name in MIRRORED:
            with self.subTest(file=name):
                source = SRC / name
                mirror = MIRROR / name
                self.assertTrue(mirror.is_file(), f"missing mirror {name}")
                self.assertEqual(source.read_bytes(), mirror.read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
